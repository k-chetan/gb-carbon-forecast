"""Evaluation page: sealed-test results, three labeled legs, live self-scoring."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from views import common

LEG_LABELS = {
    "leg1": (
        "Leg 1 · vs NESO stored forecast",
        "The archived series is revised until shortly before delivery, so it "
        "is context rather than a valid 24-48 h baseline.",
    ),
    "leg2": (
        "Leg 2 · vs community-archive vintages",
        "Operator vintages from the community archive. 2026-07 onward is "
        "scored at matched issue times; the 2023-24 months are context. "
        "No 2025 archive exists.",
    ),
    "leg3": (
        "Leg 3 · vs this project's own logged vintages",
        "Vintages logged hourly here since Nov 2026. The sample starts small "
        "and grows over time; it is re-scored before submission.",
    ),
}


def pending(text: str) -> None:
    st.markdown(
        f"<div style='border:1px dashed {common.BORDER}; border-radius:12px; "
        f"padding:14px 18px; color:{common.FAINT}; font-size:0.9rem'>{text}</div>",
        unsafe_allow_html=True,
    )


def show() -> None:
    sealed = common.load_json("results/sealed/sealed_2025.json")
    legs = common.load_json("results/legs/legs.json")
    live = common.load_json("results/prospective_summary.json")
    curves = common.load_parquet("results/sealed/horizon_curves.parquet")

    # --- horizon curves -----------------------------------------------------
    common.section_card(
        "Error by horizon",
        "MAE on the sealed 2025 test year · issue-time simulation, hourly issues",
    )
    if curves is not None:
        long = curves.melt(
            id_vars=["horizon_h", "n"], var_name="method", value_name="mae"
        )
        names = {
            "track_a": "Model A (lags+calendar)",
            "track_b": "Model B (+weather)",
            "persistence": "Persistence",
            "seasonal_naive_7d": "Seasonal naive (7d)",
            "neso_stored_leg1": "NESO stored (Leg 1, short-horizon)",
        }
        long["method"] = long["method"].map(names)
        chart = (
            alt.Chart(long.dropna())
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("horizon_h:Q", title="horizon (hours)"),
                y=alt.Y("mae:Q", title="MAE, gCO₂/kWh"),
                color=alt.Color(
                    "method:N",
                    title=None,
                    scale=alt.Scale(
                        domain=list(names.values()),
                        range=[
                            common.MODEL_BLUE,
                            common.ACCENT,
                            common.NESO_ORANGE,
                            common.FAINT,
                            common.INK,
                        ],
                    ),
                ),
            )
            .properties(height=320)
        )
        st.altair_chart(chart, width="stretch")
    else:
        pending(
            "Sealed 2025 results will appear here after the one-time evaluation run."
        )

    st.markdown("<br>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    # --- headline metrics ---------------------------------------------------
    with col_a:
        common.section_card("Headline metrics", "sealed 2025 unless marked live")
        if sealed:
            short = {
                "A_vs_persistence": "A vs persistence",
                "B_vs_persistence": "B vs persistence",
                "B_vs_A_weather_ablation": "B vs A (weather)",
                "A_vs_neso_stored_LEG1_not_like_for_like": "A vs stored †",
                "B_vs_neso_stored_LEG1_not_like_for_like": "B vs stored †",
            }
            rows = []
            for row in sealed.get("comparisons", []):
                if row["bucket"] != "overall":
                    continue
                rows.append(
                    {
                        "comparison": short.get(row["comparison"], row["comparison"]),
                        "model": row["mae_a"],
                        "reference": row["mae_b"],
                        "Δ%": row["delta_pct"],
                        "p (DM)": row["dm_p"],
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption(
                "† the stored series is near-final (Leg 1): context, "
                "not a like-for-like baseline."
            )
            cov = sealed["models"]["track_b"]["metrics"]["coverage_80"]
            st.markdown(f"**80% interval coverage (Track B):** {cov:.1%}")
        else:
            pending("Sealed metrics will appear after the evaluation run.")

    # --- legs ---------------------------------------------------------------
    with col_b:
        common.section_card("Operator comparison, three legs", "each labeled")
        for key, (title, caveat) in LEG_LABELS.items():
            st.markdown(f"**{title}**")
            st.markdown(
                f"<span style='color:{common.FAINT}; "
                f"font-size:0.82rem'>{caveat}</span>",
                unsafe_allow_html=True,
            )
            if key == "leg1" and sealed:
                leg1 = [
                    r
                    for r in sealed["comparisons"]
                    if "LEG1" in r["comparison"] and r["bucket"] == "overall"
                ]
                for r in leg1:
                    st.markdown(
                        f"- `{r['comparison'].split('_vs_')[0]}` {r['mae_a']} vs "
                        f"stored {r['mae_b']} gCO₂/kWh"
                    )
            elif key == "leg2" and legs:
                for comp in legs["leg2"]["comparisons"]:
                    rows = comp.get("rows", [])
                    overall = next((r for r in rows if r["bucket"] == "overall"), None)
                    if overall:
                        st.markdown(
                            f"- `{comp['model']}` {overall['mae_a']} vs vintage "
                            f"{overall['mae_b']} (n={overall['n']})"
                        )
            elif key == "leg3" and legs:
                leg3 = legs["leg3"]
                st.markdown(
                    f"- captures at last scoring: **{leg3['n_captures']}** "
                    f"({leg3.get('capture_span', ['—', '—'])[0]} →)"
                )
                for comp in leg3["comparisons"]:
                    rows = comp.get("rows", [])
                    overall = next((r for r in rows if r["bucket"] == "overall"), None)
                    if overall:
                        st.markdown(
                            f"- `{comp['model']}` {overall['mae_a']} vs vintage "
                            f"{overall['mae_b']} (n={overall['n']})"
                        )
            else:
                st.markdown(
                    f"<span style='color:{common.FAINT}; font-size:0.82rem'>"
                    "pending</span>",
                    unsafe_allow_html=True,
                )
            st.markdown("")

    # --- live self-scoring ---------------------------------------------------
    st.markdown("---")
    common.section_card(
        "Live self-scoring",
        "updated weekly by the scheduled scoring job",
    )
    if live:
        v = live["vintages"]
        neso_leg = live["neso_fw48h"]
        k1, k2, k3 = st.columns(3)
        k1.metric("Logged NESO captures", f"{v['total_captures']:,}")
        k2.metric("Matured windows scored", f"{neso_leg['scored_windows']:,}")
        k3.metric(
            "NESO fw48h MAE (all horizons)",
            "—" if neso_leg["overall_mae"] is None else f"{neso_leg['overall_mae']}",
        )
        if neso_leg["mae_by_bucket"]:
            st.dataframe(
                pd.DataFrame(
                    {
                        "bucket": list(neso_leg["mae_by_bucket"]),
                        "MAE": list(neso_leg["mae_by_bucket"].values()),
                        "n": [
                            neso_leg["n_by_bucket"][k]
                            for k in neso_leg["mae_by_bucket"]
                        ],
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        mf = live.get("model_forecasts")
        if mf and mf.get("scored_windows"):
            st.markdown("**This project's forecasts, matured so far**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Forecasts with matured windows", f"{mf['n_forecasts']:,}")
            m2.metric("Windows scored", f"{mf['scored_windows']:,}")
            m3.metric(
                "Model MAE (all horizons)",
                "—" if mf["overall_mae"] is None else f"{mf['overall_mae']}",
            )
            st.caption(
                "Same maturation protocol as the capture scoring above, but a "
                "different and still small sample, so the two MAE figures are "
                "not directly comparable yet."
            )
        st.caption(f"Last self-scoring run: {live['updated_utc']}")
    else:
        pending("The first weekly scoring run has not completed yet.")
