"""Cross-check the API-pulled national history against the data-portal bulk CSV.

Compares row counts, coverage spans, missing-value counts and value agreement
on the overlap, then records both artifacts in the raw-data manifest. Any
disagreement beyond rounding is printed for investigation, not hidden.

Run: PYTHONPATH=src uv run python scripts/cross_check_history.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")

from gbcarbon import provenance  # noqa: E402

RAW = Path("data/raw")
API_PARQUET = RAW / "neso_api_history.parquet"
PORTAL_CSV = RAW / "neso_portal_national.csv"


def load_portal() -> pd.DataFrame:
    df = pd.read_csv(PORTAL_CSV)
    # normalize column names across portal schema variants
    cols = {c.lower().strip(): c for c in df.columns}
    start_col = next(
        cols[k] for k in cols if "datetime" in k or "from" in k or "start" in k
    )
    rename = {start_col: "window_start"}
    for k, original in cols.items():
        if "forecast" in k:
            rename[original] = "forecast_portal"
        elif "actual" in k:
            rename[original] = "actual_portal"
    df = df.rename(columns=rename)
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    keep = [c for c in ("window_start", "forecast_portal", "actual_portal") if c in df]
    return df[keep].drop_duplicates(subset=["window_start"]).sort_values("window_start")


def main() -> int:
    api = pd.read_parquet(API_PARQUET)
    portal = load_portal()

    print(
        f"api rows:    {len(api)}  "
        f"span {api['window_start'].min()} .. {api['window_start'].max()}"
    )
    print(
        f"portal rows: {len(portal)}  "
        f"span {portal['window_start'].min()} .. {portal['window_start'].max()}"
    )
    print(f"api missing actuals:    {int(api['actual'].isna().sum())}")
    print(f"api missing forecasts:  {int(api['forecast'].isna().sum())}")
    if "actual_portal" in portal:
        print(f"portal missing actuals: {int(portal['actual_portal'].isna().sum())}")

    merged = api.merge(portal, on="window_start", how="inner")
    print(f"overlap rows: {len(merged)}")
    for api_col, portal_col in (
        ("actual", "actual_portal"),
        ("forecast", "forecast_portal"),
    ):
        if portal_col not in merged:
            continue
        both = merged.dropna(subset=[api_col, portal_col])
        diff = (both[api_col] - both[portal_col]).abs()
        print(
            f"{api_col}: n={len(both)} "
            f"exact-match={float((diff == 0).mean()):.4f} "
            f"mean-abs-diff={float(diff.mean()):.4f} "
            f"max-abs-diff={float(diff.max()):.1f}"
        )

    provenance.record(
        RAW / "manifest.json",
        "neso_portal_national",
        url="https://api.neso.energy/dataset/f406810a-1a36-48d2-b542-1dfb1348096e/resource/0e5fde43-2de7-4fb4-833d-c7bca3b658b0/download/gb_carbon_intensity.csv",
        file=PORTAL_CSV.name,
        rows=int(len(portal)),
        sha256=provenance.sha256_file(PORTAL_CSV),
        coverage_start=str(portal["window_start"].min()),
        coverage_end=str(portal["window_start"].max()),
        license="CC BY 4.0 (NESO data portal)",
        role="cross-check of neso_api_history on the overlap",
    )
    print("manifest updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
