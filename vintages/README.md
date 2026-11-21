# Vintage log

Captures of NESO's forward 48 h national carbon-intensity forecast
(`/intensity/{from}/fw48h`), taken hourly at minute 17 by the
`vintage-logger` GitHub Action on `main`.

## Layout

- `vintages/daily/YYYY-MM-DD.csv` - one file per capture date (UTC), appended
  hourly. Columns: `capture_utc, window_start, window_end, forecast`.
- `vintages/monthly/YYYY-MM.parquet` - closed months, compacted weekly.
- `vintages/manifest.json` - last capture, totals, and any recorded gaps.

## Gaps

Each capture records what the operator published at that moment. A missed
hour cannot be requested again later, so gaps stay in the record and are
listed in the manifest.
