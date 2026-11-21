"""Assemble report data and figures from current artifacts.

Writes report/_data.json (everything report.typ reads) plus the result
figures under report/figures/. Missing artifacts become explicit "pending"
status flags rather than errors, so `make report` always compiles and simply
shows what has and has not matured — which is also how the pre-submission
refresh updates only the prospective sections.

Run: PYTHONPATH=src uv run python scripts/report_figures.py
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "report"
FIGS = OUT / "figures"

INK = "#1a201c"
MUTED = "#52514e"
ACCENT = "#135e43"
ORANGE = "#eb6834"
BLUE = "#2a78d6"
GRID = "#e1e0d9"

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": GRID,
        "axes.grid": True,
        "grid.color": GRID,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 11,
    }
)


def read_json(rel: str):
    path = ROOT / rel
    return json.loads(path.read_text()) if path.exists() else None


def save(fig, name: str) -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"fig: {name}")


def fig_horizon_curves() -> bool:
    path = ROOT / "results/sealed/horizon_curves.parquet"
    if not path.exists():
        return False
    curve = pd.read_parquet(path)
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    series = [
        ("track_b", "Track B (+weather)", ACCENT, "-"),
        ("track_a", "Track A (lags+calendar)", BLUE, "-"),
        ("persistence", "Persistence", ORANGE, "--"),
        ("seasonal_naive_7d", "Seasonal naive (7 d)", MUTED, "--"),
        ("neso_stored_leg1", "NESO stored (Leg 1)", INK, ":"),
    ]
    for col, label, color, style in series:
        if col in curve:
            ax.plot(
                curve["horizon_h"], curve[col], style, color=color, label=label, lw=1.7
            )
    ax.set_xlabel("horizon (hours)")
    ax.set_ylabel("MAE (gCO₂/kWh)")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    save(fig, "horizon_curves.png")
    return True


def fig_ablation() -> bool:
    ablation = read_json("results/ablation.json")
    if not ablation:
        return False
    rows = [r for r in ablation["comparisons"] if r["bucket"] != "overall"]
    buckets = [r["bucket"].replace("_", "–").replace("h", " h") for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = range(len(rows))
    width = 0.38
    ax.bar(
        [i - width / 2 for i in x],
        [r["mae_a"] for r in rows],
        width,
        color=BLUE,
        label="Track A (lags+calendar)",
    )
    ax.bar(
        [i + width / 2 for i in x],
        [r["mae_b"] for r in rows],
        width,
        color=ACCENT,
        label="Track B (+weather)",
    )
    for i, r in enumerate(rows):
        ax.text(
            i + width / 2,
            r["mae_b"] + 0.6,
            f"{r['delta_pct']:+.0f}%",
            ha="center",
            fontsize=8,
            color=INK,
        )
    ax.set_xticks(list(x), buckets)
    ax.set_ylabel("validation MAE (gCO₂/kWh)")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "ablation.png")
    return True


def fig_calibration() -> bool:
    sealed = read_json("results/sealed/sealed_2025.json")
    if not sealed:
        return False
    fig, ax = plt.subplots(figsize=(5.6, 3.0))
    tracks = {"track_a": ("Track A", BLUE), "track_b": ("Track B", ACCENT)}
    buckets = ["01_06h", "07_24h", "25_48h"]
    for key, (label, color) in tracks.items():
        by_bucket = sealed["models"][key]["metrics"]["by_bucket"]
        values = [by_bucket[b]["coverage_80"] for b in buckets if b in by_bucket]
        ax.plot(range(len(values)), values, "o-", color=color, label=label)
    ax.axhline(0.8, color=INK, lw=1, ls="--")
    ax.text(0.02, 0.805, "nominal 80%", fontsize=8, color=MUTED)
    ax.set_xticks(range(3), ["1–6 h", "7–24 h", "25–48 h"])
    ax.set_ylabel("80% interval coverage")
    ax.set_ylim(0.5, 1.0)
    ax.legend(frameon=False, fontsize=8)
    save(fig, "calibration.png")
    return True


def fig_fan_example() -> bool:
    payload = read_json("forecasts/latest.json")
    if not payload:
        return False
    df = pd.DataFrame(payload["windows"])
    df["start"] = pd.to_datetime(df["start"], utc=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.fill_between(
        df["start"], df["p10"], df["p90"], color=BLUE, alpha=0.18, label="80% band"
    )
    ax.plot(df["start"], df["p50"], color=BLUE, lw=1.8, label="p50")
    ax.set_ylabel("gCO₂/kWh")
    ax.set_title(f"Forecast issued {payload['issued_utc']}")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "fan_example.png")
    return True


def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.axis("off")

    def box(x, y, w, h, text, color=ACCENT, fc="#f4f5f1"):
        ax.add_patch(
            plt.Rectangle(
                (x, y), w, h, fill=True, facecolor=fc, edgecolor=color, lw=1.4
            )
        )
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5)

    def arrow(x1, y1, x2, y2):
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.2),
        )

    box(0.02, 0.62, 0.20, 0.25, "NESO Carbon\nIntensity API", color=ORANGE)
    box(0.02, 0.12, 0.20, 0.25, "Open-Meteo\nforecast archives", color=ORANGE)
    box(0.33, 0.70, 0.26, 0.22, "vintage-logger\n(hourly :17)")
    box(0.33, 0.40, 0.26, 0.22, "nightly-forecast\n(03:07 UTC)")
    box(0.33, 0.10, 0.26, 0.22, "self-scoring (weekly)\nwatchdog + keepalive (daily)")
    box(
        0.68,
        0.55,
        0.30,
        0.30,
        "repository artifacts\nvintages/ · forecasts/ · results/",
        color=INK,
        fc="white",
    )
    box(
        0.68,
        0.10,
        0.30,
        0.26,
        "Streamlit app + JSON\n(read-only consumers)",
        color=BLUE,
    )
    arrow(0.22, 0.76, 0.33, 0.80)
    arrow(0.22, 0.70, 0.33, 0.52)
    arrow(0.22, 0.24, 0.33, 0.48)
    arrow(0.22, 0.20, 0.33, 0.20)
    arrow(0.59, 0.80, 0.68, 0.73)
    arrow(0.59, 0.50, 0.68, 0.66)
    arrow(0.59, 0.20, 0.68, 0.60)
    arrow(0.83, 0.55, 0.83, 0.36)
    save(fig, "architecture.png")


def main() -> int:
    FIGS.mkdir(parents=True, exist_ok=True)
    for png in (ROOT / "results/eda").glob("*.png"):
        shutil.copy(png, FIGS / f"eda_{png.name}")

    status = {
        "horizon_curves": fig_horizon_curves(),
        "ablation": fig_ablation(),
        "calibration": fig_calibration(),
        "fan_example": fig_fan_example(),
    }
    fig_architecture()

    data = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "status": status,
        "anchors": read_json("results/anchor_reproduction.json"),
        "sealed": read_json("results/sealed/sealed_2025.json"),
        "ablation": read_json("results/ablation.json"),
        "legs": read_json("results/legs/legs.json"),
        "live": read_json("results/prospective_summary.json"),
        "weather_coverage": read_json("data/raw/weather_coverage.json"),
        "manifest": read_json("data/raw/manifest.json"),
        "eda": read_json("results/eda/summary_stats.json"),
        "vintage_audit": read_json("data/external/community_vintages_audit.json"),
        "app_url": "https://gb-carbon-forecast-go.streamlit.app/",
        "repo_url": "https://github.com/k-chetan/gb-carbon-forecast",
    }
    (OUT / "_data.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"data -> {OUT / '_data.json'}  status={status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
