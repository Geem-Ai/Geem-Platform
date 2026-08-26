"""ChatOrchestrator — persisted Conversation turn streaming (Phase 4B).

Owns persistence (conversations, messages, title, generation lock) around a
chat turn. Generation itself is ExpertQueryService → RagService.

Public ``/api/v1/chat/completions`` uses ``ChatTurnExecutor`` against the same ExpertQuery
path without persistence. Attribution is ``ChatInvocationContext`` so Workspace
Chat never inherits an API key.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.public_model import redact_public_models
from app.conversations.invocation import ChatInvocationContext
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
from app.conversations.validation import validate_chat_message
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.query_service import ExpertQueryService
from app.identity.models import User
from app.usage.ai_usage import AiUsageService
from app.usage.attribution import GenerationUsageContext
from app.usage.weights import settled_tokens_from_payload
from app.workspaces.models import Workspace, WorkspaceMembership
from app.mcp.executor import ToolLoopTurnExecutor
from app.mcp.resolver import McpGrantResolver

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
        attachment_id: uuid.UUID | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Persist user + assistant messages and stream Expert-scoped RAG."""
        ConversationPolicy.require(membership, ConversationAction.UPDATE)

        turn_attachment = None
        if attachment_id is not None:
            from app.chat_attachments.service import ChatAttachmentService

            turn_attachment = ChatAttachmentService(self.db, self.settings).load_for_turn(
                workspace=workspace,
                actor=actor,
                attachment_id=attachment_id,
            )

        question = validate_chat_message(
            content,
            settings=self.settings,
            allow_empty=turn_attachment is not None,
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
        usage_closed = False
        turn_committed = False
        request_id: str | None = None
        accumulated = ""
        usage_ctx: GenerationUsageContext | None = None

        try:
            self._heal_stale_generations(conversation, workspace)

            if self.repo.has_active_generation(conversation.id):
                raise AppError(
                    ErrorCategory.CONVERSATION_BUSY,
                    "A response is already being generated for this conversation.",
                )

            # Revalidate Expert access + readiness on every turn (grants can change).
            knowledge = self.expert_query.resolve_knowledge(
                workspace=workspace,
                membership=membership,
                actor=actor,
                expert_id=conversation.expert_id,
            )

            needs_title = not bool((conversation.title or "").strip())

            now = datetime.now(timezone.utc)
            attachment_snapshot = [turn_attachment.snapshot()] if turn_attachment else []
            user_msg = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=question,
                citations=[],
                attachments=attachment_snapshot,
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
                attachments=[],
                status=MessageStatus.STREAMING.value,
                created_at=now + timedelta(microseconds=1000),
                updated_at=now + timedelta(microseconds=1000),
            )
            self.repo.create_message(assistant)
            conversation.updated_at = now + timedelta(microseconds=1000)
            self.db.flush()
            invocation = self._workspace_invocation(
                workspace=workspace,
                actor=actor,
                conversation=conversation,
                assistant=assistant,
            )
            mcp_tools = list(
                McpGrantResolver(self.db, settings=self.settings).resolve(
                    invocation,
                    conversation.expert_id,
                )
            )
            self._reserve_turn(
                workspace=workspace,
                actor=actor,
                conversation=conversation,
                assistant=assistant,
                reservation_multiplier=(
                    self.settings.mcp_max_tool_iterations + 1 if mcp_tools else 1
                ),
            )
            self.db.commit()
            turn_committed = True
            request_id = str(assistant.id)
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
                title_seed = question or (
                    turn_attachment.filename if turn_attachment is not None else ""
                )
                schedule_conversation_title(
                    conversation_id=conversation.id,
                    workspace_id=workspace.id,
                    user_id=actor.id,
                    user_message=title_seed,
                    assistant_message="",
                )

            history = self._history_payload(conversation.id, before_message_id=user_msg.id)
            usage_ctx = self._usage_context(
                workspace=workspace,
                actor=actor,
                conversation=conversation,
                assistant=assistant,
            )

            try:
                if mcp_tools:
                    yield {"event": "status", "data": {"stage": "using_tools"}}
                    loop_executor = ToolLoopTurnExecutor(
                        self.db,
                        settings=self.settings,
                        rag=self.expert_query._rag,
                    )
                    loop = None
                    for lifecycle in loop_executor.execute_events(
                        knowledge=knowledge,
                        expert_id=conversation.expert_id,
                        question=question,
                        invocation=invocation,
                        usage_context=usage_ctx,
                        tools=mcp_tools,
                        history=history,
                        attachment=turn_attachment,
                    ):
                        if lifecycle.event == "complete":
                            loop = lifecycle.result
                        else:
                            yield {
                                "event": lifecycle.event,
                                "data": lifecycle.data,
                            }
                    if loop is None:
                        raise AppError(
                            ErrorCategory.GENERATION_FAILED,
                            "The MCP tool loop did not complete.",
                        )
                    if loop.pending is not None:
                        pending_copy = "This tool call is awaiting your approval."
                        assistant.content = pending_copy
                        assistant.citations = []
                        assistant.status = MessageStatus.PENDING.value
                        assistant.updated_at = datetime.now(timezone.utc)
                        conversation.updated_at = assistant.updated_at
                        self._settle_usage(
                            workspace.id,
                            request_id,
                            usage_ctx.extra_billed_tokens,
                        )
                        self.db.commit()
                        usage_closed = True
                        settled = True
                        yield {
                            "event": "tool_approval_required",
                            "data": {
                                "approval_id": str(loop.pending.id),
                                "tool_call_id": loop.pending.tool_call_id,
                                "connection_name": loop.pending.connection_name,
                                "tool_name": loop.pending.tool_name,
                                "arguments": loop.pending.arguments,
                                "expires_at": loop.pending.expires_at.isoformat(),
                                "conversation_id": str(conversation.id),
                                "assistant_message_id": str(assistant.id),
                                "status": MessageStatus.PENDING.value,
                            },
                        }
                        return

                    answer = loop.answer
                    citations = ConversationService.normalize_citations(loop.citations)
                    loop_payload = loop.as_payload()
                    self._complete_and_settle(
                        conversation,
                        assistant,
                        content=answer,
                        citations=citations,
                        usage_event_id=None,
                        workspace_id=workspace.id,
                        request_id=request_id,
                        actual_tokens=self._actual_tokens(
                            loop_payload,
                            extra_billed=usage_ctx.extra_billed_tokens,
                        ),
                    )
                    usage_closed = True
                    settled = True
                    if answer:
                        yield {"event": "replace", "data": {"text": answer}}
                    final_data = redact_public_models(
                        {
                            **loop_payload,
                            "conversation_id": str(conversation.id),
                            "user_message_id": str(user_msg.id),
                            "assistant_message_id": str(assistant.id),
                            "status": MessageStatus.COMPLETED.value,
                            "citations": citations,
                        }
                    )
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
                    return

                for item in self.expert_query.query_stream(
                    workspace=workspace,
                    membership=membership,
                    actor=actor,
                    expert_id=conversation.expert_id,
                    question=question,
                    history=history,
                    usage_context=usage_ctx,
                    attachment=turn_attachment,
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
                        self._complete_and_settle(
                            conversation,
                            assistant,
                            content=answer,
                            citations=citations,
                            usage_event_id=usage_id,
                            workspace_id=workspace.id,
                            request_id=request_id,
                            actual_tokens=self._actual_tokens(
                                data, extra_billed=usage_ctx.extra_billed_tokens
                            ),
                        )
                        usage_closed = True
                        settled = True
                        final_data = redact_public_models(
                            {
                                **data,
                                "conversation_id": str(conversation.id),
                                "user_message_id": str(user_msg.id),
                                "assistant_message_id": str(assistant.id),
                                "status": MessageStatus.COMPLETED.value,
                                "citations": citations,
                            }
                        )
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
                if request_id is not None and not usage_closed:
                    self._close_usage(
                        workspace.id, request_id, extra=usage_ctx.extra_billed_tokens
                    )
                    usage_closed = True
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
                if request_id is not None and not usage_closed:
                    self._close_usage(
                        workspace.id, request_id, extra=usage_ctx.extra_billed_tokens
                    )
                    usage_closed = True
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
            if request_id is not None and not usage_closed:
                self._close_usage(
                    workspace.id,
                    request_id,
                    extra=usage_ctx.extra_billed_tokens if usage_ctx else 0,
                )
                usage_closed = True
            if assistant is not None and not settled:
                self._cancel_assistant(conversation, assistant, accumulated=accumulated)
                settled = True
            raise
        except AppError:
            # Pre-stream validation / quota: do not persist a turn if we never committed.
            if turn_committed:
                if request_id is not None and not usage_closed:
                    self._close_usage(
                        workspace.id,
                        request_id,
                        extra=usage_ctx.extra_billed_tokens if usage_ctx else 0,
                    )
                    usage_closed = True
                if assistant is not None and not settled:
                    self._fail_assistant(conversation, assistant, accumulated=accumulated)
            else:
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
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
        ConversationPolicy.require(membership, ConversationAction.UPDATE)

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
        usage_closed = False
        turn_committed = False
        request_id: str | None = None
        accumulated = ""
        usage_ctx: GenerationUsageContext | None = None
        needs_title = not bool((conversation.title or "").strip())

        try:
            self._heal_stale_generations(conversation, workspace)

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
            knowledge = self.expert_query.resolve_knowledge(
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
                attachments=[],
                status=MessageStatus.STREAMING.value,
                created_at=now,
                updated_at=now,
            )
            self.repo.create_message(assistant)
            conversation.updated_at = now
            self.db.flush()
            invocation = self._workspace_invocation(
                workspace=workspace,
                actor=actor,
                conversation=conversation,
                assistant=assistant,
            )
            mcp_tools = list(
                McpGrantResolver(self.db, settings=self.settings).resolve(
                    invocation,
                    conversation.expert_id,
                )
            )
            self._reserve_turn(
                workspace=workspace,
                actor=actor,
                conversation=conversation,
                assistant=assistant,
                reservation_multiplier=(
                    self.settings.mcp_max_tool_iterations + 1 if mcp_tools else 1
                ),
            )
            self.db.commit()
            turn_committed = True
            request_id = str(assistant.id)
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
            usage_ctx = self._usage_context(
                workspace=workspace,
                actor=actor,
                conversation=conversation,
                assistant=assistant,
            )

            try:
                if mcp_tools:
                    yield {"event": "status", "data": {"stage": "using_tools"}}
                    loop_executor = ToolLoopTurnExecutor(
                        self.db,
                        settings=self.settings,
                        rag=self.expert_query._rag,
                    )
                    loop = None
                    for lifecycle in loop_executor.execute_events(
                        knowledge=knowledge,
                        expert_id=conversation.expert_id,
                        question=question,
                        invocation=invocation,
                        usage_context=usage_ctx,
                        tools=mcp_tools,
                        history=history,
                    ):
                        if lifecycle.event == "complete":
                            loop = lifecycle.result
                        else:
                            yield {
                                "event": lifecycle.event,
                                "data": lifecycle.data,
                            }
                    if loop is None:
                        raise AppError(
                            ErrorCategory.GENERATION_FAILED,
                            "The MCP tool loop did not complete.",
                        )
                    if loop.pending is not None:
                        pending_copy = "This tool call is awaiting your approval."
                        assistant.content = pending_copy
                        assistant.citations = []
                        assistant.status = MessageStatus.PENDING.value
                        assistant.updated_at = datetime.now(timezone.utc)
                        conversation.updated_at = assistant.updated_at
                        self._settle_usage(
                            workspace.id,
                            request_id,
                            usage_ctx.extra_billed_tokens,
                        )
                        self.db.commit()
                        usage_closed = True
                        settled = True
                        yield {
                            "event": "tool_approval_required",
                            "data": {
                                "approval_id": str(loop.pending.id),
                                "tool_call_id": loop.pending.tool_call_id,
                                "connection_name": loop.pending.connection_name,
                                "tool_name": loop.pending.tool_name,
                                "arguments": loop.pending.arguments,
                                "expires_at": loop.pending.expires_at.isoformat(),
                                "conversation_id": str(conversation.id),
                                "assistant_message_id": str(assistant.id),
                                "status": MessageStatus.PENDING.value,
                            },
                        }
                        return

                    answer = loop.answer
                    citations = ConversationService.normalize_citations(loop.citations)
                    loop_payload = loop.as_payload()
                    self._complete_and_settle(
                        conversation,
                        assistant,
                        content=answer,
                        citations=citations,
                        usage_event_id=None,
                        workspace_id=workspace.id,
                        request_id=request_id,
                        actual_tokens=self._actual_tokens(
                            loop_payload,
                            extra_billed=usage_ctx.extra_billed_tokens,
                        ),
                    )
                    usage_closed = True
                    settled = True
                    if answer:
                        yield {"event": "replace", "data": {"text": answer}}
                    final_data = redact_public_models(
                        {
                            **loop_payload,
                            "conversation_id": str(conversation.id),
                            "user_message_id": str(user_msg.id),
                            "assistant_message_id": str(assistant.id),
                            "status": MessageStatus.COMPLETED.value,
                            "citations": citations,
                        }
                    )
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
                    return

                for item in self.expert_query.query_stream(
                    workspace=workspace,
                    membership=membership,
                    actor=actor,
                    expert_id=conversation.expert_id,
                    question=question,
                    history=history,
                    usage_context=usage_ctx,
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
                        self._complete_and_settle(
                            conversation,
                            assistant,
                            content=answer,
                            citations=citations,
                            usage_event_id=usage_id,
                            workspace_id=workspace.id,
                            request_id=request_id,
                            actual_tokens=self._actual_tokens(
                                data, extra_billed=usage_ctx.extra_billed_tokens
                            ),
                        )
                        usage_closed = True
                        settled = True
                        final_data = redact_public_models(
                            {
                                **data,
                                "conversation_id": str(conversation.id),
                                "user_message_id": str(user_msg.id),
                                "assistant_message_id": str(assistant.id),
                                "status": MessageStatus.COMPLETED.value,
                                "citations": citations,
                            }
                        )
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
                if request_id is not None and not usage_closed:
                    self._close_usage(
                        workspace.id, request_id, extra=usage_ctx.extra_billed_tokens
                    )
                    usage_closed = True
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
                if request_id is not None and not usage_closed:
                    self._close_usage(
                        workspace.id, request_id, extra=usage_ctx.extra_billed_tokens
                    )
                    usage_closed = True
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
            if request_id is not None and not usage_closed:
                self._close_usage(
                    workspace.id,
                    request_id,
                    extra=usage_ctx.extra_billed_tokens if usage_ctx else 0,
                )
                usage_closed = True
            if assistant is not None and not settled:
                self._cancel_assistant(conversation, assistant, accumulated=accumulated)
                settled = True
            raise
        except AppError:
            if turn_committed:
                if request_id is not None and not usage_closed:
                    self._close_usage(
                        workspace.id,
                        request_id,
                        extra=usage_ctx.extra_billed_tokens if usage_ctx else 0,
                    )
                    usage_closed = True
                if assistant is not None and not settled:
                    self._fail_assistant(conversation, assistant, accumulated=accumulated)
            else:
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            self.lock.release(conversation_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _usage_context(
        self,
        *,
        workspace: Workspace,
        actor: User,
        conversation: Conversation,
        assistant: Message,
    ) -> GenerationUsageContext:
        return ChatInvocationContext.workspace_user(
            workspace_id=workspace.id,
            user_id=actor.id,
            expert_id=conversation.expert_id,
            conversation_id=conversation.id,
            message_id=assistant.id,
            request_id=str(assistant.id),
        ).to_usage_context()

    def _workspace_invocation(
        self,
        *,
        workspace: Workspace,
        actor: User,
        conversation: Conversation,
        assistant: Message,
    ) -> ChatInvocationContext:
        return ChatInvocationContext.workspace_user(
            workspace_id=workspace.id,
            user_id=actor.id,
            expert_id=conversation.expert_id,
            conversation_id=conversation.id,
            message_id=assistant.id,
            request_id=str(assistant.id),
        )

    def _reserve_turn(
        self,
        *,
        workspace: Workspace,
        actor: User,
        conversation: Conversation,
        assistant: Message,
        reservation_multiplier: int = 1,
    ) -> None:
        AiUsageService(self.db, self.settings).reserve_ai_usage(
            workspace.id,
            str(assistant.id),
            self.settings.effective_ai_usage_reservation_tokens
            * max(1, int(reservation_multiplier)),
            conversation_id=conversation.id,
            message_id=assistant.id,
            user_id=actor.id,
            expert_id=conversation.expert_id,
        )

    def _heal_stale_generations(self, conversation: Conversation, workspace: Workspace) -> None:
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=self.lock.ttl_seconds)
        stale = self.repo.cancel_stale_generations(
            conversation.id, older_than=stale_before
        )
        if not stale:
            return
        self.db.commit()
        for msg in stale:
            self._release_usage(workspace.id, str(msg.id))

    def _actual_tokens(
        self, final_data: dict[str, Any], extra_billed: int = 0
    ) -> int:
        return settled_tokens_from_payload(
            self.settings, final_data, extra_billed=extra_billed
        )

    def _close_usage(
        self, workspace_id: uuid.UUID, request_id: str, extra: int = 0
    ) -> None:
        if extra > 0:
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._settle_usage(workspace_id, request_id, extra)
                self.db.commit()
                return
            except Exception:  # noqa: BLE001
                logger.exception("chat_orchestrator_extra_settle_failed")
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
        self._release_usage(workspace_id, request_id)

    def _settle_usage(
        self, workspace_id: uuid.UUID, request_id: str, actual: int
    ) -> None:
        AiUsageService(self.db, self.settings).settle_ai_usage(
            workspace_id, request_id, actual
        )

    def _complete_and_settle(
        self,
        conversation: Conversation,
        assistant: Message,
        *,
        content: str,
        citations: list[dict[str, Any]],
        usage_event_id: uuid.UUID | None,
        workspace_id: uuid.UUID,
        request_id: str | None,
        actual_tokens: int,
    ) -> None:
        """Persist the completed assistant row and settle usage in one commit."""
        self._apply_complete_fields(
            conversation,
            assistant,
            content=content,
            citations=citations,
            usage_event_id=usage_event_id,
        )
        if request_id is not None:
            self._settle_usage(workspace_id, request_id, actual_tokens)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("chat_orchestrator_complete_commit_failed")
            self._apply_complete_fields(
                conversation,
                assistant,
                content=content,
                citations=citations,
                usage_event_id=None,
            )
            if request_id is not None:
                self._settle_usage(workspace_id, request_id, actual_tokens)
            self.db.commit()

    def _apply_complete_fields(
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

    def _release_usage(self, workspace_id: uuid.UUID, request_id: str) -> None:
        try:
            self.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            AiUsageService(self.db, self.settings).release_ai_usage(
                workspace_id, request_id
            )
            self.db.commit()
        except AppError as exc:
            if exc.category == ErrorCategory.NOT_FOUND:
                return
            self.db.rollback()
            logger.exception("chat_orchestrator_release_failed")
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception("chat_orchestrator_release_failed")

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
