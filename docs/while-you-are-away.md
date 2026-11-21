# While you are away

Everything time-dependent runs by itself on GitHub Actions: the **vintage
logger** captures NESO's forward 48 h forecast every hour at minute 17; the
**nightly forecast** job issues the model's 48 h forecast at 03:07 UTC once a
model is deployed; **self-scoring** re-scores everything that has matured every
Sunday and compacts the vintage log; and the **watchdog** checks daily that
captures and forecasts are fresh. If anything goes stale, the watchdog opens a
GitHub issue titled **PIPELINE STALE** on the repository — GitHub e-mails you
about issues on your own repo, so a broken pipeline reaches your inbox without
anyone watching. It closes the issue itself when things recover, and a
keepalive commit prevents GitHub from disabling the schedules during long
quiet spells.

**The one thing to glance at monthly:** the `vintage-logger` badge at the top
of the README — green means the instrument is alive and the evidence base is
still growing.

**Before submission:** run `make refresh` (see README) to re-score the
prospective legs with everything accumulated since the build and rebuild the
report; the frozen sealed-test results do not change.
