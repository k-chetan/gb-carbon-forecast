"""Shared palette, loaders and chart helpers for the app views."""

from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ACCENT = "#135e43"
INK = "#1a201c"
MUTED = "#52514e"
FAINT = "#898781"
CARD = "#fcfcfb"
BORDER = "#e1e0d9"
MODEL_BLUE = "#2a78d6"
NESO_ORANGE = "#eb6834"

REPO_URL = "https://github.com/k-chetan/gb-carbon-forecast"
ROOT = Path(__file__).resolve().parent.parent


@st.cache_data(ttl=900, show_spinner=False)
def load_json(rel_path: str) -> dict | None:
    path = ROOT / rel_path
    if not path.exists():
        return None
    return json.loads(path.read_text())


@st.cache_data(ttl=900, show_spinner=False)
def load_parquet(rel_path: str) -> pd.DataFrame | None:
    path = ROOT / rel_path
    if not path.exists():
        return None
    return pd.read_parquet(path)


def latest_forecast() -> pd.DataFrame | None:
    payload = load_json("forecasts/latest.json")
    if not payload:
        return None
    df = pd.DataFrame(payload["windows"])
    df["start"] = pd.to_datetime(df["start"], utc=True)
    df["end"] = pd.to_datetime(df["end"], utc=True)
    df.attrs["issued_utc"] = payload["issued_utc"]
    df.attrs["model"] = payload["model"]
    return df


def section_card(title: str, subtitle: str = "") -> None:
    st.markdown(f"#### {title}")
    if subtitle:
        st.markdown(
            f"<span style='color:{FAINT}; font-size: 0.85rem'>{subtitle}</span>",
            unsafe_allow_html=True,
        )


def legend_chip(color: str, label: str, dashed: bool = False) -> str:
    style = (
        f"border-top: 3px dashed {color}; width: 16px; height: 0;"
        if dashed
        else f"background: {color}; width: 16px; height: 3px; border-radius: 2px;"
    )
    return (
        f"<span style='display:inline-flex; align-items:center; gap:6px; "
        f"margin-right:14px; font-size:0.8rem; color:{MUTED}'>"
        f"<span style='display:inline-block; {style}'></span>{label}</span>"
    )


def time_axis() -> alt.X:
    return alt.X("window_start:T", title=None, axis=alt.Axis(format="%a %H:%M"))
