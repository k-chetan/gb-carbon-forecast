"""Train gradient-boosted quantile models under the issue-time protocol.

Track A: lag + calendar features, full history (2018-2024).
Track B: Track A plus issue-admissible archived weather forecasts, on the
archive-covered window.

Validation is rolling-origin with a 7-day embargo before each validation
quarter; development never touches the sealed year (2025), enforced by a hard
date assertion, not convention. Each run writes runs/<id>/run.json (config,
per-fold and pooled metrics) plus per-fold validation predictions for paired
significance tests.

Example:
    PYTHONPATH=src uv run python -m gbcarbon.train --track A --cv
    PYTHONPATH=src uv run python -m gbcarbon.train --track B --cv \
        --train-start 2022-07-01 --issue-step-h 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import holidays as holidays_lib
import lightgbm as lgb
import numpy as np
import pandas as pd

from gbcarbon import features, metrics

SEALED_START = pd.Timestamp("2025-01-01", tz="UTC")
SEALED_END = pd.Timestamp("2026-01-01", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
QUANTILES = (0.1, 0.5, 0.9)
BUCKETS = ((0.0, 6.0, "01_06h"), (6.0, 24.0, "07_24h"), (24.0, 48.0, "25_48h"))

LGB_PARAMS = dict(
    n_estimators=600,
    learning_rate=0.05,
    num_leaves=127,
    min_child_samples=100,
    subsample=0.9,
    subsample_freq=1,
    colsample_bytree=0.9,
    random_state=42,
    verbose=-1,
)


def assert_outside_sealed(times: pd.Series | pd.DatetimeIndex, label: str) -> None:
    times = pd.DatetimeIndex(times)
    inside = (times >= SEALED_START) & (times < SEALED_END)
    if inside.any():
        raise RuntimeError(
            f"{label} touches the sealed test year 2025 "
            f"({int(inside.sum())} timestamps); development must not."
        )


def gb_holiday_dates(start_year: int, end_year: int) -> set:
    cal = holidays_lib.country_holidays(
        "GB", subdiv="England", years=range(start_year, end_year + 1)
    )
    return set(cal.keys())


def issue_grid(
    start: pd.Timestamp, end: pd.Timestamp, step_h: float
) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq=pd.Timedelta(hours=step_h), tz="UTC")


def quarter_folds(
    issues: pd.DatetimeIndex, n_folds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """The last `n_folds` complete quarters of the issue grid as validation windows."""
    last = issues.max()
    quarter_start = pd.Timestamp(
        year=last.year, month=3 * ((last.month - 1) // 3) + 1, day=1, tz="UTC"
    )
    folds = []
    cursor = quarter_start
    for _ in range(n_folds):
        folds.append((cursor, cursor + pd.offsets.QuarterBegin(startingMonth=1)))
        cursor = cursor - pd.offsets.QuarterBegin(startingMonth=1)
    return sorted(folds)


def bucket_of(horizons: pd.Series) -> pd.Series:
    def lookup(h: float) -> str | None:
        for low, high, name in BUCKETS:
            if low < h <= high:
                return name
        return None

    return horizons.map(lookup)


def fold_metrics(frame: pd.DataFrame) -> dict:
    out: dict = {"n": int(len(frame))}
    out["mae_p50"] = metrics.mae(frame["p50"] - frame["y"])
    for q in QUANTILES:
        out[f"pinball_q{int(q * 100)}"] = metrics.pinball_loss(
            frame["y"].to_numpy(), frame[f"p{int(q * 100)}"].to_numpy(), q
        )
    out["coverage_80"] = metrics.interval_coverage(
        frame["y"].to_numpy(), frame["p10"].to_numpy(), frame["p90"].to_numpy()
    )
    by_bucket = {}
    for bucket, group in frame.groupby(bucket_of(frame["horizon_h"])):
        by_bucket[bucket] = {
            "mae_p50": metrics.mae(group["p50"] - group["y"]),
            "coverage_80": metrics.interval_coverage(
                group["y"].to_numpy(),
                group["p10"].to_numpy(),
                group["p90"].to_numpy(),
            ),
            "n": int(len(group)),
        }
    out["by_bucket"] = by_bucket
    return out


def fit_quantiles(
    train: pd.DataFrame, cols: list[str]
) -> dict[float, lgb.LGBMRegressor]:
    models = {}
    for q in QUANTILES:
        model = lgb.LGBMRegressor(objective="quantile", alpha=q, **LGB_PARAMS)
        model.fit(train[cols], train["y"])
        models[q] = model
    return models


def predict_quantiles(
    models: dict[float, lgb.LGBMRegressor],
    frame: pd.DataFrame,
    cols: list[str],
    offsets: dict[str, float] | None = None,
) -> pd.DataFrame:
    preds = np.column_stack([models[q].predict(frame[cols]) for q in QUANTILES])
    preds.sort(axis=1)  # enforce non-crossing
    out = frame[["issue_time", "target_time", "horizon_h", "y"]].copy()
    out["p10"], out["p50"], out["p90"] = preds[:, 0], preds[:, 1], preds[:, 2]
    if offsets:
        widen = bucket_of(out["horizon_h"]).map(offsets).fillna(0.0).to_numpy()
        out["p10"] = out["p10"] - widen
        out["p90"] = out["p90"] + widen
    return out


def split_calibration(
    frame: pd.DataFrame, frac: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-ordered core/calibration split on issue times (CQR)."""
    issues = frame["issue_time"].sort_values().unique()
    cut = issues[int(len(issues) * (1 - frac))]
    return frame[frame["issue_time"] < cut], frame[frame["issue_time"] >= cut]


def conformal_offsets(
    models: dict[float, lgb.LGBMRegressor],
    calib: pd.DataFrame,
    cols: list[str],
    alpha: float = 0.2,
) -> dict[str, float]:
    """Per-horizon-bucket CQR offsets: the finite-sample (1-alpha) quantile of
    conformity scores E = max(p10 - y, y - p90) on the calibration slice."""
    preds = predict_quantiles(models, calib, cols)
    scores = np.maximum(preds["p10"] - preds["y"], preds["y"] - preds["p90"]).to_numpy()
    buckets = bucket_of(preds["horizon_h"])
    offsets: dict[str, float] = {}
    for bucket in sorted(buckets.dropna().unique()):
        s = np.sort(scores[(buckets == bucket).to_numpy()])
        n = len(s)
        if n == 0:
            continue
        rank = min(int(np.ceil((1 - alpha) * (n + 1))) - 1, n - 1)
        offsets[str(bucket)] = float(s[rank])
    return offsets


def load_frame(args: argparse.Namespace) -> pd.DataFrame:
    history = pd.read_parquet("data/raw/neso_api_history.parquet")
    start = pd.Timestamp(args.train_start, tz="UTC")
    # last issue must keep its 48 h horizon strictly before train_end
    end = pd.Timestamp(args.train_end, tz="UTC") - pd.Timedelta(hours=48, minutes=30)
    issues = issue_grid(start, end, args.issue_step_h)
    assert_outside_sealed(issues, "issue grid")

    weather = None
    if args.track == "B":
        weather = pd.read_parquet("data/raw/weather_prev_runs.parquet")

    hol = gb_holiday_dates(start.year, end.year + 1)
    frame = features.build_training_frame(
        history, issues, holiday_dates=hol, weather_prev=weather
    )
    assert_outside_sealed(frame["target_time"], "training targets")
    cols = features.feature_columns(frame)
    cols = [c for c in cols if c not in ("issue_time", "target_time")]
    frame[cols] = frame[cols].astype(np.float32)
    return frame


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=["A", "B"], required=True)
    parser.add_argument("--train-start", default="2018-01-01")
    parser.add_argument("--train-end", default="2025-01-01")
    parser.add_argument("--issue-step-h", type=float, default=2.0)
    parser.add_argument("--cv-folds", type=int, default=6)
    parser.add_argument("--cv", action="store_true", help="rolling-origin validation")
    parser.add_argument("--final", action="store_true", help="fit on the full span")
    parser.add_argument("--tag", default=None, help="run id suffix")
    parser.add_argument("--runs-dir", default="runs")
    args = parser.parse_args(argv)

    started = time.time()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"_track{args.track}"
    if args.tag:
        run_id += f"_{args.tag}"
    run_dir = Path(args.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    frame = load_frame(args)
    cols = [
        c
        for c in features.feature_columns(frame)
        if c not in ("issue_time", "target_time")
    ]

    git_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    config = {
        "run_id": run_id,
        "track": args.track,
        "train_start": args.train_start,
        "train_end": args.train_end,
        "issue_step_h": args.issue_step_h,
        "cv_folds": args.cv_folds,
        "embargo_days": EMBARGO.days,
        "quantiles": list(QUANTILES),
        "lgb_params": LGB_PARAMS,
        "n_samples": int(len(frame)),
        "n_features": len(cols),
        "features": cols,
        "git_hash": git_hash,
        "seed": 42,
    }

    result: dict = {"config": config, "computed_utc": datetime.now(UTC).isoformat()}

    if args.cv:
        folds = quarter_folds(pd.DatetimeIndex(frame["issue_time"]), args.cv_folds)
        fold_rows, fold_reports = [], {}
        for fold_start, fold_end in folds:
            train = frame[frame["issue_time"] < fold_start - EMBARGO]
            val = frame[
                (frame["issue_time"] >= fold_start) & (frame["issue_time"] < fold_end)
            ]
            if len(train) < 10_000 or len(val) == 0:
                continue
            core, calib = split_calibration(train)
            models = fit_quantiles(core, cols)
            offsets = conformal_offsets(models, calib, cols)
            preds = predict_quantiles(models, val, cols, offsets)
            preds["fold"] = str(fold_start.date())
            fold_rows.append(preds)
            report = fold_metrics(preds)
            report["conformal_offsets"] = offsets
            fold_reports[str(fold_start.date())] = report
            print(
                f"fold {fold_start.date()}: {report['mae_p50']:.2f} MAE(p50) "
                f"coverage80={report['coverage_80']:.3f} n={len(preds)}"
            )
        pooled = pd.concat(fold_rows, ignore_index=True)
        pooled.to_parquet(run_dir / "val_predictions.parquet", index=False)
        result["cv"] = {"folds": fold_reports, "pooled": fold_metrics(pooled)}
        print(
            f"pooled: {result['cv']['pooled']['mae_p50']:.2f} MAE(p50), "
            f"coverage80={result['cv']['pooled']['coverage_80']:.3f}"
        )

    if args.final:
        core, calib = split_calibration(frame)
        models = fit_quantiles(core, cols)
        offsets = conformal_offsets(models, calib, cols)
        for q, model in models.items():
            model.booster_.save_model(run_dir / f"model_q{int(q * 100)}.txt")
        (run_dir / "conformal.json").write_text(json.dumps(offsets, indent=2) + "\n")
        result["final_fit"] = {
            "n_core": int(len(core)),
            "n_calib": int(len(calib)),
            "conformal_offsets": offsets,
        }

    result["duration_s"] = round(time.time() - started, 1)
    (run_dir / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"run -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
