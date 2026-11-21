"""Model card page: data, protocol, assumptions, limitations, reproduction."""

from __future__ import annotations

import streamlit as st

from views import common


def show() -> None:
    deployed = common.load_json("models/deployed/run.json")
    sealed = common.load_json("results/sealed/sealed_2025.json")

    common.section_card("Model card")

    st.markdown(
        """
**Task.** 48-hour probabilistic forecasts of GB national grid carbon
intensity (gCO₂/kWh), issued as p10/p50/p90 for each half-hour window.

**Models.** Gradient-boosted quantile regression (LightGBM) with the horizon
as a feature, over 96 half-hour horizons, with conformal interval calibration
per horizon bucket. Track A uses lag and calendar features on the full
history; Track B adds archived weather forecasts on the window where those
are available.
"""
    )

    split_a = sealed["models"]["track_a"]["run"] if sealed else "pending"
    split_b = sealed["models"]["track_b"]["run"] if sealed else "pending"
    deployed_id = deployed["config"]["run_id"] if deployed else "pending"
    st.markdown(
        f"""
**Evaluated vs deployed.** The report numbers come from models trained only
on data before the sealed year (`{split_a}`, `{split_b}`). The app serves a
separate refit on all data through the present (`{deployed_id}`). The report
does not cite the deployed model.
"""
    )

    st.markdown(
        """
**Protocol.**
- A forecast issued at time T uses only information available at T. This is
  enforced in the feature construction code and checked by tests that corrupt
  everything after the issue time and assert the features do not change.
- The sealed test is calendar 2025, scored once. Development used validation
  windows inside the training years.
- Weather enters as forecasts as they were issued (previous-day model runs:
  day-1 for horizons up to 24 h, day-2 beyond), at training and serving time
  alike. Observations and reanalysis are never used as inputs.
- Significance tests use day-length block bootstrap and HAC Diebold-Mariano,
  since half-hourly errors are strongly autocorrelated.

**Data and licences.**
- [NESO Carbon Intensity API](https://carbonintensity.org.uk/) — CC BY 4.0.
  The national history was cross-checked against the data-portal CSV (99.96%
  exact agreement on actuals).
- [Open-Meteo](https://open-meteo.com/) — CC BY 4.0, non-commercial tier.
  Archive coverage was verified per variable and recorded in the manifest.
- [Community vintage archive](https://github.com/nmpowell/carbon-intensity-forecast-tracking)
  — MIT (Nick Powell). Months audited individually; no 2025 coverage.

**Assumptions and limitations.**
- Values are *attributed* emissions under NESO's methodology, not metered and
  not marginal. Shifting load based on them is a modelling claim.
- Scoring is national only. There are no published regional actuals, so
  regional series are shown as labelled operator forecasts and not scored.
- True weather vintages begin in March 2024, so the weather ablation window
  is short.
- Missed vintage captures are permanent gaps and are recorded, not
  backfilled. Published actuals can be revised after the fact.

**Reproduce.**
```bash
git clone https://github.com/k-chetan/gb-carbon-forecast && cd gb-carbon-forecast
make setup && make test     # environment from the lockfile, test suite
make report                 # rebuild the report from current artifacts
```
"""
    )
    st.caption(
        f"Code MIT · [repository]({common.REPO_URL}) · independent research "
        "project, not affiliated with NESO."
    )
