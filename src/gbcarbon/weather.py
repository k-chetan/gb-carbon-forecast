"""Issue-time weather forecast pulls for GB grid points (Open-Meteo).

Two archived sources, both forecasts-as-issued (never observations):

- Historical Forecast API: the archived short-lead forecast chain (the most
  recent run covering each hour). Mirrors what the live forecast API serves.
- Previous Runs API: the same variables as forecast 1 and 2 days earlier
  (``*_previous_day1`` / ``*_previous_day2``). For a forecast issued at T and
  a target hour T+h, previous_day1 is admissible for h <= 24 and
  previous_day2 for h <= 48; the feature builder enforces the offset.

Writes one parquet per source under data/raw with manifest entries.
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import requests

from gbcarbon import provenance

HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
PREV_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

BASE_VARS = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_speed_100m",
    "cloud_cover",
    "shortwave_radiation",
]

# Grid points spanning the main wind regions plus demand centres.
POINTS = {
    "scotland_highlands": (57.5, -4.3),
    "scotland_south": (55.6, -3.6),
    "offshore_dogger": (54.8, 1.5),
    "irish_sea": (53.6, -3.9),
    "wales_mid": (52.5, -3.7),
    "england_southwest": (50.9, -3.6),
    "london": (51.5, -0.1),
    "east_anglia_offshore": (52.4, 2.0),
}


def _year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(date(cursor.year, 12, 31), end)
        chunks.append((cursor, chunk_end))
        cursor = date(cursor.year + 1, 1, 1)
    return chunks


def pull_source(
    url: str, variables: list[str], start: date, end: date, pause: float = 0.4
) -> pd.DataFrame:
    frames = []
    for point, (lat, lon) in POINTS.items():
        for chunk_start, chunk_end in _year_chunks(start, end):
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": str(chunk_start),
                "end_date": str(chunk_end),
                "hourly": ",".join(variables),
                "timezone": "UTC",
            }
            hourly = None
            for attempt in range(4):
                try:
                    resp = requests.get(url, params=params, timeout=120)
                    resp.raise_for_status()
                    hourly = resp.json()["hourly"]
                    break
                except requests.RequestException as err:
                    if attempt == 3:
                        raise
                    wait = 10 * 2**attempt
                    print(f"retry {point} {chunk_start}: {err}; waiting {wait}s")
                    time.sleep(wait)
            frame = pd.DataFrame(hourly)
            frame.insert(0, "point", point)
            frames.append(frame)
            time.sleep(pause)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values(["point", "time"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hist-start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--prev-start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", default="data/raw")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).date()
    manifest = out_dir / "manifest.json"

    hist = pull_source(HIST_URL, BASE_VARS, date.fromisoformat(args.hist_start), today)
    hist_path = out_dir / "weather_hist_forecast.parquet"
    hist.to_parquet(hist_path, index=False)
    provenance.record(
        manifest,
        "weather_hist_forecast",
        url=HIST_URL,
        file=hist_path.name,
        rows=int(len(hist)),
        sha256=provenance.sha256_file(hist_path),
        coverage_start=str(hist["time"].min()),
        coverage_end=str(hist["time"].max()),
        points=sorted(POINTS),
        variables=BASE_VARS,
        license="CC BY 4.0 (Open-Meteo, non-commercial tier)",
        note=(
            "archived short-lead forecast chain; "
            "issue-time safe for nowcast-lead features"
        ),
    )
    print(f"hist: rows={len(hist)} -> {hist_path.name}")

    prev_vars = [f"{v}_previous_day{n}" for v in BASE_VARS for n in (1, 2)]
    prev = pull_source(PREV_URL, prev_vars, date.fromisoformat(args.prev_start), today)
    prev_path = out_dir / "weather_prev_runs.parquet"
    prev.to_parquet(prev_path, index=False)
    provenance.record(
        manifest,
        "weather_prev_runs",
        url=PREV_URL,
        file=prev_path.name,
        rows=int(len(prev)),
        sha256=provenance.sha256_file(prev_path),
        coverage_start=str(prev["time"].min()),
        coverage_end=str(prev["time"].max()),
        points=sorted(POINTS),
        variables=prev_vars,
        license="CC BY 4.0 (Open-Meteo, non-commercial tier)",
        note="previous_day1 admissible for horizons <=24 h, previous_day2 for <=48 h",
    )
    print(f"prev: rows={len(prev)} -> {prev_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
