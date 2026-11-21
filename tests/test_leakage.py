"""Leakage guards: no feature may see past its issue time.

These tests corrupt every observation that was not yet available at the
issue time and check that the built features are identical. If any feature
reads the future, they fail.
"""

import numpy as np
import pandas as pd
import pytest

from gbcarbon import features

START = pd.Timestamp("2026-01-01 00:00", tz="UTC")
N_STEPS = 48 * 30  # 30 days of half-hours


@pytest.fixture()
def history() -> pd.DataFrame:
    times = pd.date_range(START, periods=N_STEPS, freq="30min")
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "window_start": times,
            "window_end": times + pd.Timedelta(minutes=30),
            "forecast": rng.normal(150, 30, N_STEPS).round(0),
            "actual": np.arange(N_STEPS, dtype=float),  # distinct, traceable
        }
    )


def poison_after(history: pd.DataFrame, issue: pd.Timestamp) -> pd.DataFrame:
    """Corrupt every window not fully elapsed at the issue time."""
    poisoned = history.copy()
    not_available = poisoned["window_start"] >= issue
    poisoned.loc[not_available, ["actual", "forecast"]] = 1e9
    return poisoned


def test_issue_features_ignore_the_future(history):
    issues = pd.DatetimeIndex(
        [START + pd.Timedelta(days=d, hours=hr) for d in (10, 15, 20) for hr in (0, 13)]
    )
    clean = features.build_training_frame(history, issues, holiday_dates=set())
    cols = [
        c
        for c in features.feature_columns(clean)
        if c not in ("issue_time", "target_time")
    ]
    for issue in issues:
        poisoned = features.build_training_frame(
            poison_after(history, issue), pd.DatetimeIndex([issue]), holiday_dates=set()
        )
        clean_rows = clean[clean["issue_time"] == issue].reset_index(drop=True)
        # poisoned y values differ (they are the future); features must not
        merged = clean_rows.merge(
            poisoned, on=["issue_time", "target_time"], suffixes=("", "_p")
        )
        assert len(merged) > 0
        for col in cols:
            if col == "y":
                continue
            pd.testing.assert_series_equal(
                merged[col],
                merged[f"{col}_p"].rename(col),
                check_exact=True,
                obj=f"feature {col} changed when the future was poisoned at {issue}",
            )


def test_lag_zero_is_last_elapsed_window(history):
    issue = START + pd.Timedelta(days=10)
    frame = features.build_training_frame(
        history, pd.DatetimeIndex([issue]), holiday_dates=set()
    )
    expected = history.set_index("window_start")["actual"].loc[
        issue - pd.Timedelta(minutes=30)
    ]
    assert frame["lag_0h"].iloc[0] == expected


def test_targets_align_with_horizons(history):
    issue = START + pd.Timedelta(days=12)
    frame = features.build_training_frame(
        history, pd.DatetimeIndex([issue]), holiday_dates=set()
    )
    grid = history.set_index("window_start")["actual"]
    sample = frame.sample(10, random_state=0)
    for _, row in sample.iterrows():
        assert row["target_time"] == row["issue_time"] + pd.Timedelta(
            hours=row["horizon_h"]
        )
        assert row["y"] == grid.loc[row["target_time"]]


def _weather_fixture() -> pd.DataFrame:
    hours = pd.date_range(START, periods=24 * 30, freq="1h")
    frames = []
    for point in ("alpha", "beta"):
        frame = pd.DataFrame({"point": point, "time": hours})
        for var in features.WEATHER_BASE_VARS:
            base = np.arange(len(hours), dtype=float)
            frame[f"{var}_previous_day1"] = base + 0.1
            frame[f"{var}_previous_day2"] = base + 0.2
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_day1_weather_masked_beyond_24h(history):
    issue = START + pd.Timedelta(days=10)
    frame = features.build_training_frame(
        history,
        pd.DatetimeIndex([issue]),
        holiday_dates=set(),
        weather_prev=_weather_fixture(),
    )
    day1_cols = [c for c in frame.columns if "previous_day1" in c]
    day2_cols = [c for c in frame.columns if "previous_day2" in c]
    assert day1_cols and day2_cols

    beyond = frame["horizon_h"] > features.DAY1_MAX_HORIZON_H
    assert frame.loc[beyond, day1_cols].isna().all().all()
    assert frame.loc[~beyond, day1_cols].notna().all().all()
    assert frame.loc[:, day2_cols].notna().all().all()


def test_holiday_flag(history):
    issue = START + pd.Timedelta(days=10)
    holiday = (issue + pd.Timedelta(hours=30)).date()
    frame = features.build_training_frame(
        history, pd.DatetimeIndex([issue]), holiday_dates={holiday}
    )
    flagged = frame[frame["t_holiday"] == 1]
    assert len(flagged) > 0
    assert (pd.DatetimeIndex(flagged["target_time"]).date == holiday).all()
