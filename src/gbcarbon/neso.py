"""Minimal client for the NESO Carbon Intensity API.

Keyless, national endpoints only (https://api.carbonintensity.org.uk).
All timestamps are UTC; the API serves half-hour settlement windows with
ISO-8601 'Z' stamps. Standard library only, so the hourly logger job needs
no dependency install.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import UTC, datetime

BASE = "https://api.carbonintensity.org.uk"
USER_AGENT = "gb-carbon-forecast (github.com/k-chetan/gb-carbon-forecast)"
TS_FMT = "%Y-%m-%dT%H:%MZ"


def _get(path: str, retries: int = 3, timeout: int = 30) -> dict:
    url = BASE + path
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as err:  # noqa: BLE001 - any transport/parse error retries
            last_err = err
            if attempt < retries - 1:
                time.sleep(5 * 2**attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_err}")


def utc_now_minute() -> str:
    return datetime.now(UTC).strftime(TS_FMT)


def parse_ts(stamp: str) -> datetime:
    return datetime.strptime(stamp, TS_FMT).replace(tzinfo=UTC)


def fw48h(from_utc: str | None = None) -> list[dict]:
    """Forward 48 h of half-hour forecasts issued from ``from_utc`` (now if omitted).

    The bare ``/intensity/fw48h`` form returns HTTP 400; the dated form is required.
    """
    stamp = from_utc or utc_now_minute()
    return _get(f"/intensity/{stamp}/fw48h")["data"]


def current() -> dict:
    """The current half-hour window: forecast, actual (may be null), index."""
    return _get("/intensity")["data"][0]


def intensity_range(from_utc: str, to_utc: str) -> list[dict]:
    """Half-hour windows between two stamps (API limit: 14 days per call)."""
    return _get(f"/intensity/{from_utc}/{to_utc}")["data"]


def parse_windows(data: list[dict]) -> list[tuple[str, str, int | None]]:
    """Flatten API items to (window_start, window_end, forecast) tuples."""
    return [
        (item["from"], item["to"], item["intensity"].get("forecast")) for item in data
    ]
