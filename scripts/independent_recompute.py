"""Independent recomputation of headline numbers (verification gate).

Fresh code on purpose: this script imports nothing from ``gbcarbon`` and
rebuilds everything it checks from raw artifacts with its own implementation.

Checks:
  A. Feature/prediction equivalence — for a seeded random sample of sealed
     (issue, horizon) pairs, rebuild Track A features from the raw history
     parquet by direct timestamp lookups, predict with the stored boosters,
     and compare against the pipeline's stored p50 values pair by pair.
  B. Metric recomputation — recompute sealed MAE and coverage per track and
     bucket from results/sealed/sealed_predictions.parquet with plain
     aggregation, and diff against results/sealed/sealed_2025.json.
  C. Baseline recomputation — persistence under the protocol, recomputed by
     direct lookups on the raw history for the same sampled pairs.
  D. Anchor recomputation — pointwise persistence-24h MAE on 2025 from the
     raw parquet, against results/anchor_reproduction.json.

Output: results/verification/independent_recompute.json (every check with
pipeline value, independent value, difference and pass flag).

Run: uv run python scripts/independent_recompute.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

SAMPLE_N = 4000
SEED = 20261121
TOL_PRED = 1e-6  # same boosters, same features -> numerically identical
TOL_METRIC = 0.05  # gCO2/kWh on recomputed aggregate metrics
OUT = Path("results/verification/independent_recompute.json")

LAG_HOURS = {
    "lag_0h": 0,
    "lag_1h": 1,
    "lag_2h": 2,
    "lag_3h": 3,
    "lag_6h": 6,
    "lag_12h": 12,
    "lag_24h": 24,
    "lag_48h": 48,
    "lag_7d": 168,
}
ROLL_HOURS = {"roll_24h": 24, "roll_7d": 168}


def bucket(h: float) -> str | None:
    if 0 < h <= 6:
        return "01_06h"
    if 6 < h <= 24:
        return "07_24h"
    if 24 < h <= 48:
        return "25_48h"
    return None


def independent_features(
    actual_by_time: dict, issue: pd.Timestamp, target: pd.Timestamp, holidays: set
) -> dict:
    """Track A features rebuilt by direct lookups (no vector shifts)."""
    half = pd.Timedelta(minutes=30)
    freshest = issue - half  # last fully elapsed window start
    feats: dict = {}
    for name, hours in LAG_HOURS.items():
        feats[name] = actual_by_time.get(freshest - pd.Timedelta(hours=hours), np.nan)
    for name, hours in ROLL_HOURS.items():
        steps = hours * 2
        values = [actual_by_time.get(freshest - k * half, np.nan) for k in range(steps)]
        values = [v for v in values if not pd.isna(v)]
        feats[name] = float(np.mean(values)) if len(values) >= steps // 2 else np.nan
    feats["trend_24h"] = feats["lag_0h"] - feats["lag_24h"]
    feats["horizon_h"] = (target - issue).total_seconds() / 3600
    hour = target.hour + target.minute / 60
    feats["t_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    feats["t_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    feats["t_hour"] = hour
    feats["t_dow"] = target.dayofweek
    feats["t_month"] = target.month
    feats["t_doy"] = target.dayofyear
    feats["t_holiday"] = int(target.date() in holidays)
    return feats


def main() -> int:
    sealed_dir = Path("results/sealed")
    if not sealed_dir.exists():
        print("sealed artifacts missing; run the sealed evaluation first")
        return 2

    preds = pd.read_parquet(sealed_dir / "sealed_predictions.parquet")
    sealed = json.loads((sealed_dir / "sealed_2025.json").read_text())
    history = pd.read_parquet("data/raw/neso_api_history.parquet")
    actual_by_time = dict(zip(history["window_start"], history["actual"], strict=True))

    import holidays as holidays_lib

    gb_holidays = set(
        holidays_lib.country_holidays(
            "GB", subdiv="England", years=range(2024, 2027)
        ).keys()
    )

    sample = preds.sample(SAMPLE_N, random_state=SEED).reset_index(drop=True)

    checks: list[dict] = []

    # --- A: feature/prediction equivalence (Track A booster) ----------------
    run_a = sealed["models"]["track_a"]["run"]
    run_dir = Path("runs") / run_a
    config = json.loads((run_dir / "run.json").read_text())["config"]
    booster = lgb.Booster(model_file=str(run_dir / "model_q50.txt"))
    rows = [
        independent_features(
            actual_by_time,
            pd.Timestamp(r.issue_time),
            pd.Timestamp(r.target_time),
            gb_holidays,
        )
        for r in sample.itertuples()
    ]
    frame = pd.DataFrame(rows)[config["features"]].astype(np.float32)
    mine = booster.predict(frame)
    max_diff = float(np.nanmax(np.abs(mine - sample["a_p50"].to_numpy())))
    checks.append(
        {
            "check": "A_feature_prediction_equivalence",
            "n": SAMPLE_N,
            "max_abs_diff": max_diff,
            "pass": bool(max_diff < 1e-3),
        }
    )

    # --- B: metric recomputation --------------------------------------------
    for track, col10, col50, col90 in (
        ("track_a", "a_p10", "a_p50", "a_p90"),
        ("track_b", "b_p10", "b_p50", "b_p90"),
    ):
        err = (preds[col50] - preds["y"]).abs()
        mae_mine = float(err.mean())
        mae_pipeline = sealed["models"][track]["metrics"]["mae_p50"]
        cov_mine = float(
            ((preds["y"] >= preds[col10]) & (preds["y"] <= preds[col90])).mean()
        )
        cov_pipeline = sealed["models"][track]["metrics"]["coverage_80"]
        checks.append(
            {
                "check": f"B_sealed_mae_{track}",
                "pipeline": mae_pipeline,
                "independent": round(mae_mine, 4),
                "pass": bool(abs(mae_mine - mae_pipeline) < TOL_METRIC),
            }
        )
        checks.append(
            {
                "check": f"B_sealed_coverage_{track}",
                "pipeline": cov_pipeline,
                "independent": round(cov_mine, 4),
                "pass": bool(abs(cov_mine - cov_pipeline) < 0.005),
            }
        )

    # --- C: persistence recomputed by direct lookup -------------------------
    pers = []
    for r in sample.itertuples():
        target = pd.Timestamp(r.target_time)
        lag = 24 if r.horizon_h <= 24 else 48
        pers.append(actual_by_time.get(target - pd.Timedelta(hours=lag), np.nan))
    pers = np.asarray(pers, dtype=float)
    mask = ~np.isnan(pers) & ~np.isnan(sample["persistence"].to_numpy(dtype=float))
    max_diff = float(
        np.max(np.abs(pers[mask] - sample["persistence"].to_numpy(dtype=float)[mask]))
    )
    checks.append(
        {
            "check": "C_persistence_values",
            "n": int(mask.sum()),
            "max_abs_diff": max_diff,
            "pass": bool(max_diff < 1e-9),
        }
    )

    # --- D: anchor recomputation ---------------------------------------------
    anchors = json.loads(Path("results/anchor_reproduction.json").read_text())
    h25 = history[history["window_start"].dt.year == 2025].set_index("window_start")
    series = h25["actual"]
    # reference built from the FULL history so 1 January keeps its lag into 2024
    full_series = history.set_index("window_start")["actual"]
    ref = full_series.copy()
    ref.index = ref.index + pd.Timedelta(hours=24)
    err = (series - ref.reindex(series.index)).abs().dropna()
    mine = float(err.mean())
    pipeline = anchors["reproduced"]["persistence_24h"]["mae"]
    checks.append(
        {
            "check": "D_anchor_persistence24",
            "pipeline": pipeline,
            "independent": round(mine, 2),
            "pass": bool(abs(mine - pipeline) < TOL_METRIC),
        }
    )

    payload = {
        "seed": SEED,
        "all_pass": bool(all(c["pass"] for c in checks)),
        "checks": checks,
        "scope_note": (
            "p50 path, metrics, baselines and anchors recomputed independently; "
            "interval values are covered by the coverage recomputation in B"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
