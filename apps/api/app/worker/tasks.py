from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from app.common.security_log import security_log
from app.common.tenant_context import tenant_context
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.db.session import SessionLocal
from app.ingestion.pipeline import IngestionPipeline
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_MCP_RESUME_RESULT_STATUSES = frozenset(
    {
        "approved",
        "busy",
        "denied",
        "executed",
        "executing",
        "expired",
        "failed",
        "missing",
        "outcome_unknown",
        "pending",
    }
)
_MCP_DELIVERY_RESULT_STATUSES = frozenset(
    {"delivery_unknown", "not_claimed", "retry_pending", "sent"}
)


def _mcp_task_boundary(
    event: str,
    *,
    id_field: str | None = None,
    failure_status: str = "failed",
) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Keep sensitive exceptions out of Celery logs and result backends."""

    def decorate(task: Callable[..., dict]) -> Callable[..., dict]:
        @wraps(task)
        def guarded(self: Any, *args: Any, **kwargs: Any) -> dict:
            try:
                return task(self, *args, **kwargs)
            except Exception:  # noqa: BLE001 - this is the task serialization boundary
                task_id = getattr(self.request, "id", None)
                safe_id: str | None = None
                raw_id = (
                    args[0]
                    if args
                    else kwargs.get(id_field) if id_field is not None else None
                )
                if id_field is not None and raw_id is not None:
                    try:
                        safe_id = str(uuid.UUID(str(raw_id)))
                    except (TypeError, ValueError, AttributeError):
                        pass
                fields: dict[str, object] = {
                    "category": "internal_error",
                    "task_id": task_id,
                }
                result: dict[str, object] = {
                    "status": failure_status,
                    "task_id": task_id,
                }
                if id_field is not None and safe_id is not None:
                    fields[id_field] = safe_id
                    result[id_field] = safe_id
                # Never attach the exception/traceback. Provider errors may
                # contain decrypted arguments, results, credentials, or URLs;
                # database/broker errors may contain a DSN.
                logger.error(event, extra=fields)
                return result

        return guarded

    return decorate


def _parse_optional_uuid(value: str | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return uuid.UUID(str(value))


@celery_app.task(name="ingest_document", bind=True, max_retries=3)
def ingest_document(
    self,
    document_id: str,
    mode: str = "full",
    workspace_id: str | None = None,
    actor_id: str | None = None,
) -> dict:
    """Ingest a document with explicit tenant contract (Phase 2B).

    Task args are re-sent on retry — never derive tenant from process globals.
    Document.workspace_id is authoritative; mismatch with task workspace_id fails closed.
    """
    db = SessionLocal()
    task_workspace_id = _parse_optional_uuid(workspace_id)
    task_actor_id = _parse_optional_uuid(actor_id)
    doc_uuid = uuid.UUID(document_id)

    try:
        document = db.get(Document, doc_uuid)
        if document is None:
            raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "Document not found")
        if document.deleted_at is not None or document.status == "deleting":
            security_log(
                "ingest.skipped_deleted",
                document_id=document_id,
                workspace_id=str(task_workspace_id) if task_workspace_id else None,
                task_id=getattr(self.request, "id", None),
                action="ingest_skipped",
            )
            return {
                "document_id": document_id,
                "workspace_id": str(task_workspace_id) if task_workspace_id else None,
                "status": "deleted",
            }

        from app.workspaces.models import Workspace

        workspace_row = db.get(Workspace, document.workspace_id)
        if workspace_row is None or workspace_row.deleted_at is not None:
            security_log(
                "ingest.skipped_workspace_deleted",
                document_id=document_id,
                workspace_id=str(document.workspace_id) if document.workspace_id else None,
                task_id=getattr(self.request, "id", None),
                action="ingest_skipped",
            )
            return {
                "document_id": document_id,
                "workspace_id": str(document.workspace_id) if document.workspace_id else None,
                "status": "workspace_deleted",
            }

        # Fail closed on tenant mismatch (including None vs UUID).
        if document.workspace_id != task_workspace_id:
            security_log(
                "ingest.workspace_mismatch",
                document_id=document_id,
                task_workspace_id=str(task_workspace_id) if task_workspace_id else None,
                document_workspace_id=str(document.workspace_id) if document.workspace_id else None,
                task_id=getattr(self.request, "id", None),
                action="ingest_rejected",
            )
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Ingest tenant mismatch — refusing to process document",
                details={
                    "document_id": document_id,
                    "task_workspace_id": str(task_workspace_id) if task_workspace_id else None,
                },
            )

        with tenant_context(
            workspace_id=task_workspace_id,
            document_id=doc_uuid,
            actor_id=task_actor_id,
            request_id=getattr(self.request, "id", None),
        ):
            security_log(
                "ingest.start",
                document_id=document_id,
                workspace_id=str(task_workspace_id) if task_workspace_id else None,
                actor_id=str(task_actor_id) if task_actor_id else None,
                task_id=getattr(self.request, "id", None),
                mode=mode,
                action="ingest",
            )
            pipeline = IngestionPipeline(db)
            pipeline.run(doc_uuid, mode=mode)
            return {
                "document_id": document_id,
                "workspace_id": str(task_workspace_id) if task_workspace_id else None,
                "status": "ready",
            }
    except AppError as exc:
        logger.exception(
            "ingest_task_failed",
            extra={
                "document_id": document_id,
                "workspace_id": workspace_id,
                "task_id": getattr(self.request, "id", None),
            },
        )
        # Tenant mismatch / forbidden must not retry (would never succeed).
        if exc.category in {
            ErrorCategory.FORBIDDEN,
            ErrorCategory.DOCUMENT_NOT_FOUND,
            ErrorCategory.DOCUMENT_DELETED,
        }:
            return {
                "document_id": document_id,
                "workspace_id": workspace_id,
                "status": "failed",
                "error": str(exc),
            }
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=30,
                args=[document_id],
                kwargs={
                    "mode": mode,
                    "workspace_id": workspace_id,
                    "actor_id": actor_id,
                },
            ) from exc
        return {
            "document_id": document_id,
            "workspace_id": workspace_id,
            "status": "failed",
            "error": str(exc),
        }
    except Exception as exc:
        logger.exception(
            "ingest_task_failed",
            extra={"document_id": document_id, "workspace_id": workspace_id},
        )
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=30,
                args=[document_id],
                kwargs={
                    "mode": mode,
                    "workspace_id": workspace_id,
                    "actor_id": actor_id,
                },
            ) from exc
        return {
            "document_id": document_id,
            "workspace_id": workspace_id,
            "status": "failed",
            "error": str(exc),
        }
    finally:
        db.close()


def enqueue_ingest(
    document_id: str,
    mode: str = "full",
    *,
    workspace_id: str | None = None,
    actor_id: str | None = None,
) -> str:
    result = ingest_document.delay(
        document_id,
        mode=mode,
        workspace_id=workspace_id,
        actor_id=actor_id,
    )
    return result.id


@celery_app.task(name="generate_conversation_title", bind=True, max_retries=2)
def generate_conversation_title_task(
    self,
    conversation_id: str,
    workspace_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
) -> dict:
    """Background LLM title for the first user message (runs beside answer streaming)."""
    from app.conversations.title import persist_generated_conversation_title

    titled = persist_generated_conversation_title(
        conversation_id=uuid.UUID(conversation_id),
        workspace_id=uuid.UUID(workspace_id),
        user_id=uuid.UUID(user_id),
        user_message=user_message,
        assistant_message=assistant_message,
    )
    return {
        "conversation_id": conversation_id,
        "title": titled,
        "task_id": getattr(self.request, "id", None),
    }


@celery_app.task(name="purge_expired_chat_attachments", bind=True, max_retries=1)
def purge_expired_chat_attachments(self, limit: int = 200) -> dict:
    """Periodic sweep — delete chat attachments past expires_at."""
    from app.chat_attachments.service import ChatAttachmentService

    db = SessionLocal()
    try:
        purged = ChatAttachmentService(db).purge_expired(limit=limit)
        return {"purged": purged, "task_id": getattr(self.request, "id", None)}
    finally:
        db.close()


@celery_app.task(name="purge_expired_widget_messages", bind=True, max_retries=1)
def purge_expired_widget_messages(self, limit: int = 500) -> dict:
    """Periodic sweep — hard-delete Chat Widget messages older than TTL."""
    from app.widgets.retention import WidgetRetentionService

    db = SessionLocal()
    try:
        result = WidgetRetentionService(db).purge_expired(limit=limit)
        result["task_id"] = getattr(self.request, "id", None)
        return result
    finally:
        db.close()


@celery_app.task(name="purge_chat_attachment_if_expired", bind=True, max_retries=2)
def purge_chat_attachment_if_expired(self, attachment_id: str) -> dict:
    """ETA task scheduled at upload time (TTL countdown)."""
    from app.chat_attachments.service import ChatAttachmentService

    db = SessionLocal()
    try:
        deleted = ChatAttachmentService(db).purge_by_id_if_expired(uuid.UUID(attachment_id))
        return {
            "attachment_id": attachment_id,
            "deleted": deleted,
            "task_id": getattr(self.request, "id", None),
        }
    finally:
        db.close()


def schedule_chat_attachment_expiry(attachment_id: str, *, countdown_seconds: int) -> str | None:
    """Enqueue a one-shot TTL purge for a newly uploaded attachment.

    Returns the Celery task id, or ``None`` if the broker is unavailable.
    Callers must not treat scheduling failure as upload failure — Beat sweep
    still purges by ``expires_at``.
    """
    try:
        result = purge_chat_attachment_if_expired.apply_async(
            args=[attachment_id],
            countdown=max(1, int(countdown_seconds)),
        )
        return result.id
    except Exception:
        logger.exception(
            "chat_attachment.ttl_schedule_failed",
            extra={"attachment_id": attachment_id},
        )
        return None


@celery_app.task(name="run_mcp_widget_turn_receipt", bind=True, max_retries=0)
@_mcp_task_boundary(
    "widget_mcp_turn_task_failed",
    id_field="receipt_id",
)
def run_mcp_widget_turn_receipt(self, receipt_id: str) -> dict:
    """Execute one durable Widget receipt; only its opaque database ID is queued."""

    from app.widgets.service import WidgetService

    parsed = uuid.UUID(receipt_id)
    safe_receipt_id = str(parsed)
    db = SessionLocal()
    try:
        status = WidgetService(db).execute_mcp_turn_receipt(parsed)
        return {
            "receipt_id": safe_receipt_id,
            "status": status,
            "task_id": getattr(self.request, "id", None),
        }
    finally:
        db.close()


@celery_app.task(name="recover_mcp_widget_turn_receipts", bind=True, max_retries=0)
@_mcp_task_boundary("widget_mcp_turn_recovery_task_failed")
def recover_mcp_widget_turn_receipts(self, limit: int = 100) -> dict:
    """Re-enqueue committed pre-execution receipts; never replay a running turn."""

    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.conversations.models import Message, MessageStatus
    from app.core.config import get_settings
    from app.mcp.runtime_models import McpWidgetTurnReceipt

    db = SessionLocal()
    try:
        mcp_settings = get_settings()
        accepted = list(
            db.scalars(
                select(McpWidgetTurnReceipt.id)
                .where(McpWidgetTurnReceipt.status == "accepted")
                .order_by(McpWidgetTurnReceipt.created_at)
                .limit(max(1, int(limit)))
            )
        )
        stale_before = datetime.now(timezone.utc) - timedelta(
            seconds=max(60, int(mcp_settings.mcp_total_turn_timeout_seconds) + 30)
        )
        stale = list(
            db.scalars(
                select(McpWidgetTurnReceipt)
                .where(
                    McpWidgetTurnReceipt.status == "running",
                    McpWidgetTurnReceipt.updated_at < stale_before,
                )
                .with_for_update(skip_locked=True)
                .limit(max(1, int(limit)))
            )
        )
        for receipt in stale:
            receipt.status = "outcome_unknown"
            assistant = db.get(Message, receipt.assistant_message_id)
            if assistant is not None:
                assistant.content = "The tool outcome could not be confirmed."
                assistant.citations = []
                assistant.status = MessageStatus.FAILED.value
                assistant.updated_at = datetime.now(timezone.utc)
        db.commit()
        enqueued = 0
        for receipt_id in accepted:
            try:
                run_mcp_widget_turn_receipt.delay(str(receipt_id))
                enqueued += 1
            except Exception:  # noqa: BLE001
                logger.error(
                    "widget_mcp_turn_recovery_enqueue_failed",
                    extra={"receipt_id": str(receipt_id)},
                )
        return {
            "enqueued": enqueued,
            "outcome_unknown": len(stale),
            "task_id": getattr(self.request, "id", None),
        }
    finally:
        db.close()


@celery_app.task(name="discover_mcp_connection", bind=True, max_retries=0)
@_mcp_task_boundary(
    "mcp_discovery_task_failed",
    id_field="connection_id",
)
def discover_mcp_connection(self, connection_id: str) -> dict:
    """Refresh one MCP inventory/health snapshot; broker payload is ID-only."""

    from datetime import datetime, timezone

    from app.connectors.models import AppConnection
    from app.connectors.types import ConnectionHealth
    from app.mcp.constants import MCP_CONNECTOR_KEY
    from app.mcp.services import McpServerService

    parsed = uuid.UUID(connection_id)
    safe_connection_id = str(parsed)
    db = SessionLocal()
    try:
        row = db.get(AppConnection, parsed)
        if row is None or row.connector_key != MCP_CONNECTOR_KEY:
            return {"connection_id": safe_connection_id, "status": "missing"}
        if row.connected_by_user_id is None:
            return {"connection_id": safe_connection_id, "status": "no_actor"}
        workspace_id = row.workspace_id
        actor_id = row.connected_by_user_id
        try:
            with tenant_context(workspace_id=workspace_id, actor_id=actor_id):
                result = McpServerService(db).discover(
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    connection_id=parsed,
                )
            db.expire_all()
            current = db.get(AppConnection, parsed)
            if current is not None:
                current.last_health_check_at = datetime.now(timezone.utc)
                db.commit()
            return {
                "connection_id": safe_connection_id,
                "status": "complete" if result.complete else "partial",
                "task_id": getattr(self.request, "id", None),
            }
        except AppError as exc:
            db.rollback()
            current = db.get(AppConnection, parsed)
            if current is not None:
                current.last_health_check_at = datetime.now(timezone.utc)
                current.last_error_at = current.last_health_check_at
                current.last_error_code = exc.category.value
                current.last_error_message = "MCP background discovery failed."
                # Commerce/workspace denial says nothing about remote health.
                if exc.category not in {
                    ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                    ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                    ErrorCategory.APP_NOT_INSTALLED,
                }:
                    current.health = ConnectionHealth.DEGRADED.value
                db.commit()
            return {
                "connection_id": safe_connection_id,
                "status": "failed",
                "error": exc.category.value,
                "task_id": getattr(self.request, "id", None),
            }
    finally:
        db.close()


@celery_app.task(name="poll_mcp_connections", bind=True, max_retries=0)
@_mcp_task_boundary("mcp_discovery_poll_task_failed")
def poll_mcp_connections(self, limit: int = 100) -> dict:
    """Schedule bounded TTL inventory/health refreshes using opaque IDs only."""

    from datetime import datetime, timedelta, timezone

    from sqlalchemy import or_, select

    from app.connectors.models import AppConnection
    from app.connectors.types import CONNECTION_USABLE_STATUSES
    from app.core.config import get_settings
    from app.mcp.constants import MCP_CONNECTOR_KEY

    bounded = max(1, min(int(limit), 500))
    settings = get_settings()
    if not settings.mcp_connector_enabled:
        return {
            "selected": 0,
            "enqueued": 0,
            "status": "skipped",
            "reason": "mcp_connector_disabled",
            "task_id": getattr(self.request, "id", None),
        }
    claimed_at = datetime.now(timezone.utc)
    cutoff = claimed_at - timedelta(
        seconds=max(30, int(settings.mcp_tool_inventory_ttl_seconds) // 2)
    )
    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(AppConnection)
                .where(
                    AppConnection.connector_key == MCP_CONNECTOR_KEY,
                    AppConnection.status.in_(tuple(CONNECTION_USABLE_STATUSES)),
                    AppConnection.mcp_reauthorization_required.is_(False),
                    AppConnection.connected_by_user_id.is_not(None),
                    or_(
                        AppConnection.mcp_inventory_refreshed_at.is_(None),
                        AppConnection.mcp_inventory_refreshed_at < cutoff,
                        AppConnection.last_health_check_at.is_(None),
                        AppConnection.last_health_check_at < cutoff,
                    ),
                )
                .order_by(
                    AppConnection.last_health_check_at.asc().nullsfirst(),
                    AppConnection.id,
                )
                .limit(bounded)
                .with_for_update(skip_locked=True)
            ).all()
        )
        ids = [row.id for row in rows]
        # Claim before enqueue so concurrent Beat instances and the next tick
        # cannot fan out duplicate network refreshes for the same connection.
        for row in rows:
            row.last_health_check_at = claimed_at
        db.commit()
    finally:
        db.close()
    enqueued = 0
    for row_id in ids:
        try:
            discover_mcp_connection.delay(str(row_id))
            enqueued += 1
        except Exception:  # noqa: BLE001
            logger.error(
                "mcp_discovery_poll_enqueue_failed",
                extra={"connection_id": str(row_id)},
            )
    return {
        "selected": len(ids),
        "enqueued": enqueued,
        "task_id": getattr(self.request, "id", None),
    }


@celery_app.task(name="resume_mcp_pending_tool_call", bind=True, max_retries=0)
@_mcp_task_boundary(
    "mcp_pending_resume_task_failed",
    id_field="pending_id",
    failure_status="outcome_unknown",
)
def resume_mcp_pending_tool_call(self, pending_id: str) -> dict:
    """Resume one approved MCP write; only its opaque database ID is queued."""

    from app.mcp.resume import McpPendingResumeService

    parsed = uuid.UUID(pending_id)
    safe_pending_id = str(parsed)
    db = SessionLocal()
    service = McpPendingResumeService(db)
    try:
        service_result = service.resume(parsed)
        raw_status = service_result.get("status")
        status = (
            raw_status
            if raw_status in _MCP_RESUME_RESULT_STATUSES
            else "failed"
        )
        result: dict[str, object] = {
            "pending_id": safe_pending_id,
            "status": status,
            "task_id": getattr(self.request, "id", None),
        }
        deliveries = service_result.get("deliveries")
        if isinstance(deliveries, int) and not isinstance(deliveries, bool):
            result["deliveries"] = max(0, deliveries)
        return result
    except Exception:  # noqa: BLE001
        logger.error(
            "mcp_pending_resume_failed",
            extra={"pending_id": safe_pending_id},
        )
        db.rollback()
        status = service.fail_unhandled(parsed)
        return {
            "pending_id": safe_pending_id,
            "status": status,
            "task_id": getattr(self.request, "id", None),
        }
    finally:
        db.close()


@celery_app.task(name="recover_mcp_approval_state", bind=True, max_retries=0)
@_mcp_task_boundary("mcp_approval_recovery_task_failed")
def recover_mcp_approval_state(self, limit: int = 100) -> dict:
    """Recover pre-dispatch claims, expire approvals, scrub, and re-enqueue IDs."""

    from sqlalchemy import select

    from app.mcp.approvals import McpApprovalService
    from app.mcp.runtime_models import McpPendingToolCall

    bounded = max(1, min(int(limit), 500))
    db = SessionLocal()
    try:
        approvals = McpApprovalService(db)
        recovered, unknown = approvals.recover_stale_claims(limit=bounded)
        expired = approvals.expire_due(limit=bounded)
        approved_ids = list(
            db.scalars(
                select(McpPendingToolCall.id)
                .where(McpPendingToolCall.status == "approved")
                .order_by(McpPendingToolCall.resume_requested_at)
                .limit(bounded)
            ).all()
        )
        terminal_ids = list(
            db.scalars(
                select(McpPendingToolCall.id)
                .where(
                    McpPendingToolCall.status.in_(
                        ("denied", "expired", "outcome_unknown")
                    )
                )
                .order_by(McpPendingToolCall.updated_at)
                .limit(bounded)
            ).all()
        )
        db.commit()
    finally:
        db.close()

    enqueued = 0
    for row_id in approved_ids:
        try:
            resume_mcp_pending_tool_call.delay(str(row_id))
            enqueued += 1
        except Exception:  # noqa: BLE001
            logger.error(
                "mcp_resume_recovery_enqueue_failed",
                extra={"pending_id": str(row_id)},
            )
    finalized = 0
    from app.mcp.resume import McpPendingResumeService

    for row_id in terminal_ids:
        terminal_db = SessionLocal()
        try:
            if McpPendingResumeService(terminal_db).finalize_terminal(row_id):
                finalized += 1
        finally:
            terminal_db.close()
    # Terminal rows are the only durable coordinates from which WhatsApp can
    # create its denied/expired/outcome-unknown revision.  Purge only after
    # every selected row had an opportunity to finalize; doing this in the
    # earlier recovery transaction could delete the row before the follow-up.
    purge_db = SessionLocal()
    try:
        purged = McpApprovalService(purge_db).purge_due(
            limit=bounded,
            finalized_terminal_ids=tuple(terminal_ids),
        )
        purge_db.commit()
    finally:
        purge_db.close()
    return {
        "recovered": recovered,
        "outcome_unknown": unknown,
        "expired": expired,
        "purged": purged,
        "enqueued": enqueued,
        "finalized": finalized,
        "task_id": getattr(self.request, "id", None),
    }


@celery_app.task(name="deliver_mcp_surface_segment", bind=True, max_retries=0)
@_mcp_task_boundary(
    "mcp_surface_delivery_task_failed",
    id_field="delivery_id",
    failure_status="delivery_unknown",
)
def deliver_mcp_surface_segment(self, delivery_id: str) -> dict:
    """Deliver one immutable WhatsApp segment without automatic POST retry."""

    from app.mcp.delivery import McpWhatsAppDeliveryService

    parsed = uuid.UUID(delivery_id)
    service_result = McpWhatsAppDeliveryService().deliver(parsed)
    raw_status = service_result.get("status")
    status = (
        raw_status
        if raw_status in _MCP_DELIVERY_RESULT_STATUSES
        else "delivery_unknown"
    )
    result: dict[str, object] = {
        "delivery_id": str(parsed),
        "status": status,
        "task_id": getattr(self.request, "id", None),
    }
    raw_error = service_result.get("error")
    try:
        if raw_error is not None:
            result["error"] = ErrorCategory(str(raw_error)).value
    except ValueError:
        pass
    return result


@celery_app.task(name="recover_mcp_surface_deliveries", bind=True, max_retries=0)
@_mcp_task_boundary("mcp_delivery_recovery_task_failed")
def recover_mcp_surface_deliveries(self, limit: int = 100) -> dict:
    """Mark abandoned ambiguous claims unknown and enqueue ordered pending IDs."""

    from sqlalchemy import select

    from app.mcp.runtime_models import McpSurfaceDelivery
    from app.mcp.surfaces import McpSurfaceOutboxService

    bounded = max(1, min(int(limit), 500))
    db = SessionLocal()
    try:
        outbox = McpSurfaceOutboxService(db)
        recovered_unknown = outbox.recover_pre_send_claims(limit=bounded)
        purged = outbox.purge_terminal(limit=bounded)
        pending_ids = list(
            db.scalars(
                select(McpSurfaceDelivery.id)
                .where(McpSurfaceDelivery.status == "pending")
                .order_by(
                    McpSurfaceDelivery.conversation_id,
                    McpSurfaceDelivery.conversation_sequence,
                    McpSurfaceDelivery.segment_index,
                )
                .limit(bounded)
            ).all()
        )
        db.commit()
    finally:
        db.close()
    enqueued = 0
    for row_id in pending_ids:
        try:
            deliver_mcp_surface_segment.delay(str(row_id))
            enqueued += 1
        except Exception:  # noqa: BLE001
            logger.error(
                "mcp_delivery_recovery_enqueue_failed",
                extra={"delivery_id": str(row_id)},
            )
    return {
        "enqueued": enqueued,
        "delivery_unknown": recovered_unknown,
        "purged": purged,
        "task_id": getattr(self.request, "id", None),
    }
