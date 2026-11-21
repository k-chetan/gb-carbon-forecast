"""Reference forecasts: persistence and seasonal-naive.

All operate on the half-hourly national history frame (window_start, actual)
and produce pointwise reference forecasts via fixed lags. A lag of k steps is
k/2 hours; persistence-24h is 48 steps, persistence-48h is 96, and the
7-day seasonal naive is 336.
"""

from __future__ import annotations

import pandas as pd

STEPS_24H = 48
STEPS_48H = 96
STEPS_7D = 336


def lagged_reference(history: pd.DataFrame, steps: int) -> pd.Series:
    """Reference forecast for each window: the actual `steps` half-hours earlier.

    Assumes `history` is sorted, half-hourly and indexed 0..n-1; gaps in the
    published series stay NaN and drop out of scoring.
    """
    frame = history.set_index("window_start")
    full = frame.asfreq("30min")  # explicit grid so a shift is a time shift
    return full["actual"].shift(steps).reindex(history["window_start"])


def mae(forecast: pd.Series, actual: pd.Series) -> float:
    err = (forecast - actual.to_numpy()).abs().dropna()
    return float(err.mean())
