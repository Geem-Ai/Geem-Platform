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
            public_message = (
                str(exc.message)
                if isinstance(exc, AppError)
                else "Synchronization failed. Please try again."
            )
            _mark_sync_run_failed(
                workspace_id=ws_id,
                connection_id=conn_id,
                sync_run_id=run_id,
                error_code=code,
                error_message=public_message,
            )
            logger.exception(
                "connector_sync_task_failed",
                extra={
                    "workspace_id": str(ws_id),
                    "connection_id": str(conn_id),
                    "sync_run_id": str(run_id),
                    "error_code": code,
                },
            )
        raise
    finally:
        db.close()


@celery_app.task(name="process_connector_webhook_event", bind=True, max_retries=3)
def process_connector_webhook_event(self, payload: dict[str, Any]) -> dict:
    """Heavy webhook follow-up — enqueue coalesced sync for knowledge connectors."""
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
            from app.connectors.registry import connector_registry
            from app.connectors.sync import ConnectorSyncService
            from app.connectors.types import WebhookEventStatus

            connector_key = str(payload.get("connector_key") or "")
            sync_run_id = None
            caps = connector_registry.capabilities(connector_key)
            if caps is not None and caps.supports_sync and caps.supports_webhooks:
                out = ConnectorSyncService(db).request_webhook_sync(
                    workspace_id=ws_id,
                    connection_id=conn_id,
                    enqueue=True,
                )
                if out is not None:
                    sync_run_id = str(out.id)

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
                    "sync_run_id": sync_run_id,
                },
            )
            return {
                "workspace_id": str(ws_id),
                "connection_id": str(conn_id),
                "status": "processed",
                "sync_run_id": sync_run_id,
            }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="renew_google_drive_watches", bind=True)
def renew_google_drive_watches(self) -> dict:
    """Renew Google Drive changes.watch channels nearing expiry (~every 6h)."""
    from app.common.crypto import decrypt_secret
    from app.connectors.credentials import ConnectorCredentialService
    from app.connectors.models import AppConnection
    from app.connectors.providers.google_drive.client import GoogleDriveClient
    from app.connectors.providers.google_drive.token import ensure_fresh_access
    from app.connectors.providers.google_drive.watch import (
        ensure_changes_watch,
        watch_needs_renewal,
    )
    from app.connectors.types import CONNECTION_USABLE_STATUSES
    from app.core.config import get_settings
    from sqlalchemy import select

    settings = get_settings()
    if not settings.google_drive_configured:
        return {"status": "skipped", "reason": "not_configured"}

    db = SessionLocal()
    renewed = 0
    skipped = 0
    failed = 0
    try:
        rows = list(
            db.scalars(
                select(AppConnection).where(
                    AppConnection.connector_key == "google_drive",
                    AppConnection.status.in_(list(CONNECTION_USABLE_STATUSES)),
                )
            ).all()
        )
        cred_svc = ConnectorCredentialService(db, settings=settings)
        for row in rows:
            with tenant_context(workspace_id=row.workspace_id):
                state = cred_svc.get_sync_state(row) or {}
                if not watch_needs_renewal(state):
                    skipped += 1
                    continue
                page_token = state.get("start_page_token")
                if not page_token or not row.webhook_routing_token_encrypted:
                    skipped += 1
                    continue
                credentials = cred_svc.get_credentials(row)
                if not credentials:
                    skipped += 1
                    continue
                try:
                    fresh = ensure_fresh_access(db, row, credentials, settings)
                    routing = decrypt_secret(
                        row.webhook_routing_token_encrypted, settings=settings
                    )
                    client = GoogleDriveClient(
                        settings=settings, access_token=str(fresh["access_token"])
                    )
                    try:
                        new_state = ensure_changes_watch(
                            client,
                            sync_state=state,
                            page_token=str(page_token),
                            routing_token=routing,
                            settings=settings,
                            force=True,
                        )
                        cred_svc.set_sync_state(row, new_state)
                        renewed += 1
                    finally:
                        client.close()
                except Exception:  # noqa: BLE001
                    failed += 1
                    logger.exception(
                        "google_drive_watch_renew_failed",
                        extra={"connection_id": str(row.id)},
                    )
        db.commit()
        return {
            "status": "ok",
            "renewed": renewed,
            "skipped": skipped,
            "failed": failed,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="renew_microsoft_onedrive_subscriptions", bind=True)
def renew_microsoft_onedrive_subscriptions(self) -> dict:
    """Renew Microsoft Graph OneDrive subscriptions nearing expiry (~every 6h)."""
    from app.common.crypto import decrypt_secret
    from app.connectors.credentials import ConnectorCredentialService
    from app.connectors.models import AppConnection
    from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
    from app.connectors.providers.microsoft_onedrive.subscription import (
        ensure_subscription,
        subscription_needs_renewal,
    )
    from app.connectors.providers.microsoft_onedrive.token import ensure_fresh_access
    from app.connectors.types import CONNECTION_USABLE_STATUSES
    from app.core.config import get_settings
    from sqlalchemy import select

    settings = get_settings()
    if not settings.microsoft_onedrive_configured:
        return {"status": "skipped", "reason": "not_configured"}

    db = SessionLocal()
    renewed = 0
    skipped = 0
    failed = 0
    try:
        rows = list(
            db.scalars(
                select(AppConnection).where(
                    AppConnection.connector_key == "microsoft_onedrive",
                    AppConnection.status.in_(list(CONNECTION_USABLE_STATUSES)),
                )
            ).all()
        )
        cred_svc = ConnectorCredentialService(db, settings=settings)
        for row in rows:
            with tenant_context(workspace_id=row.workspace_id):
                state = cred_svc.get_sync_state(row) or {}
                if not subscription_needs_renewal(state):
                    skipped += 1
                    continue
                drive_id = state.get("drive_id")
                if not drive_id or not row.webhook_routing_token_encrypted:
                    skipped += 1
                    continue
                credentials = cred_svc.get_credentials(row)
                if not credentials:
                    skipped += 1
                    continue
                try:
                    fresh = ensure_fresh_access(db, row, credentials, settings)
                    routing = decrypt_secret(
                        row.webhook_routing_token_encrypted, settings=settings
                    )
                    client = MicrosoftOneDriveClient(
                        settings=settings,
                        access_token=str(fresh["access_token"]),
                        tenant=str(
                            fresh.get("tenant_id")
                            or settings.microsoft_onedrive_tenant
                        ),
                    )
                    try:
                        new_state = ensure_subscription(
                            client,
                            sync_state=state,
                            drive_id=str(drive_id),
                            routing_token=routing,
                            settings=settings,
                            force=False,
                        )
                        cred_svc.set_sync_state(row, new_state)
                        renewed += 1
                    finally:
                        client.close()
                except Exception:  # noqa: BLE001
                    failed += 1
                    logger.exception(
                        "microsoft_onedrive_subscription_renew_failed",
                        extra={"connection_id": str(row.id)},
                    )
        db.commit()
        return {
            "status": "ok",
            "renewed": renewed,
            "skipped": skipped,
            "failed": failed,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
