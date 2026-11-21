"""Paired Track A vs Track B ablation on a common validation window.

Joins the two runs' validation predictions on identical (issue_time,
target_time) pairs, then reports MAE per horizon bucket with paired
significance from the day-block bootstrap and HAC Diebold-Mariano. The
weather contribution — whatever its sign — is the research finding.

Run: PYTHONPATH=src uv run python scripts/ablation.py \
        --run-a runs/<idA> --run-b runs/<idB>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")

from gbcarbon import metrics  # noqa: E402
from gbcarbon.train import bucket_of  # noqa: E402

STEPS_PER_BUCKET = {"01_06h": 12, "07_24h": 48, "25_48h": 96, "overall": 96}


def load_run(run_dir: Path) -> tuple[dict, pd.DataFrame]:
    config = json.loads((run_dir / "run.json").read_text())["config"]
    preds = pd.read_parquet(run_dir / "val_predictions.parquet")
    return config, preds


def compare(paired: pd.DataFrame, label: str, steps: int) -> dict:
    err_a = (paired["p50_a"] - paired["y"]).abs().to_numpy()
    err_b = (paired["p50_b"] - paired["y"]).abs().to_numpy()
    boot = metrics.block_bootstrap_test(err_b - err_a)
    dm = metrics.dm_test_hac(err_b, err_a, horizon_steps=steps)
    mae_a, mae_b = metrics.mae(err_a), metrics.mae(err_b)
    return {
        "bucket": label,
        "n_pairs": int(len(paired)),
        "mae_a": round(mae_a, 2),
        "mae_b": round(mae_b, 2),
        "delta_pct": round(100 * (mae_b - mae_a) / mae_a, 2),
        "coverage80_a": round(
            metrics.interval_coverage(
                paired["y"].to_numpy(),
                paired["p10_a"].to_numpy(),
                paired["p90_a"].to_numpy(),
            ),
            3,
        ),
        "coverage80_b": round(
            metrics.interval_coverage(
                paired["y"].to_numpy(),
                paired["p10_b"].to_numpy(),
                paired["p90_b"].to_numpy(),
            ),
            3,
        ),
        "block_bootstrap": {
            "mean_diff": round(boot["mean"], 3),
            "p_value": round(boot["p_value"], 5),
            "ci95": [round(v, 3) for v in boot["ci95"]],
        },
        "dm_hac": {
            "stat": round(dm["dm_stat"], 3),
            "p_value": round(dm["p_value"], 5),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True)
    parser.add_argument("--run-b", required=True)
    parser.add_argument("--out", default="results/ablation.json")
    args = parser.parse_args()

    config_a, preds_a = load_run(Path(args.run_a))
    config_b, preds_b = load_run(Path(args.run_b))

    paired = preds_a.merge(
        preds_b,
        on=["issue_time", "target_time", "horizon_h", "y"],
        suffixes=("_a", "_b"),
        how="inner",
    ).sort_values(["target_time", "issue_time"])
    if paired.empty:
        raise SystemExit("no overlapping validation pairs between the two runs")

    rows = [compare(paired, "overall", STEPS_PER_BUCKET["overall"])]
    for bucket, group in paired.groupby(bucket_of(paired["horizon_h"])):
        rows.append(compare(group, str(bucket), STEPS_PER_BUCKET[str(bucket)]))

    payload = {
        "computed_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "run_a": {"id": config_a["run_id"], "track": config_a["track"]},
        "run_b": {"id": config_b["run_id"], "track": config_b["track"]},
        "note": (
            "negative delta_pct means B (weather) beats A (lags+calendar); "
            "paired on identical issue/target times"
        ),
        "comparisons": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["comparisons"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
