"""Celery orchestration for connector sync / webhook heavy work (Phase 9C)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.common.tenant_context import tenant_context
from app.connectors.sanitize import sanitize_error_message
from app.connectors.types import SyncRunStatus
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return uuid.UUID(str(value))


def enqueue_connector_sync(
    *,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> None:
    run_connector_sync.delay(
        str(workspace_id),
        str(connection_id),
        str(sync_run_id),
        str(actor_id) if actor_id else None,
    )


def enqueue_connector_webhook_work(payload: dict[str, Any]) -> None:
    """Enqueue heavy webhook follow-up — no inline download/OCR/RAG."""
    process_connector_webhook_event.delay(payload)


def _mark_sync_run_failed(
    *,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    error_code: str,
    error_message: str | None,
) -> None:
    """Best-effort finalize so orphaned pending/running runs cannot block forever."""
    db = SessionLocal()
    try:
        from app.connectors.models import ConnectorSyncRun

        run = db.get(ConnectorSyncRun, sync_run_id)
        if (
            run is None
            or run.workspace_id != workspace_id
            or run.app_connection_id != connection_id
        ):
            return
        if run.status not in {
            SyncRunStatus.PENDING.value,
            SyncRunStatus.RUNNING.value,
        }:
            return
        run.status = SyncRunStatus.FAILED.value
        run.error_code = error_code
        run.error_message = sanitize_error_message(error_message)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "connector_sync_failed",
            extra={
                "workspace_id": str(workspace_id),
                "connection_id": str(connection_id),
                "sync_run_id": str(sync_run_id),
                "error_code": error_code,
            },
        )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception(
            "connector_sync_fail_mark_error",
            extra={
                "workspace_id": str(workspace_id),
                "connection_id": str(connection_id),
                "sync_run_id": str(sync_run_id),
            },
        )
    finally:
        db.close()


@celery_app.task(name="run_connector_sync", bind=True, max_retries=2)
def run_connector_sync(
    self,
    workspace_id: str,
    connection_id: str,
    sync_run_id: str,
    actor_id: str | None = None,
) -> dict:
    """Execute a sync run with explicit Workspace tenant context."""
    ws_id = _parse_uuid(workspace_id)
    conn_id = _parse_uuid(connection_id)
    run_id = _parse_uuid(sync_run_id)
    act_id = _parse_uuid(actor_id)
    if ws_id is None or conn_id is None or run_id is None:
        raise AppError(
            ErrorCategory.VALIDATION,
            "workspace_id, connection_id, and sync_run_id are required.",
        )

    db = SessionLocal()
    try:
        with tenant_context(
            workspace_id=ws_id,
            actor_id=act_id,
            request_id=getattr(self.request, "id", None),
        ):
            from app.connectors.sync import ConnectorSyncService

            run = ConnectorSyncService(db).execute_sync_run(
                workspace_id=ws_id,
                connection_id=conn_id,
                sync_run_id=run_id,
                actor_id=act_id,
            )
            db.commit()
            return {
                "workspace_id": str(ws_id),
                "connection_id": str(conn_id),
                "sync_run_id": str(run.id),
                "status": run.status,
            }
    except Exception as exc:
        db.rollback()
        retries = int(getattr(self.request, "retries", 0) or 0)
        max_retries = int(getattr(self, "max_retries", 0) or 0)
        # Finalize only when Celery will not retry — otherwise leave pending/running
        # for the next attempt. On the last attempt, clear the slot.
        if retries >= max_retries:
            code = (
                exc.category.value
                if isinstance(exc, AppError)
                else ErrorCategory.CONNECTOR_CONNECTION_FAILED.value
            )
            _mark_sync_run_failed(
                workspace_id=ws_id,
                connection_id=conn_id,
                sync_run_id=run_id,
                error_code=code,
                error_message=str(exc),
            )
        raise
    finally:
        db.close()


@celery_app.task(name="process_connector_webhook_event", bind=True, max_retries=3)
def process_connector_webhook_event(self, payload: dict[str, Any]) -> dict:
    """Placeholder heavy-work handler — providers fill in during 9D–9F."""
    ws_id = _parse_uuid(payload.get("workspace_id"))
    conn_id = _parse_uuid(payload.get("connection_id"))
    if ws_id is None or conn_id is None:
        return {"status": "ignored", "reason": "missing_tenant"}

    db = SessionLocal()
    try:
        with tenant_context(
            workspace_id=ws_id,
            request_id=getattr(self.request, "id", None),
        ):
            from app.connectors.models import ConnectorWebhookEvent
            from app.connectors.types import WebhookEventStatus

            event_id = _parse_uuid(payload.get("webhook_event_id"))
            if event_id is not None:
                event = db.get(ConnectorWebhookEvent, event_id)
                if event is not None and event.workspace_id == ws_id:
                    event.status = WebhookEventStatus.PROCESSED.value
                    event.processed_at = datetime.now(timezone.utc)
                    db.commit()
            logger.info(
                "connector_webhook_processed",
                extra={
                    "workspace_id": str(ws_id),
                    "connection_id": str(conn_id),
                    "webhook_event_id": str(event_id) if event_id else None,
                },
            )
            return {
                "workspace_id": str(ws_id),
                "connection_id": str(conn_id),
                "status": "processed",
            }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
