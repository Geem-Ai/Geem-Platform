"""Phase 14 Agent retrieval/cache correctness tests."""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from redis.exceptions import RedisError

from app.agent.retrieval import AgentRetrievalService
from app.core.config import Settings
from app.experts.models import ExpertKnowledgeMode
from app.rag.service import RagService, expert_query_embedding_input
from app.usage.weights import OpenRouterFamily


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
        settings=Settings(
            _env_file=None,
            agent_context_cache_ttl_seconds=77,
            agent_query_embedding_cache_ttl_seconds=41,
        ),
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
    assert len(cache.get_calls) == 1
    assert cache.get_calls[0].startswith("agent:query-embedding:v1:")
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
    assert len(cache.get_calls) == 1
    assert cache.get_calls[0].startswith("agent:query-embedding:v1:")
    assert cache.set_calls == []
    assert rag.prepare_expert_context_for_agent.call_count == 1


def test_fresh_round_reuses_embedding_across_api_keys_but_retrieves_again(
    monkeypatch,
) -> None:
    cache = _MemoryCache()
    knowledge = _knowledge()
    vector = [0.125, -0.25, 0.5]
    prepared = _prepared_context("fresh evidence") | {"_query_embedding": vector}
    service, rag = _service(cache, prepared)
    monkeypatch.setattr(service, "knowledge_revision", lambda _knowledge: "revision-a")

    first = service.prepare(
        knowledge=knowledge,
        api_key_id=uuid.uuid4(),
        question="Invoice   total",
        continuation=False,
    )
    second = service.prepare(
        knowledge=knowledge,
        api_key_id=uuid.uuid4(),
        question="  Invoice total  ",
        continuation=False,
    )

    assert first.status == second.status == "executed"
    assert rag.prepare_expert_context_for_agent.call_count == 2
    calls = rag.prepare_expert_context_for_agent.call_args_list
    assert calls[0].kwargs["query_embedding"] is None
    assert calls[1].kwargs["query_embedding"] == vector
    embedding_writes = [
        call for call in cache.set_calls if call[0].startswith("agent:query-embedding:v1:")
    ]
    assert len(embedding_writes) == 1
    assert embedding_writes[0][1] == 41

    # The Redis key exposes neither tenant identifiers nor query content.
    embedding_key = embedding_writes[0][0]
    assert str(knowledge.consumer_workspace_id) not in embedding_key
    assert str(knowledge.expert_id) not in embedding_key
    assert "Invoice" not in embedding_key


def test_embedding_cache_key_isolates_scope_model_and_version() -> None:
    cache = _MemoryCache()
    service, _rag = _service(cache)
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    normalized = expert_query_embedding_input("  المادة ١٤  ")

    base = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=expert_id,
        normalized_query=normalized,
    )
    same = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=expert_id,
        normalized_query=expert_query_embedding_input("المادة ١٤"),
    )
    another_workspace = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=uuid.uuid4(),
        expert_id=expert_id,
        normalized_query=normalized,
    )
    another_expert = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=uuid.uuid4(),
        normalized_query=normalized,
    )

    model_service = AgentRetrievalService(
        MagicMock(),
        settings=service.settings.model_copy(
            update={"openrouter_embedding_model": "different/embed-model"}
        ),
        rag_service=MagicMock(),
        cache=cache,
    )
    another_model = model_service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=expert_id,
        normalized_query=normalized,
    )
    version_service = AgentRetrievalService(
        MagicMock(),
        settings=service.settings.model_copy(update={"embedding_version": "v-next"}),
        rag_service=MagicMock(),
        cache=cache,
    )
    another_version = version_service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=expert_id,
        normalized_query=normalized,
    )

    assert base == same
    assert None not in {
        base,
        another_workspace,
        another_expert,
        another_model,
        another_version,
    }
    assert len(
        {base, another_workspace, another_expert, another_model, another_version}
    ) == 5


def test_corrupt_embedding_cache_fails_open_and_is_replaced(monkeypatch) -> None:
    cache = _MemoryCache()
    knowledge = _knowledge()
    replacement = [0.1, 0.2]
    service, rag = _service(
        cache,
        _prepared_context("replacement") | {"_query_embedding": replacement},
    )
    monkeypatch.setattr(service, "knowledge_revision", lambda _knowledge: None)
    key = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=knowledge.consumer_workspace_id,
        expert_id=knowledge.expert_id,
        normalized_query=expert_query_embedding_input("question"),
    )
    assert key is not None
    cache.values[key] = json.dumps(
        {
            "schema": 1,
            "model": service.settings.openrouter_embedding_model,
            "embedding_version": service.settings.embedding_version,
            "dimension": 2,
            "vector": [0.5, float("nan")],
        }
    )

    result = service.prepare(
        knowledge=knowledge,
        api_key_id=uuid.uuid4(),
        question="question",
        continuation=False,
    )

    assert result.status == "executed"
    assert rag.prepare_expert_context_for_agent.call_args.kwargs["query_embedding"] is None
    repaired = json.loads(cache.values[key])
    assert repaired["vector"] == replacement
    assert repaired["dimension"] == len(replacement)


def test_redis_outage_fails_open_for_embedding_read_and_write(monkeypatch) -> None:
    class _UnavailableCache:
        def get(self, _key: str) -> None:
            raise RedisError("redis unavailable")

        def setex(self, _key: str, _ttl: int, _value: str) -> None:
            raise RedisError("redis unavailable")

    knowledge = _knowledge()
    rag = MagicMock()
    rag.prepare_expert_context_for_agent.return_value = _prepared_context("live") | {
        "_query_embedding": [0.25, 0.75]
    }
    service = AgentRetrievalService(
        MagicMock(),
        settings=Settings(_env_file=None),
        rag_service=rag,
        cache=_UnavailableCache(),
    )
    monkeypatch.setattr(service, "knowledge_revision", lambda _knowledge: None)

    result = service.prepare(
        knowledge=knowledge,
        api_key_id=uuid.uuid4(),
        question="still retrieve",
        continuation=False,
    )

    assert result.status == "executed"
    assert result.source_xml == "<sources>live</sources>"
    assert rag.prepare_expert_context_for_agent.call_args.kwargs["query_embedding"] is None


def test_cached_vector_validation_rejects_wrong_shape_dimension_and_non_finite() -> None:
    validate = AgentRetrievalService._validated_query_embedding  # noqa: SLF001

    assert validate([1, 2.5], declared_dimension=2) == [1.0, 2.5]
    assert validate([], declared_dimension=0) is None
    assert validate([1.0], declared_dimension=2) is None
    assert validate([1.0], expected_dimension=2) is None
    assert validate([True]) is None
    assert validate(["1.0"]) is None
    assert validate([float("inf")]) is None
    assert validate([float("nan")]) is None


def test_embedding_payload_tamper_or_cross_scope_swap_is_a_cache_miss() -> None:
    cache = _MemoryCache()
    service, _rag = _service(cache)
    workspace_id = uuid.uuid4()
    normalized = expert_query_embedding_input("private question")
    key_a = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=uuid.uuid4(),
        normalized_query=normalized,
    )
    key_b = service._query_embedding_cache_key(  # noqa: SLF001
        workspace_id=workspace_id,
        expert_id=uuid.uuid4(),
        normalized_query=normalized,
    )
    assert key_a is not None and key_b is not None and key_a != key_b

    service._query_embedding_cache_set(key_a, [0.1, 0.2])  # noqa: SLF001
    assert service._query_embedding_cache_get(key_a) == [0.1, 0.2]  # noqa: SLF001

    tampered = json.loads(cache.values[key_a])
    tampered["vector"] = [0.9, 0.8]
    cache.values[key_a] = json.dumps(tampered)
    assert service._query_embedding_cache_get(key_a) is None  # noqa: SLF001

    service._query_embedding_cache_set(key_a, [0.1, 0.2])  # noqa: SLF001
    cache.values[key_b] = cache.values[key_a]
    assert service._query_embedding_cache_get(key_b) is None  # noqa: SLF001


def test_rag_injected_embedding_skips_only_embedding_provider_and_usage_note() -> None:
    settings = Settings(_env_file=None)
    rag = object.__new__(RagService)
    rag.db = MagicMock()
    rag.settings = settings
    rag.embedder = MagicMock()
    rag.embedder.embed_query.return_value = [0.75, 0.25]
    rag.reranker = MagicMock()
    rag.reranker.rerank.return_value = []
    rag.vectors = MagicMock()
    rag.vectors.search_expert.return_value = []
    rag.chunker = MagicMock()
    rag._note_openrouter_call = MagicMock()  # type: ignore[method-assign]

    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    document_id = uuid.uuid4()
    knowledge = SimpleNamespace(
        has_ready_knowledge=True,
        scope=SimpleNamespace(
            consumer_workspace_id=workspace_id,
            knowledge_workspace_id=workspace_id,
            expert_id=expert_id,
        ),
        ready_document_ids=(document_id,),
        rag_config=SimpleNamespace(
            top_k=3,
            similarity_threshold=None,
            rerank_top_n=2,
        ),
    )

    injected = [0.1, 0.2]
    prepared = rag.prepare_expert_context_for_agent(
        question="plain question",
        knowledge=knowledge,
        query_embedding=injected,
    )

    rag.embedder.embed_query.assert_not_called()
    rag.vectors.search_expert.assert_called_once()
    assert rag.vectors.search_expert.call_args.kwargs["vector"] == injected
    assert prepared["_query_embedding"] == injected
    assert [call.args[0] for call in rag._note_openrouter_call.call_args_list] == [
        OpenRouterFamily.RERANK
    ]

    rag._note_openrouter_call.reset_mock()
    rag.vectors.search_expert.reset_mock()
    rag.prepare_expert_context_for_agent(
        question="uncached question",
        knowledge=knowledge,
    )

    rag.embedder.embed_query.assert_called_once()
    assert [call.args[0] for call in rag._note_openrouter_call.call_args_list] == [
        OpenRouterFamily.EMBED,
        OpenRouterFamily.RERANK,
    ]
