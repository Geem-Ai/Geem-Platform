"""Phase 14 Agent retrieval/cache correctness tests."""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent.retrieval import AgentRetrievalService
from app.core.config import Settings
from app.experts.models import ExpertKnowledgeMode


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, int, str]] = []

    def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.set_calls.append((key, ttl, value))
        self.values[key] = value


def _knowledge(*, mode: str = ExpertKnowledgeMode.RAG.value):
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    expert = SimpleNamespace(
        id=expert_id,
        knowledge_mode=mode,
        rag_config={"client_agent": {"enabled": True}},
    )
    return SimpleNamespace(
        authorized=SimpleNamespace(expert=expert),
        consumer_workspace_id=workspace_id,
        expert_id=expert_id,
    )


def _prepared_context(text: str = "Scoped source") -> dict:
    return {
        "context": f"<sources>{text}</sources>",
        "context_chunks": [
            {
                "chunk_id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "document_title": "Workspace document",
                "page": 3,
                "canonical_text": f"  {text}   with   normalized spacing  ",
                # This field must never escape through the citation contract.
                "storage_key": "workspaces/secret/original.pdf",
            }
        ],
    }


def _service(cache: _MemoryCache, prepared: dict | None = None):
    rag = MagicMock()
    rag.prepare_expert_context_for_agent.return_value = prepared or _prepared_context()
    service = AgentRetrievalService(
        MagicMock(),
        settings=Settings(_env_file=None, agent_context_cache_ttl_seconds=77),
        rag_service=rag,
        cache=cache,
    )
    return service, rag


def test_fresh_user_round_always_retrieves_and_refreshes_cache(monkeypatch) -> None:
    cache = _MemoryCache()
    knowledge = _knowledge()
    api_key_id = uuid.uuid4()
    service, rag = _service(cache, _prepared_context("fresh evidence"))
    monkeypatch.setattr(service, "knowledge_revision", lambda _knowledge: "revision-a")

    key = service._cache_key(  # noqa: SLF001 - assert the correctness boundary
        workspace_id=knowledge.consumer_workspace_id,
        expert_id=knowledge.expert_id,
        api_key_id=api_key_id,
        question_hash=hashlib.sha256(b"What changed?").hexdigest(),
        knowledge_revision="revision-a",
    )
    cache.values[key] = json.dumps(
        {
            "source_xml": "<sources>stale</sources>",
            "citations": [],
            "insufficient_context": False,
            "question_hash": hashlib.sha256(b"What changed?").hexdigest(),
        }
    )

    result = service.prepare(
        knowledge=knowledge,
        api_key_id=api_key_id,
        question="  What changed?  ",
        continuation=False,
    )

    assert result.status == "executed"
    assert result.source_xml == "<sources>fresh evidence</sources>"
    assert result.insufficient_context is False
    assert result.citations[0].snippet == "fresh evidence with normalized spacing"
    assert "storage_key" not in result.citations[0].model_dump()
    assert cache.get_calls == []
    assert cache.set_calls[-1][0:2] == (key, 77)
    rag.prepare_expert_context_for_agent.assert_called_once()


def test_tool_continuation_uses_matching_cache_without_retrieval(monkeypatch) -> None:
    cache = _MemoryCache()
    knowledge = _knowledge()
    service, rag = _service(cache)
    monkeypatch.setattr(service, "knowledge_revision", lambda _knowledge: "revision-a")
    api_key_id = uuid.uuid4()

    fresh = service.prepare(
        knowledge=knowledge,
        api_key_id=api_key_id,
        question="lookup invoice",
        continuation=False,
    )
    rag.reset_mock()

    replay = service.prepare(
        knowledge=knowledge,
        api_key_id=api_key_id,
        question="lookup invoice",
        continuation=True,
    )

    assert fresh.status == "executed"
    assert replay.status == "cache_hit"
    assert replay.source_xml == fresh.source_xml
    assert replay.citations == fresh.citations
    assert replay.knowledge_revision == "revision-a"
    rag.prepare_expert_context_for_agent.assert_not_called()


def test_continuation_cache_miss_retrieves_and_revision_change_isolated(
    monkeypatch,
) -> None:
    cache = _MemoryCache()
    knowledge = _knowledge()
    service, rag = _service(cache)
    revision = {"value": "revision-a"}
    monkeypatch.setattr(
        service, "knowledge_revision", lambda _knowledge: revision["value"]
    )
    api_key_id = uuid.uuid4()

    first = service.prepare(
        knowledge=knowledge,
        api_key_id=api_key_id,
        question="same question",
        continuation=True,
    )
    revision["value"] = "revision-b"
    second = service.prepare(
        knowledge=knowledge,
        api_key_id=api_key_id,
        question="same question",
        continuation=True,
    )

    assert first.status == "executed"
    assert second.status == "executed"
    assert first.knowledge_revision == "revision-a"
    assert second.knowledge_revision == "revision-b"
    assert rag.prepare_expert_context_for_agent.call_count == 2
    assert len(cache.values) == 2
    assert cache.get_calls[0] != cache.get_calls[1]


def test_unreliable_revision_disables_cache_and_general_mode_skips_rag(
    monkeypatch,
) -> None:
    cache = _MemoryCache()
    service, rag = _service(cache, {"context": "", "context_chunks": []})
    monkeypatch.setattr(service, "knowledge_revision", lambda _knowledge: None)

    executed = service.prepare(
        knowledge=_knowledge(),
        api_key_id=uuid.uuid4(),
        question="unknown",
        continuation=True,
    )
    skipped = service.prepare(
        knowledge=_knowledge(mode=ExpertKnowledgeMode.GENERAL.value),
        api_key_id=uuid.uuid4(),
        question="general",
        continuation=False,
    )

    assert executed.status == "executed"
    assert executed.insufficient_context is True
    assert executed.knowledge_revision is None
    assert skipped.status == "skipped_general"
    assert skipped.insufficient_context is None
    assert cache.get_calls == []
    assert cache.set_calls == []
    assert rag.prepare_expert_context_for_agent.call_count == 1
