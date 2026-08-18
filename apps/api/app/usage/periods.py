"""Deterministic UTC period boundaries for usage counters.

Internal clock is always timezone-aware UTC. Naive datetimes are rejected.
There is no Workspace timezone abstraction yet.

Weekly periods follow the KSA calendar week: Saturday 00:00:00 UTC inclusive
through the following Saturday exclusive (Friday is the last included day).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class PeriodType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class NaiveDatetimeError(ValueError):
    """Raised when a naive datetime is supplied to period utilities."""


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    period_type: PeriodType
    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        aware = require_aware_utc(moment)
        return self.start <= aware < self.end


def require_aware_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise NaiveDatetimeError("Period calculations require a timezone-aware datetime.")
    return moment.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def period_containing(moment: datetime, period_type: PeriodType | str) -> PeriodWindow:
    aware = require_aware_utc(moment)
    parsed = PeriodType(period_type) if not isinstance(period_type, PeriodType) else period_type
    if parsed == PeriodType.DAILY:
        return _daily(aware)
    if parsed == PeriodType.WEEKLY:
        return _weekly(aware)
    if parsed == PeriodType.MONTHLY:
        return _monthly(aware)
    raise ValueError(f"Unsupported period type: {parsed}")


def current_period(period_type: PeriodType | str, *, now: datetime | None = None) -> PeriodWindow:
    return period_containing(now or utcnow(), period_type)


def _daily(moment: datetime) -> PeriodWindow:
    start = datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc)
    return PeriodWindow(PeriodType.DAILY, start, start + timedelta(days=1))


# Python weekday(): Monday=0 … Saturday=5, Sunday=6.
_KSA_WEEK_START_WEEKDAY = 5


def _weekly(moment: datetime) -> PeriodWindow:
    """KSA week: Saturday 00:00 UTC → next Saturday 00:00 UTC."""
    day_start = datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc)
    days_since_saturday = (day_start.weekday() - _KSA_WEEK_START_WEEKDAY) % 7
    start = day_start - timedelta(days=days_since_saturday)
    return PeriodWindow(PeriodType.WEEKLY, start, start + timedelta(days=7))


def _monthly(moment: datetime) -> PeriodWindow:
    start = datetime(moment.year, moment.month, 1, tzinfo=timezone.utc)
    if moment.month == 12:
        end = datetime(moment.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(moment.year, moment.month + 1, 1, tzinfo=timezone.utc)
    return PeriodWindow(PeriodType.MONTHLY, start, end)
