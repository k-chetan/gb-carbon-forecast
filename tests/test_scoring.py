import csv
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from gbcarbon import scoring

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def write_daily(vintage_dir: Path, day: str, rows: list[list]) -> Path:
    daily = vintage_dir / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    path = daily / f"{day}.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(scoring.VINTAGE_COLUMNS)
        writer.writerows(rows)
    return path


def capture_rows(capture: str, windows: list[tuple[str, str, int]]) -> list[list]:
    return [[capture, start, end, forecast] for start, end, forecast in windows]


def test_horizon_buckets():
    assert scoring.horizon_bucket(0.0) is None
    assert scoring.horizon_bucket(0.5) == "01_06h"
    assert scoring.horizon_bucket(6.0) == "01_06h"
    assert scoring.horizon_bucket(6.5) == "07_24h"
    assert scoring.horizon_bucket(24.0) == "07_24h"
    assert scoring.horizon_bucket(48.0) == "25_48h"
    assert scoring.horizon_bucket(48.5) is None


def test_compact_folds_closed_months_only(tmp_path):
    old = write_daily(
        tmp_path,
        "2026-10-05",
        capture_rows(
            "2026-10-05T10:17Z",
            [("2026-10-05T11:00Z", "2026-10-05T11:30Z", 100)],
        ),
    )
    current = write_daily(
        tmp_path,
        "2026-11-21",
        capture_rows(
            "2026-11-21T10:17Z",
            [("2026-11-21T11:00Z", "2026-11-21T11:30Z", 200)],
        ),
    )

    written = scoring.compact(tmp_path, NOW)

    assert [p.name for p in written] == ["2026-10.parquet"]
    assert not old.exists()
    assert current.exists()
    monthly = pd.read_parquet(tmp_path / "monthly" / "2026-10.parquet")
    assert len(monthly) == 1

    # idempotent: nothing left to fold
    assert scoring.compact(tmp_path, NOW) == []


def test_load_vintages_merges_sources_and_dedups(tmp_path):
    write_daily(
        tmp_path,
        "2026-10-05",
        capture_rows(
            "2026-10-05T10:17Z",
            [("2026-10-05T11:00Z", "2026-10-05T11:30Z", 100)],
        ),
    )
    scoring.compact(tmp_path, NOW)
    write_daily(
        tmp_path,
        "2026-11-21",
        capture_rows(
            "2026-11-21T10:17Z",
            [
                ("2026-11-21T11:00Z", "2026-11-21T11:30Z", 200),
                ("2026-11-21T11:30Z", "2026-11-21T12:00Z", ""),  # missing forecast
            ],
        ),
    )

    df = scoring.load_vintages(tmp_path)
    assert len(df) == 2  # missing-forecast row dropped
    assert df["capture_utc"].dt.tz is not None


def test_score_filters_maturity_and_buckets():
    vintages = pd.DataFrame(
        {
            "capture_utc": pd.to_datetime(["2026-11-20T12:00Z"] * 3, utc=True),
            "window_start": pd.to_datetime(
                ["2026-11-20T14:00Z", "2026-11-21T06:00Z", "2026-11-21T13:00Z"],
                utc=True,
            ),
            "window_end": pd.to_datetime(
                ["2026-11-20T14:30Z", "2026-11-21T06:30Z", "2026-11-21T13:30Z"],
                utc=True,
            ),
            "forecast": [110.0, 120.0, 130.0],
        }
    )
    actuals = pd.DataFrame(
        {
            "window_start": vintages["window_start"],
            "actual": [100.0, 100.0, 100.0],
        }
    )

    scored = scoring.score(vintages, actuals, NOW)

    # third window ends after NOW -> not matured
    assert len(scored) == 2
    assert scored["bucket"].tolist() == ["01_06h", "07_24h"]  # 2 h and 18 h ahead
    assert scored["abs_err"].tolist() == [10.0, 20.0]

    summary = scoring.summarize(scored, vintages, NOW)
    assert summary["neso_fw48h"]["scored_windows"] == 2
    assert summary["neso_fw48h"]["mae_by_bucket"] == {"01_06h": 10.0, "07_24h": 20.0}
    assert summary["vintages"]["total_captures"] == 1
    assert summary["model_forecasts"]["status"] == "pending"
