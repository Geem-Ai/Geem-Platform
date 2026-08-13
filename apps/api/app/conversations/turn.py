"""Shared Chat execution core (Phase 7B).

Workspace Chat persists around this. Public ``/api/v1/chat`` is stateless.
Neither path reimplements RAG, Expert auth, or AI metering.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.conversations.invocation import ChatInvocationContext
from app.conversations.service import ConversationService
from app.conversations.validation import validate_chat_message
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.query_service import ExpertQueryService
from app.usage.metered import MeteredWorkspaceGeneration
from app.usage.weights import settled_tokens_from_payload
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)


class ChatTurnExecutor:
    """One Expert turn: authorize → RAG/general → citations.

    Callers own AI reservation via ``MeteredWorkspaceGeneration``.
    """

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        expert_query: ExpertQueryService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.expert_query = expert_query or ExpertQueryService(db, self.settings)

    def validate_message(self, content: str) -> str:
        return validate_chat_message(content, settings=self.settings)

    def authorize_expert(
        self,
        *,
        workspace: Workspace,
        expert_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Fail closed before AI reservation / retrieval."""
        self.expert_query.resolve_knowledge_for_workspace(
            workspace=workspace,
            expert_id=expert_id,
            actor_id=actor_id,
        )

    def execute(
        self,
        *,
        workspace: Workspace,
        expert_id: uuid.UUID,
        question: str,
        invocation: ChatInvocationContext,
        meter: MeteredWorkspaceGeneration,
    ) -> dict[str, Any]:
        usage_ctx = meter.context()
        result = self.expert_query.query_for_workspace(
            workspace=workspace,
            expert_id=expert_id,
            question=question,
            usage_context=usage_ctx,
            actor_id=invocation.api_key_id,
        )
        citations = ConversationService.normalize_citations(result.get("citations") or [])
        billed = settled_tokens_from_payload(
            self.settings, result, extra_billed=usage_ctx.extra_billed_tokens
        )
        meter.settle(result)
        return {
            "answer": result.get("answer") or "",
            "citations": citations,
            "billed_tokens": billed,
            "insufficient_context": bool(result.get("insufficient_context")),
            "model": result.get("model"),
        }

    def stream(
        self,
        *,
        workspace: Workspace,
        expert_id: uuid.UUID,
        question: str,
        invocation: ChatInvocationContext,
        meter: MeteredWorkspaceGeneration,
        request_id: str,
    ) -> Iterator[dict[str, Any]]:
        usage_ctx = meter.context()
        accumulated = ""
        settled = False
        yield {
            "event": "message_start",
            "data": {
                "request_id": request_id,
                "expert_id": str(expert_id),
            },
        }
        try:
            for item in self.expert_query.query_stream_for_workspace(
                workspace=workspace,
                expert_id=expert_id,
                question=question,
                usage_context=usage_ctx,
                actor_id=invocation.api_key_id,
            ):
                event = item.get("event")
                data = item.get("data") or {}
                if event == "token":
                    text = data.get("text") or ""
                    accumulated += text
                    yield {"event": "delta", "data": {"content": text}}
                elif event == "replace":
                    accumulated = data.get("text") or ""
                    yield {"event": "delta", "data": {"content": accumulated}}
                elif event == "final":
                    citations = ConversationService.normalize_citations(
                        data.get("citations") or []
                    )
                    answer = data.get("answer") or accumulated or ""
                    billed = settled_tokens_from_payload(
                        self.settings, data, extra_billed=usage_ctx.extra_billed_tokens
                    )
                    meter.settle(data)
                    settled = True
                    yield {
                        "event": "message_complete",
                        "data": {
                            "request_id": request_id,
                            "answer": answer,
                            "citations": citations,
                            "usage": {"billed_tokens": billed},
                        },
                    }
                # Drop internal status events from the public contract.
            if not settled and not meter.closed:
                meter.release()
        except AppError as exc:
            if not meter.closed:
                meter.release()
            yield {
                "event": "error",
                "data": {
                    "code": exc.category.value,
                    "error": exc.category.value,
                    "message": exc.message,
                    "details": exc.details,
                },
            }
        except GeneratorExit:
            if not meter.closed:
                meter.release()
            raise
        except Exception:  # noqa: BLE001
            logger.exception("public_chat_turn_failed")
            if not meter.closed:
                meter.release()
            yield {
                "event": "error",
                "data": {
                    "code": ErrorCategory.GENERATION_FAILED.value,
                    "error": ErrorCategory.GENERATION_FAILED.value,
                    "message": "Generation failed.",
                },
            }
