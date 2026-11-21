"""Exploratory analysis of the national half-hourly history.

Produces the report's EDA figures and a stats JSON under results/eda/:
long-run trend, seasonal day-profiles, month-by-hour structure, yearly
distribution shift, missing-actual gaps, and the error-relevant
autocorrelation structure that motivates day-block inference.

Run: PYTHONPATH=src uv run python scripts/eda.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HISTORY = Path("data/raw/neso_api_history.parquet")
OUT = Path("results/eda")

INK = "#1a201c"
MUTED = "#52514e"
ACCENT = "#135e43"
ORANGE = "#eb6834"
BLUE = "#2a78d6"
GRID = "#e1e0d9"
CARD = "#fcfcfb"

plt.rcParams.update(
    {
        "figure.facecolor": CARD,
        "axes.facecolor": CARD,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / name}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(HISTORY).sort_values("window_start")
    df["year"] = df["window_start"].dt.year
    df["month"] = df["window_start"].dt.month
    df["hour"] = df["window_start"].dt.hour + df["window_start"].dt.minute / 60

    # --- annual stats + distribution shift ---------------------------------
    annual = (
        df.groupby("year")["actual"]
        .agg(["mean", "std", "min", "max", "count"])
        .round(1)
    )
    quantiles = (
        df.groupby("year")["actual"].quantile([0.1, 0.5, 0.9]).unstack().round(1)
    )
    annual = annual.join(quantiles.rename(columns={0.1: "p10", 0.5: "p50", 0.9: "p90"}))
    missing = df.groupby("year")["actual"].apply(lambda s: int(s.isna().sum()))
    annual["missing_actuals"] = missing

    # --- fig 1: monthly trend ----------------------------------------------
    monthly = df.set_index("window_start")["actual"].resample("MS").mean()
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(monthly.index, monthly.values, color=ACCENT, lw=1.6)
    ax.plot(
        monthly.index,
        monthly.rolling(12, center=True).mean().values,
        color=INK,
        lw=2.2,
        label="12-month rolling mean",
    )
    ax.set_title("GB carbon intensity, monthly mean")
    ax.set_ylabel("gCO₂/kWh")
    ax.legend(frameon=False)
    save(fig, "trend_monthly.png")

    # --- fig 2: seasonal day profiles --------------------------------------
    seasons = {
        "Winter (DJF)": (12, 1, 2),
        "Spring (MAM)": (3, 4, 5),
        "Summer (JJA)": (6, 7, 8),
        "Autumn (SON)": (9, 10, 11),
    }
    fig, ax = plt.subplots(figsize=(9, 4))
    palette = [INK, BLUE, ORANGE, ACCENT]
    for (label, months), color in zip(seasons.items(), palette, strict=True):
        profile = df[df["month"].isin(months)].groupby("hour")["actual"].mean()
        ax.plot(profile.index, profile.values, label=label, color=color, lw=1.8)
    ax.set_title("Average day profile by season (2017-2026)")
    ax.set_xlabel("hour of day (UTC)")
    ax.set_ylabel("gCO₂/kWh")
    ax.legend(frameon=False, ncol=2)
    save(fig, "seasonal_profiles.png")

    # --- fig 3: yearly distributions ----------------------------------------
    years = [y for y in range(2018, 2027) if y in set(df["year"])]
    data = [df.loc[df["year"] == y, "actual"].dropna() for y in years]
    fig, ax = plt.subplots(figsize=(9, 4))
    box = ax.boxplot(
        data, tick_labels=[str(y) for y in years], showfliers=False, patch_artist=True
    )
    for patch in box["boxes"]:
        patch.set_facecolor(ACCENT)
        patch.set_alpha(0.25)
    for med in box["medians"]:
        med.set_color(INK)
    ax.set_title("Distribution shift by year")
    ax.set_ylabel("gCO₂/kWh")
    save(fig, "yearly_distributions.png")

    # --- fig 4: gaps ---------------------------------------------------------
    gaps = (
        df.set_index("window_start")["actual"].isna().resample("MS").sum().astype(int)
    )
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.bar(gaps.index, gaps.values, width=20, color=ORANGE)
    ax.set_title("Missing published actuals per month")
    ax.set_ylabel("half-hours")
    save(fig, "missing_actuals.png")

    # --- fig 5: autocorrelation ---------------------------------------------
    series = df.set_index("window_start")["actual"].asfreq("30min").interpolate(limit=4)
    lags = list(range(1, 337))
    acf = [series.autocorr(lag) for lag in lags]
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.plot([lag / 2 for lag in lags], acf, color=BLUE, lw=1.5)
    for mark, label in ((24, "24 h"), (48, "48 h"), (168, "7 d")):
        ax.axvline(mark, color=GRID, lw=1)
        ax.text(mark, ax.get_ylim()[1], f" {label}", color=MUTED, fontsize=9, va="top")
    ax.set_title("Autocorrelation of half-hourly intensity")
    ax.set_xlabel("lag (hours)")
    ax.set_ylabel("ACF")
    save(fig, "autocorrelation.png")

    # --- stats json ----------------------------------------------------------
    payload = {
        "computed_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "rows": int(len(df)),
        "span": [str(df["window_start"].min()), str(df["window_start"].max())],
        "missing_actuals_total": int(df["actual"].isna().sum()),
        "annual": json.loads(annual.to_json(orient="index")),
        "acf": {"24h": round(float(acf[47]), 3), "7d": round(float(acf[335]), 3)},
    }
    (OUT / "summary_stats.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {"annual_means": {y: payload["annual"][str(y)]["mean"] for y in years}},
            indent=2,
        )
    )
    print(f"acf: 24h={payload['acf']['24h']} 7d={payload['acf']['7d']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
