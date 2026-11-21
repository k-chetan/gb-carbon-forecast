# Decisions log

One line per material decision or deviation from the PRD / UI canvas.

- 2026-11-21 · Typst builds the report instead of pandoc+LaTeX: single binary, trivial to run in CI.
- 2026-11-21 · Repo artifacts are CSV/parquet files (PRD: single DuckDB store): files diff cleanly, Actions jobs stay independent; DuckDB remains available as a local query layer.
- 2026-11-21 · Vintage logger runs hourly and captures national fw48h only (PRD: daily, national + regional): hourly captures give horizon-resolved 48 h comparisons; regional operator forecasts are display-only and fetched live by the app, so logging them adds payload without evaluation value.
- 2026-11-21 · No Chronos zero-shot reference model (PRD optional item): scope held to baselines plus gradient-boosted quantile models.
- 2026-11-21 · ruff replaces black+isort (the CO2-Dashboard convention): one tool, same 88-column style.
- 2026-11-21 · New repo and new Streamlit app; CO2-Dashboard stays untouched. Its navigation/CSS/module patterns are reused here.
- 2026-11-21 · Python 3.12 pinned project-wide (.python-version): broadest wheel support for the pinned stack.
- 2026-11-21 · PRD's weekly automated retrain dropped: the deployed model is the post-evaluation refit; the nightly job only issues forecasts, so the served model stays identical to the documented one.
- 2026-11-21 · App is a read-only consumer of committed artifacts (forecasts/latest.json): no model libraries in the deployed environment.
