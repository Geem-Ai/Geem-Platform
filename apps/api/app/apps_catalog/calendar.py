"""Calendar-month arithmetic for App subscriptions (Phase 9B).

Anniversary periods — not usage-meter month windows.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone


def ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def add_calendar_months(moment: datetime, months: int) -> datetime:
    """Add whole calendar months, clamping day to the target month's last day.

    Examples (UTC):
    * 2026-01-31 + 1 → 2026-02-28
    * 2026-08-17 + 1 → 2026-09-17
    """
    dt = ensure_utc(moment)
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def initial_period(now: datetime) -> tuple[datetime, datetime]:
    start = ensure_utc(now)
    return start, add_calendar_months(start, 1)


def compute_renewal_period(
    *,
    current_period_start: datetime,
    current_period_end: datetime,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Return (period_start, period_end) after a successful renewal payment.

    Active (current_end > now): keep start, extend end by one calendar month.
    Expired (current_end <= now): fresh period from now.
    """
    moment = ensure_utc(now)
    end = ensure_utc(current_period_end)
    if end > moment:
        return ensure_utc(current_period_start), add_calendar_months(end, 1)
    start = moment
    return start, add_calendar_months(start, 1)
