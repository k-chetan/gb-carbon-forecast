"""Extract national forecast vintages from the community archive (Leg 2).

Source: github.com/nmpowell/carbon-intensity-forecast-tracking (MIT), monthly
``national_YYYY-MM.sqlite`` files with (window_utc, capture_utc, forecast,
actual) keyed by unix seconds. This script:

- keeps captures on the half-hour cadence closest to each hour (hourly
  subsample, matching this project's own logger cadence),
- keeps horizons 0 < h <= 48 h,
- writes data/external/community_vintages.parquet,
- writes a per-month provenance audit JSON (the PRD's "audit still owed"),
- records both in the raw-data manifest with the source commit hash.

Run: PYTHONPATH=src uv run python scripts/build_community_vintages.py --src <clone>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")

from gbcarbon import provenance  # noqa: E402

OUT_DIR = Path("data/external")


def read_month(path: Path) -> pd.DataFrame:
    with sqlite3.connect(path) as conn:
        df = pd.read_sql_query(
            "SELECT window_utc, capture_utc, forecast FROM national_intensity", conn
        )
    df["window_start"] = pd.to_datetime(df["window_utc"], unit="s", utc=True)
    df["capture_utc"] = pd.to_datetime(df["capture_utc"], unit="s", utc=True)
    df["month"] = path.stem.removeprefix("national_")
    return df[["month", "capture_utc", "window_start", "forecast"]]


def audit_month(df: pd.DataFrame) -> dict:
    captures = df["capture_utc"].drop_duplicates().sort_values()
    gaps = captures.diff().dt.total_seconds().div(3600).dropna()
    return {
        "captures": int(len(captures)),
        "rows": int(len(df)),
        "first_capture": captures.min().strftime("%Y-%m-%dT%H:%MZ"),
        "last_capture": captures.max().strftime("%Y-%m-%dT%H:%MZ"),
        "capture_gaps_over_2h": int((gaps > 2).sum()),
        "largest_gap_h": round(float(gaps.max()), 1) if len(gaps) else None,
        "median_windows_per_capture": float(df.groupby("capture_utc").size().median()),
        "null_forecast_rows": int(df["forecast"].isna().sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, help="path to the cloned archive repo")
    args = parser.parse_args()
    src = Path(args.src)

    commit = subprocess.run(
        ["git", "-C", str(src), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    frames, audit = [], {}
    for db in sorted(src.glob("data/db/*/national_*.sqlite")):
        df = read_month(db)
        audit[df["month"].iloc[0]] = audit_month(df)
        # hourly subsample: keep the capture in the first half of each hour
        df = df[df["capture_utc"].dt.minute < 30]
        horizon_h = (df["window_start"] - df["capture_utc"]).dt.total_seconds() / 3600
        df = df[(horizon_h > 0) & (horizon_h <= 48)]
        frames.append(df)

    out = pd.concat(frames, ignore_index=True).sort_values(
        ["capture_utc", "window_start"]
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parquet = OUT_DIR / "community_vintages.parquet"
    out.to_parquet(parquet, index=False)

    audit_payload = {
        "built_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "source_repo": "https://github.com/nmpowell/carbon-intensity-forecast-tracking",
        "source_commit": commit,
        "source_license": "MIT (c) 2023 Nick Powell",
        "filters": "hourly capture subsample (minute < 30); horizons 0 < h <= 48 h",
        "full_resolution_note": (
            "re-run this script without the subsample for 30-min cadence"
        ),
        "months": audit,
    }
    audit_path = OUT_DIR / "community_vintages_audit.json"
    audit_path.write_text(json.dumps(audit_payload, indent=2, sort_keys=True) + "\n")

    provenance.record(
        Path("data/raw/manifest.json"),
        "community_vintages",
        url=audit_payload["source_repo"],
        source_commit=commit,
        file=str(parquet),
        rows=int(len(out)),
        sha256=provenance.sha256_file(parquet),
        months=sorted(audit),
        license="MIT (archive); underlying data NESO CC BY 4.0",
        role="Leg 2: operator vintages on archive-covered months (no 2025)",
    )
    print(f"months: {sorted(audit)}")
    print(f"rows kept: {len(out)} -> {parquet} ({parquet.stat().st_size / 1e6:.1f} MB)")
    print(f"audit -> {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
