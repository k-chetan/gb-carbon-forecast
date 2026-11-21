from datetime import UTC, datetime, timedelta

from gbcarbon.watchdog import assess

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def test_fresh_capture_is_ok():
    ok, lines = assess(NOW, NOW - timedelta(hours=1), 6.0, None)
    assert ok
    assert any("forecast job not live yet" in line for line in lines)


def test_old_capture_is_stale():
    ok, lines = assess(NOW, NOW - timedelta(hours=7), 6.0, None)
    assert not ok
    assert "7.0 h ago" in lines[0]


def test_zero_threshold_forces_alert_path():
    ok, _ = assess(NOW, NOW - timedelta(minutes=10), 0.0, None)
    assert not ok


def test_missing_capture_is_stale():
    ok, lines = assess(NOW, None, 6.0, None)
    assert not ok
    assert "no vintage capture" in lines[0]


def test_old_forecast_is_stale_once_live():
    ok, _ = assess(NOW, NOW - timedelta(hours=1), 6.0, NOW - timedelta(hours=50))
    assert not ok
    ok, _ = assess(NOW, NOW - timedelta(hours=1), 6.0, NOW - timedelta(hours=20))
    assert ok
