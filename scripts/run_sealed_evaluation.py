"""The sealed-test run: calendar 2025, scored once.

Refuses to run if results/sealed already exists. Hourly issue grid over 2025,
96 half-hour horizons; Track A and Track B final models (quantile heads +
conformal offsets) against persistence, seasonal-naive and NESO's stored
near-final forecast (Leg 1, labeled), all on identical (issue, target) pairs.
Outputs are frozen artifacts: per-pair predictions, horizon curves, bucket
metrics, paired significance.

Run (M4, once):
    PYTHONPATH=src uv run python scripts/run_sealed_evaluation.py \
        --run-a runs/<final-A> --run-b runs/<final-B> --seal
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from gbcarbon import conformal, evaluate, features  # noqa: E402
from gbcarbon.train import fold_metrics, gb_holiday_dates, issue_grid  # noqa: E402

SEALED_DIR = Path("results/sealed")
WORK_DIR = Path("results/.sealed_tmp")  # built here, renamed atomically at the end


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True)
    parser.add_argument("--run-b", required=True)
    parser.add_argument("--issue-step-h", type=float, default=1.0)
    parser.add_argument(
        "--seal",
        action="store_true",
        help="acknowledge this is the single sealed run",
    )
    args = parser.parse_args()

    if SEALED_DIR.exists():
        print(
            "results/sealed already exists: the sealed test was scored once "
            "and stays frozen. Refusing to run again.",
            file=sys.stderr,
        )
        return 2
    if not args.seal:
        print("pass --seal to acknowledge the one-time sealed run", file=sys.stderr)
        return 2

    history = pd.read_parquet("data/raw/neso_api_history.parquet")
    weather = pd.read_parquet("data/raw/weather_prev_runs.parquet")

    issues = issue_grid(
        pd.Timestamp("2025-01-01", tz="UTC"),
        pd.Timestamp("2025-12-31 23:00", tz="UTC"),
        args.issue_step_h,
    )
    assert issues.min().year == 2025 and issues.max().year == 2025

    print(f"building sealed frame: {len(issues)} issues x 96 horizons")
    hol = gb_holiday_dates(2024, 2026)
    frame = features.build_training_frame(
        history, issues, holiday_dates=hol, weather_prev=weather
    )

    bundle_a = evaluate.ModelBundle(Path(args.run_a))
    bundle_b = evaluate.ModelBundle(Path(args.run_b))
    # raw intervals + trailing-window conformal: offsets at each issue come
    # only from already-matured pairs, admissible under the protocol
    preds_a = conformal.apply_trailing(
        bundle_a.predict(frame, calibrate=False),
        seed_offsets=bundle_a.conformal["offsets"],
    ).drop(columns=["conformal_widen"])
    preds_b = conformal.apply_trailing(
        bundle_b.predict(frame, calibrate=False),
        seed_offsets=bundle_b.conformal["offsets"],
    ).drop(columns=["conformal_widen"])

    base = evaluate.protocol_baselines(history, frame)
    merged = preds_a.rename(
        columns={"p10": "a_p10", "p50": "a_p50", "p90": "a_p90"}
    ).merge(
        preds_b.rename(columns={"p10": "b_p10", "p50": "b_p50", "p90": "b_p90"}),
        on=["issue_time", "target_time", "horizon_h", "y"],
    )
    merged = merged.merge(
        base, on=["issue_time", "target_time", "horizon_h", "y"], how="left"
    )

    if WORK_DIR.exists():
        import shutil

        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)
    merged.to_parquet(WORK_DIR / "sealed_predictions.parquet", index=False)

    curve = evaluate.horizon_curve(
        merged,
        {
            "track_a": "a_p50",
            "track_b": "b_p50",
            "persistence": "persistence",
            "seasonal_naive_7d": "seasonal_naive_7d",
            "neso_stored_leg1": "neso_stored",
        },
    )
    curve.to_parquet(WORK_DIR / "horizon_curves.parquet", index=False)

    def errs(col: str) -> np.ndarray:
        return (merged[col] - merged["y"]).abs().to_numpy()

    comparisons: list[dict] = []
    comparisons += evaluate.paired_comparison(
        errs("a_p50"), errs("persistence"), merged["horizon_h"], "A_vs_persistence"
    )
    comparisons += evaluate.paired_comparison(
        errs("b_p50"), errs("persistence"), merged["horizon_h"], "B_vs_persistence"
    )
    comparisons += evaluate.paired_comparison(
        errs("b_p50"), errs("a_p50"), merged["horizon_h"], "B_vs_A_weather_ablation"
    )
    comparisons += evaluate.paired_comparison(
        errs("a_p50"),
        errs("neso_stored"),
        merged["horizon_h"],
        "A_vs_neso_stored_LEG1_not_like_for_like",
    )
    comparisons += evaluate.paired_comparison(
        errs("b_p50"),
        errs("neso_stored"),
        merged["horizon_h"],
        "B_vs_neso_stored_LEG1_not_like_for_like",
    )

    metrics_a = fold_metrics(
        merged.rename(columns={"a_p10": "p10", "a_p50": "p50", "a_p90": "p90"})
    )
    metrics_b = fold_metrics(
        merged.rename(columns={"b_p10": "p10", "b_p50": "p50", "b_p90": "p90"})
    )

    payload = {
        "sealed_year": 2025,
        "scored_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "issue_step_h": args.issue_step_h,
        "n_pairs": int(len(merged)),
        "models": {
            "track_a": {"run": bundle_a.config["run_id"], "metrics": metrics_a},
            "track_b": {"run": bundle_b.config["run_id"], "metrics": metrics_b},
        },
        "leg1_label": (
            "NESO stored forecast is a near-final, short-horizon product; "
            "this leg is NOT like-for-like at 24-48 h and is reported as context."
        ),
        "comparisons": comparisons,
        "frozen": True,
    }
    (WORK_DIR / "sealed_2025.json").write_text(json.dumps(payload, indent=2) + "\n")
    WORK_DIR.rename(SEALED_DIR)  # atomic: sealed exists only when complete

    print(
        json.dumps(
            {"track_a": metrics_a["mae_p50"], "track_b": metrics_b["mae_p50"]}, indent=2
        )
    )
    for row in comparisons:
        if row["bucket"] == "overall":
            print(
                f"{row['comparison']}: {row['mae_a']} vs {row['mae_b']} "
                f"({row['delta_pct']}%), dm_p={row['dm_p']}"
            )
    print(f"sealed artifacts -> {SEALED_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
