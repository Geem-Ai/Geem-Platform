from __future__ import annotations

import logging
import uuid

from app.common.security_log import security_log
from app.common.tenant_context import tenant_context
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.db.session import SessionLocal
from app.ingestion.pipeline import IngestionPipeline
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


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
