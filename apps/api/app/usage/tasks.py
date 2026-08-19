"""Celery tasks for daily usage rollups (Phase 11B).

Not registered on Celery Beat in this slice — invoke manually:

    celery -A app.worker.celery_app call rollup_usage_daily
    celery -A app.worker.celery_app call rollup_usage_daily --args='["2026-08-18"]'
    celery -A app.worker.celery_app call rollup_usage_daily --kwargs='{"start_day":"2026-07-01","end_day":"2026-08-18"}'

Default with no dates: yesterday UTC (the last completed calendar day).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from app.db.session import SessionLocal
from app.usage.rollup import UsageDailyRollupService, parse_iso_day, utc_today
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _as_dicts(results) -> list[dict]:
    return [
        {
            "day": item.day.isoformat(),
            "rows": item.rows,
            "event_count": item.event_count,
            "billed_tokens": item.billed_tokens,
            "workspaces": item.workspaces,
        }
        for item in results
    ]


@celery_app.task(name="rollup_usage_daily", bind=True, max_retries=3)
def rollup_usage_daily(
    self,
    day: str | None = None,
    start_day: str | None = None,
    end_day: str | None = None,
) -> dict:
    db = SessionLocal()
    try:
        svc = UsageDailyRollupService(db)
        if start_day or end_day:
            if not start_day or not end_day:
                raise ValueError("start_day and end_day must be provided together")
            results = svc.backfill(parse_iso_day(start_day), parse_iso_day(end_day))
        elif day:
            results = [svc.rollup_day(parse_iso_day(day))]
        else:
            results = [svc.rollup_day(utc_today() - timedelta(days=1))]
        db.commit()
        payload = {
            "days": _as_dicts(results),
            "row_count": sum(item.rows for item in results),
            "event_count": sum(item.event_count for item in results),
            "billed_tokens": sum(item.billed_tokens for item in results),
            "task_id": getattr(self.request, "id", None),
        }
        logger.info("usage.rollup.task_done", extra={k: payload[k] for k in ("row_count", "event_count")})
        return payload
    except Exception:
        db.rollback()
        logger.exception("usage.rollup.task_failed")
        raise
    finally:
        db.close()
