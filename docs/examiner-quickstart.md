# Examiner quick-start

1. Open the live app: <https://gb-carbon-forecast-go.streamlit.app/> — free-tier
   apps sleep when idle; press the wake button and give it ~30 s.
2. **Forecast** page: the model's 48 h fan chart (p10/p50/p90) with the
   operator's own forward curve dashed for context; pick any region to see
   display-only operator forecasts (labeled; no regional actuals exist).
3. **Evaluation** page: sealed-2025 horizon curves, the three labeled operator
   legs, and live self-scoring counters that have been growing unattended.
4. **Model card** page: data, licences, assumptions, limitations, and the
   evaluated-vs-deployed split.
5. Repository: <https://github.com/k-chetan/gb-carbon-forecast> — the README
   badges show the pipeline is alive (hourly logger, CI).
6. Every number in the report regenerates from the repository: `make setup`,
   `make test`, `make report`.
7. The vintage log (branch `vintage-log`) holds the operator's forward
   forecasts captured hourly since 2026-11-21 — evidence that cannot be
   reconstructed after the fact.
8. Scheduled jobs run in `.github/workflows/`; their run history is public
   under the repository's Actions tab.
9. The sealed 2025 test was scored exactly once; `results/sealed/` is frozen
   and the evaluation script refuses to run twice.
10. Questions about any figure: each one is written by
    `scripts/report_figures.py` from committed artifacts — nothing is pasted
    by hand.
