"""Model card: data, protocol, assumptions, limitations, split, reproduction."""

from __future__ import annotations

import streamlit as st

from views import common


def show() -> None:
    deployed = common.load_json("models/deployed/run.json")
    sealed = common.load_json("results/sealed/sealed_2025.json")

    common.section_card("Model card")

    st.markdown(
        """
**Task.** Probabilistic 48-hour forecasts of GB national grid carbon intensity
(gCO₂/kWh), issued as p10/p50/p90 per half-hour window.

**Models.** Gradient-boosted quantile regression (LightGBM), horizon-as-feature
over 96 half-hour horizons, with split-conformal (CQR) interval calibration per
horizon bucket. Track A uses lag and calendar features on the full history;
Track B adds archived weather-forecast vintages on their covered window.
"""
    )

    split_a = sealed["models"]["track_a"]["run"] if sealed else "pending"
    split_b = sealed["models"]["track_b"]["run"] if sealed else "pending"
    deployed_id = deployed["config"]["run_id"] if deployed else "pending"
    st.markdown(
        f"""
**Evaluated vs deployed.** Report numbers come from models trained strictly
before the sealed year (`{split_a}`, `{split_b}`); the app serves a
post-evaluation refit on all data through the present (`{deployed_id}`).
The two are never conflated.
"""
    )

    st.markdown(
        """
**Protocol.**
- Issue-time simulation throughout: a forecast uses only information available
  at its issue time, enforced in the feature builder and covered by tests that
  poison the future and assert bit-identical features.
- Sealed test: calendar 2025, scored exactly once; development used rolling
  validation windows inside the training years only.
- Weather enters as *forecasts as issued* (previous-day model runs: day-1 for
  horizons ≤ 24 h, day-2 beyond), at train and serve time alike — never
  observations, never reanalysis.
- Significance via day-block moving bootstrap and HAC Diebold-Mariano; iid
  tests are invalid on half-hourly errors.

**Data and licenses.**
- [NESO Carbon Intensity API](https://carbonintensity.org.uk/) — CC BY 4.0;
  national history cross-checked against the data-portal CSV (99.96% exact
  agreement on actuals).
- [Open-Meteo](https://open-meteo.com/) — CC BY 4.0, non-commercial tier;
  per-variable archive coverage verified and recorded in the manifest.
- [Community vintage archive](https://github.com/nmpowell/carbon-intensity-forecast-tracking)
  — MIT (Nick Powell); months audited individually, no 2025 coverage.

**Assumptions and limitations.**
- Values are *attributed* emissions under NESO's stated methodology — not
  metered, not marginal; shifting load by this signal is a modelling claim.
- Scoring is national only: no published regional actuals exist, so regional
  series are display-only operator forecasts.
- True weather vintages begin 2024-03, so the weather ablation window is thin
  and powered accordingly.
- Missed vintage captures are permanent gaps (recorded, never backfilled);
  published actuals can be revised after the fact.

**Reproduce.**
```bash
git clone https://github.com/k-chetan/gb-carbon-forecast && cd gb-carbon-forecast
make setup && make test     # environment from the lockfile, full test suite
make report                 # rebuild the report from current artifacts
```
"""
    )
    st.caption(
        f"Code MIT · [repository]({common.REPO_URL}) · independent research "
        "project, not affiliated with NESO or Open-Meteo."
    )
