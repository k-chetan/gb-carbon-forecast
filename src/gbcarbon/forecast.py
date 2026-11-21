"""Nightly 48 h forecast issuance from the deployed model bundle.

Pulls recent published actuals (lags) and the previous-day weather runs for
the target span — the exact lead structure the model was trained on — builds
one issue's feature frame, predicts p10/p50/p90, and writes
``forecasts/latest.json`` plus an immutable dated copy under
``forecasts/history/``.

JSON schema (stable; the Semester 2 scheduler consumes it):
    {
      "schema_version": "1.0",
      "issued_utc": "2026-11-22T03:07Z",
      "model": "<run id of the deployed bundle>",
      "unit": "gCO2e/kWh (attributed, national GB)",
      "windows": [
        {"start": ..., "end": ..., "p10": ..., "p50": ..., "p90": ...}, x96
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from gbcarbon import evaluate, features, neso
from gbcarbon.train import gb_holiday_dates
from gbcarbon.weather import BASE_VARS, POINTS, PREV_URL

DEPLOYED_DIR = Path("models/deployed")
SCHEMA_VERSION = "1.0"


def fetch_recent_history(now: datetime, days: int = 16) -> pd.DataFrame:
    rows = []
    cursor = now - timedelta(days=days)
    while cursor < now:
        chunk_end = min(cursor + timedelta(days=13), now)
        data = neso.intensity_range(
            cursor.strftime(neso.TS_FMT), chunk_end.strftime(neso.TS_FMT)
        )
        rows.extend(
            (
                item["from"],
                item["to"],
                item["intensity"].get("forecast"),
                item["intensity"].get("actual"),
            )
            for item in data
        )
        cursor = chunk_end
    df = pd.DataFrame(
        rows, columns=["window_start", "window_end", "forecast", "actual"]
    )
    for col in ("window_start", "window_end"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df.drop_duplicates(subset=["window_start"]).sort_values("window_start")


def fetch_prev_runs_live(pause: float = 0.3) -> pd.DataFrame:
    """Previous-day runs covering the forecast span (past 2 to next 4 days)."""
    variables = [f"{v}_previous_day{n}" for v in BASE_VARS for n in (1, 2)]
    frames = []
    for point, (lat, lon) in POINTS.items():
        params = {
            "latitude": lat,
            "longitude": lon,
            "past_days": 2,
            "forecast_days": 4,
            "hourly": ",".join(variables),
            "timezone": "UTC",
        }
        for attempt in range(4):
            try:
                resp = requests.get(PREV_URL, params=params, timeout=60)
                resp.raise_for_status()
                frame = pd.DataFrame(resp.json()["hourly"])
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(10 * 2**attempt)
        frame.insert(0, "point", point)
        frames.append(frame)
        time.sleep(pause)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def issue_forecast(now: datetime | None = None) -> dict:
    bundle = evaluate.ModelBundle(DEPLOYED_DIR)
    now = now or datetime.now(UTC)
    issue = pd.Timestamp(now).floor("30min")

    history = fetch_recent_history(now)
    uses_weather = any("previous_day" in c for c in bundle.config["features"])
    weather = fetch_prev_runs_live() if uses_weather else None

    frame = features.build_training_frame(
        history,
        pd.DatetimeIndex([issue]),
        holiday_dates=gb_holiday_dates(now.year, now.year + 1),
        weather_prev=weather,
        keep_unlabelled=True,
    )
    if len(frame) != len(features.HORIZONS_H):
        raise RuntimeError(f"expected 96 horizon rows, built {len(frame)}")
    if uses_weather:
        day2_cols = [c for c in frame.columns if "previous_day2" in c]
        missing = float(frame[day2_cols].isna().mean().mean())
        if missing > 0.05:
            raise RuntimeError(f"day2 weather {missing:.0%} missing at inference")

    preds = bundle.predict(frame)
    assert (preds["p10"] <= preds["p50"]).all() and (preds["p50"] <= preds["p90"]).all()

    windows = [
        {
            "start": row["target_time"].strftime(neso.TS_FMT),
            "end": (row["target_time"] + pd.Timedelta(minutes=30)).strftime(
                neso.TS_FMT
            ),
            "p10": round(float(row["p10"]), 1),
            "p50": round(float(row["p50"]), 1),
            "p90": round(float(row["p90"]), 1),
        }
        for _, row in preds.iterrows()
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "issued_utc": issue.strftime(neso.TS_FMT),
        "model": bundle.config["run_id"],
        "unit": "gCO2e/kWh (attributed, national GB)",
        "windows": windows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="forecasts")
    args = parser.parse_args(argv)

    payload = issue_forecast()
    out = Path(args.out)
    (out / "history").mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    stamp = payload["issued_utc"].replace(":", "")
    (out / "history" / f"{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"issued {payload['issued_utc']}: 96 windows, "
        f"p50 range {min(w['p50'] for w in payload['windows'])}-"
        f"{max(w['p50'] for w in payload['windows'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
