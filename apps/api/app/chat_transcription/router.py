"""HTTP routes for chat composer speech-to-text."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.chat_transcription.schemas import ChatTranscribeOut
from app.chat_transcription.service import ChatTranscriptionService
from app.conversations.policy import ConversationAction, ConversationPolicy
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access

router = APIRouter(prefix="/api/chat", tags=["chat"])

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


@router.post("/transcribe", response_model=ChatTranscribeOut)
async def transcribe_chat_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ChatTranscribeOut:
    ConversationPolicy.require(access.membership.role, ConversationAction.CREATE)
    settings = get_settings()
    data = await _read_upload_capped(file, settings.chat_transcribe_max_bytes)
    result = ChatTranscriptionService(db, settings).transcribe(
        workspace=access.workspace,
        actor=access.user,
        file_bytes=data,
        filename=file.filename or "recording.webm",
        declared_mime_type=file.content_type,
        language=language,
    )
    return ChatTranscribeOut(
        text=result.text,
        duration_seconds=result.duration_seconds,
    )
