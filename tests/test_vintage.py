import csv
import json

from gbcarbon import vintage

ROWS = [
    ("2026-11-21T09:30Z", "2026-11-21T10:00Z", 226),
    ("2026-11-21T10:00Z", "2026-11-21T10:30Z", 230),
    ("2026-11-21T10:30Z", "2026-11-21T11:00Z", None),
]


def read_csv(path):
    with open(path, newline="") as handle:
        return list(csv.reader(handle))


def test_write_capture_appends_single_header(tmp_path):
    first = vintage.write_capture(tmp_path, "2026-11-21T09:17Z", ROWS)
    second = vintage.write_capture(tmp_path, "2026-11-21T10:17Z", ROWS)
    assert first == second  # same capture date, same daily file
    content = read_csv(first)
    assert content[0] == vintage.CSV_HEADER
    assert len(content) == 1 + 2 * len(ROWS)
    assert content[3][3] == ""  # missing forecast stored as empty string


def test_new_day_gets_new_file(tmp_path):
    a = vintage.write_capture(tmp_path, "2026-11-21T23:17Z", ROWS)
    b = vintage.write_capture(tmp_path, "2026-11-22T00:17Z", ROWS)
    assert a != b


def test_manifest_counts_and_gap_detection(tmp_path):
    vintage.update_manifest(tmp_path, "2026-11-21T09:17Z", 96)
    manifest = vintage.update_manifest(tmp_path, "2026-11-21T10:17Z", 96)
    assert manifest["total_captures"] == 2
    assert manifest["gaps"] == []  # one-hour cadence is not a gap

    manifest = vintage.update_manifest(tmp_path, "2026-11-21T14:17Z", 96)
    assert len(manifest["gaps"]) == 1
    gap = manifest["gaps"][0]
    assert gap["after"] == "2026-11-21T10:17Z"
    assert gap["hours"] == 4.0

    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk["total_captures"] == 3
