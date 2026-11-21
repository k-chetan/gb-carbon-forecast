// GB carbon-intensity forecasting — master's project report.
// Build: make report   (assembles _data.json + figures, then compiles this file)

#let data = json("_data.json")
#let sealed = data.sealed
#let ablation = data.ablation
#let legs = data.legs
#let live = data.live
#let anchors = data.anchors

#set page(paper: "a4", margin: (x: 2.4cm, y: 2.6cm), numbering: "1")
#set text(font: "New Computer Modern", size: 10.5pt)
#set par(justify: true)
#set heading(numbering: "1.1")
#show heading: it => block(above: 1.4em, below: 0.8em, it)
#show link: set text(fill: rgb("#135e43"))

#let pending(msg) = block(
  fill: rgb("#f4f5f1"),
  inset: 8pt,
  radius: 4pt,
  text(size: 9pt, style: "italic", "[Pending: " + msg + "]"),
)

// ============================================================================
// Title page
// ============================================================================

#align(center)[
  #v(3.2cm)
  #text(size: 20pt, weight: "bold")[
    Probabilistic 48-hour Forecasting of Great Britain's\ Grid Carbon Intensity
  ]
  #v(0.5cm)
  #text(size: 12pt)[
    An open-data forecaster with a self-running evaluation instrument,\
    benchmarked against the grid operator's own forecasts
  ]
  #v(2.2cm)
  #text(size: 12pt)[
    [TO BE FILLED: Author name]\
    [TO BE FILLED: Student number]\
    [TO BE FILLED: Degree programme]\
    [TO BE FILLED: Department and university]\
    [TO BE FILLED: Supervisor]\
    [TO BE FILLED: Submission date]
  ]
  #v(1.6cm)
  #text(size: 10pt, fill: rgb("#52514e"))[
    Live system: #link(data.app_url) \
    Source and artifacts: #link(data.repo_url)
  ]
]
#pagebreak()

// ============================================================================
// Abstract
// ============================================================================

#heading(numbering: none, outlined: false)[Abstract]

#if sealed != none [
  Great Britain's grid carbon intensity varies two- to four-fold within a day,
  but evaluating new forecasts against the grid operator is subtly broken: the
  operator's archived series is near-final, so retrospective comparisons at
  24–48 hours are not like-for-like. This project builds a probabilistic
  48-hour forecaster of GB national carbon intensity from keyless public data
  and evaluates it under strict issue-time discipline, with a sealed test year
  (2025) scored exactly once. Gradient-boosted quantile models with
  trailing-window conformal calibration achieve a sealed MAE of
  28.1 gCO#sub[2]/kWh across horizons to 48 h — 35% below persistence — with
  80.2% empirical coverage of the nominal 80% intervals. Archived
  weather-forecast vintages are the decisive input, improving MAE by 42% on a
  provenance-clean ablation window. Against true operator forecast vintages at
  matched issue times, the model is statistically indistinguishable at 7–48 h
  horizons, while the operator retains a clear advantage inside 6 hours.
  Because operator vintages do not exist historically, the project also
  deploys a self-running evaluation instrument — hourly vintage capture,
  nightly forecast issuance, weekly self-scoring and alerting — that matures
  the prospective evidence base unattended into the second semester, when a
  carbon-aware scheduler will consume these forecasts.
] else [
  #pending("abstract is written once the sealed 2025 evaluation lands")
]

#v(1em)
#outline(depth: 2)
#pagebreak()

// ============================================================================
// 1. Introduction
// ============================================================================

= Introduction

The carbon intensity of Great Britain's electricity — grams of CO#sub[2] per
kilowatt-hour of consumption — routinely swings by a factor of two to four
within a single day as wind output, demand and imports shift. Flexible loads
(electric-vehicle charging, heating cycles, batch computation) could exploit
these swings, but only if credible forecasts exist far enough ahead to plan
against, and only if their uncertainty is characterized honestly.

The grid operator, NESO, publishes such forecasts through its keyless Carbon
Intensity API @neso2026api. Evaluating a new forecaster against the operator,
however, runs into a subtle provenance problem: the operator's *stored*
forecast series is continuously revised until shortly before delivery, so the
archived values are near-final, short-horizon products. Comparing a genuine
48-hour forecast against them is not like-for-like, and most retrospective
comparisons silently inherit this flaw. A clean comparison requires forecast
*vintages* — the operator's forward curve captured as it was issued — which
largely do not exist for past years and cannot be reconstructed.

== Research question

#quote(block: true)[
  Can a lightweight, open-data model produce calibrated 48-hour forecasts of
  GB national grid carbon intensity that are competitive with the grid
  operator's own forecasts at longer horizons?
]

== Contributions

+ *A probabilistic 48-hour forecaster* (p10/p50/p90) built solely from keyless
  public data, with issue-time discipline enforced structurally and intervals
  calibrated by conformalized quantile regression @romano2019cqr.
+ *A measured answer to the weather question.* On a provenance-clean window,
  archived weather-forecast vintages are either the decisive covariate family
  or they are not; the ablation is reported either way, with
  dependence-aware significance.
+ *A three-leg operator comparison* that replaces one invalid comparison with
  three labeled ones (stored series; community vintage archive; own logged
  vintages), each stating exactly what it does and does not prove.
+ *A self-running longitudinal evaluation instrument*: an hourly vintage
  logger, nightly forecast issuance, weekly self-scoring and a daily watchdog
  run unattended on repository infrastructure, so the prospective evidence
  base matures without intervention and is refreshed once before submission.
  This design is a feature, not a workaround: time-dependent evidence is
  collected by instrument rather than by hand.

== Scope

National GB only; regional series have no published actuals and appear in the
deployment strictly as labeled operator forecasts. All impact language means
*attributed* emissions under NESO's stated methodology — never metered or
marginal effects. A carbon-aware task scheduler consuming these forecasts is
deliberately out of scope (it is the planned second-semester product; the
forecast JSON contract and dated vintage archive are its handoff interfaces).

// ============================================================================
// 2. Background and related work
// ============================================================================

= Background and related work

*Carbon-intensity forecasting.* CarbonCast @maji2022carboncast established
multi-day gradient-boosted and neural forecasts of grid carbon intensity
across several grids, using generation-mix modelling plus weather forecasts;
it reports that weather inputs matter most at longer horizons. Commercial
providers such as Electricity Maps @electricitymaps2026 publish forecasts but
neither their methods nor their forecast vintages are open. NESO's own
methodology @neso2026methodology combines generation forecasts by fuel with
intensity factors; its API @neso2026api exposes national forecast and actual
series at half-hour resolution, which this project both learns from and
benchmarks against.

*Carbon-aware computing.* The Green Software Foundation's Carbon Aware SDK
@gsf2024sdk and a growing scheduling literature shift flexible load toward
cleaner windows; they consume exactly the kind of forecast built here and
motivate the 48-hour horizon (day-ahead planning with a margin).

*Methods.* Quantile regression @koenker1978regression with gradient-boosted
trees @ke2017lightgbm provides sharp conditional quantiles; conformalized
quantile regression @romano2019cqr restores finite-sample marginal coverage.
Forecast comparison uses the Diebold–Mariano construction
@diebold1995comparing with HAC variance @newey1987simple, and the moving-block
bootstrap @kunsch1989jackknife for dependence-aware intervals, since
half-hourly error series are strongly autocorrelated. Pinball loss is the
proper score for quantiles @gneiting2007strictly.

*The vintage problem.* The only systematic public archive of NESO forecast
vintages is a community project @powell2023cift, which captured forward
curves every 30 minutes for parts of 2023–2024 and 2026 — with no coverage of
2025. This gap is structural to the field: forecasts that were never archived
can never be re-issued. The instrument built here exists to close that gap
prospectively.

// ============================================================================
// 3. Data
// ============================================================================

= Data

All sources are keyless and public; every raw pull is recorded in a manifest
with URL, pull time, row count, SHA-256 and coverage dates.

== National carbon intensity

The NESO API provides half-hourly national forecast and actual intensity from
2017-09-24 onward
#if data.manifest != none and "neso_api_history" in data.manifest.entries {
  let h = data.manifest.entries.neso_api_history
  [ (#h.rows rows pulled; #h.missing_actuals missing actuals,
  #h.missing_forecasts missing stored forecasts). ]
} else [ . ]
The data-portal bulk CSV was pulled independently as a cross-check: on the
overlap, actual values agree exactly on 99.96#sym.percent of windows (mean
absolute difference 0.0015 gCO#sub[2]/kWh), with a handful of post-publication
revisions explaining the remainder — the API series is used as the actuals
reference, and the possibility of revisions is carried as a limitation.
Published actuals are missing for a small number of windows; these are
documented and excluded from scoring, never imputed (@fig-gaps).

#figure(
  image("figures/eda_missing_actuals.png", width: 86%),
  caption: [Missing published actuals per month across the full history:
  sparse, clustered, and carried as exclusions rather than imputations.],
) <fig-gaps>

== Exploratory structure

#if data.eda != none [
  The decade of history carries a strong decarbonization trend — annual mean
  intensity fell from 247.7 gCO#sub[2]/kWh (2018) to 125.3 (2026), with the
  2021 gas-price episode visible as a plateau — and the distribution tightens
  as it falls (@fig-trend, @fig-shift). Intensity is strongly diurnal and
  seasonal, and its autocorrelation stays high at the daily lag
  (ACF #str(data.eda.acf.at("24h")) at 24 h,
  #str(data.eda.acf.at("7d")) at 7 days), which motivates both the lag
  feature family and day-block inference; both figures and the gap census
  regenerate from the raw pull.

  #figure(
    image("figures/eda_trend_monthly.png", width: 88%),
    caption: [Monthly mean national carbon intensity with a 12-month rolling
    mean: the decarbonization trend every model must survive.],
  ) <fig-trend>

  #figure(
    image("figures/eda_yearly_distributions.png", width: 88%),
    caption: [Distribution shift by year (boxes without outliers): the level
    falls and the spread narrows — training-era statistics do not transfer
    unexamined, which is why intervals are recalibrated from trailing
    errors.],
  ) <fig-shift>

  #figure(
    image("figures/eda_seasonal_profiles.png", width: 88%),
    caption: [Average day profile by season: the within-day swing that makes
    load-shifting worthwhile in the first place.],
  ) <fig-season>
] else [
  #pending("EDA artifacts")
]

== Weather forecast archives

Weather enters exclusively as *forecasts as issued*. Two Open-Meteo
@zippenfenig2023openmeteo archives were verified variable by variable before
any modelling:

#if data.weather_coverage != none [
  the lead-stamped previous-run vintages (#raw("previous_day1") /
  #raw("previous_day2")) are populated only from
  February–March 2024 — matching the known archiving start of the underlying
  model runs — while the short-lead historical-forecast chain probes back
  much further with unverifiable early provenance. Track B therefore uses
  previous-run vintages only, and its training window is correspondingly
  thin: an honest constraint reported as a finding, not buried. A provenance
  check against reanalysis @hersbach2020era5 confirmed the vintages are true
  forecasts: day-1 and day-2 values disagree with observed weather by a
  realistic, lead-growing error (e.g. 100 m wind MAE 2.7 then 3.2 km/h).
] else [
  #pending("weather coverage verification output")
]

Eight fixed grid points span the wind regions and demand centres (Highlands,
southern Scotland, Dogger Bank, Irish Sea, mid-Wales, south-west England,
London, East Anglia offshore); variables are 10 m and 100 m wind speed, 2 m
temperature, cloud cover and shortwave radiation.

== Operator forecast vintages

Three sources of operator comparison exist, with different provenance:
the *stored* near-final series (full history); the *community archive*
@powell2023cift (audited month by month:
#if data.vintage_audit != none [
  #data.vintage_audit.months.len() months across 2023–2024 and 2026, no 2025
] else [ coverage audit pending ]); and this project's *own hourly log* of the
operator's forward 48-hour curve, running since 2026-11-21 (see
@instrument). Missed capture hours are permanent, recorded gaps — vintages
cannot be backfilled.

// ============================================================================
// 4. Methodology
// ============================================================================

= Methodology

== Issue-time simulation

Every evaluation in this report simulates forecasts *as they could have been
issued*: a forecast issued at time $T$ for target window $T + h$,
$h in {0.5, ..., 48}$ hours, may use only information available at $T$. This
is enforced structurally in the feature builder — lag features are shifts on
the issue grid; weather joins carry explicit lead admissibility — and tested
by poisoning: unit tests corrupt every observation after each issue time and
assert the built features are bit-identical.

== Features and models

Both tracks use gradient-boosted quantile regression (LightGBM
@ke2017lightgbm) with horizon-as-feature over all 96 half-hour horizons and
three quantile heads (p10/p50/p90), non-crossing enforced by sorting.

*Track A (lags + calendar, full history).* Lags of published actuals at the
issue time (30 min to 7 days), rolling means, a 24-hour trend term, and
target-time calendar features (cyclic hour, weekday, month, day of year, GB
holidays).

*Track B (+ archived weather forecasts).* Track A plus previous-run weather
vintages at the target time: day-1 values admissible for horizons #sym.lt.eq
24 h (masked to missing beyond, which gradient boosting handles natively),
day-2 values for all horizons to 48 h. Per-point 100 m wind plus cross-point
means of the other variables, per lead. The nightly serving path pulls the
same previous-run vintages, so there is no train/serve skew; against a
freshest-run serving design this makes the measured weather contribution a
conservative lower bound.

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, left, left),
    table.header([*feature family*], [*derivation*], [*availability at issue $T$*]),
    [lags (9)], [published actuals 0.5 h–7 d behind the last elapsed window],
    [window fully elapsed by $T$, structural],
    [rolling means (2)], [24 h and 7 d means ending at the last elapsed window],
    [same],
    [trend (1)], [freshest value minus its 24 h lag], [same],
    [calendar (7)], [cyclic hour, weekday, month, day-of-year, GB holiday,
    of the *target* time], [deterministic],
    [horizon (1)], [$h$ in hours], [deterministic],
    [weather day-2 (11)], [previous-run vintages at the target time,
    lead ≈ 48 h], [run issued at $T + h - 48 "h" lt.eq T$ for all
    $h lt.eq 48$],
    [weather day-1 (11)], [previous-run vintages, lead ≈ 24 h],
    [admissible only for $h lt.eq 24$; masked to missing beyond],
  ),
  caption: [Feature families and their availability rules. Admissibility is
  enforced in the builder and covered by future-poisoning tests.],
) <tbl-features>

== Interval calibration

Raw quantile heads under-covered on validation (0.50 against the nominal
0.80), a known failure mode of boosted quantiles under distribution shift.
Intervals are therefore conformalized @romano2019cqr on a time-ordered
calibration tail inside each training window, per horizon bucket. The median
is never recalibrated and trains on the full window. Both an additive and a
width-scaled conformity score were evaluated on development folds; the
deployed choice and its validation coverage are reported in @results.

== Validation design

Model development used rolling-origin validation strictly inside the training
years (quarterly folds on 2018–2024 for Track A; monthly folds on the thin
2024 common window for the ablation), with a 7-day embargo before every
validation window. The sealed test — calendar 2025 — was scored exactly once,
by a script that refuses to run twice; its guard proved itself during
development by aborting a training run whose last issue's 48-hour horizon
touched 2025-01-01 00:00 by a single window.

== Significance

Half-hourly forecast errors are strongly autocorrelated (lag-24 h ACF 0.74,
@fig-acf), so iid tests are invalid. Paired comparisons use (i) a
moving-block bootstrap @kunsch1989jackknife with day-length blocks and (ii)
Diebold–Mariano @diebold1995comparing with Bartlett/HAC variance
@newey1987simple, truncation at the forecast-horizon MA order floored at one
day.

#figure(
  image("figures/eda_autocorrelation.png", width: 86%),
  caption: [Autocorrelation of half-hourly intensity out to one week: the
  daily and weekly structure that both the lag features exploit and the
  block-inference design respects.],
) <fig-acf>

== Pilot-anchor reproduction

Before any modelling, the data pipeline reproduced five pre-registered anchor
numbers from the preceding pilot study on the same protocol, all within
1.1#sym.percent (@tbl-anchors).

#if anchors != none [
  #figure(
    table(
      columns: (auto, auto, auto, auto),
      align: (left, right, right, right),
      table.header([*anchor*], [*pilot*], [*reproduced*], [*n*]),
      [persistence-24 h], [38.9],
      [#str(anchors.reproduced.persistence_24h.mae)],
      [#str(anchors.reproduced.persistence_24h.n)],
      [persistence-48 h], [47.5],
      [#str(anchors.reproduced.persistence_48h.mae)],
      [#str(anchors.reproduced.persistence_48h.n)],
      [seasonal naive (7 d)], [55.9],
      [#str(anchors.reproduced.seasonal_naive_7d.mae)],
      [#str(anchors.reproduced.seasonal_naive_7d.n)],
      [lags+calendar GBM, 24 h], [38.3],
      [#str(anchors.reproduced.gbm_lags_calendar_24h.mae)],
      [#str(anchors.reproduced.gbm_lags_calendar_24h.n)],
      [NESO stored series], [9.3],
      [#str(anchors.reproduced.neso_stored_forecast.mae)],
      [#str(anchors.reproduced.neso_stored_forecast.n)],
    ),
    caption: [Pilot anchors and their reproduction on the fresh pull
    (MAE on calendar 2025, gCO#sub[2]/kWh). The stored-series pair count
    reproduces exactly, a strong end-to-end pipeline check.],
  ) <tbl-anchors>
] else [ #pending("anchor reproduction output") ]
The anchor involving a learned model re-runs a pilot experiment once, without
iteration; all genuine model development used validation inside the training
years only.

// ============================================================================
// 5. Results
// ============================================================================

= Results <results>

== Weather ablation on the provenance-clean window

#if ablation != none [
  #let overall = ablation.comparisons.at(0)
  On identical (issue, target) pairs across the monthly validation folds of
  the 2024 common window (n = #overall.n_pairs pairs), adding archived
  weather-forecast vintages moved the validation MAE from
  #overall.mae_a to #overall.mae_b gCO#sub[2]/kWh
  (#overall.delta_pct#sym.percent), with block-bootstrap and HAC-DM
  p-values below 10#super[-4] in every horizon bucket.

  #figure(
    image("figures/ablation.png", width: 86%),
    caption: [Track A vs Track B validation MAE by horizon bucket, paired on
    identical issue and target times; percentages are the weather deltas.],
  ) <fig-ablation>
] else [
  #pending("ablation artifacts (results/ablation.json)")
]

== Sealed 2025 test

#if sealed != none [
  #let ma = sealed.models.track_a.metrics
  #let mb = sealed.models.track_b.metrics
  #let r2 = (x) => str(calc.round(x, digits: 2))
  #let pct = (x) => str(calc.round(x * 100, digits: 1)) + "%"

  Calendar 2025 was scored exactly once, on an hourly issue grid
  (#str(sealed.n_pairs) issue–target pairs). @tbl-sealed gives the frozen
  headline metrics; @fig-horizon the per-horizon curves.

  #figure(
    table(
      columns: (auto, auto, auto, auto, auto, auto),
      align: (left, right, right, right, right, right),
      table.header(
        [*model*], [*MAE*], [*1–6 h*], [*7–24 h*], [*25–48 h*], [*coverage 80%*],
      ),
      [Track A (lags+calendar)],
      [#r2(ma.mae_p50)], [#r2(ma.by_bucket.at("01_06h").mae_p50)],
      [#r2(ma.by_bucket.at("07_24h").mae_p50)],
      [#r2(ma.by_bucket.at("25_48h").mae_p50)], [#pct(ma.coverage_80)],
      [Track B (+weather)],
      [#r2(mb.mae_p50)], [#r2(mb.by_bucket.at("01_06h").mae_p50)],
      [#r2(mb.by_bucket.at("07_24h").mae_p50)],
      [#r2(mb.by_bucket.at("25_48h").mae_p50)], [#pct(mb.coverage_80)],
    ),
    caption: [Sealed 2025 metrics (MAE in gCO#sub[2]/kWh; 80% interval
    coverage from trailing-window conformal calibration).],
  ) <tbl-sealed>

  Three readings stand out. First, Track B beats issue-time persistence by
  35.2% overall (28.05 vs 43.31, block-bootstrap and HAC-DM p #sym.lt
  10#super[-5]) and Track A by 24.3%, confirming the ablation on seven years
  of training data. Second, Track B's error is almost flat in horizon (27.8 →
  28.2 gCO#sub[2]/kWh from the first to the last bucket) while Track A
  degrades steeply (20.8 → 42.8): weather forecasts carry nearly all of the
  long-horizon signal. Third — an honest crossover — Track A is the better
  model below 6 hours (20.8 vs 27.8), where recent lags dominate and Track B
  pays for its thin training window; an operational blend would route by
  horizon, and the deployed model accepts this cost to keep provenance
  simple. Track B's intervals hit nominal coverage almost exactly
  (80.0–80.3% in every bucket), the direct payoff of recalibrating from
  trailing matured errors.

  #figure(
    image("figures/horizon_curves.png", width: 92%),
    caption: [MAE by horizon on the sealed 2025 year, hourly issue grid; the
    stored NESO series (Leg 1) is a near-final short-horizon product and is
    shown as labeled context, not as a like-for-like baseline.],
  ) <fig-horizon>

  #figure(
    image("figures/calibration.png", width: 72%),
    caption: [80#sym.percent interval coverage by horizon bucket on the
    sealed year.],
  ) <fig-calibration>
] else [
  #pending("the one-time sealed evaluation (results/sealed/)")
]

== Three-leg operator comparison

*Leg 1 — stored series (labeled).* The operator's archived forecast scores
9.28 gCO#sub[2]/kWh on 2025: three times better than any 48-hour model, and
exactly why it is not a valid 24–48 h baseline — it is a near-final product,
revised until shortly before delivery. It is reported as context, never as
the comparison.

*Leg 2 — archive vintages at matched issue times.* On 550 hourly captures
from the community archive (July–November 2026, out-of-sample for models
trained through 2024), Track B is statistically indistinguishable from the
operator's true forward forecasts at longer horizons: 26.39 vs 26.49
(−0.4%, DM p = 0.89) at 7–24 h and 27.70 vs 26.47 (+4.6%, p = 0.14) at
25–48 h. Inside 6 hours the operator is clearly better (+21.6%,
p #sym.lt 10#super[-3]), as expected for a system with near-real-time
generation data. Without weather, Track A loses to the vintages everywhere
(+47% overall) — weather is what buys operator parity. The operator's own
vintage accuracy on its 2023–24 archive months (MAE 18.2 / 24.4 / 26.0 by
bucket) matches its 2026 window, supporting the comparison's stability.

*Leg 3 — own logged vintages.* At build time the project's logger had
captured two forward curves and nothing had matured: by construction this leg
starts at zero. Its value is the slope. At the hourly capture cadence and one
nightly model forecast per day, roughly 5,000 operator captures
(≈ 0.5 million scored windows) and 200 model forecast issues (≈ 19,000
windows) will have matured by June 2027 — ample power for bucket-level
block inference — and the pre-submission refresh regenerates this section
from whatever has accumulated.

#if legs != none [] else [ #pending("operator legs (results/legs/legs.json)") ]

== Live self-scoring instrument

#if live != none [
  At the time of this build the instrument had logged
  #live.vintages.total_captures operator captures since
  #live.vintages.first_capture_utc and scored
  #live.neso_fw48h.scored_windows matured forecast windows; these figures
  update weekly without intervention, and this section is one of the two
  (with the legs above) that the pre-submission refresh regenerates.
] else [
  #pending("prospective self-scoring summary")
]

// ============================================================================
// 6. The longitudinal instrument
// ============================================================================

= The self-running evaluation instrument <instrument>

Time-dependent evidence in this project is collected by instrument. Four
scheduled jobs run unattended on repository infrastructure (GitHub Actions),
writing versioned artifacts that the application and this report both read:

- *vintage-logger* (hourly, minute 17): captures the operator's forward
  48-hour national curve — \~96 half-hour windows per capture — to a
  dedicated branch, with a manifest that records capture counts and permanent
  gaps.
- *nightly-forecast* (03:07 UTC): issues the deployed model's 48-hour
  probabilistic forecast, writing a stable JSON contract plus an immutable
  dated copy; these dated copies are the project's own vintages, scored as
  they mature.
- *self-scoring* (weekly): recomputes, from scratch and idempotently, the
  error of every matured logged forecast against published actuals, and
  compacts closed months of the vintage log to parquet.
- *watchdog* (daily): opens or updates a "PIPELINE STALE" issue — which
  e-mails the owner — when the last capture exceeds 6 hours or the last
  forecast 48 hours; closes it on recovery; and pushes a keepalive commit if
  capture activity ever pauses for 7 days, because the platform disables
  schedules after 60 days of repository inactivity.

The alert path was verified live on build day: a deliberately failed capture,
a drill that opened the real issue, a recovery run that closed it, and a
subsequent normal capture. Gaps are never backfilled; the manifest records
them. The single number worth a monthly glance is the logger badge on the
repository README.

// ============================================================================
// 7. Deployment
// ============================================================================

= Deployment

#figure(
  image("figures/architecture.png", width: 94%),
  caption: [Everything scheduled runs on repository infrastructure and writes
  versioned artifacts; the application is a read-only consumer, so a job
  failure can only age what users see, never corrupt it.],
) <fig-arch>

The public application (#link(data.app_url)) serves three pages: a forecast
explorer (model fan chart with the operator's forward curve and recent
actuals; regional series shown only as labeled operator forecasts), an
evaluation page whose sections are gated on committed artifacts — including
the live self-scoring counters that grow weekly — and a model card stating
data, licences, assumptions, limitations and the evaluated-versus-deployed
split. The deployed model is a post-evaluation refit on all data through the
present; every number in this report comes from the sealed-evaluated models,
and the two are never conflated. Free-tier hosting sleeps when idle and wakes
from a button in roughly thirty seconds.

#if data.status.fan_example [
  #figure(
    image("figures/fan_example.png", width: 92%),
    caption: [A production forecast as served (issued by the nightly job).],
  )
]

#if data.status.at("app_screenshot", default: false) [
  #figure(
    image("figures/app_forecast.png", width: 86%),
    caption: [The live forecast explorer, captured headlessly from the public
    URL at report build time.],
  )
]

// ============================================================================
// 8. Discussion and limitations
// ============================================================================

= Discussion and limitations

*The research question, answered with a boundary.* A lightweight open-data
model can match the grid operator at 7–48 h horizons — the horizons that
matter for day-ahead load shifting — but not inside 6 hours, where the
operator's near-real-time generation telemetry is decisive. The weather
ablation locates the mechanism: forecast vintages of wind above all carry the
long-horizon signal (−41.9% on the matched common window; −24.3% against a
Track A that enjoys seven years of history), and the two deltas differ for an
instructive reason — lag models improve with more history, weather models
with better weather, so the measured weather contribution shrinks as the
lags-only baseline strengthens.

*Calibration was the hard part.* Raw quantile heads under-covered badly
(0.50), and every static correction decayed under regime shift; only
recalibrating from trailing matured errors — which the unattended instrument
produces anyway — held nominal coverage on a full unseen year. The sealed
80.2% against nominal 80% is the project's quietest but most load-bearing
number.

Fixed limitations:

- *Attributed, not marginal.* Values follow NESO's average-intensity
  methodology; shifting load by this signal is a modelling claim about
  attributed emissions, not a metered or causal one.
- *National scoring only.* No published regional actuals exist; regional
  accuracy is unknowable from public data and is not claimed.
- *Thin weather window.* True forecast vintages begin 2024-03; the ablation
  is powered accordingly and its window is stated wherever it is cited.
- *Prospective n at build time.* Leg 3 starts near zero by construction; its
  value is the slope, not the intercept — the instrument matures it
  unattended, and the refresh updates only those sections.
- *Revisable actuals.* The operator can revise published actuals; the
  cross-check bounds this effect at the 0.04#sym.percent level of windows.

// ============================================================================
// 9. Ethics, licensing, reproducibility
// ============================================================================

= Ethics, licensing and reproducibility

All data are public and non-personal. NESO data are used under CC BY 4.0 with
attribution @neso2026api; Open-Meteo under CC BY 4.0 on the non-commercial
tier @zippenfenig2023openmeteo; the community vintage archive under MIT
@powell2023cift. Code is MIT-licensed. The deployment and report state
attribution in their footers, and the application is clearly labeled as an
independent research project.

Reproducibility: dependencies are pinned by lockfile; seeds are fixed; every
raw artifact carries a manifest entry with content hash; every reported
number traces to a committed artifact and regenerates from the repository
(`make report`), and the pre-submission refresh (`make refresh`) regenerates
only the prospective sections, leaving the frozen sealed results untouched.

// ============================================================================
// 10. Future work
// ============================================================================

= Future work

The second semester consumes this system as infrastructure: a carbon-aware
task scheduler (duration and deadline in, greenest start window out) built on
the forecast JSON contract, evaluated in simulation against hindsight-optimal
and run-now policies using the matured vintage archive this instrument is
accumulating — including, by then, a usefully sized Leg 3. On the forecasting
side: freshest-run weather features (lifting the conservative lower bound),
regional modelling if regional actuals are ever published, and interval
methods that adapt faster to regime shifts.

// ============================================================================
// Appendix
// ============================================================================

#pagebreak()
#heading(numbering: none)[Appendix A: repository map]

#raw(block: true, lang: "text",
"src/gbcarbon/        neso.py vintage.py scoring.py watchdog.py
                     features.py train.py evaluate.py forecast.py
scripts/             verify_weather_coverage.py cross_check_history.py
                     build_community_vintages.py reproduce_anchors.py
                     eda.py ablation.py run_sealed_evaluation.py
                     score_operator_legs.py report_figures.py
.github/workflows/   vintage-logger ci watchdog self-scoring nightly-forecast
data/raw/            manifested immutable pulls (+ manifest.json)
data/external/       community vintages + per-month audit
results/             eda/ sealed/ legs/ ablation.json prospective summaries
runs/                one directory per training run (config + metrics)
forecasts/           latest.json + dated history/ (the project's own vintages)
report/              this document, its data file, figures, references")

#heading(numbering: none)[Appendix B: model and run configuration]

#if sealed != none [
  Both tracks share one LightGBM configuration (600 trees, learning rate
  0.05, 127 leaves, minimum 100 samples per leaf, 90% row and column
  subsampling, seed 42), three quantile heads (0.1 / 0.5 / 0.9), and the
  trailing conformal window of 30 days with day-level updates. Sealed-eval
  runs: Track A `#sealed.models.track_a.run` (trained 2018-01-01 →
  2024-12-29, two-hourly issues); Track B `#sealed.models.track_b.run`
  (trained 2024-04-01 → 2024-12-29, hourly issues). The deployed model is a
  tagged refit of Track B through the present; report numbers never come
  from it. Every run directory under `runs/` carries its full configuration,
  feature list, git hash and metrics as JSON.
]

#heading(numbering: none)[Appendix C: decisions log]

The repository file `docs/decisions.md` records every material deviation from
the product requirements and design references, one line each, dated.

#pagebreak()
#bibliography("refs.bib", style: "apa", title: "References")
