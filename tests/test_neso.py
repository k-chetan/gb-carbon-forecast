import json
from pathlib import Path

from gbcarbon import neso

FIXTURE = Path(__file__).parent / "fixtures" / "fw48h_sample.json"


def load_fixture() -> list[dict]:
    return json.loads(FIXTURE.read_text())["data"]


def test_parse_windows_shape():
    rows = neso.parse_windows(load_fixture())
    assert len(rows) == 96  # 48 hours of half-hour windows
    for window_start, window_end, forecast in rows:
        assert window_start.endswith("Z") and window_end.endswith("Z")
        assert forecast is None or isinstance(forecast, int)


def test_windows_are_contiguous_and_ordered():
    rows = neso.parse_windows(load_fixture())
    for (_, end_a, _), (start_b, _, _) in zip(rows, rows[1:], strict=False):
        assert end_a == start_b


def test_parse_ts_roundtrip():
    stamp = "2026-11-21T09:30Z"
    parsed = neso.parse_ts(stamp)
    assert parsed.strftime(neso.TS_FMT) == stamp
    assert parsed.tzinfo is not None
