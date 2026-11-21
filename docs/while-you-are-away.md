# While you are away

Everything time-dependent runs by itself on GitHub Actions. The vintage
logger saves NESO's forward 48 h forecast every hour at minute 17. The
nightly job issues the model's own 48 h forecast at 03:07 UTC. Self-scoring
runs every Sunday and re-scores whatever has matured, and a daily watchdog
checks that captures and forecasts are fresh.

If something goes stale, the watchdog opens a GitHub issue called
**PIPELINE STALE** on the repo. GitHub emails you about issues on your own
repository, so a broken pipeline shows up in your inbox. The watchdog closes
the issue itself when things recover. A keepalive commit stops GitHub from
disabling the schedules during long quiet periods.

The one thing worth checking roughly once a month is the `vintage-logger`
badge at the top of the README. Green means the pipeline is alive and the
comparison data is still growing.

Before submission, run `make refresh` (see the README) to re-score the
prospective comparisons with everything collected since the build and
rebuild the report. The frozen sealed-test results do not change.
