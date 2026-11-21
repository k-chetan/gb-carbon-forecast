"""Reproduce the pilot study's 2025 sanity anchors before any modelling.

Pilot anchors (train 2018-2024 where applicable, scored on calendar 2025):
persistence-24h MAE ~38.9, persistence-48h ~47.5, seasonal-naive(7d) ~55.9,
lags+calendar GBM ~38.3, stored NESO forecast ~9.3 over ~17.5k pairs.

Protocol note: these are reproductions of experiments the pilot already ran —
no-parameter reference forecasts plus one untuned GBM built exactly once. The
GBM is not iterated against 2025; a mismatch triggers a data-pipeline
investigation, never tuning. The sealed M4 evaluation covers the real
candidate models, whose development uses validation windows inside the
training years only.

Run: PYTHONPATH=src uv run python scripts/reproduce_anchors.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import holidays
import pandas as pd

sys.path.insert(0, "src")

from gbcarbon import baselines  # noqa: E402

HISTORY = Path("data/raw/neso_api_history.parquet")
OUT = Path("results/anchor_reproduction.json")

ANCHORS = {
    "persistence_24h": 38.9,
    "persistence_48h": 47.5,
    "seasonal_naive_7d": 55.9,
    "gbm_lags_calendar_24h": 38.3,
    "neso_stored_forecast": 9.3,
}


def build_gbm_frame(history: pd.DataFrame) -> pd.DataFrame:
    """Features available 24 h before each target window (lags >= 48 steps)."""
    frame = history.set_index("window_start").asfreq("30min")
    y = frame["actual"]
    feats = pd.DataFrame(index=frame.index)
    feats["lag_24h"] = y.shift(48)
    feats["lag_25h"] = y.shift(50)
    feats["lag_48h"] = y.shift(96)
    feats["lag_7d"] = y.shift(336)
    feats["roll_mean_24h_asof_24h"] = y.shift(48).rolling(48).mean()
    feats["roll_mean_7d_asof_24h"] = y.shift(48).rolling(336).mean()
    idx = feats.index
    feats["hour"] = idx.hour + idx.minute / 60
    feats["dow"] = idx.day_of_week
    feats["month"] = idx.month
    gb_holidays = holidays.country_holidays("GB", subdiv="England")
    feats["holiday"] = (
        pd.Series(idx.date, index=idx).map(lambda d: d in gb_holidays).astype(int)
    )
    feats["target"] = y
    return feats


def main() -> int:
    history = pd.read_parquet(HISTORY).sort_values("window_start")
    history["year"] = history["window_start"].dt.year
    test_mask = history["year"] == 2025

    results: dict[str, dict] = {}

    for name, steps in (
        ("persistence_24h", baselines.STEPS_24H),
        ("persistence_48h", baselines.STEPS_48H),
        ("seasonal_naive_7d", baselines.STEPS_7D),
    ):
        reference = baselines.lagged_reference(history, steps)
        err = (
            reference[test_mask.to_numpy()]
            - history.loc[test_mask, "actual"].to_numpy()
        ).abs()
        results[name] = {
            "mae": round(float(err.dropna().mean()), 2),
            "n": int(err.notna().sum()),
        }

    stored = history[test_mask].dropna(subset=["forecast", "actual"])
    results["neso_stored_forecast"] = {
        "mae": round(float((stored["forecast"] - stored["actual"]).abs().mean()), 2),
        "n": int(len(stored)),
    }

    import lightgbm as lgb

    feats = build_gbm_frame(history)
    feats = feats.dropna(subset=["target"])
    train = feats[(feats.index.year >= 2018) & (feats.index.year <= 2024)].dropna()
    test = feats[feats.index.year == 2025].dropna()
    model = lgb.LGBMRegressor(random_state=42, n_estimators=200, verbose=-1)
    feature_cols = [c for c in feats.columns if c != "target"]
    model.fit(train[feature_cols], train["target"])
    pred = model.predict(test[feature_cols])
    results["gbm_lags_calendar_24h"] = {
        "mae": round(float((pred - test["target"]).abs().mean()), 2),
        "n": int(len(test)),
    }

    report = {
        "computed_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "anchors": ANCHORS,
        "reproduced": results,
        "relative_gap": {
            k: round(abs(results[k]["mae"] - v) / v, 3) for k, v in ANCHORS.items()
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["reproduced"], indent=2))
    print("relative gaps vs anchors:", report["relative_gap"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
