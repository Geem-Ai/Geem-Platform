"""Celery tasks for daily usage rollups and partition maintenance (Phase 11B/11C).

Beat (UTC):

* 00:10 — rollup yesterday + day-before-yesterday
* 00:20 — ensure current + future partitions
* 00:30 — drop partitions older than USAGE_EVENTS_RETENTION_MONTHS
"""

from __future__ import annotations

import logging
from datetime import timedelta

from app.db.session import SessionLocal
from app.usage.partitions import UsagePartitionService
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


_RETRY = {
    "bind": True,
    "max_retries": 3,
    "autoretry_for": (Exception,),
    "dont_retry_for": (ValueError,),
    "retry_backoff": True,
    "retry_jitter": True,
    "retry_backoff_max": 120,
}


@celery_app.task(name="rollup_usage_daily", **_RETRY)
def rollup_usage_daily(
    self,
    day: str | None = None,
    start_day: str | None = None,
    end_day: str | None = None,
    recent_days: int | None = None,
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
        elif recent_days:
            n = max(1, int(recent_days))
            today = utc_today()
            days = [today - timedelta(days=offset) for offset in range(1, n + 1)]
            results = [svc.rollup_day(item) for item in days]
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
        logger.info(
            "usage.rollup.task_done",
            extra={"row_count": payload["row_count"], "event_count": payload["event_count"]},
        )
        return payload
    except Exception:
        db.rollback()
        logger.exception("usage.rollup.task_failed")
        raise
    finally:
        db.close()


@celery_app.task(name="ensure_usage_event_partitions", **_RETRY)
def ensure_usage_event_partitions(self) -> dict:
    db = SessionLocal()
    try:
        result = UsagePartitionService(db).ensure_write_window()
        db.commit()
        payload = {
            "checked": result.checked,
            "created": result.created,
            "existing": result.existing,
            "task_id": getattr(self.request, "id", None),
        }
        logger.info(
            "usage.partitions.task_ensure_done",
            extra={
                "checked_months": result.checked,
                "created_partitions": result.created,
                "existing_partitions": result.existing,
            },
        )
        return payload
    except Exception:
        db.rollback()
        logger.exception("usage.partitions.task_ensure_failed")
        raise
    finally:
        db.close()


@celery_app.task(name="retain_usage_event_partitions", **_RETRY)
def retain_usage_event_partitions(self) -> dict:
    db = SessionLocal()
    try:
        result = UsagePartitionService(db).drop_expired()
        db.commit()
        payload = {
            "cutoff": result.cutoff,
            "inspected": result.inspected,
            "dropped": result.dropped,
            "skipped": result.skipped,
            "task_id": getattr(self.request, "id", None),
        }
        logger.info(
            "usage.partitions.task_retention_done",
            extra={
                "retention_cutoff": result.cutoff,
                "inspected_partitions": result.inspected,
                "dropped_partitions": result.dropped,
            },
        )
        return payload
    except Exception:
        db.rollback()
        logger.exception("usage.partitions.task_retention_failed")
        raise
    finally:
        db.close()
