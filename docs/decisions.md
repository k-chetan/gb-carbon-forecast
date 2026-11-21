# Decisions log

Material decisions and deviations from the PRD / UI canvas, dated.

- 2026-11-21: Use Typst for the report instead of pandoc+LaTeX. Single binary, easy to run in CI.
- 2026-11-21: Repo artifacts are CSV/parquet files rather than the PRD's single DuckDB store. Files diff cleanly and the Actions jobs stay independent. DuckDB can still be used locally as a query tool.
- 2026-11-21: Vintage logger runs hourly and captures national fw48h only (PRD said daily, national + regional). Hourly captures give horizon-resolved 48 h comparisons. Regional operator forecasts are display-only in the app and fetched live, so logging them would add payload without evaluation value.
- 2026-11-21: Dropped the Chronos zero-shot reference model from the PRD's optional items. Scope held to baselines plus gradient-boosted quantile models.
- 2026-11-21: ruff replaces black+isort (the CO2-Dashboard convention). One tool, same 88-column style.
- 2026-11-21: New repo and new Streamlit app; CO2-Dashboard stays untouched. Its navigation/CSS/module patterns are reused here.
- 2026-11-21: Python 3.12 pinned project-wide (.python-version) for wheel compatibility across the pinned stack.
- 2026-11-21: Dropped the PRD's weekly automated retrain. The deployed model is the post-evaluation refit and the nightly job only issues forecasts, so the served model stays identical to the documented one.
- 2026-11-21: The app is a read-only consumer of committed artifacts (forecasts/latest.json). No model libraries in the deployed environment.
- 2026-11-21: Leg 2 community vintages subsampled to hourly capture cadence (the archive logs every 30 min) to match this project's own logger. Full resolution can be regenerated via scripts/build_community_vintages.py without the subsample.
- 2026-11-21: Weather features come from two archived-forecast sources with explicit lead semantics: the historical-forecast chain (short lead) and the previous-runs API (previous_day1 admissible for horizons <= 24 h, previous_day2 for <= 48 h). Availability offsets are enforced in the feature builder, not by convention.
- 2026-11-21: Eight weather grid points across the wind regions (Highlands, southern Scotland, Dogger Bank, Irish Sea, mid-Wales, SW England, London, East Anglia coast), fixed before any model saw data.
- 2026-11-21: Weather coverage finding: lead-stamped vintages (previous-runs) exist only from 2024-02/03, matching the PRD's "IFS from Mar 2024". The historical-forecast chain returns data back to 2017 but its early provenance can't be verified, so Track B trains on previous-run vintages only (common window 2024-04 to 2024-12) and the short window is reported as a finding. Pre-2021 chain data is never used.
- 2026-11-21: Track B ablation uses monthly validation folds on the common window; quarterly folds would only give two.
- 2026-11-21: Train/serve weather consistency: both training and the nightly job use previous-day-run vintages (day1 for horizons <= 24 h, day2 beyond), never the freshest run. The measured weather contribution is therefore conservative, and there is no train/serve skew. Freshest-run features noted as future work.
- 2026-11-21: Intervals conformalized (CQR, per horizon bucket) on a time-ordered calibration tail; the raw quantile heads under-covered (0.50 vs the 0.80 target) on validation.
- 2026-11-21: Static conformal offsets replaced by trailing-window conformal: offsets per issue day from the last 30 days of matured forecasts (issue-time admissible), seeded by the static offsets until enough errors mature. Static offsets decayed under regime shift (Track B validation coverage 0.32). A width-scaled variant was tried and dropped.
- 2026-11-21: Non-crossing enforced by clipping the interval heads to the median instead of sorting. Sorting silently swapped heads trained on different windows and corrupted the intervals.
- 2026-11-21: Leg 2 scoring window is 2026-07 to 2026-11 (out of sample for models trained through 2024). The 2023-2024 archive months provide the operator's own horizon curve as context, since the models trained on those targets.
