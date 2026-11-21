"""Self-scoring of logged forecast vintages against published actuals.

Weekly job: compacts closed months of daily vintage CSVs into monthly parquet,
scores every matured (window closed, actual published) logged forecast by
horizon, and writes ``results/prospective_scores.parquet`` plus a summary JSON
the app reads. Each run is a full recompute from the raw vintages, so the job
is idempotent and a missed week self-heals on the next run.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from gbcarbon import neso

VINTAGE_COLUMNS = ["capture_utc", "window_start", "window_end", "forecast"]
BUCKETS = [(0.0, 6.0, "01_06h"), (6.0, 24.0, "07_24h"), (24.0, 48.0, "25_48h")]


def compact(vintage_dir: Path, now: datetime) -> list[Path]:
    """Fold daily CSVs of fully closed months into monthly parquet files."""
    monthly_dir = vintage_dir / "monthly"
    current_month = now.strftime("%Y-%m")
    groups: dict[str, list[Path]] = {}
    for path in sorted((vintage_dir / "daily").glob("*.csv")):
        month = path.stem[:7]
        if month < current_month:
            groups.setdefault(month, []).append(path)
    written = []
    for month, files in sorted(groups.items()):
        frames = [pd.read_csv(f) for f in files]
        out = monthly_dir / f"{month}.parquet"
        if out.exists():
            frames.insert(0, pd.read_parquet(out))
        df = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["capture_utc", "window_start"])
            .sort_values(["capture_utc", "window_start"])
        )
        monthly_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        for f in files:
            f.unlink()
        written.append(out)
    return written


def load_vintages(vintage_dir: Path) -> pd.DataFrame:
    frames = [pd.read_csv(f) for f in sorted((vintage_dir / "daily").glob("*.csv"))] + [
        pd.read_parquet(f) for f in sorted((vintage_dir / "monthly").glob("*.parquet"))
    ]
    if not frames:
        return pd.DataFrame(columns=VINTAGE_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    for col in ("capture_utc", "window_start", "window_end"):
        df[col] = pd.to_datetime(df[col], utc=True)
    df["forecast"] = pd.to_numeric(df["forecast"], errors="coerce")
    df = df.dropna(subset=["forecast"])
    return df.drop_duplicates(subset=["capture_utc", "window_start"]).sort_values(
        ["capture_utc", "window_start"]
    )


def fetch_actuals(start: datetime, end: datetime) -> pd.DataFrame:
    """Published actuals for [start, end], fetched in <14-day chunks."""
    rows: list[tuple[str, float | None]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=13), end)
        data = neso.intensity_range(
            cursor.strftime(neso.TS_FMT), chunk_end.strftime(neso.TS_FMT)
        )
        rows.extend((item["from"], item["intensity"].get("actual")) for item in data)
        cursor = chunk_end
    df = pd.DataFrame(rows, columns=["window_start", "actual"])
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df["actual"] = pd.to_numeric(df["actual"], errors="coerce")
    df = df.dropna(subset=["actual"])
    return df.drop_duplicates(subset=["window_start"])


def horizon_bucket(hours: float) -> str | None:
    for low, high, name in BUCKETS:
        if low < hours <= high:
            return name
    return None


def score(vintages: pd.DataFrame, actuals: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Absolute error per matured (capture, window) pair, with horizon bucket."""
    df = vintages.merge(actuals, on="window_start", how="inner")
    df = df[df["window_end"] <= now]
    df["horizon_h"] = (df["window_start"] - df["capture_utc"]).dt.total_seconds() / 3600
    df["bucket"] = df["horizon_h"].map(horizon_bucket)
    df = df.dropna(subset=["bucket"])
    df["abs_err"] = (df["forecast"] - df["actual"]).abs()
    return df.reset_index(drop=True)


def summarize(scored: pd.DataFrame, vintages: pd.DataFrame, now: datetime) -> dict:
    if scored.empty:
        mae_by_bucket: dict[str, float] = {}
        n_by_bucket: dict[str, int] = {}
    else:
        by_bucket = scored.groupby("bucket")["abs_err"]
        mae_by_bucket = {k: round(float(v), 2) for k, v in by_bucket.mean().items()}
        n_by_bucket = {k: int(v) for k, v in by_bucket.count().items()}
    return {
        "updated_utc": now.strftime(neso.TS_FMT),
        "vintages": {
            "first_capture_utc": (
                vintages["capture_utc"].min().strftime(neso.TS_FMT)
                if len(vintages)
                else None
            ),
            "last_capture_utc": (
                vintages["capture_utc"].max().strftime(neso.TS_FMT)
                if len(vintages)
                else None
            ),
            "total_captures": int(vintages["capture_utc"].nunique()),
        },
        "neso_fw48h": {
            "scored_windows": int(len(scored)),
            "overall_mae": round(float(scored["abs_err"].mean()), 2)
            if len(scored)
            else None,
            "mae_by_bucket": mae_by_bucket,
            "n_by_bucket": n_by_bucket,
        },
        "model_forecasts": {
            "status": "pending",
            "detail": "nightly forecast job not live yet",
        },
    }


def load_model_forecasts(forecast_dir: Path) -> pd.DataFrame:
    """All dated nightly forecasts (this project's own vintages)."""
    rows = []
    for path in sorted((forecast_dir / "history").glob("*.json")):
        payload = json.loads(path.read_text())
        issued = payload["issued_utc"]
        for w in payload["windows"]:
            rows.append((issued, w["start"], w["p10"], w["p50"], w["p90"]))
    df = pd.DataFrame(rows, columns=["issued_utc", "window_start", "p10", "p50", "p90"])
    if df.empty:
        return df
    df["issued_utc"] = pd.to_datetime(
        df["issued_utc"], format="%Y-%m-%dT%H:%MZ", utc=True
    )
    df["window_start"] = pd.to_datetime(
        df["window_start"], format="%Y-%m-%dT%H:%MZ", utc=True
    )
    return df.drop_duplicates(subset=["issued_utc", "window_start"])


def score_model(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    df = forecasts.merge(actuals, on="window_start", how="inner")
    df["horizon_h"] = (df["window_start"] - df["issued_utc"]).dt.total_seconds() / 3600
    df["bucket"] = df["horizon_h"].map(horizon_bucket)
    df = df.dropna(subset=["bucket"])
    df["abs_err"] = (df["p50"] - df["actual"]).abs()
    df["covered_80"] = (df["actual"] >= df["p10"]) & (df["actual"] <= df["p90"])
    return df.reset_index(drop=True)


def summarize_model(scored: pd.DataFrame) -> dict:
    if scored.empty:
        return {"status": "pending", "detail": "no matured model forecasts yet"}
    grp = scored.groupby("bucket")
    return {
        "status": "live",
        "scored_windows": int(len(scored)),
        "n_forecasts": int(scored["issued_utc"].nunique()),
        "overall_mae": round(float(scored["abs_err"].mean()), 2),
        "mae_by_bucket": {
            k: round(float(v), 2) for k, v in grp["abs_err"].mean().items()
        },
        "coverage80_by_bucket": {
            k: round(float(v), 3) for k, v in grp["covered_80"].mean().items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintages", required=True, help="vintages directory")
    parser.add_argument("--results", required=True, help="results output directory")
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    vintage_dir = Path(args.vintages)
    results_dir = Path(args.results)
    results_dir.mkdir(parents=True, exist_ok=True)

    compacted = compact(vintage_dir, now)
    for path in compacted:
        print(f"compacted -> {path}")

    vintages = load_vintages(vintage_dir)
    model_forecasts = load_model_forecasts(Path("forecasts"))

    starts = [
        df["window_start"].min() for df in (vintages, model_forecasts) if not df.empty
    ]
    actuals = (
        fetch_actuals(min(starts).to_pydatetime(), now)
        if starts
        else pd.DataFrame(columns=["window_start", "actual"])
    )

    if vintages.empty:
        scored = pd.DataFrame()
        print("no vintages to score yet")
    else:
        scored = score(vintages, actuals, now)
        scored.to_parquet(results_dir / "prospective_scores.parquet", index=False)

    summary = summarize(scored, vintages, now)

    model_scored = (
        score_model(model_forecasts[model_forecasts["window_start"] < now], actuals)
        if not model_forecasts.empty
        else pd.DataFrame()
    )
    if not model_scored.empty:
        model_scored.to_parquet(
            results_dir / "prospective_model_scores.parquet", index=False
        )
    summary["model_forecasts"] = summarize_model(model_scored)
    out = results_dir / "prospective_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["neso_fw48h"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
