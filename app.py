import sys
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from gbcarbon import neso  # noqa: E402

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

st.set_page_config(
    page_title="GB Carbon Intensity Forecast",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REPO_URL = "https://github.com/k-chetan/gb-carbon-forecast"

ACCENT = "#135e43"
INK = "#1a201c"
MUTED = "#52514e"
FAINT = "#898781"
CARD = "#fcfcfb"
BORDER = "#e1e0d9"
NESO_ORANGE = "#eb6834"

# ==============================================================================
# 2. STYLING (CSS)
# ==============================================================================

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

    html, body, [class*="css"] {{ font-family: 'IBM Plex Sans', sans-serif; }}
    h1, h2, h3 {{ font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.02em; }}

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    [data-testid="stToolbar"] {{visibility: hidden;}}
    [data-testid="stDecoration"] {{display: none;}}

    .block-container {{
        padding-top: 2.2rem;
        padding-bottom: 4rem;
        max-width: 1160px;
    }}

    [data-testid="stMetric"] {{
        background-color: {CARD};
        border: 1px solid {BORDER};
        padding: 16px 20px;
        border-radius: 14px;
    }}

    .pill {{
        display: inline-block;
        border: 1px solid {BORDER};
        background: #ffffff;
        color: {MUTED};
        border-radius: 999px;
        padding: 6px 14px;
        font-size: 0.85rem;
        white-space: nowrap;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 3. DATA (NESO API, cached)
# ==============================================================================


@st.cache_data(ttl=900, show_spinner=False)
def load_current() -> dict:
    return neso.current()


@st.cache_data(ttl=1800, show_spinner=False)
def load_fw48h() -> tuple[str, pd.DataFrame]:
    issued = neso.utc_now_minute()
    rows = neso.parse_windows(neso.fw48h(issued))
    df = pd.DataFrame(rows, columns=["window_start", "window_end", "forecast"])
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df["window_end"] = pd.to_datetime(df["window_end"], utc=True)
    return issued, df


def cleanest_window(df: pd.DataFrame, hours: int = 3) -> tuple | None:
    k = hours * 2  # half-hour windows
    if len(df) < k or df["forecast"].isna().all():
        return None
    roll = df["forecast"].rolling(k).mean()
    end_idx = int(roll.idxmin())
    start = df.loc[end_idx - k + 1, "window_start"]
    end = df.loc[end_idx, "window_end"]
    return start, end, float(roll.min())


# ==============================================================================
# 4. HEADER
# ==============================================================================

c_title, c_status = st.columns([3, 1])
with c_title:
    st.title("GB Carbon Intensity Forecast")
    st.markdown(
        f"<span style='color:{MUTED}'>Probabilistic 48 h forecasts for the national "
        "grid, benchmarked against the operator's own.</span>",
        unsafe_allow_html=True,
    )
with c_status:
    st.markdown(
        "<div style='text-align:right; padding-top: 1.4rem'>"
        "<span class='pill'>model in training · vintage logger live</span></div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

# ==============================================================================
# 5. LIVE STATUS + OPERATOR FORWARD VIEW
# ==============================================================================

try:
    now_window = load_current()
    issued_at, fw = load_fw48h()
except Exception as err:  # pragma: no cover - network path
    st.error(f"NESO API unreachable right now ({err}). Nothing cached to show.")
    st.stop()

kpi1, kpi2, kpi3 = st.columns(3)

intensity = now_window.get("intensity", {})
kpi1.metric(
    "Current intensity",
    f"{intensity.get('actual') or intensity.get('forecast', '—')} gCO₂/kWh",
    delta=str(intensity.get("index", "")).title(),
    delta_color="off",
)

window = cleanest_window(fw)
if window:
    start, end, level = window
    kpi2.metric(
        "Cleanest 3 h window ahead",
        f"{start:%a %H:%M} – {end:%H:%M} UTC",
        delta=f"≈ {level:.0f} gCO₂/kWh",
        delta_color="off",
    )
else:
    kpi2.metric("Cleanest 3 h window ahead", "—")

kpi3.metric(
    "48 h outlook (operator)",
    f"{fw['forecast'].min():.0f} – {fw['forecast'].max():.0f} gCO₂/kWh",
    delta="min – max of forward windows",
    delta_color="off",
)

st.markdown("<br>", unsafe_allow_html=True)

st.markdown("#### Next 48 hours · National")

now_utc = datetime.now(UTC)
base = alt.Chart(fw).encode(
    x=alt.X("window_start:T", title=None, axis=alt.Axis(format="%a %H:%M"))
)
line = base.mark_line(color=NESO_ORANGE, strokeWidth=2, strokeDash=[6, 4]).encode(
    y=alt.Y("forecast:Q", title="gCO₂/kWh", scale=alt.Scale(zero=False)),
    tooltip=[
        alt.Tooltip("window_start:T", title="window", format="%a %d %b %H:%M"),
        alt.Tooltip("forecast:Q", title="gCO₂/kWh"),
    ],
)
now_rule = (
    alt.Chart(pd.DataFrame({"t": [now_utc]}))
    .mark_rule(color=FAINT, strokeDash=[3, 3])
    .encode(x="t:T")
)
st.altair_chart((line + now_rule).properties(height=320), use_container_width=True)

st.caption(
    f"Dashed orange: NESO's own forward forecast, issued {issued_at} — shown for "
    "context while the model comes online. Operator forecasts are displayed, not "
    "used to train or score the model."
)

# ==============================================================================
# 6. MODEL PLACEHOLDER
# ==============================================================================

st.markdown("---")
with st.container():
    st.markdown("#### Model forecast — coming online")
    st.markdown(
        f"<span style='color:{MUTED}'>The probabilistic model (p10 / p50 / p90 fan "
        "chart) appears here once trained and evaluated on the sealed 2025 test "
        "year. Meanwhile an hourly job is already logging NESO's forward forecasts "
        "as issued, so true 48-hour operator comparisons accumulate from day "
        "one.</span>",
        unsafe_allow_html=True,
    )

# ==============================================================================
# 7. FOOTER
# ==============================================================================

st.markdown("---")
st.caption(
    "Data: [NESO Carbon Intensity API](https://carbonintensity.org.uk/) "
    "(CC BY 4.0) · Weather: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0) · "
    f"Code: [MIT]({REPO_URL}) · Independent research project, not affiliated "
    "with NESO."
)
