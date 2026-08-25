"""One stateless, client-owned Agent model round after paid admission."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.agent.admission import AgentCompletionAdmission
from app.agent.messages import NormalizedAgentMessages, compose_agent_system_prompt
from app.agent.retrieval import AgentRetrievalResult, AgentRetrievalService
from app.agent.schemas import (
    AgentCompletionRequest,
    AgentGeemExtension,
    AgentProviderResult,
    AgentProviderStreamEvent,
    request_control_payload,
    request_tool_choice_payload,
    request_tools_payload,
)
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.experts.models import ExpertKnowledgeMode
from app.experts.prompt import compose_expert_system_prompt
from app.openrouter.chat import OpenRouterChatProvider
from app.openrouter.client import OpenRouterStreamCancellation
from app.rag.service import load_general_chat_prompt
from app.usage.openrouter_billing import record_openrouter_event
from app.usage.weights import OpenRouterFamily

logger = logging.getLogger(__name__)

_AGENT_RAG_PROMPT_PATH = Path(__file__).with_name("prompts") / "agent_rag_v1.txt"


@lru_cache(maxsize=1)
def load_agent_rag_prompt() -> str:
    return _AGENT_RAG_PROMPT_PATH.read_text(encoding="utf-8").strip()


@dataclass(slots=True)
class PreparedAgentRound:
    request: AgentCompletionRequest
    normalized: NormalizedAgentMessages
    admission: AgentCompletionAdmission
    retrieval: AgentRetrievalResult
    system_prompt: str

    @property
    def request_id(self) -> str:
        return self.admission.request_id


@dataclass(frozen=True, slots=True)
class CompletedAgentRound:
    result: AgentProviderResult
    geem: AgentGeemExtension


class AgentCompletionService:
    """Prepare retrieval, invoke the isolated provider path, and settle usage."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        retrieval: AgentRetrievalService | None = None,
        provider: OpenRouterChatProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.retrieval = retrieval or AgentRetrievalService(
            db,
            settings=self.settings,
        )
        self.provider = provider or OpenRouterChatProvider(settings=self.settings)

    def prepare_round(
        self,
        *,
        request: AgentCompletionRequest,
        normalized: NormalizedAgentMessages,
        admission: AgentCompletionAdmission,
    ) -> PreparedAgentRound:
        """Run post-admission retrieval and close its DB transaction before LLM I/O."""

        try:
            retrieval = self.retrieval.prepare(
                knowledge=admission.knowledge,
                api_key_id=admission.usage_context().api_key_id,
                question=normalized.retrieval_question,
                continuation=normalized.is_tool_continuation,
                usage_context=admission.usage_context(),
            )
            # Revision/context queries and usage telemetry must not leave a
            # transaction open while the provider request is in flight.
            self.db.commit()
            expert = admission.knowledge.authorized.expert
            base_prompt = (
                load_general_chat_prompt()
                if expert.knowledge_mode == ExpertKnowledgeMode.GENERAL.value
                else load_agent_rag_prompt()
            )
            expert_prompt = compose_expert_system_prompt(
                base_prompt,
                admission.knowledge.system_instructions,
            )
            system_prompt = compose_agent_system_prompt(
                expert_prompt,
                source_context=retrieval.source_xml,
            )
            audit = normalized.instruction_audit
            security_log(
                "agent.round_prepared",
                request_id=admission.request_id,
                workspace_id=str(admission.access.workspace_id),
                expert_id=str(admission.knowledge.expert_id),
                api_key_id=str(admission.usage_context().api_key_id),
                instruction_length=audit.normalized_length,
                instruction_digest=audit.digest,
                retrieval=retrieval.status,
                continuation=normalized.is_tool_continuation,
                stream=request.stream,
            )
            return PreparedAgentRound(
                request=request,
                normalized=normalized,
                admission=admission,
                retrieval=retrieval,
                system_prompt=system_prompt,
            )
        except Exception:
            self.db.rollback()
            admission.release()
            raise

    def run_round(self, prepared: PreparedAgentRound) -> CompletedAgentRound:
        """Run and settle one non-streaming provider round."""

        try:
            result = self.provider.complete_for_agent(
                prepared.normalized.provider_messages(),
                system_prompt=prepared.system_prompt,
                tools=request_tools_payload(prepared.request),
                tool_choice=request_tool_choice_payload(prepared.request),
                **request_control_payload(prepared.request),
            )
            geem = self.finalize_round(prepared, result)
            return CompletedAgentRound(result=result, geem=geem)
        except Exception:
            if not prepared.admission.closed:
                prepared.admission.release()
            raise

    def stream_events(
        self,
        prepared: PreparedAgentRound,
        *,
        cancellation: OpenRouterStreamCancellation | None = None,
    ) -> Iterator[AgentProviderStreamEvent]:
        """Return the validated provider event iterator for one streaming round."""

        return self.provider.stream_for_agent(
            prepared.normalized.provider_messages(),
            system_prompt=prepared.system_prompt,
            tools=request_tools_payload(prepared.request),
            tool_choice=request_tool_choice_payload(prepared.request),
            cancellation=cancellation,
            **request_control_payload(prepared.request),
        )

    def finalize_round(
        self,
        prepared: PreparedAgentRound,
        result: AgentProviderResult,
    ) -> AgentGeemExtension:
        """Atomically persist provider telemetry and settle the AI reservation."""

        admission = prepared.admission
        usage = result.usage.model_dump(mode="json")
        try:
            billed_chat = record_openrouter_event(
                admission.db,
                self.settings,
                family=OpenRouterFamily.CHAT,
                operation_type="agent_completion",
                provider_usage=usage,
                model=result.provider_model,
                request_id=admission.request_id,
                workspace_id=admission.access.workspace_id,
                expert_id=admission.knowledge.expert_id,
                api_key_id=admission.usage_context().api_key_id,
                extra_metadata={
                    "provider_request_id": result.provider_request_id,
                    "provider_completion_id": result.provider_completion_id,
                    "public_model": prepared.request.model,
                },
                charge_now=False,
            )
            billed_total = admission.settle(
                {
                    "usage": usage,
                    "model": result.provider_model,
                    "billed_chat_tokens": billed_chat,
                }
            )
        except Exception:
            if not admission.closed:
                admission.release()
            raise

        security_log(
            "agent.round_completed",
            request_id=admission.request_id,
            workspace_id=str(admission.access.workspace_id),
            expert_id=str(admission.knowledge.expert_id),
            api_key_id=str(admission.usage_context().api_key_id),
            retrieval=prepared.retrieval.status,
            finish_reason=result.finish_reason,
            billed_tokens=billed_total,
            stream=prepared.request.stream,
        )
        return AgentGeemExtension(
            retrieval=prepared.retrieval.status,
            citations=list(prepared.retrieval.citations),
            insufficient_context=prepared.retrieval.insufficient_context,
            billed_tokens=billed_total,
        )

    @staticmethod
    def abort_round(prepared: PreparedAgentRound) -> None:
        if not prepared.admission.closed:
            prepared.admission.release()


__all__ = [
    "AgentCompletionService",
    "CompletedAgentRound",
    "PreparedAgentRound",
    "load_agent_rag_prompt",
]
