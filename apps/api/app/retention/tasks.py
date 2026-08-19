"""Celery tasks for soft-delete retention purge (Phase 11A).

Not registered on Celery Beat in this slice — invoke manually in development:

    celery -A app.worker.celery_app call purge_deleted_conversations
    celery -A app.worker.celery_app call purge_deleted_experts
    celery -A app.worker.celery_app call purge_deleted_workspaces

Or from a Python shell with a worker running:

    from app.retention.tasks import purge_deleted_workspaces
    purge_deleted_workspaces.delay()
"""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.retention.service import RetentionPurgeService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(method_name: str, *, limit: int | None = None) -> dict:
    db = SessionLocal()
    try:
        svc = RetentionPurgeService(db)
        method = getattr(svc, method_name)
        result = method(limit=limit) if limit is not None else method()
        return result.as_dict()
    except Exception:
        db.rollback()
        logger.exception("retention.task_failed", extra={"method": method_name})
        raise
    finally:
        db.close()


@celery_app.task(name="purge_deleted_conversations", bind=True, max_retries=1)
def purge_deleted_conversations(self, limit: int | None = None) -> dict:
    payload = _run("purge_deleted_conversations", limit=limit)
    payload["task_id"] = getattr(self.request, "id", None)
    return payload


@celery_app.task(name="purge_deleted_experts", bind=True, max_retries=1)
def purge_deleted_experts(self, limit: int | None = None) -> dict:
    payload = _run("purge_deleted_experts", limit=limit)
    payload["task_id"] = getattr(self.request, "id", None)
    return payload


@celery_app.task(name="purge_deleted_workspaces", bind=True, max_retries=1)
def purge_deleted_workspaces(self, limit: int | None = None) -> dict:
    payload = _run("purge_deleted_workspaces", limit=limit)
    payload["task_id"] = getattr(self.request, "id", None)
    return payload
