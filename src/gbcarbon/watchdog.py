"""Daily health check of the unattended pipeline.

Assesses the age of the last vintage capture and (once the nightly forecast
job is live) the age of the last issued forecast. Prints a report, and when
running inside GitHub Actions writes ``status`` / ``detail`` outputs that the
workflow turns into a "PIPELINE STALE" issue or a recovery close.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from gbcarbon import neso

MAX_FORECAST_AGE_HOURS = 48.0


def assess(
    now: datetime,
    last_capture: datetime | None,
    max_capture_age_hours: float,
    last_forecast_issued: datetime | None,
    max_forecast_age_hours: float = MAX_FORECAST_AGE_HOURS,
) -> tuple[bool, list[str]]:
    problems: list[str] = []
    notes: list[str] = []

    if last_capture is None:
        problems.append("no vintage capture found in the manifest")
    else:
        age = (now - last_capture).total_seconds() / 3600
        line = (
            f"last vintage capture {age:.1f} h ago "
            f"(threshold {max_capture_age_hours:g} h)"
        )
        (problems if age > max_capture_age_hours else notes).append(line)

    if last_forecast_issued is None:
        notes.append("nightly forecast job not live yet; forecast-age check skipped")
    else:
        age = (now - last_forecast_issued).total_seconds() / 3600
        line = (
            f"last forecast issued {age:.1f} h ago "
            f"(threshold {max_forecast_age_hours:g} h)"
        )
        (problems if age > max_forecast_age_hours else notes).append(line)

    return (not problems, problems + notes)


def _read_last_capture(vintage_dir: Path) -> datetime | None:
    manifest = vintage_dir / "manifest.json"
    if not manifest.exists():
        return None
    stamp = json.loads(manifest.read_text()).get("last_capture_utc")
    return neso.parse_ts(stamp) if stamp else None


def _read_last_forecast(forecast_dir: Path) -> datetime | None:
    latest = forecast_dir / "latest.json"
    if not latest.exists():
        return None
    stamp = json.loads(latest.read_text()).get("issued_utc")
    return neso.parse_ts(stamp) if stamp else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintages", required=True)
    parser.add_argument("--forecasts", required=True)
    parser.add_argument("--max-capture-age-hours", type=float, default=6.0)
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    ok, lines = assess(
        now,
        _read_last_capture(Path(args.vintages)),
        args.max_capture_age_hours,
        _read_last_forecast(Path(args.forecasts)),
    )

    status = "ok" if ok else "stale"
    print(f"status: {status}")
    for line in lines:
        print(f"- {line}")

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as handle:
            handle.write(f"status={status}\n")
            handle.write("detail<<WATCHDOG_EOF\n")
            handle.write("\n".join(f"- {line}" for line in lines))
            handle.write("\nWATCHDOG_EOF\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
