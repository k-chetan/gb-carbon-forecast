"""Trailing-window conformal calibration of forecast intervals.

Static split-conformal offsets decay under regime shift: conformity scores
from a fixed calibration tail systematically underestimate errors a month
later, which collapsed interval coverage in development. The remedy here
recalibrates per issue time from *matured* forecasts only — pairs whose
target time precedes the issue — so it is strictly admissible under the
issue-time protocol and mirrors what the deployed nightly system does with
its self-scored history.

Per horizon bucket b and issue day d, the additive offset is the
finite-sample (1 - alpha) quantile of conformity scores
E = max(p10 - y, y - p90) over pairs with target_time in
[d - window, d). Days with fewer than ``min_n`` matured pairs fall back to
the static seed offsets fitted at training time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gbcarbon.metrics import bucket_of

ALPHA = 0.2
WINDOW = pd.Timedelta(days=30)
MIN_N = 400


def _finite_sample_q(scores: np.ndarray, alpha: float) -> float:
    s = np.sort(scores)
    n = len(s)
    rank = min(int(np.ceil((1 - alpha) * (n + 1))) - 1, n - 1)
    return float(s[rank])


def apply_trailing(
    preds: pd.DataFrame,
    seed_offsets: dict[str, float] | None = None,
    alpha: float = ALPHA,
    window: pd.Timedelta = WINDOW,
    min_n: int = MIN_N,
) -> pd.DataFrame:
    """Adjust p10/p90 per issue day from trailing matured conformity scores.

    ``preds`` holds RAW (uncalibrated) p10/p50/p90 with issue_time,
    target_time, horizon_h and y. Rows with missing y still get calibrated
    intervals (from history), they just never feed the score stream.
    """
    out = preds.sort_values(["issue_time", "target_time"]).reset_index(drop=True)
    out["bucket"] = bucket_of(out["horizon_h"])
    seed = seed_offsets or {}

    scored = out.dropna(subset=["y"]).copy()
    scored["score"] = np.maximum(
        scored["p10"] - scored["y"], scored["y"] - scored["p90"]
    )
    scored["target_day"] = scored["target_time"].dt.floor("D")

    issue_days = pd.DatetimeIndex(out["issue_time"].dt.floor("D").unique())
    offsets_by_day: dict[tuple[pd.Timestamp, str], float] = {}
    for day in issue_days:
        matured = scored[
            (scored["target_time"] < day) & (scored["target_time"] >= day - window)
        ]
        for bucket in ("01_06h", "07_24h", "25_48h"):
            pool = matured[matured["bucket"] == bucket]["score"].to_numpy()
            if len(pool) >= min_n:
                offsets_by_day[(day, bucket)] = _finite_sample_q(pool, alpha)
            else:
                offsets_by_day[(day, bucket)] = float(seed.get(bucket, 0.0))

    keys = pd.MultiIndex.from_arrays([out["issue_time"].dt.floor("D"), out["bucket"]])
    widen = np.array([offsets_by_day.get(k, 0.0) for k in keys])
    out["p10"] = out["p10"] - widen
    out["p90"] = out["p90"] + widen
    out["conformal_widen"] = widen
    return out.drop(columns=["bucket"])
