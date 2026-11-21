# Vintage log

Point-in-time captures of NESO's forward 48 h national carbon-intensity
forecast (`/intensity/{from}/fw48h`), taken hourly at minute 17 by the
`vintage-logger` GitHub Action on `main`.

## Layout

- `vintages/daily/YYYY-MM-DD.csv` — one file per capture date (UTC), appended
  hourly. Columns: `capture_utc, window_start, window_end, forecast`.
- `vintages/monthly/YYYY-MM.parquet` — weekly compaction of closed days.
- `vintages/manifest.json` — last capture, totals, and recorded gaps.

## Permanence

A vintage is what the operator published at capture time. A missed hour can
never be re-requested, so gaps are permanent and are recorded in the manifest
rather than hidden.
