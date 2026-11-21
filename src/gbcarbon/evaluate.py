"""Sealed-test evaluation and the three-leg operator comparison.

The sealed year (calendar 2025) is scored exactly once: this module refuses
to run if ``results/sealed`` already exists. Everything is evaluated under
one issue-time protocol — hourly issues, 96 half-hour horizons — with
baselines computed on the identical (issue, target) pairs:

- Track A / Track B final models (quantile heads + conformal offsets).
- Persistence under the protocol (lag 24 h for horizons <= 24 h, else 48 h)
  and the 7-day seasonal naive.
- Leg 1: NESO's stored forecast series — a near-final, short-horizon product,
  labeled as such; not like-for-like at 48 h.
- Leg 2: archive vintages (community archive) at matched issue times, on
  months where both the archive and an out-of-sample model exist.
- Leg 3: this repo's own logged fw48h vintages — the only fully clean 48 h
  comparison; tiny n at build time, maturing unattended.
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from gbcarbon import features, metrics
from gbcarbon.train import QUANTILES, bucket_of

SEALED_DIR = Path("results/sealed")
STEPS_PER_BUCKET = {"01_06h": 12, "07_24h": 48, "25_48h": 96}


# --------------------------------------------------------------------------
# model bundles
# --------------------------------------------------------------------------


class ModelBundle:
    """Final-fit quantile boosters plus conformal offsets, loaded from a run dir."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.boosters = {
            q: lgb.Booster(model_file=str(self.run_dir / f"model_q{int(q * 100)}.txt"))
            for q in QUANTILES
        }
        conformal = json.loads((self.run_dir / "conformal.json").read_text())
        if "offsets" not in conformal:  # legacy flat additive format
            conformal = {"mode": "additive", "offsets": conformal}
        self.conformal = conformal
        self.config = json.loads((self.run_dir / "run.json").read_text())["config"]

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in self.config["features"] if c in frame.columns]
        missing = [c for c in self.config["features"] if c not in frame.columns]
        if missing:
            raise ValueError(f"frame lacks model features: {missing[:5]}...")
        preds = np.column_stack(
            [self.boosters[q].predict(frame[cols]) for q in QUANTILES]
        )
        preds.sort(axis=1)
        out = frame[["issue_time", "target_time", "horizon_h", "y"]].copy()
        out["p10"], out["p50"], out["p90"] = preds[:, 0], preds[:, 1], preds[:, 2]
        factor = (
            bucket_of(out["horizon_h"])
            .map(self.conformal["offsets"])
            .fillna(0.0)
            .to_numpy()
        )
        if self.conformal.get("mode") == "scaled":
            width = np.maximum((out["p90"] - out["p10"]).to_numpy(), 1.0)
            widen = factor * width
        else:
            widen = factor
        out["p10"] -= widen
        out["p90"] += widen
        return out


# --------------------------------------------------------------------------
# baselines and operator series on the same pairs
# --------------------------------------------------------------------------


def protocol_baselines(history: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Persistence and seasonal-naive forecasts for given (issue, target) pairs.

    Persistence uses the same clock time one day before the target when the
    horizon allows it (h <= 24), else two days before; both lags reference
    windows fully elapsed at the issue time by construction.
    """
    grid = features.half_hour_grid(history)["actual"]
    out = pairs[["issue_time", "target_time", "horizon_h", "y"]].copy()
    t = pd.DatetimeIndex(out["target_time"])
    lag1 = grid.reindex(t - pd.Timedelta(hours=24)).to_numpy()
    lag2 = grid.reindex(t - pd.Timedelta(hours=48)).to_numpy()
    h = out["horizon_h"].to_numpy()
    out["persistence"] = np.where(h <= 24.0, lag1, lag2)
    out["seasonal_naive_7d"] = grid.reindex(t - pd.Timedelta(days=7)).to_numpy()
    out["neso_stored"] = (
        features.half_hour_grid(history)["forecast"].reindex(t).to_numpy()
    )
    return out


def paired_comparison(
    err_a: np.ndarray, err_b: np.ndarray, horizons: pd.Series, label: str
) -> list[dict]:
    """A-vs-B absolute-error comparison overall and per bucket."""
    frame = pd.DataFrame(
        {"err_a": err_a, "err_b": err_b, "horizon_h": horizons.to_numpy()}
    ).dropna()
    rows = []
    groups: list[tuple[str, pd.DataFrame, int]] = [("overall", frame, 96)]
    for bucket, group in frame.groupby(bucket_of(frame["horizon_h"])):
        groups.append((str(bucket), group, STEPS_PER_BUCKET[str(bucket)]))
    for name, group, steps in groups:
        diff = (group["err_a"] - group["err_b"]).to_numpy()
        boot = metrics.block_bootstrap_test(diff)
        dm = metrics.dm_test_hac(
            group["err_a"].to_numpy(), group["err_b"].to_numpy(), steps
        )
        rows.append(
            {
                "comparison": label,
                "bucket": name,
                "n": int(len(group)),
                "mae_a": round(float(group["err_a"].mean()), 2),
                "mae_b": round(float(group["err_b"].mean()), 2),
                "delta_pct": round(
                    100
                    * (group["err_a"].mean() - group["err_b"].mean())
                    / group["err_b"].mean(),
                    2,
                ),
                "bootstrap_p": round(boot["p_value"], 5),
                "dm_p": round(dm["p_value"], 5),
                "dm_stat": round(dm["dm_stat"], 3),
            }
        )
    return rows


def horizon_curve(preds: pd.DataFrame, value_cols: dict[str, str]) -> pd.DataFrame:
    """MAE per half-hour horizon for each named prediction column."""
    rows = []
    for horizon, group in preds.groupby("horizon_h"):
        row: dict = {"horizon_h": float(horizon), "n": int(len(group))}
        for label, col in value_cols.items():
            err = (group[col] - group["y"]).abs()
            row[label] = round(float(err.mean()), 2)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("horizon_h")


# --------------------------------------------------------------------------
# vintage legs (2: community archive, 3: own logger)
# --------------------------------------------------------------------------


def score_against_vintages(
    model_preds: pd.DataFrame, vintages: pd.DataFrame, tolerance: pd.Timedelta
) -> pd.DataFrame:
    """Join model forecasts to operator vintages at matched issue times.

    A model forecast issued at T is matched to the operator vintage captured
    closest to T within ``tolerance``, then compared per target window.
    """
    captures = vintages[["capture_utc"]].drop_duplicates().sort_values("capture_utc")
    issues = model_preds[["issue_time"]].drop_duplicates().sort_values("issue_time")
    matched = pd.merge_asof(
        issues,
        captures,
        left_on="issue_time",
        right_on="capture_utc",
        direction="nearest",
        tolerance=tolerance,
    ).dropna()
    merged = model_preds.merge(matched, on="issue_time").merge(
        vintages.rename(columns={"window_start": "target_time"}),
        on=["capture_utc", "target_time"],
        how="inner",
    )
    return merged.rename(columns={"forecast": "operator_vintage"})
