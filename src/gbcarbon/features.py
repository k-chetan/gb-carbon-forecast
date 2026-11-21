"""Issue-time feature construction with availability rules.

The frame is built per (issue_time T, horizon h) sample, with target y(T+h).
A value may enter a sample only if it was available at T, and the rules live
in this module rather than in documentation:

- Lag and rolling features are computed on the series up to T only (shifts
  on the issue grid).
- Calendar features of the target time are deterministic, so always
  available.
- Weather values at the target time come from archived forecast runs.
  ``*_previous_day2`` (issued ~48 h before validity) is admissible at every
  horizon up to 48 h. ``*_previous_day1`` (issued ~24 h before validity) is
  admissible only for horizons up to 24 h and is set to NaN beyond that,
  which LightGBM handles natively.

tests/test_leakage.py corrupts all values after each issue time and checks
that the built features do not change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS_H = np.arange(0.5, 48.5, 0.5)  # 96 half-hour horizons
DAY1_MAX_HORIZON_H = 24.0

# lags in half-hour steps behind the issue time
ISSUE_LAGS_STEPS = {
    "lag_0h": 0,
    "lag_1h": 2,
    "lag_2h": 4,
    "lag_3h": 6,
    "lag_6h": 12,
    "lag_12h": 24,
    "lag_24h": 48,
    "lag_48h": 96,
    "lag_7d": 336,
}
ROLLING_WINDOWS_STEPS = {"roll_24h": 48, "roll_7d": 336}

WEATHER_BASE_VARS = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_speed_100m",
    "cloud_cover",
    "shortwave_radiation",
]
WIND_POINT_VAR = "wind_speed_100m"


def half_hour_grid(history: pd.DataFrame) -> pd.DataFrame:
    """History on an explicit half-hour grid indexed by window_start."""
    return history.set_index("window_start").sort_index().asfreq("30min")


def issue_features(grid: pd.DataFrame, issue_times: pd.DatetimeIndex) -> pd.DataFrame:
    """Lag/rolling features of the actual series, as known at each issue time.

    The last published actual at issue T is the window ending at or before T,
    i.e. the window starting at T-30min; ``lag_0h`` encodes that freshest
    value and deeper lags follow from it.
    """
    actual = grid["actual"]
    base = actual.shift(1)  # value of the window starting one step before T
    feats = pd.DataFrame(index=grid.index)
    for name, steps in ISSUE_LAGS_STEPS.items():
        feats[name] = base.shift(steps)
    for name, steps in ROLLING_WINDOWS_STEPS.items():
        feats[name] = base.rolling(steps, min_periods=steps // 2).mean()
    feats["trend_24h"] = feats["lag_0h"] - feats["lag_24h"]
    return feats.reindex(issue_times)


def target_calendar(times: pd.DatetimeIndex, holiday_dates: set) -> pd.DataFrame:
    hours = times.hour + times.minute / 60
    frame = pd.DataFrame(index=times)
    frame["t_hour_sin"] = np.sin(2 * np.pi * hours / 24)
    frame["t_hour_cos"] = np.cos(2 * np.pi * hours / 24)
    frame["t_hour"] = hours
    frame["t_dow"] = times.day_of_week
    frame["t_month"] = times.month
    frame["t_doy"] = times.day_of_year
    frame["t_holiday"] = [int(d in holiday_dates) for d in times.date]
    return frame


def weather_target_features(weather_prev: pd.DataFrame) -> pd.DataFrame:
    """Per-validity-hour weather features from the previous-runs archive.

    Input: long frame (point, time, <var>_previous_day1/2). Output: wide frame
    indexed by time with per-point 100 m wind and cross-point means of the
    other variables, one column set per lead. Hourly values are forward-filled
    onto the half-hour grid (weather is hourly; both half-hours share it).
    """
    out: list[pd.DataFrame] = []
    for lead in ("previous_day1", "previous_day2"):
        cols = [f"{v}_{lead}" for v in WEATHER_BASE_VARS]
        sub = weather_prev[["point", "time", *cols]].copy()
        wind = sub.pivot(
            index="time", columns="point", values=f"{WIND_POINT_VAR}_{lead}"
        ).add_prefix(f"wind100_{lead}_")
        means = (
            sub.drop(columns=[f"{WIND_POINT_VAR}_{lead}"])
            .groupby("time")[[c for c in cols if WIND_POINT_VAR not in c]]
            .mean()
        )
        means.columns = [c.replace(f"_{lead}", f"_mean_{lead}") for c in means.columns]
        out.append(pd.concat([wind, means], axis=1))
    wide = pd.concat(out, axis=1).sort_index()
    half = wide.resample("30min").ffill(limit=1)
    return half


def build_training_frame(
    history: pd.DataFrame,
    issue_times: pd.DatetimeIndex,
    holiday_dates: set,
    weather_prev: pd.DataFrame | None = None,
    horizons_h: np.ndarray = HORIZONS_H,
    keep_unlabelled: bool = False,
) -> pd.DataFrame:
    """One row per (issue, horizon): meta columns, features, target.

    Row count is len(issue_times) x len(horizons_h); rows with no published
    target actual are dropped unless ``keep_unlabelled`` (inference mode).
    """
    grid = half_hour_grid(history)
    issue = issue_features(grid, issue_times)
    wx = weather_target_features(weather_prev) if weather_prev is not None else None

    n_h = len(horizons_h)
    issue_rep = issue.loc[issue.index.repeat(n_h)].reset_index(names="issue_time")
    horizons = np.tile(horizons_h, len(issue_times))
    issue_rep["horizon_h"] = horizons
    issue_rep["target_time"] = issue_rep["issue_time"] + pd.to_timedelta(
        horizons, unit="h"
    )

    target_times = pd.DatetimeIndex(issue_rep["target_time"])
    cal = target_calendar(target_times, holiday_dates).reset_index(drop=True)
    frame = pd.concat([issue_rep.reset_index(drop=True), cal], axis=1)

    frame["y"] = grid["actual"].reindex(target_times).to_numpy()

    if wx is not None:
        wx_rows = wx.reindex(target_times).reset_index(drop=True)
        day1_cols = [c for c in wx_rows.columns if "previous_day1" in c]
        mask = (frame["horizon_h"] > DAY1_MAX_HORIZON_H).to_numpy()
        wx_rows.loc[mask, day1_cols] = np.nan
        frame = pd.concat([frame, wx_rows], axis=1)

    if not keep_unlabelled:
        frame = frame.dropna(subset=["y"])
    return frame.reset_index(drop=True)


def feature_columns(frame: pd.DataFrame) -> list[str]:
    meta = {"issue_time", "target_time", "y"}
    return [c for c in frame.columns if c not in meta]
