"""Phase 5A — UTC period boundary calculations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.usage.periods import (
    NaiveDatetimeError,
    PeriodType,
    current_period,
    period_containing,
    require_aware_utc,
)


def test_rejects_naive_datetime() -> None:
    naive = datetime(2026, 8, 13, 12, 0, 0)
    with pytest.raises(NaiveDatetimeError):
        period_containing(naive, PeriodType.DAILY)
    with pytest.raises(NaiveDatetimeError):
        require_aware_utc(naive)


def test_daily_period_midnight_boundary() -> None:
    before = datetime(2026, 8, 13, 23, 59, 59, tzinfo=timezone.utc)
    start = datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)
    window_before = period_containing(before, PeriodType.DAILY)
    window_start = period_containing(start, PeriodType.DAILY)
    assert window_before.start == datetime(2026, 8, 13, tzinfo=timezone.utc)
    assert window_before.end == start
    assert window_before.contains(before)
    assert not window_before.contains(start)
    assert window_start.start == start
    assert window_start.end == datetime(2026, 8, 15, tzinfo=timezone.utc)


def test_daily_converts_offset_to_utc() -> None:
    # 2026-08-14 00:30 +03:00 == 2026-08-13 21:30 UTC → 13th daily window.
    local = datetime(2026, 8, 14, 0, 30, tzinfo=timezone(timedelta(hours=3)))
    window = period_containing(local, PeriodType.DAILY)
    assert window.start == datetime(2026, 8, 13, tzinfo=timezone.utc)
    assert window.end == datetime(2026, 8, 14, tzinfo=timezone.utc)


def test_weekly_iso_monday_boundary() -> None:
    # 2026-08-10 is Monday; 2026-08-09 is Sunday of the previous ISO week.
    sunday = datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc)
    monday = datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)
    prev = period_containing(sunday, PeriodType.WEEKLY)
    nxt = period_containing(monday, PeriodType.WEEKLY)
    assert prev.start == datetime(2026, 8, 3, tzinfo=timezone.utc)
    assert prev.end == monday
    assert nxt.start == monday
    assert nxt.end == datetime(2026, 8, 17, tzinfo=timezone.utc)
    assert prev.contains(sunday)
    assert not prev.contains(monday)


def test_weekly_midweek() -> None:
    thursday = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
    window = period_containing(thursday, PeriodType.WEEKLY)
    assert window.start == datetime(2026, 8, 10, tzinfo=timezone.utc)
    assert window.end == datetime(2026, 8, 17, tzinfo=timezone.utc)
    assert window.contains(thursday)


def test_monthly_end_of_month_and_year() -> None:
    jan31 = datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc)
    feb1 = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
    dec31 = datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)
    jan_window = period_containing(jan31, PeriodType.MONTHLY)
    feb_window = period_containing(feb1, PeriodType.MONTHLY)
    dec_window = period_containing(dec31, PeriodType.MONTHLY)
    assert jan_window.start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert jan_window.end == feb1
    assert not jan_window.contains(feb1)
    assert feb_window.start == feb1
    assert feb_window.end == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert dec_window.start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert dec_window.end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_monthly_february_non_leap() -> None:
    feb28 = datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)
    window = period_containing(feb28, PeriodType.MONTHLY)
    assert window.start == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert window.end == datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_monthly_february_leap() -> None:
    feb29 = datetime(2028, 2, 29, 23, 59, tzinfo=timezone.utc)
    window = period_containing(feb29, PeriodType.MONTHLY)
    assert window.start == datetime(2028, 2, 1, tzinfo=timezone.utc)
    assert window.end == datetime(2028, 3, 1, tzinfo=timezone.utc)


def test_current_period_uses_now() -> None:
    now = datetime(2026, 8, 13, 4, 5, 6, tzinfo=timezone.utc)
    window = current_period(PeriodType.DAILY, now=now)
    assert window.start == datetime(2026, 8, 13, tzinfo=timezone.utc)
