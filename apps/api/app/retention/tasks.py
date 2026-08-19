"""Celery tasks for soft-delete retention purge (Phase 11A / 11D).

Beat (UTC), offset from usage maintenance at 00:10/00:20/00:30:

* 01:00 — purge_deleted_conversations
* 01:15 — purge_deleted_experts
* 01:30 — purge_deleted_workspaces

``SOFT_DELETE_RETENTION_DAYS`` remains authoritative. Tasks are idempotent.
"""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.retention.service import RetentionPurgeService
from app.worker.celery_app import celery_app
from app.observability.tracing import start_span

logger = logging.getLogger(__name__)


_SPAN = {
    "purge_deleted_conversations": "conversation.purge",
    "purge_deleted_experts": "expert.purge",
    "purge_deleted_workspaces": "workspace.purge",
}


def _run(method_name: str, *, limit: int | None = None) -> dict:
    with start_span(_SPAN.get(method_name, "lifecycle.purge")):
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
