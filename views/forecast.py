"""Forecast page: 48 h fan chart, national-first, operator context."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gbcarbon import neso  # noqa: E402
from views import common  # noqa: E402

REGIONS = {
    "National": None,
    "North Scotland": 1,
    "South Scotland": 2,
    "North West England": 3,
    "North East England": 4,
    "Yorkshire": 5,
    "North Wales & Merseyside": 6,
    "South Wales": 7,
    "West Midlands": 8,
    "East Midlands": 9,
    "East England": 10,
    "South West England": 11,
    "South England": 12,
    "London": 13,
    "South East England": 14,
}


@st.cache_data(ttl=1800, show_spinner=False)
def operator_fw48h(region_id: int | None) -> tuple[str, pd.DataFrame]:
    issued = neso.utc_now_minute()
    if region_id is None:
        rows = neso.parse_windows(neso.fw48h(issued))
    else:
        data = neso._get(f"/regional/intensity/{issued}/fw48h/regionid/{region_id}")
        rows = [
            (item["from"], item["to"], item["intensity"].get("forecast"))
            for item in data["data"]["data"]
        ]
    df = pd.DataFrame(rows, columns=["window_start", "window_end", "forecast"])
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    return issued, df


@st.cache_data(ttl=900, show_spinner=False)
def recent_actuals(hours: int = 12) -> pd.DataFrame:
    now = datetime.now(UTC)
    start = (now - pd.Timedelta(hours=hours)).strftime(neso.TS_FMT)
    data = neso.intensity_range(start, now.strftime(neso.TS_FMT))
    df = pd.DataFrame(
        [(d["from"], d["intensity"].get("actual")) for d in data],
        columns=["window_start", "actual"],
    )
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    return df.dropna()


def cleanest_window(df: pd.DataFrame, col: str, hours: int = 3) -> str:
    k = hours * 2
    if len(df) < k or df[col].isna().all():
        return "—"
    roll = df[col].rolling(k).mean()
    end_idx = int(roll.idxmin())
    start = df.loc[end_idx - k + 1, "window_start"]
    end = df.loc[end_idx, "window_start"] + pd.Timedelta(minutes=30)
    return f"{start:%a %H:%M}–{end:%H:%M} UTC · ≈{roll.min():.0f} gCO₂/kWh"


def show() -> None:
    c1, c2 = st.columns([1.2, 2.8])
    with c1:
        region = st.selectbox(
            "Region",
            list(REGIONS),
            label_visibility="collapsed",
            help="Regional values are NESO's own forecasts. There are no "
            "published regional actuals, so these are display-only.",
        )
    region_id = REGIONS[region]

    model = common.latest_forecast()
    now = pd.Timestamp.now(tz="UTC")

    try:
        issued_op, op = operator_fw48h(region_id)
        actuals = recent_actuals() if region_id is None else pd.DataFrame()
    except Exception as err:
        st.error(f"NESO API unreachable ({err}).")
        return

    if region_id is None:
        if model is not None:
            fan_src = model.rename(columns={"start": "window_start"})
            clean = cleanest_window(fan_src, "p50")
            src_label = "model median"
        else:
            clean = cleanest_window(op.reset_index(drop=True), "forecast")
            src_label = "operator forecast"
        with c2:
            st.markdown(
                f"<div style='text-align:right; padding-top:0.4rem'>"
                f"<span class='pill'>cleanest 3 h ahead: {clean} "
                f"({src_label})</span></div>",
                unsafe_allow_html=True,
            )

    layers = []
    if region_id is None and model is not None:
        fan = model.rename(columns={"start": "window_start"})
        band = (
            alt.Chart(fan)
            .mark_area(color=common.MODEL_BLUE, opacity=0.16)
            .encode(
                common.time_axis(),
                y=alt.Y("p10:Q", title="gCO₂/kWh", scale=alt.Scale(zero=False)),
                y2="p90:Q",
            )
        )
        median = (
            alt.Chart(fan)
            .mark_line(color=common.MODEL_BLUE, strokeWidth=2)
            .encode(
                common.time_axis(),
                y="p50:Q",
                tooltip=[
                    alt.Tooltip("window_start:T", title="window", format="%a %H:%M"),
                    alt.Tooltip("p10:Q", title="p10"),
                    alt.Tooltip("p50:Q", title="p50"),
                    alt.Tooltip("p90:Q", title="p90"),
                ],
            )
        )
        layers += [band, median]

    layers.append(
        alt.Chart(op)
        .mark_line(color=common.NESO_ORANGE, strokeWidth=2, strokeDash=[6, 4])
        .encode(
            common.time_axis(),
            y=alt.Y("forecast:Q", title="gCO₂/kWh", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("window_start:T", title="window", format="%a %H:%M"),
                alt.Tooltip("forecast:Q", title="NESO forecast"),
            ],
        )
    )
    if len(actuals):
        layers.append(
            alt.Chart(actuals)
            .mark_line(color=common.INK, strokeWidth=2)
            .encode(common.time_axis(), y="actual:Q")
        )
    layers.append(
        alt.Chart(pd.DataFrame({"t": [now]}))
        .mark_rule(color=common.FAINT, strokeDash=[3, 3])
        .encode(x="t:T")
    )

    title = f"Carbon intensity, next 48 h · {region}"
    if region_id is not None:
        title += " · operator forecast, not evaluated"
    common.section_card(title)
    st.altair_chart(alt.layer(*layers).properties(height=340), width="stretch")

    chips = []
    if region_id is None and model is not None:
        chips.append(common.legend_chip(common.MODEL_BLUE, "Model median (p50)"))
        chips.append(
            common.legend_chip(common.MODEL_BLUE, "80% band").replace(
                "height:3px", "height:10px; opacity:0.25"
            )
        )
    chips.append(common.legend_chip(common.NESO_ORANGE, "NESO forecast", dashed=True))
    if len(actuals):
        chips.append(common.legend_chip(common.INK, "Actual (last 12 h)"))
    st.markdown("".join(chips), unsafe_allow_html=True)

    if region_id is None and model is not None:
        st.caption(
            f"Model forecast issued {model.attrs['issued_utc']} "
            f"({model.attrs['model']}). NESO's forward forecast (dashed) issued "
            f"{issued_op}, shown for comparison. Values are attributed emissions "
            "under NESO's methodology, not metered or marginal."
        )
    elif region_id is None:
        st.caption(
            f"NESO forward forecast issued {issued_op}. The model forecast will "
            "appear here once the nightly job starts publishing."
        )
    else:
        st.caption(
            f"Regional series are NESO's own forecasts (issued {issued_op}). "
            "There are no published regional actuals, so these are display-only "
            "and not scored."
        )
