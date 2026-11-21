"""Hourly vintage capture of NESO's forward 48 h forecast, as issued.

Each run appends one capture (~96 half-hour windows) to
``vintages/daily/<capture-date>.csv`` on the ``vintage-log`` branch and
refreshes ``vintages/manifest.json``. A capture is a point-in-time snapshot:
a missed hour is a permanent gap, recorded in the manifest, because past
vintages cannot be re-requested from the API.

Standard library only; run as ``PYTHONPATH=src python -m gbcarbon.vintage``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from gbcarbon import neso

CSV_HEADER = ["capture_utc", "window_start", "window_end", "forecast"]
GAP_HOURS = 2.0  # two consecutive missed hourly captures count as a gap


def write_capture(
    out_dir: Path, capture_utc: str, rows: list[tuple[str, str, int | None]]
) -> Path:
    daily = out_dir / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    path = daily / f"{capture_utc[:10]}.csv"
    is_new = not path.exists()
    with open(path, "a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(CSV_HEADER)
        for window_start, window_end, forecast in rows:
            writer.writerow(
                [
                    capture_utc,
                    window_start,
                    window_end,
                    forecast if forecast is not None else "",
                ]
            )
    return path


def update_manifest(out_dir: Path, capture_utc: str, n_rows: int) -> dict:
    path = out_dir / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text())
    else:
        manifest = {
            "created_utc": capture_utc,
            "last_capture_utc": None,
            "total_captures": 0,
            "gaps": [],
            "note": "Gaps are permanent: past vintages cannot be backfilled.",
        }
    last = manifest.get("last_capture_utc")
    if last:
        delta_h = (
            neso.parse_ts(capture_utc) - neso.parse_ts(last)
        ).total_seconds() / 3600
        if delta_h > GAP_HOURS:
            manifest["gaps"].append(
                {"after": last, "before": capture_utc, "hours": round(delta_h, 1)}
            )
    manifest["last_capture_utc"] = capture_utc
    manifest["last_rows"] = n_rows
    manifest["total_captures"] = int(manifest.get("total_captures", 0)) + 1
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="vintages directory to write into")
    args = parser.parse_args(argv)

    if os.environ.get("SIMULATE_FAILURE", "").lower() == "true":
        print(
            "SIMULATE_FAILURE=true: failing on purpose (alerting drill)",
            file=sys.stderr,
        )
        return 1

    capture_utc = neso.utc_now_minute()
    rows = neso.parse_windows(neso.fw48h(capture_utc))
    if not rows:
        print("API returned no forward windows", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    path = write_capture(out_dir, capture_utc, rows)
    manifest = update_manifest(out_dir, capture_utc, len(rows))
    print(
        f"captured {len(rows)} windows at {capture_utc} -> {path.name} "
        f"(total captures: {manifest['total_captures']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
