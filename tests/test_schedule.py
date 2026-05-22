"""Daily scheduler helpers."""

from __future__ import annotations

from schedule_daily_report import _seconds_until


def test_seconds_until_positive():
    secs = _seconds_until(0, 0, "UTC")
    assert 0 < secs <= 86400
