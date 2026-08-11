"""ChatOrchestrator — persisted Conversation turn streaming (Phase 4B).

Owns the application workflow around a chat turn. Does not implement vector
search; delegates to ExpertQueryService → RagService.

Future Phase 7 ``/api/v1/chat`` should call into this orchestrator rather than
re-implementing persistence + SSE framing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.conversations.locks import ConversationGenerationLock
from app.conversations.models import (
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from app.conversations.policy import ConversationAction, ConversationPolicy
from app.conversations.repository import ConversationRepository
from app.conversations.service import ConversationService
from app.conversations.title import schedule_conversation_title
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.query_service import ExpertQueryService
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.policy import WorkspaceAction, WorkspacePolicy

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        expert_query: ExpertQueryService | None = None,
        lock: ConversationGenerationLock | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = ConversationRepository(db)
        self.expert_query = expert_query or ExpertQueryService(db, self.settings)
        self.lock = lock or ConversationGenerationLock(settings=self.settings)

    # ------------------------------------------------------------------
    # Public generators (SSE event dicts: {"event": str, "data": dict})
    # ------------------------------------------------------------------

    def stream_turn(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
        content: str,
    ) -> Iterator[dict[str, Any]]:
        """Persist user + assistant messages and stream Expert-scoped RAG."""
        WorkspacePolicy.require(membership.role, WorkspaceAction.READ_DOCUMENT)
        ConversationPolicy.require(membership.role, ConversationAction.UPDATE)

        question = (content or "").strip()
        if not question:
            raise AppError(ErrorCategory.VALIDATION, "Message content is required.")
        max_chars = self.settings.max_chat_message_chars
        if len(question) > max_chars:
            raise AppError(
                ErrorCategory.VALIDATION,
                f"Message exceeds maximum length of {max_chars} characters.",
            )

        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace=workspace,
            actor=actor,
        )

        if not self.lock.acquire(conversation.id):
            raise AppError(
                ErrorCategory.CONVERSATION_BUSY,
                "A response is already being generated for this conversation.",
            )

        assistant: Message | None = None
        user_msg: Message | None = None
        settled = False
        accumulated = ""

        try:
            # Heal abandoned streaming rows (worker crash after insert, lock TTL expired).
            stale_before = datetime.now(timezone.utc) - timedelta(
                seconds=self.lock.ttl_seconds
            )
            cancelled = self.repo.cancel_stale_generations(
                conversation.id, older_than=stale_before
            )
            if cancelled:
                self.db.commit()

            if self.repo.has_active_generation(conversation.id):
                raise AppError(
                    ErrorCategory.CONVERSATION_BUSY,
                    "A response is already being generated for this conversation.",
                )

            # Revalidate Expert access + readiness on every turn (grants can change).
            self.expert_query.resolve_knowledge(
                workspace=workspace,
                membership=membership,
                actor=actor,
                expert_id=conversation.expert_id,
            )

            needs_title = not bool((conversation.title or "").strip())

            now = datetime.now(timezone.utc)
            user_msg = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=question,
                citations=[],
                status=MessageStatus.COMPLETED.value,
                created_at=now,
                updated_at=now,
            )
            self.repo.create_message(user_msg)

            assistant = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT.value,
                content="",
                citations=[],
                status=MessageStatus.STREAMING.value,
                created_at=now + timedelta(microseconds=1000),
                updated_at=now + timedelta(microseconds=1000),
            )
            self.repo.create_message(assistant)
            conversation.updated_at = now + timedelta(microseconds=1000)
            self.db.commit()
            self.db.refresh(user_msg)
            self.db.refresh(assistant)

            start_data: dict[str, Any] = {
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_msg.id),
                "assistant_message_id": str(assistant.id),
            }
            yield {"event": "message_start", "data": start_data}

            # Title from the first user message — run in parallel with answer streaming
            # (not after the reply finishes). Idempotent if a title already exists.
            if needs_title:
                schedule_conversation_title(
                    conversation_id=conversation.id,
                    workspace_id=workspace.id,
                    user_id=actor.id,
                    user_message=user_msg.content,
                    assistant_message="",
                )

            history = self._history_payload(conversation.id, before_message_id=user_msg.id)

            try:
                for item in self.expert_query.query_stream(
                    workspace=workspace,
                    membership=membership,
                    actor=actor,
                    expert_id=conversation.expert_id,
                    question=question,
                    history=history,
                ):
                    event = item.get("event")
                    data = item.get("data") or {}

                    if event == "token":
                        accumulated += data.get("text") or ""
                        yield item
                    elif event == "replace":
                        accumulated = data.get("text") or ""
                        yield item
                    elif event == "final":
                        citations = ConversationService.normalize_citations(
                            data.get("citations") or []
                        )
                        answer = data.get("answer") or accumulated or ""
                        usage_raw = data.get("usage_event_id")
                        usage_id = (
                            uuid.UUID(str(usage_raw)) if usage_raw else None
                        )
                        self._complete_assistant(
                            conversation,
                            assistant,
                            content=answer,
                            citations=citations,
                            usage_event_id=usage_id,
                        )
                        settled = True
                        final_data = {
                            **data,
                            "conversation_id": str(conversation.id),
                            "user_message_id": str(user_msg.id),
                            "assistant_message_id": str(assistant.id),
                            "status": MessageStatus.COMPLETED.value,
                            "citations": citations,
                        }
                        yield {"event": "final", "data": final_data}
                        yield {
                            "event": "message_complete",
                            "data": {
                                "conversation_id": str(conversation.id),
                                "user_message_id": str(user_msg.id),
                                "assistant_message_id": str(assistant.id),
                                "status": MessageStatus.COMPLETED.value,
                                "citations": citations,
                            },
                        }
                    else:
                        yield item
            except AppError as exc:
                if assistant is not None and not settled:
                    self._fail_assistant(conversation, assistant, accumulated=accumulated)
                    settled = True
                yield {
                    "event": "error",
                    "data": {
                        "error": exc.category.value,
                        "message": exc.message,
                        "details": exc.details,
                        "conversation_id": str(conversation.id),
                        "user_message_id": str(user_msg.id) if user_msg else None,
                        "assistant_message_id": str(assistant.id) if assistant else None,
                        "status": MessageStatus.FAILED.value,
                    },
                }
                return
            except Exception:  # noqa: BLE001
                logger.exception("chat_orchestrator_turn_failed")
                if assistant is not None and not settled:
                    self._fail_assistant(conversation, assistant, accumulated=accumulated)
                    settled = True
                yield {
                    "event": "error",
                    "data": {
                        "error": ErrorCategory.GENERATION_FAILED.value,
                        "message": "Generation failed.",
                        "conversation_id": str(conversation.id),
                        "user_message_id": str(user_msg.id) if user_msg else None,
                        "assistant_message_id": str(assistant.id) if assistant else None,
                        "status": MessageStatus.FAILED.value,
                    },
                }
                return
        except GeneratorExit:
            if assistant is not None and not settled:
                self._cancel_assistant(conversation, assistant, accumulated=accumulated)
                settled = True
            raise
        except AppError:
            # Pre-stream validation failures (busy / expert / auth) — no assistant yet
            # or already raised before yield. Ensure any streaming row is settled.
            if assistant is not None and not settled:
                self._fail_assistant(conversation, assistant, accumulated=accumulated)
            raise
        finally:
            self.lock.release(conversation_id)

    def stream_retry(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> Iterator[dict[str, Any]]:
        """Retry a failed/cancelled assistant turn without a new user message.

        Creates a **new** assistant message after the failed one. Only the latest
        assistant message in the conversation may be retried.
        """
        WorkspacePolicy.require(membership.role, WorkspaceAction.READ_DOCUMENT)
        ConversationPolicy.require(membership.role, ConversationAction.UPDATE)

        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace=workspace,
            actor=actor,
        )

        if not self.lock.acquire(conversation.id):
            raise AppError(
                ErrorCategory.CONVERSATION_BUSY,
                "A response is already being generated for this conversation.",
            )

        assistant: Message | None = None
        user_msg: Message | None = None
        settled = False
        accumulated = ""
        needs_title = not bool((conversation.title or "").strip())

        try:
            stale_before = datetime.now(timezone.utc) - timedelta(
                seconds=self.lock.ttl_seconds
            )
            cancelled = self.repo.cancel_stale_generations(
                conversation.id, older_than=stale_before
            )
            if cancelled:
                self.db.commit()

            if self.repo.has_active_generation(conversation.id):
                raise AppError(
                    ErrorCategory.CONVERSATION_BUSY,
                    "A response is already being generated for this conversation.",
                )

            failed = self.repo.get_message(
                assistant_message_id, conversation_id=conversation.id
            )
            if (
                failed is None
                or failed.role != MessageRole.ASSISTANT.value
            ):
                raise AppError(ErrorCategory.MESSAGE_NOT_FOUND, "Message not found.")
            if failed.status not in {
                MessageStatus.FAILED.value,
                MessageStatus.CANCELLED.value,
            }:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Only failed or cancelled assistant messages can be retried.",
                )

            latest = self.repo.get_latest_assistant_message(conversation.id)
            if latest is None or latest.id != failed.id:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Only the latest assistant message can be retried.",
                )

            user_msg = self.repo.find_preceding_user_message(conversation.id, failed)
            if user_msg is None or not (user_msg.content or "").strip():
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Could not find the originating user message for retry.",
                )

            question = user_msg.content.strip()

            # Revalidate Expert on every retry.
            self.expert_query.resolve_knowledge(
                workspace=workspace,
                membership=membership,
                actor=actor,
                expert_id=conversation.expert_id,
            )

            now = datetime.now(timezone.utc)
            assistant = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT.value,
                content="",
                citations=[],
                status=MessageStatus.STREAMING.value,
                created_at=now,
                updated_at=now,
            )
            self.repo.create_message(assistant)
            conversation.updated_at = now
            self.db.commit()
            self.db.refresh(assistant)

            yield {
                "event": "message_start",
                "data": {
                    "conversation_id": str(conversation.id),
                    "user_message_id": str(user_msg.id),
                    "assistant_message_id": str(assistant.id),
                    "retry_of_message_id": str(failed.id),
                },
            }

            # Still untitled (e.g. first attempt failed before title ran) — parallelize.
            if needs_title:
                schedule_conversation_title(
                    conversation_id=conversation.id,
                    workspace_id=workspace.id,
                    user_id=actor.id,
                    user_message=user_msg.content,
                    assistant_message="",
                )

            history = self._history_payload(conversation.id, before_message_id=user_msg.id)

            try:
                for item in self.expert_query.query_stream(
                    workspace=workspace,
                    membership=membership,
                    actor=actor,
                    expert_id=conversation.expert_id,
                    question=question,
                    history=history,
                ):
                    event = item.get("event")
                    data = item.get("data") or {}
                    if event == "token":
                        accumulated += data.get("text") or ""
                        yield item
                    elif event == "replace":
                        accumulated = data.get("text") or ""
                        yield item
                    elif event == "final":
                        citations = ConversationService.normalize_citations(
                            data.get("citations") or []
                        )
                        answer = data.get("answer") or accumulated or ""
                        usage_raw = data.get("usage_event_id")
                        usage_id = (
                            uuid.UUID(str(usage_raw)) if usage_raw else None
                        )
                        self._complete_assistant(
                            conversation,
                            assistant,
                            content=answer,
                            citations=citations,
                            usage_event_id=usage_id,
                        )
                        settled = True
                        final_data = {
                            **data,
                            "conversation_id": str(conversation.id),
                            "user_message_id": str(user_msg.id),
                            "assistant_message_id": str(assistant.id),
                            "status": MessageStatus.COMPLETED.value,
                            "citations": citations,
                        }
                        yield {"event": "final", "data": final_data}
                        yield {
                            "event": "message_complete",
                            "data": {
                                "conversation_id": str(conversation.id),
                                "user_message_id": str(user_msg.id),
                                "assistant_message_id": str(assistant.id),
                                "status": MessageStatus.COMPLETED.value,
                                "citations": citations,
                            },
                        }
                    else:
                        yield item
            except AppError as exc:
                if assistant is not None and not settled:
                    self._fail_assistant(conversation, assistant, accumulated=accumulated)
                    settled = True
                yield {
                    "event": "error",
                    "data": {
                        "error": exc.category.value,
                        "message": exc.message,
                        "details": exc.details,
                        "conversation_id": str(conversation.id),
                        "user_message_id": str(user_msg.id) if user_msg else None,
                        "assistant_message_id": str(assistant.id) if assistant else None,
                        "status": MessageStatus.FAILED.value,
                    },
                }
                return
            except Exception:
                logger.exception("chat_orchestrator_retry_failed")
                if assistant is not None and not settled:
                    self._fail_assistant(conversation, assistant, accumulated=accumulated)
                    settled = True
                yield {
                    "event": "error",
                    "data": {
                        "error": ErrorCategory.GENERATION_FAILED.value,
                        "message": "Generation failed.",
                        "conversation_id": str(conversation.id),
                        "user_message_id": str(user_msg.id) if user_msg else None,
                        "assistant_message_id": str(assistant.id) if assistant else None,
                        "status": MessageStatus.FAILED.value,
                    },
                }
                return

        except GeneratorExit:
            if assistant is not None and not settled:
                self._cancel_assistant(conversation, assistant, accumulated=accumulated)
                settled = True
            raise
        except AppError:
            if assistant is not None and not settled:
                self._fail_assistant(conversation, assistant, accumulated=accumulated)
            raise
        finally:
            self.lock.release(conversation_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_owned(
        self,
        *,
        conversation_id: uuid.UUID,
        workspace: Workspace,
        actor: User,
    ) -> Conversation:
        conversation = self.repo.get_for_user(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            user_id=actor.id,
        )
        if conversation is None:
            raise AppError(ErrorCategory.CONVERSATION_NOT_FOUND, "Conversation not found.")
        return conversation

    def _history_payload(
        self,
        conversation_id: uuid.UUID,
        *,
        before_message_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        limit = max(0, int(self.settings.chat_history_max_messages))
        if limit == 0:
            return []
        rows = self.repo.list_history_for_rag(
            conversation_id,
            before_message_id=before_message_id,
            limit=limit,
        )
        return [
            {"role": m.role, "content": m.content or ""}
            for m in rows
            if (m.content or "").strip()
        ]

    def _complete_assistant(
        self,
        conversation: Conversation,
        assistant: Message,
        *,
        content: str,
        citations: list[dict[str, Any]],
        usage_event_id: uuid.UUID | None,
    ) -> None:
        assistant.content = content
        assistant.citations = citations
        assistant.status = MessageStatus.COMPLETED.value
        assistant.usage_event_id = usage_event_id
        assistant.updated_at = datetime.now(timezone.utc)
        conversation.updated_at = datetime.now(timezone.utc)
        try:
            self.db.commit()
        except Exception:
            # Usage FK / transient flush errors must not leave status=streaming.
            self.db.rollback()
            logger.exception("chat_orchestrator_complete_commit_failed")
            assistant.content = content
            assistant.citations = citations
            assistant.status = MessageStatus.COMPLETED.value
            assistant.usage_event_id = None
            assistant.updated_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def _fail_assistant(
        self,
        conversation: Conversation,
        assistant: Message,
        *,
        accumulated: str = "",
    ) -> None:
        try:
            self.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        assistant.content = accumulated or assistant.content or ""
        assistant.status = MessageStatus.FAILED.value
        assistant.usage_event_id = None
        assistant.updated_at = datetime.now(timezone.utc)
        conversation.updated_at = datetime.now(timezone.utc)
        try:
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception("chat_orchestrator_fail_commit_failed")

    def _cancel_assistant(
        self,
        conversation: Conversation,
        assistant: Message,
        *,
        accumulated: str = "",
    ) -> None:
        try:
            self.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        assistant.content = accumulated or assistant.content or ""
        assistant.status = MessageStatus.CANCELLED.value
        assistant.updated_at = datetime.now(timezone.utc)
        conversation.updated_at = datetime.now(timezone.utc)
        try:
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception("chat_orchestrator_cancel_commit_failed")
