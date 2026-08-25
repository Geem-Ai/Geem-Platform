"""Phase 14 post-admission retrieval/provider/settlement orchestration tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import app.agent.service as service_module
from app.agent.messages import normalize_agent_messages
from app.agent.retrieval import AgentRetrievalResult
from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentProviderResult,
    AgentUsage,
    parse_agent_completion_request,
)
from app.agent.service import AgentCompletionService
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertKnowledgeMode
from app.usage.attribution import GenerationUsageContext


def _request_and_messages():
    request = parse_agent_completion_request(
        {
            "model": PUBLIC_MODEL_ID,
            "messages": [
                {"role": "system", "content": "Use concise replies"},
                {"role": "user", "content": "What is in the source?"},
            ],
        },
        settings=Settings(_env_file=None),
    )
    return request, normalize_agent_messages(
        request,
        settings=Settings(_env_file=None),
        digest_key="unit-test-audit-key",
    )


def _result() -> AgentProviderResult:
    return AgentProviderResult(
        message=AgentAssistantResponseMessage(content="Scoped answer", tool_calls=None),
        finish_reason="stop",
        usage=AgentUsage(prompt_tokens=10, completion_tokens=3, total_tokens=13),
        provider_model="private/model",
        provider_request_id="provider-request",
        provider_completion_id="provider-completion",
    )


class _Db:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def commit(self) -> None:
        self.events.append("retrieval_commit")

    def rollback(self) -> None:
        self.events.append("retrieval_rollback")


class _Admission:
    def __init__(
        self,
        events: list[str],
        *,
        execution_mode: str = ExpertKnowledgeMode.RAG.value,
        settle_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.closed = False
        self.db = SimpleNamespace()
        self.request_id = "agent-service-round"
        self.access = SimpleNamespace(workspace_id=uuid.uuid4())
        self.execution_mode = execution_mode
        self.uses_general_knowledge = (
            execution_mode == ExpertKnowledgeMode.GENERAL.value
        )
        expert = SimpleNamespace(
            id=uuid.uuid4(),
            knowledge_mode=ExpertKnowledgeMode.RAG.value,
        )
        self.knowledge = SimpleNamespace(
            authorized=SimpleNamespace(expert=expert),
            expert_id=expert.id,
            system_instructions="Answer as the configured Expert.",
        )
        self._context = GenerationUsageContext(
            workspace_id=self.access.workspace_id,
            expert_id=expert.id,
            api_key_id=uuid.uuid4(),
            request_id=self.request_id,
        )
        self.settle_error = settle_error

    def usage_context(self) -> GenerationUsageContext:
        return self._context

    def settle(self, payload) -> int:
        self.events.append("ai_settle")
        assert payload["usage"] == {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
        }
        assert payload["billed_chat_tokens"] == 11
        if self.settle_error is not None:
            raise self.settle_error
        self.closed = True
        return 17

    def release(self) -> None:
        self.events.append("ai_release")
        self.closed = True


class _Retrieval:
    def __init__(self, events: list[str], *, error: Exception | None = None) -> None:
        self.events = events
        self.error = error

    def prepare(self, **kwargs) -> AgentRetrievalResult:
        self.events.append("retrieval")
        assert kwargs["question"] == "What is in the source?"
        assert kwargs["continuation"] is False
        assert kwargs["usage_context"].api_key_id is not None
        if self.error is not None:
            raise self.error
        return AgentRetrievalResult(
            source_xml=(
                '<SOURCE id="chunk" document_id="document" '
                'document_title="Fixture" page="1">evidence</SOURCE>'
            ),
            citations=(),
            insufficient_context=False,
            status="executed",
            question_hash="question-hash",
            knowledge_revision="revision",
        )


class _Provider:
    def __init__(self, events: list[str], *, error: Exception | None = None) -> None:
        self.events = events
        self.error = error
        self.messages = None
        self.kwargs = None

    def complete_for_agent(self, messages, **kwargs) -> AgentProviderResult:
        self.events.append("provider")
        self.messages = messages
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return _result()


def _service(
    events: list[str],
    *,
    retrieval_error: Exception | None = None,
    provider_error: Exception | None = None,
):
    provider = _Provider(events, error=provider_error)
    service = AgentCompletionService(
        _Db(events),
        settings=Settings(_env_file=None),
        retrieval=_Retrieval(events, error=retrieval_error),
        provider=provider,
    )
    return service, provider


def test_nonstream_round_commits_retrieval_before_provider_then_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    service, provider = _service(events)
    admission = _Admission(events)
    request, normalized = _request_and_messages()

    def record(_db, _settings, **kwargs) -> int:
        events.append("usage_event")
        assert kwargs["charge_now"] is False
        assert kwargs["workspace_id"] == admission.access.workspace_id
        assert kwargs["api_key_id"] == admission.usage_context().api_key_id
        assert kwargs["provider_usage"]["total_tokens"] == 13
        return 11

    monkeypatch.setattr(service_module, "record_openrouter_event", record)
    monkeypatch.setattr(service_module, "security_log", lambda *_args, **_kwargs: None)

    prepared = service.prepare_round(
        request=request,
        normalized=normalized,
        admission=admission,
    )
    completed = service.run_round(prepared)

    assert events == [
        "retrieval",
        "retrieval_commit",
        "provider",
        "usage_event",
        "ai_settle",
    ]
    assert completed.geem.billed_tokens == 17
    assert completed.geem.retrieval == "executed"
    assert admission.closed is True
    assert provider.messages[0]["role"] == "user"
    assert "CLIENT_AGENT_INSTRUCTIONS" in provider.messages[0]["content"]
    assert all(message["role"] not in {"system", "developer"} for message in provider.messages)
    assert provider.kwargs["system_prompt"].count("<SOURCE") == 1
    assert "evidence" in provider.kwargs["system_prompt"]
    assert provider.kwargs["tool_choice"] == "none"


def test_general_execution_mode_skips_retrieval_and_uses_general_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    service, provider = _service(events)
    admission = _Admission(
        events,
        execution_mode=ExpertKnowledgeMode.GENERAL.value,
    )
    request, normalized = _request_and_messages()

    monkeypatch.setattr(
        service_module,
        "load_general_chat_prompt",
        lambda: "GENERAL EXECUTION BASE",
    )
    monkeypatch.setattr(
        service_module,
        "load_agent_rag_prompt",
        lambda: (_ for _ in ()).throw(AssertionError("RAG prompt loaded")),
    )
    monkeypatch.setattr(
        service_module,
        "record_openrouter_event",
        lambda *_args, **_kwargs: events.append("usage_event") or 11,
    )
    monkeypatch.setattr(service_module, "security_log", lambda *_args, **_kwargs: None)

    prepared = service.prepare_round(
        request=request,
        normalized=normalized,
        admission=admission,
    )

    assert events == ["retrieval_commit"]
    assert prepared.retrieval.status == "skipped_general"
    assert prepared.retrieval.citations == ()
    assert prepared.retrieval.insufficient_context is None
    assert prepared.retrieval.knowledge_revision is None
    assert "GENERAL EXECUTION BASE" in prepared.system_prompt
    assert "GEEM_RAG_CONTEXT" not in prepared.system_prompt
    assert admission.knowledge.authorized.expert.knowledge_mode == "rag"

    completed = service.run_round(prepared)

    assert events == [
        "retrieval_commit",
        "provider",
        "usage_event",
        "ai_settle",
    ]
    assert completed.geem.retrieval == "skipped_general"
    assert completed.geem.citations == []
    assert completed.geem.insufficient_context is None
    assert provider.kwargs["system_prompt"] == prepared.system_prompt


def test_retrieval_failure_rolls_back_and_releases_without_provider_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    failure = AppError(ErrorCategory.GENERATION_FAILED, "retrieval failed")
    service, _provider = _service(events, retrieval_error=failure)
    admission = _Admission(events)
    request, normalized = _request_and_messages()
    monkeypatch.setattr(service_module, "security_log", lambda *_args, **_kwargs: None)

    with pytest.raises(AppError) as raised:
        service.prepare_round(
            request=request,
            normalized=normalized,
            admission=admission,
        )

    assert raised.value is failure
    assert events == ["retrieval", "retrieval_rollback", "ai_release"]
    assert admission.closed is True


def test_provider_failure_releases_committed_ai_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    failure = AppError(ErrorCategory.GENERATION_FAILED, "provider failed")
    service, _provider = _service(events, provider_error=failure)
    admission = _Admission(events)
    request, normalized = _request_and_messages()
    monkeypatch.setattr(service_module, "security_log", lambda *_args, **_kwargs: None)
    prepared = service.prepare_round(
        request=request,
        normalized=normalized,
        admission=admission,
    )

    with pytest.raises(AppError) as raised:
        service.run_round(prepared)

    assert raised.value is failure
    assert events == ["retrieval", "retrieval_commit", "provider", "ai_release"]
    assert admission.closed is True


def test_settlement_failure_releases_hold_and_never_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    failure = RuntimeError("settlement unavailable")
    service, _provider = _service(events)
    admission = _Admission(events, settle_error=failure)
    request, normalized = _request_and_messages()
    monkeypatch.setattr(service_module, "record_openrouter_event", lambda *_a, **_kw: 11)
    monkeypatch.setattr(service_module, "security_log", lambda *_args, **_kwargs: None)
    prepared = service.prepare_round(
        request=request,
        normalized=normalized,
        admission=admission,
    )

    with pytest.raises(RuntimeError) as raised:
        service.run_round(prepared)

    assert raised.value is failure
    assert events == [
        "retrieval",
        "retrieval_commit",
        "provider",
        "ai_settle",
        "ai_release",
    ]
    assert admission.closed is True
