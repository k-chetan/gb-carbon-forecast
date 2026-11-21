"""Verify Open-Meteo archived-forecast coverage per variable.

Probes the Historical Forecast API (archived best-match forecast chain) and
the Previous Runs API (same variables as forecast 1 and 2 days earlier) for
the earliest date each variable is actually populated, by coarse scan plus
day-level bisection. Writes data/raw/weather_coverage.json; the result sets
the Track B training window.

Run: uv run python scripts/verify_weather_coverage.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

POINT = {"latitude": 55.0, "longitude": -3.0}  # mid-GB probe point
HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
PREV_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
BASE_VARS = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_speed_100m",
    "cloud_cover",
    "shortwave_radiation",
]
SCAN_DATES = [
    "2016-01-05",
    "2017-01-05",
    "2018-01-05",
    "2019-01-05",
    "2020-01-05",
    "2021-01-05",
    "2021-03-25",
    "2021-06-05",
    "2022-01-05",
    "2022-06-05",
    "2023-01-05",
    "2024-01-05",
    "2024-06-05",
    "2025-01-05",
]


def probe(url: str, variables: list[str], day: str) -> dict[str, float]:
    """Fraction of non-null hourly values per variable on one probe day."""
    start = date.fromisoformat(day)
    params = {
        **POINT,
        "start_date": day,
        "end_date": str(start + timedelta(days=1)),
        "hourly": ",".join(variables),
        "timezone": "UTC",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return {v: 0.0 for v in variables}
        hourly = resp.json().get("hourly", {})
    except requests.RequestException:
        return {v: 0.0 for v in variables}
    out = {}
    for var in variables:
        values = hourly.get(var) or []
        out[var] = sum(v is not None for v in values) / len(values) if values else 0.0
    return out


def earliest_covered(url: str, variables: list[str]) -> dict[str, str | None]:
    """Earliest populated date per variable: coarse scan, then day bisection."""
    coverage: dict[str, list[tuple[str, float]]] = {v: [] for v in variables}
    for day in SCAN_DATES:
        fractions = probe(url, variables, day)
        for var, frac in fractions.items():
            coverage[var].append((day, frac))
        time.sleep(0.3)

    result: dict[str, str | None] = {}
    for var, scans in coverage.items():
        first_hit = next((d for d, f in scans if f >= 0.9), None)
        if first_hit is None:
            result[var] = None
            continue
        idx = [d for d, _ in scans].index(first_hit)
        low = (
            date.fromisoformat(scans[idx - 1][0])
            if idx
            else date.fromisoformat(first_hit) - timedelta(days=365)
        )
        high = date.fromisoformat(first_hit)
        while (high - low).days > 1:
            mid = low + (high - low) / 2
            frac = probe(url, [var], str(mid)).get(var, 0.0)
            if frac >= 0.9:
                high = mid
            else:
                low = mid
            time.sleep(0.3)
        result[var] = str(high)
    return result


def main() -> int:
    hist = earliest_covered(HIST_URL, BASE_VARS)
    prev_vars = [f"{v}_previous_day{n}" for v in BASE_VARS for n in (1, 2)]
    prev = earliest_covered(PREV_URL, prev_vars)

    payload = {
        "checked_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "probe_point": POINT,
        "model": "best_match (API default)",
        "method": (
            "coarse date scan + day-level bisection, >=90% non-null hourly values"
        ),
        "historical_forecast_api": hist,
        "previous_runs_api": prev,
    }
    out = Path("data/raw/weather_coverage.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
