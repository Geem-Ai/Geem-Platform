"""Expert-scoped retrieval and optional deterministic Agent context cache."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import Citation
from app.core.config import Settings, get_settings
from app.db.models import Chunk, Document
from app.experts.knowledge import ResolvedExpertKnowledge
from app.experts.models import ExpertDocument, ExpertKnowledgeMode
from app.rag.service import RagService
from app.usage.attribution import GenerationUsageContext

logger = logging.getLogger(__name__)


class AgentContextCache(Protocol):
    def get(self, key: str) -> bytes | str | None: ...

    def setex(self, key: str, ttl: int, value: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class AgentRetrievalResult:
    source_xml: str
    citations: tuple[Citation, ...]
    insufficient_context: bool | None
    status: str
    question_hash: str
    knowledge_revision: str | None


class AgentRetrievalService:
    """Resolve fresh or continuation context without making Redis authoritative.

    Fresh user rounds always retrieve. Tool continuations may reuse a cache
    entry only when Workspace, Expert, API key, question, and a reliably
    computed knowledge revision all match. Any cache or revision failure falls
    back to scoped retrieval.
    """

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        rag_service: RagService | None = None,
        cache: AgentContextCache | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.rag = rag_service or RagService(db, self.settings)
        self._cache = cache

    def prepare(
        self,
        *,
        knowledge: ResolvedExpertKnowledge,
        api_key_id: uuid.UUID,
        question: str,
        continuation: bool,
        usage_context: GenerationUsageContext | None = None,
    ) -> AgentRetrievalResult:
        normalized_question = (question or "").strip()
        question_hash = hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()
        expert = knowledge.authorized.expert

        if expert.knowledge_mode == ExpertKnowledgeMode.GENERAL.value:
            return AgentRetrievalResult(
                source_xml="",
                citations=(),
                insufficient_context=None,
                status="skipped_general",
                question_hash=question_hash,
                knowledge_revision=self.knowledge_revision(knowledge),
            )

        revision = self.knowledge_revision(knowledge)
        cache_key = (
            self._cache_key(
                workspace_id=knowledge.consumer_workspace_id,
                expert_id=knowledge.expert_id,
                api_key_id=api_key_id,
                question_hash=question_hash,
                knowledge_revision=revision,
            )
            if revision is not None
            else None
        )
        if continuation and cache_key is not None:
            cached = self._cache_get(cache_key, question_hash=question_hash)
            if cached is not None:
                return AgentRetrievalResult(
                    source_xml=cached["source_xml"],
                    citations=tuple(cached["citations"]),
                    insufficient_context=bool(cached["insufficient_context"]),
                    status="cache_hit",
                    question_hash=question_hash,
                    knowledge_revision=revision,
                )

        prepared = self.rag.prepare_expert_context_for_agent(
            question=normalized_question,
            knowledge=knowledge,
            usage_context=usage_context,
        )
        chunks = prepared.get("context_chunks") or []
        citations = tuple(self._citation(chunk) for chunk in chunks)
        result = AgentRetrievalResult(
            source_xml=str(prepared.get("context") or ""),
            citations=citations,
            insufficient_context=not bool(chunks),
            status="executed",
            question_hash=question_hash,
            knowledge_revision=revision,
        )
        if cache_key is not None:
            self._cache_set(cache_key, result)
        return result

    def knowledge_revision(
        self, knowledge: ResolvedExpertKnowledge
    ) -> str | None:
        """Fingerprint retrieval-affecting Expert, membership, and index state.

        Document rows are immutable across replacements and are updated when
        ingestion reaches ready. Chunk aggregates include the index version and
        cardinality, making a partially rebuilt index a different revision.
        Unexpected/missing state disables caching rather than producing an
        under-scoped revisionless key.
        """

        try:
            expert = knowledge.authorized.expert
            links = self.db.execute(
                select(
                    ExpertDocument.id,
                    ExpertDocument.document_id,
                    ExpertDocument.source_id,
                    ExpertDocument.created_at,
                    Document.sha256,
                    Document.status,
                    Document.processing_version,
                    Document.updated_at,
                    Document.completed_at,
                    Document.deleted_at,
                )
                .join(Document, Document.id == ExpertDocument.document_id)
                .where(ExpertDocument.expert_id == expert.id)
                .order_by(ExpertDocument.document_id)
            ).all()

            ready_ids = tuple(sorted(str(value) for value in knowledge.ready_document_ids))
            observed_ready = tuple(
                sorted(
                    str(row.document_id)
                    for row in links
                    if row.status == "ready" and row.deleted_at is None
                )
            )
            if ready_ids != observed_ready:
                return None

            chunk_rows: list[Any] = []
            if knowledge.ready_document_ids:
                chunk_rows = self.db.execute(
                    select(
                        Chunk.document_id,
                        func.count(Chunk.id).label("chunk_count"),
                        func.min(Chunk.created_at).label("first_chunk_at"),
                        func.max(Chunk.created_at).label("last_chunk_at"),
                        func.min(Chunk.embedding_version).label("min_embedding_version"),
                        func.max(Chunk.embedding_version).label("max_embedding_version"),
                    )
                    .where(Chunk.document_id.in_(knowledge.ready_document_ids))
                    .group_by(Chunk.document_id)
                    .order_by(Chunk.document_id)
                ).all()
                if len(chunk_rows) != len(knowledge.ready_document_ids):
                    return None

            payload = {
                "expert_id": str(expert.id),
                "expert_updated_at": _json_scalar(expert.updated_at),
                "knowledge_mode": expert.knowledge_mode,
                "rag_config": expert.rag_config or {},
                "effective_rag_config": knowledge.rag_config.as_dict(),
                "retrieval_runtime": {
                    "rag_pipeline_version": self.settings.rag_pipeline_version,
                    "embedding_version": self.settings.embedding_version,
                    "embedding_model": self.settings.openrouter_embedding_model,
                    "rerank_model": self.settings.openrouter_rerank_model,
                    "max_context_tokens": self.settings.max_context_tokens,
                },
                "links": [
                    {
                        "id": str(row.id),
                        "document_id": str(row.document_id),
                        "source_id": str(row.source_id) if row.source_id else None,
                        "linked_at": _json_scalar(row.created_at),
                        "sha256": row.sha256,
                        "status": row.status,
                        "processing_version": row.processing_version,
                        "updated_at": _json_scalar(row.updated_at),
                        "completed_at": _json_scalar(row.completed_at),
                        "deleted_at": _json_scalar(row.deleted_at),
                    }
                    for row in links
                ],
                "chunks": [
                    {
                        "document_id": str(row.document_id),
                        "count": int(row.chunk_count),
                        "first": _json_scalar(row.first_chunk_at),
                        "last": _json_scalar(row.last_chunk_at),
                        "min_version": row.min_embedding_version,
                        "max_version": row.max_embedding_version,
                    }
                    for row in chunk_rows
                ],
            }
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            return hashlib.sha256(encoded).hexdigest()
        except Exception:  # noqa: BLE001 - cache is never correctness-critical
            logger.warning("agent.context_revision_unavailable", exc_info=True)
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return None

    @staticmethod
    def _cache_key(
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        api_key_id: uuid.UUID,
        question_hash: str,
        knowledge_revision: str,
    ) -> str:
        material = ":".join(
            (
                str(workspace_id),
                str(expert_id),
                str(api_key_id),
                question_hash,
                knowledge_revision,
            )
        )
        digest = hashlib.sha256(material.encode("ascii")).hexdigest()
        return f"agent:context:v1:{digest}"

    @staticmethod
    def _citation(chunk: dict[str, Any]) -> Citation:
        raw = str(chunk.get("canonical_text") or "").strip()
        snippet = " ".join(raw.split())[:320]
        return Citation(
            chunk_id=uuid.UUID(str(chunk["chunk_id"])),
            document_id=uuid.UUID(str(chunk["document_id"])),
            document_title=str(chunk.get("document_title") or ""),
            page=int(chunk.get("page") or 0),
            snippet=snippet,
        )

    def _client(self) -> AgentContextCache:
        if self._cache is None:
            self._cache = Redis.from_url(
                self.settings.redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        return self._cache

    def _cache_get(
        self, key: str, *, question_hash: str
    ) -> dict[str, Any] | None:
        try:
            raw = self._client().get(key)
            if raw is None:
                return None
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            if not isinstance(payload, dict) or payload.get("question_hash") != question_hash:
                return None
            citations = tuple(
                Citation.model_validate(item) for item in payload.get("citations", [])
            )
            return {
                "source_xml": str(payload.get("source_xml") or ""),
                "citations": citations,
                "insufficient_context": bool(payload.get("insufficient_context")),
            }
        except (RedisError, OSError, ValueError, TypeError):
            logger.info("agent.context_cache_miss_on_error", exc_info=True)
            return None

    def _cache_set(self, key: str, result: AgentRetrievalResult) -> None:
        ttl = max(1, int(self.settings.agent_context_cache_ttl_seconds))
        payload = json.dumps(
            {
                "source_xml": result.source_xml,
                "citations": [item.model_dump(mode="json") for item in result.citations],
                "insufficient_context": bool(result.insufficient_context),
                "question_hash": result.question_hash,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            self._client().setex(key, ttl, payload)
        except (RedisError, OSError):
            logger.info("agent.context_cache_write_skipped", exc_info=True)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


__all__ = ["AgentRetrievalResult", "AgentRetrievalService"]
