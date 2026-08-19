"""Database-side daily rollups of API-attributed usage_events (Phase 11B).

Replace-per-day: DELETE the UTC calendar day, then INSERT … SELECT … GROUP BY.
Safe to retry; does not add onto previous totals. Does not load event rows
into Python. Platform/non-tenant events (``workspace_id IS NULL``) and
internal Workspace Chat (``api_key_id IS NULL``) are excluded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import BigInteger, Date, cast, delete, func, insert, literal, select
from sqlalchemy.orm import Session

from app.db.models import UsageEvent
from app.usage.event_tokens import billed_tokens_expr
from app.usage.models import UsageDailyWorkspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RollupDayResult:
    day: date
    rows: int
    event_count: int
    billed_tokens: int
    workspaces: int


def utc_today(now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).date()


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def parse_iso_day(raw: str) -> date:
    return date.fromisoformat(raw.strip())


class UsageDailyRollupService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def rollup_day(self, day: date) -> RollupDayResult:
        start, end = utc_day_bounds(day)
        billed = billed_tokens_expr()
        self.db.execute(delete(UsageDailyWorkspace).where(UsageDailyWorkspace.day == day))
        table = UsageDailyWorkspace.__table__
        self.db.execute(
            insert(table).from_select(
                [
                    "id",
                    "workspace_id",
                    "day",
                    "api_key_id",
                    "event_count",
                    "billed_tokens",
                    "input_tokens",
                    "output_tokens",
                ],
                select(
                    func.gen_random_uuid(),
                    UsageEvent.workspace_id,
                    literal(day, type_=Date),
                    UsageEvent.api_key_id,
                    func.count(),
                    func.coalesce(func.sum(billed), 0),
                    func.coalesce(
                        func.sum(func.coalesce(cast(UsageEvent.input_tokens, BigInteger), 0)),
                        0,
                    ),
                    func.coalesce(
                        func.sum(func.coalesce(cast(UsageEvent.output_tokens, BigInteger), 0)),
                        0,
                    ),
                )
                .where(
                    UsageEvent.workspace_id.is_not(None),
                    UsageEvent.api_key_id.is_not(None),
                    UsageEvent.created_at >= start,
                    UsageEvent.created_at < end,
                )
                .group_by(UsageEvent.workspace_id, UsageEvent.api_key_id),
            )
        )
        stats = self.db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(UsageDailyWorkspace.event_count), 0),
                func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0),
                func.count(func.distinct(UsageDailyWorkspace.workspace_id)),
            ).where(UsageDailyWorkspace.day == day)
        ).one()
        result = RollupDayResult(
            day=day,
            rows=int(stats[0] or 0),
            event_count=int(stats[1] or 0),
            billed_tokens=int(stats[2] or 0),
            workspaces=int(stats[3] or 0),
        )
        logger.info(
            "usage.rollup.day",
            extra={
                "day": day.isoformat(),
                "rows": result.rows,
                "event_count": result.event_count,
                "billed_tokens": result.billed_tokens,
                "workspaces": result.workspaces,
            },
        )
        return result

    def rollup_range(self, start_day: date, end_day: date) -> list[RollupDayResult]:
        """Inclusive UTC date range, one day at a time."""
        if end_day < start_day:
            raise ValueError("end_day must be on or after start_day")
        results: list[RollupDayResult] = []
        day = start_day
        while day <= end_day:
            results.append(self.rollup_day(day))
            logger.info(
                "usage.rollup.progress",
                extra={"day": day.isoformat(), "rows": results[-1].rows},
            )
            day += timedelta(days=1)
        return results

    def backfill(self, start_day: date, end_day: date) -> list[RollupDayResult]:
        logger.info(
            "usage.rollup.backfill_start",
            extra={"start_day": start_day.isoformat(), "end_day": end_day.isoformat()},
        )
        results = self.rollup_range(start_day, end_day)
        logger.info(
            "usage.rollup.backfill_done",
            extra={
                "days": len(results),
                "rows": sum(item.rows for item in results),
                "billed_tokens": sum(item.billed_tokens for item in results),
            },
        )
        return results
