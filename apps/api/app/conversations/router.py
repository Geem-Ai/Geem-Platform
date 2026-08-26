"""Conversation REST API (Phases 4A + 4B).

4A: CRUD persistence. 4B: ChatOrchestrator SSE streaming / retry.
``/api/query`` remains available for Expert-scoped diagnostics.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.conversations.chat_orchestrator import ChatOrchestrator
from app.conversations.schemas import (
    ConversationClearHistoryOut,
    ConversationCreateRequest,
    ConversationDetailOut,
    ConversationMessageStreamRequest,
    ConversationOut,
    ConversationUpdateRequest,
    MessageOut,
)
from app.conversations.service import ConversationService
from app.core.errors import AppError
from app.db.session import SessionLocal, get_db
from app.documents.dependencies import DocumentAccess, get_document_access

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _stream_item(item: dict) -> str:
    if item.get("event") == "keepalive":
        return ": keepalive\n\n"
    return _sse(str(item["event"]), item.get("data") or {})


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationCreateRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ConversationOut:
    svc = ConversationService(db)
    conversation = svc.create(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=body.expert_id,
        title=body.title,
    )
    return svc.to_out(conversation)


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> list[ConversationOut]:
    """Pinned first, then recent — scoped to current user in current Workspace."""
    return ConversationService(db).list_for_actor(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        limit=limit,
        offset=offset,
    )


@router.delete("", response_model=ConversationClearHistoryOut)
def clear_conversation_history(
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ConversationClearHistoryOut:
    """Soft-delete all conversations for the current user in this Workspace."""
    deleted = ConversationService(db).clear_history(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
    )
    return ConversationClearHistoryOut(deleted_count=deleted)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ConversationDetailOut:
    out = ConversationService(db).get_for_actor(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        conversation_id=conversation_id,
    )
    return ConversationDetailOut.model_validate(out.model_dump())


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdateRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ConversationOut:
    svc = ConversationService(db)
    # Distinguish "title omitted" vs "title cleared to null" via model fields_set.
    title_provided = "title" in body.model_fields_set
    conversation = svc.update(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        conversation_id=conversation_id,
        title=body.title,
        title_provided=title_provided,
        is_pinned=body.is_pinned,
        is_favorite=body.is_favorite,
    )
    return svc.to_out(conversation)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> Response:
    ConversationService(db).soft_delete(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        conversation_id=conversation_id,
    )
    return Response(status_code=204)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    return ConversationService(db).list_messages(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )


@router.post("/{conversation_id}/messages/stream")
async def stream_conversation_message(
    conversation_id: uuid.UUID,
    body: ConversationMessageStreamRequest,
    access: DocumentAccess = Depends(get_document_access),
) -> StreamingResponse:
    """Persisted chat turn — SSE contract extends ``/api/query/stream``."""
    workspace = access.workspace
    membership = access.membership
    actor = access.user
    content = body.content
    attachment_id = body.attachment_id

    def generate() -> Iterator[str]:
        db = SessionLocal()
        try:
            orch = ChatOrchestrator(db)
            for item in orch.stream_turn(
                workspace=workspace,
                membership=membership,
                actor=actor,
                conversation_id=conversation_id,
                content=content,
                attachment_id=attachment_id,
            ):
                yield _stream_item(item)
        except AppError as exc:
            yield _sse(
                "error",
                {
                    "error": exc.category.value,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except GeneratorExit:
            raise
        except Exception:  # noqa: BLE001
            yield _sse(
                "error",
                {"error": "generation_failed", "message": "Generation failed."},
            )
        finally:
            db.close()

    return StreamingResponse(
        iterate_in_threadpool(generate()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{conversation_id}/messages/{assistant_message_id}/retry/stream")
async def retry_conversation_message(
    conversation_id: uuid.UUID,
    assistant_message_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
) -> StreamingResponse:
    """Retry a failed/cancelled assistant message without a new user bubble."""
    workspace = access.workspace
    membership = access.membership
    actor = access.user

    def generate() -> Iterator[str]:
        db = SessionLocal()
        try:
            orch = ChatOrchestrator(db)
            for item in orch.stream_retry(
                workspace=workspace,
                membership=membership,
                actor=actor,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
            ):
                yield _stream_item(item)
        except AppError as exc:
            yield _sse(
                "error",
                {
                    "error": exc.category.value,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except GeneratorExit:
            raise
        except Exception:  # noqa: BLE001
            yield _sse(
                "error",
                {"error": "generation_failed", "message": "Generation failed."},
            )
        finally:
            db.close()

    return StreamingResponse(
        iterate_in_threadpool(generate()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
