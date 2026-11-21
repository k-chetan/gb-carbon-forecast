import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from gbcarbon import neso  # noqa: E402
from views import common, evaluation, forecast, model_card  # noqa: E402

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

st.set_page_config(
    page_title="GB Carbon Intensity Forecast",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "current_page" not in st.session_state:
    st.session_state.current_page = "Forecast"

# ==============================================================================
# 2. STYLING (CSS)
# ==============================================================================

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

    html, body, [class*="css"] {{ font-family: 'IBM Plex Sans', sans-serif; }}
    h1, h2, h3, h4 {{
        font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.02em;
    }}

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    [data-testid="stToolbar"] {{visibility: hidden;}}
    [data-testid="stDecoration"] {{display: none;}}

    .block-container {{
        padding-top: 2.0rem;
        padding-bottom: 4rem;
        max-width: 1160px;
    }}

    [data-testid="stMetric"] {{
        background-color: {common.CARD};
        border: 1px solid {common.BORDER};
        padding: 16px 20px;
        border-radius: 14px;
    }}

    div.stButton > button {{
        border-radius: 999px;
        border: 1px solid {common.BORDER};
        font-weight: 500;
    }}

    .pill {{
        display: inline-block;
        border: 1px solid {common.BORDER};
        background: #ffffff;
        color: {common.MUTED};
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
# 3. HEADER & NAVIGATION
# ==============================================================================


def status_pill() -> str:
    live = common.load_json("results/prospective_summary.json")
    model = common.load_json("forecasts/latest.json")
    left = (
        f"vintage log · {live['vintages']['total_captures']:,} captures"
        if live
        else "vintage logger live"
    )
    right = (
        f"model forecast issued {model['issued_utc']}" if model else "model in training"
    )
    return f"{left} · {right}"


c_brand, c_status = st.columns([2.4, 1.6])
with c_brand:
    st.markdown(
        f"<div style='display:flex; align-items:center; gap:10px'>"
        f"<span style='width:12px; height:12px; border-radius:50%; "
        f"background:{common.ACCENT}; display:inline-block'></span>"
        f"<span style='font-family: Space Grotesk, sans-serif; font-weight:600; "
        f"font-size:1.55rem'>GB Carbon Intensity Forecast</span></div>",
        unsafe_allow_html=True,
    )
with c_status:
    st.markdown(
        f"<div style='text-align:right; padding-top:0.35rem'>"
        f"<span class='pill'>{status_pill()}</span></div>",
        unsafe_allow_html=True,
    )

nav_cols = st.columns([1, 1, 1, 2])
PAGES = {"Forecast": forecast, "Evaluation": evaluation, "Model card": model_card}
for col, name in zip(nav_cols, PAGES, strict=False):
    with col:
        if st.button(
            name,
            type="primary" if st.session_state.current_page == name else "secondary",
            width="stretch",
        ):
            st.session_state.current_page = name
            st.rerun()

st.markdown("---")

# ==============================================================================
# 4. LIVE KPI ROW (national, shown on every page)
# ==============================================================================

try:
    now_window = neso.current()
    intensity = now_window.get("intensity", {})
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(
        "Current intensity",
        f"{intensity.get('actual') or intensity.get('forecast', '—')} gCO₂/kWh",
        delta=str(intensity.get("index", "")).title(),
        delta_color="off",
    )
    window = now_window.get("to", "")
    kpi2.metric("Settlement window ends", window.replace("T", " ").replace("Z", " UTC"))
    model_live = common.load_json("forecasts/latest.json")
    kpi3.metric(
        "Served model",
        model_live["model"].split("_")[0] if model_live else "in training",
        delta="post-evaluation refit" if model_live else "sealed eval first",
        delta_color="off",
    )
except Exception:
    st.warning("NESO API unreachable right now; live status hidden.")

st.markdown("<br>", unsafe_allow_html=True)

# ==============================================================================
# 5. VIEW CONTROLLER + FOOTER
# ==============================================================================

PAGES[st.session_state.current_page].show()

st.markdown("---")
st.caption(
    "Data: [NESO Carbon Intensity API](https://carbonintensity.org.uk/) "
    "(CC BY 4.0) · Weather: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0) · "
    "Vintage archive: [nmpowell/carbon-intensity-forecast-tracking]"
    "(https://github.com/nmpowell/carbon-intensity-forecast-tracking) (MIT) · "
    f"Code: [MIT]({common.REPO_URL}) · Independent research project, not "
    "affiliated with NESO."
)
