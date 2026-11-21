// GB carbon intensity forecasting - master's project report.
// Build: make report (assembles _data.json + figures, then compiles this file)

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
    Forecasting from open data, with an automated comparison\
    against the grid operator's forecasts
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
  The carbon intensity of Great Britain's electricity varies by a factor of
  two to four within a day. Good forecasts of this signal would let flexible
  demand move to cleaner hours, but evaluating a new forecaster against the
  grid operator is harder than it looks, because the operator's archived
  forecast series is revised until shortly before delivery and is therefore
  not a valid baseline at 24 to 48 hour horizons. This project builds a
  probabilistic 48-hour forecaster of national carbon intensity from public
  data and evaluates it under an issue-time protocol, with a sealed test year
  (2025) that was scored once. Gradient boosted quantile models with
  trailing-window conformal calibration reach a sealed MAE of 28.1
  gCO#sub[2]/kWh, 35% below persistence, with 80.2% coverage at the nominal
  80% level. Archived weather forecasts are the main driver of this result:
  they improve MAE by 42% in a matched ablation. Compared with operator
  forecast vintages captured at the same issue times, the model is
  statistically indistinguishable at horizons of 7 to 48 hours, and clearly
  worse inside 6 hours. An automated capture and scoring pipeline continues
  to accumulate comparison data unattended ahead of the second semester,
  which will build a carbon-aware scheduler on top of these forecasts.
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

The carbon intensity of Great Britain's electricity, in grams of CO#sub[2]
per kilowatt-hour, routinely swings by a factor of two to four within a
single day as wind output, demand and imports change. Flexible loads such as
EV charging, heating cycles and batch computation could exploit these swings,
but only if forecasts exist far enough ahead to plan against, and only if
their uncertainty is described honestly.

The grid operator, NESO, publishes forecasts through its free Carbon
Intensity API @neso2026api. Evaluating a new forecaster against the operator
runs into a provenance problem, however. The operator's _stored_ forecast
series is revised continuously until shortly before delivery, so the archived
values are close to final and reflect very short lead times. Comparing a
genuine 48-hour forecast against them is not a fair comparison, and
retrospective studies that use the stored series inherit this flaw. A clean
comparison needs forecast _vintages_, meaning the operator's forward curve
saved at the moment it was issued. For past years these mostly do not exist
and cannot be reconstructed.

== Research question

#quote(block: true)[
  Can a lightweight model built only on open data produce calibrated 48-hour
  forecasts of GB national grid carbon intensity that are competitive with
  the grid operator's own forecasts at longer horizons?
]

== Contributions

+ A probabilistic 48-hour forecaster (p10/p50/p90) built from free public
  data, with the issue-time rules enforced in the feature construction code
  and the intervals calibrated by conformalized quantile regression
  @romano2019cqr.
+ A measured answer to the weather question. On a window where forecast
  provenance is clean, archived weather forecasts either matter or they do
  not; the ablation is reported either way, with significance tests that
  respect the autocorrelation of the errors.
+ An operator comparison in three parts, replacing one invalid comparison
  with three labelled ones (the stored series, a community vintage archive,
  and the project's own logged vintages), where each part states what it can
  and cannot show.
+ An automated evaluation pipeline. An hourly vintage logger, nightly
  forecast issuance, weekly self-scoring and a daily health check run
  unattended on repository infrastructure, so the prospective comparison data
  keeps growing without manual work and is refreshed once before submission.
  Collecting time-dependent evidence this way was a deliberate design choice
  rather than a workaround.

== Scope

The work covers the national GB signal only. Regional series have no
published actuals, so they appear in the deployment purely as labelled
operator forecasts. All impact language refers to _attributed_ emissions
under NESO's stated methodology, not metered or marginal effects. A
carbon-aware task scheduler that consumes these forecasts is out of scope for
this semester; it is the planned second-semester product, and the forecast
JSON contract and the dated vintage archive are the interfaces it will use.

// ============================================================================
// 2. Background and related work
// ============================================================================

= Background and related work

*Carbon intensity forecasting.* CarbonCast @maji2022carboncast produced
multi-day forecasts of grid carbon intensity for several grids using
generation-mix models together with weather forecasts, and found that weather
inputs matter most at longer horizons. Commercial providers such as
Electricity Maps @electricitymaps2026 publish forecasts, but neither their
methods nor their historical forecast vintages are open. NESO's own
methodology @neso2026methodology builds fuel-level generation forecasts and
applies intensity factors; its API @neso2026api exposes national forecast and
actual series at half-hour resolution. This project learns from that data
and also benchmarks against it.

*Carbon-aware computing.* The Green Software Foundation's Carbon Aware SDK
@gsf2024sdk and related scheduling work shift flexible load toward cleaner
windows. These consumers motivate the 48-hour horizon used here, since
day-ahead planning needs some margin.

*Methods.* Quantile regression @koenker1978regression with gradient boosted
trees @ke2017lightgbm gives sharp conditional quantiles, and conformalized
quantile regression @romano2019cqr restores finite-sample marginal coverage.
For comparing forecasts I use the Diebold-Mariano construction
@diebold1995comparing with HAC variance @newey1987simple and a moving-block
bootstrap @kunsch1989jackknife, because half-hourly error series are strongly
autocorrelated and tests that assume independence overstate significance.
Pinball loss is the standard proper score for quantiles @gneiting2007strictly.

*The vintage problem.* The only systematic public archive of NESO forecast
vintages is a community project @powell2023cift that captured forward curves
every 30 minutes during parts of 2023, 2024 and 2026, with no coverage of
2025. The gap is structural: forecasts that were never archived cannot be
re-issued. The logging pipeline built here exists to close that gap going
forward.

// ============================================================================
// 3. Data
// ============================================================================

= Data

All sources are free and public. Every raw pull is recorded in a manifest
with its URL, pull time, row count, SHA-256 hash and coverage dates.

== National carbon intensity

The NESO API provides half-hourly national forecast and actual intensity from
2017-09-24 onward
#if data.manifest != none and "neso_api_history" in data.manifest.entries {
  let h = data.manifest.entries.neso_api_history
  [ (#h.rows rows pulled; #h.missing_actuals missing actuals and
  #h.missing_forecasts missing stored forecasts). ]
} else [ . ]
As a cross-check, the bulk CSV from the NESO data portal was downloaded
separately. On the overlap the actual values agree exactly on 99.96% of
windows, with a mean absolute difference of 0.0015 gCO#sub[2]/kWh; the small
remainder comes from post-publication revisions. The API series is used as
the reference for actuals, and the possibility of revisions is listed as a
limitation. Windows with missing actuals are excluded from scoring rather
than imputed (@fig-gaps).

#figure(
  image("figures/eda_missing_actuals.png", width: 86%),
  caption: [Missing published actuals per month over the full history. The
  gaps are sparse and clustered, and are excluded rather than imputed.],
) <fig-gaps>

== Exploratory structure

#if data.eda != none [
  The decade of history contains a strong downward trend: annual mean
  intensity fell from 247.7 gCO#sub[2]/kWh in 2018 to 125.3 in 2026, with the
  2021 gas-price period visible as a plateau, and the distribution narrows as
  the level falls (@fig-trend, @fig-shift). Intensity has clear daily and
  seasonal structure, and the autocorrelation remains high at the daily lag
  (#str(data.eda.acf.at("24h")) at 24 h, #str(data.eda.acf.at("7d")) at 7
  days). This motivates the lag features and also the use of day-length
  blocks in the significance tests. The figures regenerate from the raw pull.

  #figure(
    image("figures/eda_trend_monthly.png", width: 88%),
    caption: [Monthly mean national carbon intensity with a 12-month rolling
    mean. Any model trained on several years must cope with this trend.],
  ) <fig-trend>

  #figure(
    image("figures/eda_yearly_distributions.png", width: 88%),
    caption: [Distribution by year (boxes without outliers). The level falls
    and the spread narrows, which is one reason the intervals are
    recalibrated from recent errors rather than fixed at training time.],
  ) <fig-shift>

  #figure(
    image("figures/eda_seasonal_profiles.png", width: 88%),
    caption: [Average day profile by season. The within-day swing is what
    makes load shifting worthwhile.],
  ) <fig-season>
] else [
  #pending("EDA artifacts")
]

== Weather forecast archives

Weather enters the models only as forecasts as they were issued, never as
observations. Two Open-Meteo @zippenfenig2023openmeteo archives were checked
variable by variable before any modelling:

#if data.weather_coverage != none [
  the lead-stamped previous-run data (#raw("previous_day1") /
  #raw("previous_day2")) is only populated from February-March 2024, which
  matches the known archiving start of the underlying model runs. The
  short-lead historical-forecast chain returns data much further back, but
  the provenance of that early data cannot be verified, so Track B uses the
  previous-run data only and its training window is short. This constraint
  is reported as a finding rather than hidden. A check against reanalysis
  @hersbach2020era5 confirmed that the previous-run values are real
  forecasts: day-1 and day-2 values differ from observed weather by a
  realistic error that grows with lead time (for 100 m wind, MAE 2.7 and
  then 3.2 km/h).
] else [
  #pending("weather coverage verification output")
]

Eight fixed grid points cover the main wind regions and demand centres
(the Highlands, southern Scotland, Dogger Bank, the Irish Sea, mid-Wales,
south-west England, London and the East Anglia coast). The variables are
10 m and 100 m wind speed, 2 m temperature, cloud cover and shortwave
radiation.

== Operator forecast vintages

Three sources of operator comparison exist, each with different provenance.
The first is the stored near-final series, available for the full history.
The second is the community archive @powell2023cift
#if data.vintage_audit != none [
  (audited month by month: #data.vintage_audit.months.len() months across
  2023-2024 and 2026, with no 2025).
] else [ (coverage audit pending). ]
The third is this project's own hourly log of the operator's forward 48-hour
curve, which has been running since 2026-11-21 (see @instrument). A missed
capture hour is recorded as a permanent gap, since vintages cannot be
requested after the fact.

// ============================================================================
// 4. Methodology
// ============================================================================

= Methodology

== Issue-time simulation

Every evaluation in this report simulates forecasts as they could have been
issued. A forecast issued at time $T$ for target window $T + h$, with
$h in {0.5, ..., 48}$ hours, may use only information available at $T$. The
rule is enforced in the feature construction code itself: lag features are
shifts on the issue grid, and weather joins carry explicit lead
admissibility. It is also tested directly. The unit tests corrupt every
observation after each issue time and check that the generated features do
not change at all.

== Features and models

Both tracks use gradient boosted quantile regression (LightGBM
@ke2017lightgbm) with the horizon as a feature, over all 96 half-hour
horizons, and three quantile heads (p10/p50/p90). Crossing quantiles are
resolved by clipping the interval heads to the median.

*Track A (lags and calendar, full history).* Lags of the published actuals
relative to the issue time (30 minutes to 7 days), rolling means, a 24-hour
trend term, and calendar features of the target time (cyclic hour, weekday,
month, day of year, GB holidays).

*Track B (plus archived weather forecasts).* Track A features plus
previous-run weather values at the target time. Day-1 values are admissible
for horizons up to 24 h and are set to missing beyond that, which gradient
boosting handles natively; day-2 values are admissible at every horizon up
to 48 h. The features are per-point 100 m wind plus cross-point means of the
other variables, for each lead. The nightly serving job pulls the same
previous-run data, so the model is served with the same lead structure it
was trained on. Compared with a system that always uses the freshest run,
this makes the measured weather contribution a conservative estimate.

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, left, left),
    table.header([*feature family*], [*derivation*], [*availability at issue $T$*]),
    [lags (9)], [published actuals 0.5 h to 7 d behind the last elapsed window],
    [window fully elapsed by $T$],
    [rolling means (2)], [24 h and 7 d means ending at the last elapsed window],
    [same],
    [trend (1)], [freshest value minus its 24 h lag], [same],
    [calendar (7)], [cyclic hour, weekday, month, day of year, GB holiday,
    of the _target_ time], [deterministic],
    [horizon (1)], [$h$ in hours], [deterministic],
    [weather day-2 (11)], [previous-run values at the target time,
    lead about 48 h], [run issued at $T + h - 48 "h" lt.eq T$ for all
    $h lt.eq 48$],
    [weather day-1 (11)], [previous-run values, lead about 24 h],
    [admissible only for $h lt.eq 24$; set to missing beyond],
  ),
  caption: [Feature families and their availability rules. The rules are
  enforced in the builder and covered by the poisoning tests.],
) <tbl-features>

== Interval calibration

The raw quantile heads under-covered on validation (0.50 against the nominal
0.80), which is a known weakness of boosted quantile models under
distribution shift. Intervals are therefore conformalized @romano2019cqr per
horizon bucket. A static calibration split turned out not to be enough: its
offsets went stale when the weather regime changed between calibration and
use. The final design recalibrates continuously, taking the offsets for each
issue day from the conformity scores of forecasts that had already matured
by that day (a trailing 30-day window). This uses only information available
at issue time, and it is also exactly what the deployed system can do with
its own scored history. The median is never recalibrated and is trained on
the full window.

== Validation design

Model development used rolling-origin validation inside the training years
only: quarterly folds on 2018-2024 for Track A, and monthly folds on the
short 2024 common window for the ablation, with a 7-day embargo before every
validation window. The sealed test, calendar 2025, was scored once by a
script that refuses to run a second time. The guard proved useful during
development, when it stopped a training run whose final issue had a 48-hour
horizon ending exactly at 2025-01-01 00:00.

== Significance

Half-hourly forecast errors are strongly autocorrelated (lag-24 h ACF 0.74,
@fig-acf), so tests that assume independent errors are not valid here.
Paired comparisons therefore use a moving-block bootstrap
@kunsch1989jackknife with day-length blocks, and Diebold-Mariano
@diebold1995comparing with Bartlett/HAC variance @newey1987simple, with the
truncation lag set to the forecast-horizon MA order and floored at one day.

#figure(
  image("figures/eda_autocorrelation.png", width: 86%),
  caption: [Autocorrelation of half-hourly intensity out to one week. The
  daily and weekly structure is used by the lag features and respected by
  the block-based significance tests.],
) <fig-acf>

== Pilot anchor reproduction

Before any modelling, the data pipeline had to reproduce five anchor numbers
from the earlier pilot study under the same protocol. All five reproduced
within 1.1% (@tbl-anchors).

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
    caption: [Pilot anchors and their reproduction on the fresh pull (MAE on
    calendar 2025, gCO#sub[2]/kWh). The pair count for the stored series
    reproduces exactly, which is a useful end-to-end check of the pipeline.],
  ) <tbl-anchors>
] else [ #pending("anchor reproduction output") ]
The anchor that involves a learned model re-runs one pilot experiment, once,
without any tuning. All genuine model development used validation windows
inside the training years.

// ============================================================================
// 5. Results
// ============================================================================

= Results <results>

== Weather ablation on the clean window

#if ablation != none [
  #let overall = ablation.comparisons.at(0)
  On identical (issue, target) pairs across the monthly validation folds of
  the 2024 common window (n = #overall.n_pairs pairs), adding archived
  weather forecasts moved the validation MAE from #overall.mae_a to
  #overall.mae_b gCO#sub[2]/kWh (#overall.delta_pct%). The block-bootstrap
  and HAC-DM p-values are below 10#super[-4] in every horizon bucket.

  #figure(
    image("figures/ablation.png", width: 86%),
    caption: [Track A and Track B validation MAE by horizon bucket, paired
    on identical issue and target times. Percentages give the change from
    adding weather.],
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

  Calendar 2025 was scored once, on an hourly issue grid
  (#str(sealed.n_pairs) issue-target pairs). @tbl-sealed gives the headline
  metrics and @fig-horizon the per-horizon curves.

  #figure(
    table(
      columns: (auto, auto, auto, auto, auto, auto),
      align: (left, right, right, right, right, right),
      table.header(
        [*model*], [*MAE*], [*1-6 h*], [*7-24 h*], [*25-48 h*], [*coverage 80%*],
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
    caption: [Sealed 2025 metrics (MAE in gCO#sub[2]/kWh; coverage of the
    80% interval after trailing-window conformal calibration).],
  ) <tbl-sealed>

  Several points are worth noting. Track B beats issue-time persistence by
  35.2% overall (28.05 against 43.31; block-bootstrap and HAC-DM p below
  10#super[-5]) and beats Track A by 24.3%, so the ablation result carries
  over to a Track A trained on seven years of data. Track B's error is also
  nearly flat in horizon (27.8 to 28.2 gCO#sub[2]/kWh between the first and
  last bucket), whereas Track A degrades steeply (20.8 to 42.8). Most of the
  long-horizon signal evidently comes from the weather inputs. There is a
  crossover, though: below 6 hours Track A is the better model (20.8 against
  27.8), where recent lags dominate and Track B is limited by its short
  training window. An operational system could switch between the two by
  horizon; the deployed model accepts the short-horizon cost to keep the
  setup simple. Finally, Track B's intervals come out very close to nominal
  coverage (80.0 to 80.3% in every bucket), which is the direct result of
  recalibrating from trailing matured errors.

  #figure(
    image("figures/horizon_curves.png", width: 92%),
    caption: [MAE by horizon on the sealed 2025 year, hourly issue grid. The
    stored NESO series (Leg 1) reflects very short lead times and is shown
    as context, not as a comparable 48-hour baseline.],
  ) <fig-horizon>

  #figure(
    image("figures/calibration.png", width: 72%),
    caption: [Coverage of the 80% interval by horizon bucket on the sealed
    year.],
  ) <fig-calibration>
] else [
  #pending("the one-time sealed evaluation (results/sealed/)")
]

== Operator comparison in three parts

*Part 1: the stored series (context only).* The operator's archived forecast
scores 9.28 gCO#sub[2]/kWh on 2025, which is about three times better than
any 48-hour model in this report. That is expected, and it is the reason the
stored series cannot serve as a 24-48 h baseline: it is revised until
shortly before delivery. It is reported for context and nothing else.

*Part 2: archive vintages at matched issue times.* On 550 hourly captures
from the community archive (July to November 2026, out of sample for models
trained through 2024), Track B is statistically indistinguishable from the
operator's true forward forecasts at longer horizons: 26.39 against 26.49
(-0.4%, DM p = 0.89) at 7-24 h, and 27.70 against 26.47 (+4.6%, p = 0.14) at
25-48 h. Inside 6 hours the operator is clearly better (+21.6%, p below
10#super[-3]), which is expected for a system with near-real-time generation
data. Track A without weather loses to the vintages at every horizon (+47%
overall). The operator's accuracy on its 2023-24 archive months (MAE 18.2 /
24.4 / 26.0 by bucket) is close to its accuracy on the 2026 window, which
supports treating the comparison window as representative.

*Part 3: the project's own logged vintages.* At the time of writing the
logger had captured two forward curves and nothing had matured, so this part
starts at zero by construction. What matters is the accumulation rate. At an
hourly capture cadence and one nightly model forecast per day, roughly 5,000
operator captures (about 0.5 million scored windows) and 200 model forecasts
(about 19,000 windows) will have matured by June 2027, which is more than
enough for bucket-level block inference. The pre-submission refresh rebuilds
this section from whatever has accumulated by then.

#if legs != none [] else [ #pending("operator legs (results/legs/legs.json)") ]

== Continuous self-scoring

#if live != none [
  At the time of this build the pipeline had logged
  #live.vintages.total_captures operator captures since
  #live.vintages.first_capture_utc and scored
  #live.neso_fw48h.scored_windows matured forecast windows. These figures
  update weekly without intervention. This section and the previous one are
  the two that the pre-submission refresh regenerates; the sealed results
  above do not change.
] else [
  #pending("prospective self-scoring summary")
]

// ============================================================================
// 6. The automated evaluation pipeline
// ============================================================================

= The automated evaluation pipeline <instrument>

Time-dependent evidence in this project is collected by scheduled jobs
rather than by hand. Four of them run unattended on repository
infrastructure (GitHub Actions) and write versioned artifacts that both the
application and this report read.

- _vintage-logger_ (hourly, minute 17) captures the operator's forward
  48-hour national curve, about 96 half-hour windows per capture, to a
  dedicated branch. A manifest records capture counts and any gaps, and gaps
  are permanent because vintages cannot be re-requested.
- _nightly-forecast_ (03:07 UTC) issues the deployed model's 48-hour
  probabilistic forecast. It writes a stable JSON file plus a dated copy
  that is never modified afterwards; the dated copies are the project's own
  vintages and are scored as they mature.
- _self-scoring_ (weekly) recomputes, from scratch, the error of every
  matured logged forecast against published actuals, and folds closed months
  of the vintage log into parquet files. Because each run is a full
  recompute, a missed week heals itself on the next run.
- _watchdog_ (daily) opens or updates a "PIPELINE STALE" issue on the
  repository when the last capture is more than 6 hours old or the last
  forecast more than 48 hours old, closes it again once things recover, and
  pushes a keepalive commit if capture activity ever stops for 7 days
  (GitHub disables schedules after 60 days of repository inactivity). Issues
  on one's own repository generate e-mail notifications, so a broken
  pipeline reaches the owner without anyone watching dashboards.

The alert path was tested live on build day with a deliberately failed
capture, a drill that opened a real issue, a recovery run that closed it,
and a normal capture afterwards. For routine monitoring, the logger badge on
the repository README is enough to check about once a month.

// ============================================================================
// 7. Deployment
// ============================================================================

= Deployment

#figure(
  image("figures/architecture.png", width: 94%),
  caption: [All scheduled work runs on repository infrastructure and writes
  versioned artifacts. The application only reads them, so a failed job
  leaves stale data rather than wrong data.],
) <fig-arch>

The public application (#link(data.app_url)) has three pages. The forecast
page shows the model fan chart together with the operator's forward curve
and recent actuals; regional series appear only as labelled operator
forecasts. The evaluation page shows the sealed results and the live
self-scoring counters, with each section appearing once its underlying
artifact exists in the repository. The model card states the data sources,
licences, assumptions, limitations and the split between the evaluated and
the deployed model. The deployed model is a refit of Track B on all data
through the present; every number in this report comes from the
sealed-evaluated models, and the report never cites the deployed one.
Free-tier hosting sleeps when idle and wakes from a button in about thirty
seconds.

#if data.status.fan_example [
  #figure(
    image("figures/fan_example.png", width: 92%),
    caption: [A production forecast as served, issued by the nightly job.],
  )
]

#if data.status.at("app_screenshot", default: false) [
  #figure(
    image("figures/app_forecast.png", width: 86%),
    caption: [The live forecast page, captured from the public URL at report
    build time.],
  )
]

// ============================================================================
// 8. Discussion and limitations
// ============================================================================

= Discussion and limitations

The research question gets a positive answer, with a boundary. A model built
on open data can match the grid operator at 7-48 hour horizons, which are
the horizons that matter for day-ahead load shifting. It cannot match the
operator inside 6 hours, where near-real-time generation telemetry decides
the outcome. The ablation locates the mechanism: forecast vintages, of wind
above all, carry most of the long-horizon signal. The two ablation deltas
(-41.9% on the matched common window, -24.3% against a Track A trained on
seven years) differ for an understandable reason: lag models improve with
more history while weather models improve with better weather, so the
measured weather contribution shrinks as the lags-only baseline gets
stronger. Both numbers are reported with their windows.

Calibration turned out to be the hardest part of the modelling. The raw
quantile heads under-covered badly (0.50), and every static correction
decayed when the regime shifted. Only recalibration from trailing matured
errors, which the automated pipeline produces anyway, held nominal coverage
over a full unseen year. The sealed coverage of 80.2% against a nominal 80%
is in some ways the most important single number in the report.

Further limitations:

- *Attributed, not marginal.* Values follow NESO's average-intensity
  methodology. Shifting load based on this signal is a claim about
  attributed emissions, not a metered or causal one.
- *National scoring only.* No published regional actuals exist, so regional
  accuracy is not knowable from public data and is not claimed.
- *Short weather window.* True forecast vintages begin in March 2024. The
  ablation is powered accordingly, and its window is stated wherever the
  number is cited.
- *Prospective sample size at submission.* Part 3 of the operator comparison
  starts near zero; its value lies in the accumulation that the pipeline
  performs unattended, and the refresh updates only those sections.
- *Revisable actuals.* The operator can revise published actuals. The
  cross-check bounds the effect at roughly 0.04% of windows.

// ============================================================================
// 9. Ethics, licensing, reproducibility
// ============================================================================

= Ethics, licensing and reproducibility

All data are public and contain no personal information. NESO data are used
under CC BY 4.0 with attribution @neso2026api, Open-Meteo under CC BY 4.0 on
the non-commercial tier @zippenfenig2023openmeteo, and the community vintage
archive under MIT @powell2023cift. The project code is MIT licensed. The
deployed application and the report both carry attribution, and the
application is labelled as an independent research project.

For reproducibility, dependencies are pinned through a lockfile, seeds are
fixed, and every raw artifact has a manifest entry with a content hash.
Every number reported here traces to a committed artifact and can be
regenerated from the repository with `make report`. The pre-submission
refresh (`make refresh`) regenerates only the prospective sections and
leaves the sealed results untouched.

// ============================================================================
// 10. Future work
// ============================================================================

= Future work

The second semester builds on this system directly: a carbon-aware task
scheduler (duration and deadline in, recommended start window out) consuming
the forecast JSON, evaluated in simulation against run-now and
hindsight-optimal policies using the vintage archive that is accumulating in
the meantime, including a usefully sized Part 3 of the operator comparison.
On the forecasting side, the obvious next steps are freshest-run weather
features (removing the conservative lead-time margin), a horizon-switched
blend of the two tracks, regional modelling if regional actuals are ever
published, and interval methods that adapt faster to regime changes.

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
  subsampling, seed 42), three quantile heads (0.1 / 0.5 / 0.9), and a
  trailing conformal window of 30 days with day-level updates. The
  sealed-eval runs are Track A `#sealed.models.track_a.run` (trained
  2018-01-01 to 2024-12-29, two-hourly issues) and Track B
  `#sealed.models.track_b.run` (trained 2024-04-01 to 2024-12-29, hourly
  issues). The deployed model is a tagged refit of Track B through the
  present; the report does not cite it. Every run directory under `runs/`
  stores its full configuration, feature list, git hash and metrics as JSON.
]

#heading(numbering: none)[Appendix C: decisions log]

The repository file `docs/decisions.md` records the material decisions and
the deviations from the product requirements and design references, one line
each, dated.

#pagebreak()
#bibliography("refs.bib", style: "apa", title: "References")