"""HTTP routes for chat composer attachments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.chat_attachments.schemas import ChatAttachmentOut
from app.chat_attachments.service import ChatAttachmentService
from app.conversations.policy import ConversationAction, ConversationPolicy
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access

router = APIRouter(prefix="/api/chat/attachments", tags=["chat-attachments"])

_READ_CHUNK = 64 * 1024


async def _read_upload_capped(upload: UploadFile, max_bytes: int) -> bytes:
    """Read multipart body with a hard cap (fail closed before buffering more)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                ErrorCategory.UPLOAD_TOO_LARGE,
                f"Upload exceeds maximum size of {max_bytes} bytes",
                details={"max_bytes": max_bytes},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=ChatAttachmentOut, status_code=201)
async def upload_chat_attachment(
    file: UploadFile = File(...),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ChatAttachmentOut:
    ConversationPolicy.require(access.membership.role, ConversationAction.CREATE)
    settings = get_settings()
    data = await _read_upload_capped(file, settings.chat_attachment_max_bytes)
    row = ChatAttachmentService(db, settings).upload(
        workspace=access.workspace,
        actor=access.user,
        file_bytes=data,
        filename=file.filename or "attachment.bin",
        declared_mime_type=file.content_type,
    )
    # Exact TTL delete; Beat sweep covers missed ETAs / worker downtime.
    # Never fail the HTTP success path after quota was charged.
    try:
        from app.worker.tasks import schedule_chat_attachment_expiry

        schedule_chat_attachment_expiry(
            str(row.id),
            countdown_seconds=settings.chat_attachment_ttl_seconds,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Failed to schedule chat attachment TTL purge; Beat sweep will cover it",
            extra={"attachment_id": str(row.id)},
        )
    return ChatAttachmentOut.model_validate(row)


@router.delete("/{attachment_id}", status_code=204)
def delete_chat_attachment(
    attachment_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> None:
    ConversationPolicy.require(access.membership.role, ConversationAction.CREATE)
    ChatAttachmentService(db).delete_for_actor(
        workspace=access.workspace,
        actor=access.user,
        attachment_id=attachment_id,
    )
