"""Full national half-hourly history pull from the NESO API.

Pulls forecast + actual for every half-hour window from the API's first
record (2017-09-24) to now, in 13-day chunks, and writes an immutable
parquet under data/raw with a manifest entry.
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from gbcarbon import neso, provenance

API_START = "2017-09-24T00:00Z"


def pull_history(
    start_utc: str = API_START, end: datetime | None = None
) -> pd.DataFrame:
    start = neso.parse_ts(start_utc)
    end = end or datetime.now(UTC)
    rows: list[tuple[str, str, float | None, float | None]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=13), end)
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
        time.sleep(0.15)  # polite pacing; ~240 calls for the full span
    df = pd.DataFrame(
        rows, columns=["window_start", "window_end", "forecast", "actual"]
    )
    for col in ("window_start", "window_end"):
        df[col] = pd.to_datetime(df[col], utc=True)
    df = (
        df.drop_duplicates(subset=["window_start"])
        .sort_values("window_start")
        .reset_index(drop=True)
    )
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/raw", help="raw data directory")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pull_history()
    path = out_dir / "neso_api_history.parquet"
    df.to_parquet(path, index=False)

    missing_actual = int(df["actual"].isna().sum())
    missing_forecast = int(df["forecast"].isna().sum())
    provenance.record(
        out_dir / "manifest.json",
        "neso_api_history",
        url="https://api.carbonintensity.org.uk/intensity/{from}/{to} (13-day chunks)",
        file=path.name,
        rows=int(len(df)),
        sha256=provenance.sha256_file(path),
        coverage_start=str(df["window_start"].min()),
        coverage_end=str(df["window_start"].max()),
        missing_actuals=missing_actual,
        missing_forecasts=missing_forecast,
        license="CC BY 4.0 (NESO Carbon Intensity API)",
    )
    print(
        f"rows={len(df)} first={df['window_start'].min()} "
        f"last={df['window_start'].max()} "
        f"missing_actuals={missing_actual} missing_forecasts={missing_forecast}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
