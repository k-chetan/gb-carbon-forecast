"""Prospective operator legs (2 and 3): re-runnable, maturing over time.

Leg 2: this project's sealed-eval models vs community-archive vintages at
matched issue times on 2026-07 onward (out-of-sample for models trained
through 2024; the archive's 2023-2024 months instead yield the operator's own
horizon curve as context).

Leg 3: the same models vs this repo's own hourly fw48h vintages — the only
fully clean 48 h comparison; n starts tiny and matures unattended.

Unlike the sealed run, this script is MEANT to be re-run (weekly self-scoring
summarizes continuously; `make refresh` re-runs this before submission).

Run:
    PYTHONPATH=src uv run python scripts/score_operator_legs.py \
        --run-a runs/<final-A> --run-b runs/<final-B> \
        --own-vintages <path to vintages dir from the vintage-log branch>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")

from gbcarbon import conformal, evaluate, features  # noqa: E402
from gbcarbon.scoring import load_vintages  # noqa: E402
from gbcarbon.train import gb_holiday_dates  # noqa: E402

OUT_DIR = Path("results/legs")
MATCH_TOLERANCE = pd.Timedelta(minutes=30)


def model_predictions_at(
    issues: pd.DatetimeIndex,
    history: pd.DataFrame,
    weather: pd.DataFrame,
    bundles: dict[str, evaluate.ModelBundle],
) -> dict[str, pd.DataFrame]:
    hol = gb_holiday_dates(issues.min().year - 1, issues.max().year + 1)
    frame = features.build_training_frame(
        history, issues, holiday_dates=hol, weather_prev=weather
    )
    return {
        name: conformal.apply_trailing(
            bundle.predict(frame, calibrate=False),
            seed_offsets=bundle.conformal["offsets"],
        )
        for name, bundle in bundles.items()
    }


def leg_rows(
    label: str,
    vintages: pd.DataFrame,
    history: pd.DataFrame,
    weather: pd.DataFrame,
    bundles: dict[str, evaluate.ModelBundle],
) -> dict:
    captures = pd.DatetimeIndex(vintages["capture_utc"].unique()).sort_values()
    if len(captures) == 0:
        return {"leg": label, "n_captures": 0, "comparisons": []}
    issues = captures.round("30min").unique()
    preds = model_predictions_at(issues, history, weather, bundles)

    out: dict = {
        "leg": label,
        "n_captures": int(len(captures)),
        "capture_span": [
            captures.min().strftime("%Y-%m-%dT%H:%MZ"),
            captures.max().strftime("%Y-%m-%dT%H:%MZ"),
        ],
        "comparisons": [],
    }
    for name, model_preds in preds.items():
        joined = evaluate.score_against_vintages(
            model_preds, vintages, MATCH_TOLERANCE
        ).dropna(subset=["operator_vintage", "y"])
        if joined.empty:
            out["comparisons"].append({"model": name, "n": 0})
            continue
        err_model = (joined["p50"] - joined["y"]).abs().to_numpy()
        err_op = (joined["operator_vintage"] - joined["y"]).abs().to_numpy()
        try:
            rows = evaluate.paired_comparison(
                err_model, err_op, joined["horizon_h"], f"{name}_vs_operator_vintage"
            )
        except ValueError:  # too few pairs for block inference yet
            rows = [
                {
                    "comparison": f"{name}_vs_operator_vintage",
                    "bucket": "overall",
                    "n": int(len(joined)),
                    "mae_a": round(float(err_model.mean()), 2),
                    "mae_b": round(float(err_op.mean()), 2),
                    "note": "n too small for block inference; matures unattended",
                }
            ]
        out["comparisons"].append({"model": name, "rows": rows})
    return out


def operator_context_curve(vintages: pd.DataFrame, history: pd.DataFrame) -> list:
    """The archive operator's own MAE by horizon bucket (2023-2024 context)."""
    grid = features.half_hour_grid(history)["actual"]
    v = vintages.copy()
    v["y"] = grid.reindex(pd.DatetimeIndex(v["window_start"])).to_numpy()
    v = v.dropna(subset=["y", "forecast"])
    v["horizon_h"] = (v["window_start"] - v["capture_utc"]).dt.total_seconds() / 3600
    from gbcarbon.train import bucket_of

    rows = []
    for bucket, group in v.groupby(bucket_of(v["horizon_h"])):
        err = (group["forecast"] - group["y"]).abs()
        rows.append(
            {
                "bucket": str(bucket),
                "mae": round(float(err.mean()), 2),
                "n": int(len(group)),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True)
    parser.add_argument("--run-b", required=True)
    parser.add_argument("--own-vintages", required=True)
    parser.add_argument("--leg2-start", default="2026-07-01")
    args = parser.parse_args()

    history = pd.read_parquet("data/raw/neso_api_history.parquet")
    weather = pd.read_parquet("data/raw/weather_prev_runs.parquet")
    bundles = {
        "track_a": evaluate.ModelBundle(Path(args.run_a)),
        "track_b": evaluate.ModelBundle(Path(args.run_b)),
    }

    community = pd.read_parquet("data/external/community_vintages.parquet")
    community["capture_utc"] = pd.to_datetime(community["capture_utc"], utc=True)
    community["window_start"] = pd.to_datetime(community["window_start"], utc=True)
    leg2_mask = community["capture_utc"] >= pd.Timestamp(args.leg2_start, tz="UTC")

    own = load_vintages(Path(args.own_vintages))
    own = own.rename(columns={"window_end": "_we"}).drop(columns=["_we"])

    payload = {
        "computed_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "leg2": leg_rows(
            "leg2_community_archive",
            community[leg2_mask],
            history,
            weather,
            bundles,
        ),
        "leg2_context_operator_curve_2023_24": operator_context_curve(
            community[~leg2_mask], history
        ),
        "leg3": leg_rows("leg3_own_logged_fw48h", own, history, weather, bundles),
        "labels": {
            "leg2": (
                "archive vintages at matched issue times, 2026-07 onward; "
                "out-of-sample for models trained through 2024; no 2025 archive"
            ),
            "leg3": (
                "own hourly fw48h log: the only fully clean 48 h comparison; "
                "tiny n at build time, matures unattended"
            ),
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "legs.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["leg2"]["comparisons"], indent=2)[:1200])
    print(json.dumps(payload["leg3"], indent=2)[:600])
    print(f"-> {OUT_DIR / 'legs.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
