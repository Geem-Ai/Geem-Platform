from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document, UsageEvent
from app.experts.knowledge import ExpertKnowledgeResolver, ResolvedExpertKnowledge
from app.experts.prompt import compose_expert_system_prompt
from app.ingestion.arabic_normalize import normalize_search
from app.ingestion.article_query import (
    article_lexical_patterns,
    expand_article_query,
    extract_article_numbers,
)
from app.ingestion.chunker import PageChunker
from app.openrouter.chat import OpenRouterChatProvider
from app.openrouter.embeddings import OpenRouterEmbeddingProvider
from app.openrouter.rerank import OpenRouterRerankProvider
from app.storage.qdrant_store import QdrantVectorStore
from app.storage.scopes import (
    ExpertRagScope,
    LegacyRagScope,
    RagScope,
    WorkspaceRagScope,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "rag_answer_v1.txt"
GENERAL_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "general_fallback_v1.txt"
GENERAL_CHAT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "general_chat_v1.txt"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def load_general_prompt() -> str:
    return GENERAL_PROMPT_PATH.read_text(encoding="utf-8")


def load_general_chat_prompt() -> str:
    return GENERAL_CHAT_PROMPT_PATH.read_text(encoding="utf-8")


def build_source_xml(chunks: list[dict]) -> str:
    parts: list[str] = []
    for c in chunks:
        parts.append(
            (
                f'<SOURCE id="{c["chunk_id"]}" '
                f'document_id="{c["document_id"]}" '
                f'document_title="{_xml_escape(c.get("document_title") or "")}" '
                f'page="{c["page"]}">\n'
                f'{c.get("canonical_text") or ""}\n'
                f"</SOURCE>"
            )
        )
    return "\n\n".join(parts)


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class RagService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        embedder: OpenRouterEmbeddingProvider | None = None,
        reranker: OpenRouterRerankProvider | None = None,
        chat: OpenRouterChatProvider | None = None,
        vectors: QdrantVectorStore | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.embedder = embedder or OpenRouterEmbeddingProvider(settings=self.settings)
        self.reranker = reranker or OpenRouterRerankProvider(settings=self.settings)
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self.chunker = PageChunker(self.settings)
        prompt = compose_expert_system_prompt(load_system_prompt(), "")
        self.chat = chat or OpenRouterChatProvider(settings=self.settings, system_prompt=prompt)
        self.general_chat = OpenRouterChatProvider(
            settings=self.settings,
            system_prompt=compose_expert_system_prompt(load_general_prompt(), ""),
            client=self.chat.client,
        )

    def query(
        self,
        question: str,
        scope: RagScope,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int | None = None,
    ) -> dict:
        prepared = self._prepare_context(
            question, scope=scope, document_ids=document_ids, top_k=top_k
        )
        result = self.chat.answer(prepared["question"], prepared["context"])
        validated = self._validate_citations(
            result, prepared["allowed_ids"], prepared["context_chunks"]
        )

        if self._needs_citation_retry(validated):
            stricter = (
                compose_expert_system_prompt(load_system_prompt(), "")
                + "\n\nSTRICT: You must cite at least one valid SOURCE id, or set insufficient_context=true."
            )
            retry_chat = OpenRouterChatProvider(settings=self.settings, system_prompt=stricter)
            result = retry_chat.answer(prepared["question"], prepared["context"])
            validated = self._validate_citations(
                result, prepared["allowed_ids"], prepared["context_chunks"]
            )
            if not validated["citations"]:
                validated["insufficient_context"] = True

        self._record_generation_usage(validated, result, scope=scope)
        self._maybe_attach_general_answer(prepared["question"], validated, scope=scope)
        return validated

    def query_stream(
        self,
        question: str,
        scope: RagScope,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield SSE-oriented events: status, token, replace, general_token, final."""
        yield {"event": "status", "data": {"stage": "retrieving"}}
        prepared = self._prepare_context(
            question, scope=scope, document_ids=document_ids, top_k=top_k
        )
        yield {"event": "status", "data": {"stage": "generating"}}

        result: dict | None = None
        for event in self.chat.answer_stream(prepared["question"], prepared["context"]):
            etype = event.get("type")
            if etype == "delta":
                yield {"event": "token", "data": {"text": event.get("text") or ""}}
            elif etype == "replace":
                yield {"event": "replace", "data": {"text": event.get("text") or ""}}
            elif etype == "done":
                result = event.get("result")

        if not result:
            raise AppError(ErrorCategory.GENERATION_FAILED, "Stream ended without a result")

        validated = self._validate_citations(
            result, prepared["allowed_ids"], prepared["context_chunks"]
        )
        if self._needs_citation_retry(validated):
            yield {"event": "status", "data": {"stage": "retrying"}}
            yield {"event": "replace", "data": {"text": ""}}
            stricter = (
                compose_expert_system_prompt(load_system_prompt(), "")
                + "\n\nSTRICT: You must cite at least one valid SOURCE id, or set insufficient_context=true."
            )
            retry_chat = OpenRouterChatProvider(settings=self.settings, system_prompt=stricter)
            result = None
            for event in retry_chat.answer_stream(prepared["question"], prepared["context"]):
                etype = event.get("type")
                if etype == "delta":
                    yield {"event": "token", "data": {"text": event.get("text") or ""}}
                elif etype == "replace":
                    yield {"event": "replace", "data": {"text": event.get("text") or ""}}
                elif etype == "done":
                    result = event.get("result")
            if not result:
                raise AppError(ErrorCategory.GENERATION_FAILED, "Retry stream ended without a result")
            validated = self._validate_citations(
                result, prepared["allowed_ids"], prepared["context_chunks"]
            )
            if not validated["citations"]:
                validated["insufficient_context"] = True

        self._record_generation_usage(validated, result, scope=scope)
        yield from self._stream_general_fallback(prepared["question"], validated, scope=scope)
        yield {
            "event": "final",
            "data": {
                "answer": validated["answer"],
                "insufficient_context": validated["insufficient_context"],
                "citations": validated["citations"],
                "model": validated["model"],
                "general_answer": validated.get("general_answer"),
                "used_general_knowledge": bool(validated.get("used_general_knowledge")),
                "general_model": validated.get("general_model"),
            },
        }

    # ------------------------------------------------------------------
    # Expert-scoped RAG (Phase 3B)
    # ------------------------------------------------------------------

    def query_expert(
        self,
        question: str,
        knowledge: ResolvedExpertKnowledge,
        top_k: int | None = None,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict:
        prepared = self._prepare_expert_context(question, knowledge, top_k)
        scope = prepared["scope"]
        expert_chat = self._build_expert_chat(knowledge)
        result = expert_chat.answer(
            prepared["question"], prepared["context"], history=history
        )
        validated = self._validate_citations(
            result, prepared["allowed_ids"], prepared["context_chunks"]
        )
        if self._needs_citation_retry(validated):
            stricter_prompt = (
                self._compose_expert_prompt(knowledge)
                + "\n\nSTRICT: You must cite at least one valid SOURCE id, or set insufficient_context=true."
            )
            retry_chat = OpenRouterChatProvider(
                settings=self.settings, system_prompt=stricter_prompt, client=self.chat.client
            )
            result = retry_chat.answer(
                prepared["question"], prepared["context"], history=history
            )
            validated = self._validate_citations(
                result, prepared["allowed_ids"], prepared["context_chunks"]
            )
            if not validated["citations"]:
                validated["insufficient_context"] = True

        usage_id = self._record_generation_usage(validated, result, scope=scope)
        if usage_id is not None:
            validated["usage_event_id"] = str(usage_id)
        self._maybe_attach_general_answer(prepared["question"], validated, scope=scope)
        return validated

    def query_expert_stream(
        self,
        question: str,
        knowledge: ResolvedExpertKnowledge,
        top_k: int | None = None,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield {"event": "status", "data": {"stage": "retrieving"}}
        prepared = self._prepare_expert_context(question, knowledge, top_k)
        scope = prepared["scope"]
        yield {"event": "status", "data": {"stage": "generating"}}

        expert_chat = self._build_expert_chat(knowledge)
        result: dict | None = None
        for event in expert_chat.answer_stream(
            prepared["question"], prepared["context"], history=history
        ):
            etype = event.get("type")
            if etype == "delta":
                yield {"event": "token", "data": {"text": event.get("text") or ""}}
            elif etype == "replace":
                yield {"event": "replace", "data": {"text": event.get("text") or ""}}
            elif etype == "done":
                result = event.get("result")

        if not result:
            raise AppError(ErrorCategory.GENERATION_FAILED, "Stream ended without a result")

        validated = self._validate_citations(
            result, prepared["allowed_ids"], prepared["context_chunks"]
        )
        if self._needs_citation_retry(validated):
            yield {"event": "status", "data": {"stage": "retrying"}}
            yield {"event": "replace", "data": {"text": ""}}
            stricter_prompt = (
                self._compose_expert_prompt(knowledge)
                + "\n\nSTRICT: You must cite at least one valid SOURCE id, or set insufficient_context=true."
            )
            retry_chat = OpenRouterChatProvider(
                settings=self.settings, system_prompt=stricter_prompt, client=self.chat.client
            )
            result = None
            for event in retry_chat.answer_stream(
                prepared["question"], prepared["context"], history=history
            ):
                etype = event.get("type")
                if etype == "delta":
                    yield {"event": "token", "data": {"text": event.get("text") or ""}}
                elif etype == "replace":
                    yield {"event": "replace", "data": {"text": event.get("text") or ""}}
                elif etype == "done":
                    result = event.get("result")
            if not result:
                raise AppError(ErrorCategory.GENERATION_FAILED, "Retry stream ended without a result")
            validated = self._validate_citations(
                result, prepared["allowed_ids"], prepared["context_chunks"]
            )
            if not validated["citations"]:
                validated["insufficient_context"] = True

        usage_id = self._record_generation_usage(validated, result, scope=scope)
        yield from self._stream_general_fallback(prepared["question"], validated, scope=scope)
        final_data = {
            "answer": validated["answer"],
            "insufficient_context": validated["insufficient_context"],
            "citations": validated["citations"],
            "model": validated["model"],
            "general_answer": validated.get("general_answer"),
            "used_general_knowledge": bool(validated.get("used_general_knowledge")),
            "general_model": validated.get("general_model"),
        }
        if usage_id is not None:
            final_data["usage_event_id"] = str(usage_id)
        yield {"event": "final", "data": final_data}

    def query_general_expert(
        self,
        question: str,
        knowledge: ResolvedExpertKnowledge,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict:
        """LLM-only Expert answer (Geem General) — no retrieve/rerank/citations."""
        question = (question or "").strip()
        if not question:
            raise AppError(ErrorCategory.VALIDATION, "question is required")
        chat = self._build_general_expert_chat(knowledge)
        result = chat.answer_general(question, history=history)
        answer = (result.get("answer_markdown") or "").strip()
        validated = {
            "answer": answer,
            "insufficient_context": False,
            "citations": [],
            "model": result.get("model"),
            "general_answer": None,
            "used_general_knowledge": True,
            "general_model": result.get("model"),
        }
        usage_id = self._record_generation_usage(
            validated,
            result,
            operation_type="general_expert",
            scope=knowledge.scope,
        )
        if usage_id is not None:
            validated["usage_event_id"] = str(usage_id)
        return validated

    def query_general_expert_stream(
        self,
        question: str,
        knowledge: ResolvedExpertKnowledge,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream LLM-only Expert answer — SSE-compatible with ChatOrchestrator."""
        question = (question or "").strip()
        if not question:
            raise AppError(ErrorCategory.VALIDATION, "question is required")

        yield {"event": "status", "data": {"stage": "generating"}}
        chat = self._build_general_expert_chat(knowledge)
        result: dict | None = None
        for event in chat.answer_general_stream(question, history=history):
            etype = event.get("type")
            if etype == "delta":
                yield {"event": "token", "data": {"text": event.get("text") or ""}}
            elif etype == "replace":
                yield {"event": "replace", "data": {"text": event.get("text") or ""}}
            elif etype == "done":
                result = event.get("result")

        if not result:
            raise AppError(ErrorCategory.GENERATION_FAILED, "Stream ended without a result")

        answer = (result.get("answer_markdown") or "").strip()
        validated = {
            "answer": answer,
            "insufficient_context": False,
            "citations": [],
            "model": result.get("model"),
            "general_answer": None,
            "used_general_knowledge": True,
            "general_model": result.get("model"),
        }
        usage_id = self._record_generation_usage(
            validated,
            result,
            operation_type="general_expert",
            scope=knowledge.scope,
        )
        final_data = {
            "answer": validated["answer"],
            "insufficient_context": False,
            "citations": [],
            "model": validated["model"],
            "general_answer": None,
            "used_general_knowledge": True,
            "general_model": validated.get("general_model"),
        }
        if usage_id is not None:
            final_data["usage_event_id"] = str(usage_id)
        yield {"event": "final", "data": final_data}

    def _build_general_expert_chat(
        self, knowledge: ResolvedExpertKnowledge
    ) -> OpenRouterChatProvider:
        prompt = compose_expert_system_prompt(
            load_general_chat_prompt(), knowledge.system_instructions
        )
        return OpenRouterChatProvider(
            settings=self.settings,
            system_prompt=prompt,
            client=self.chat.client,
        )

    def _compose_expert_prompt(self, knowledge: ResolvedExpertKnowledge) -> str:
        return compose_expert_system_prompt(
            load_system_prompt(), knowledge.system_instructions
        )

    def _build_expert_chat(self, knowledge: ResolvedExpertKnowledge) -> OpenRouterChatProvider:
        """Build a per-request chat provider composed with the Expert prompt.

        We never mutate ``self.chat.system_prompt`` — a shared RagService would
        otherwise leak one Expert's instructions into the next request. The
        underlying HTTP client is reused to preserve connection pooling.
        """
        return OpenRouterChatProvider(
            settings=self.settings,
            system_prompt=self._compose_expert_prompt(knowledge),
            client=self.chat.client,
        )

    def _prepare_expert_context(
        self,
        question: str,
        knowledge: ResolvedExpertKnowledge,
        top_k: int | None,
    ) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise AppError(ErrorCategory.VALIDATION, "question is required")
        if not knowledge.has_ready_knowledge:
            # Belt & braces — ExpertQueryService already checks this, but
            # defense-in-depth guards direct callers.
            raise AppError(
                ErrorCategory.EXPERT_HAS_NO_KNOWLEDGE,
                "Expert has no ready knowledge to answer with yet.",
            )

        scope = knowledge.scope
        ready_ids = list(knowledge.ready_document_ids)
        ready_id_strs = [str(d) for d in ready_ids]
        allowed_doc_ids = set(ready_ids)
        rag_cfg = knowledge.rag_config
        effective_top_k = top_k or rag_cfg.top_k
        similarity_threshold = rag_cfg.similarity_threshold

        retrieval_question = expand_article_query(question)
        normalized_q = normalize_search(retrieval_question)
        query_vec = self.embedder.embed_query(normalized_q)

        hits = self.vectors.search_expert(
            knowledge_workspace_id=scope.knowledge_workspace_id,
            expert_id=scope.expert_id,
            vector=query_vec,
            top_k=effective_top_k,
            document_ids=ready_id_strs,
        )

        resolver = ExpertKnowledgeResolver(self.db, self.settings)
        enriched: list[dict] = []
        seen_ids: set[str] = set()
        for hit in hits:
            chunk_id = hit.get("chunk_id")
            if not chunk_id:
                continue
            try:
                chunk_uuid = uuid.UUID(str(chunk_id))
            except (ValueError, TypeError):
                continue
            chunk = self.db.get(Chunk, chunk_uuid)
            if chunk is None:
                continue
            if chunk.document_id not in allowed_doc_ids:
                security_log(
                    "expert.stale_payload_rejected",
                    expert_id=str(scope.expert_id),
                    knowledge_workspace_id=str(scope.knowledge_workspace_id),
                    chunk_id=str(chunk_id),
                    document_id=str(chunk.document_id),
                    reason="document_not_in_ready_set",
                )
                continue
            doc = self.db.get(Document, chunk.document_id)
            if (
                doc is None
                or doc.deleted_at is not None
                or doc.status != "ready"
                or doc.workspace_id != scope.knowledge_workspace_id
            ):
                security_log(
                    "expert.stale_payload_rejected",
                    expert_id=str(scope.expert_id),
                    knowledge_workspace_id=str(scope.knowledge_workspace_id),
                    chunk_id=str(chunk_id),
                    document_id=str(chunk.document_id),
                    reason="document_out_of_scope",
                )
                continue
            if not resolver.assert_candidate_membership(
                expert_id=scope.expert_id,
                document_id=chunk.document_id,
                knowledge_workspace_id=scope.knowledge_workspace_id,
            ):
                security_log(
                    "expert.stale_payload_rejected",
                    expert_id=str(scope.expert_id),
                    knowledge_workspace_id=str(scope.knowledge_workspace_id),
                    chunk_id=str(chunk_id),
                    document_id=str(chunk.document_id),
                    reason="expert_document_link_missing",
                )
                continue
            vector_score = hit.get("vector_score")
            if (
                similarity_threshold is not None
                and vector_score is not None
                and float(vector_score) < float(similarity_threshold)
            ):
                continue

            seen_ids.add(str(chunk.id))
            enriched.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "document_title": doc.title,
                    "page": chunk.page_number,
                    "ordinal": chunk.ordinal,
                    "heading_path": chunk.heading_path or [],
                    "canonical_text": chunk.canonical_text,
                    "search_text": chunk.search_text,
                    "token_count": chunk.token_count,
                    "vector_score": vector_score,
                }
            )

        for lexical in self._lexical_article_chunks(question, ready_ids):
            if lexical["chunk_id"] in seen_ids:
                continue
            try:
                doc_uuid = uuid.UUID(str(lexical["document_id"]))
            except (ValueError, TypeError):
                continue
            if doc_uuid not in allowed_doc_ids:
                continue
            if not resolver.assert_candidate_membership(
                expert_id=scope.expert_id,
                document_id=doc_uuid,
                knowledge_workspace_id=scope.knowledge_workspace_id,
            ):
                continue
            seen_ids.add(lexical["chunk_id"])
            enriched.insert(0, lexical)

        rerank_top_n = rag_cfg.rerank_top_n
        ranked = self.reranker.rerank(normalized_q, enriched, top_n=rerank_top_n)
        expanded = self._expand_neighbors(ranked)
        # Neighbor expansion must not introduce chunks that fail Expert scope.
        filtered_expanded: list[dict] = []
        for c in expanded:
            try:
                doc_uuid = uuid.UUID(str(c["document_id"]))
            except (ValueError, TypeError):
                continue
            if doc_uuid not in allowed_doc_ids:
                continue
            if not resolver.assert_candidate_membership(
                expert_id=scope.expert_id,
                document_id=doc_uuid,
                knowledge_workspace_id=scope.knowledge_workspace_id,
            ):
                continue
            filtered_expanded.append(c)

        context_chunks = self._apply_token_budget(filtered_expanded)
        context = build_source_xml(context_chunks)
        allowed_ids = {c["chunk_id"] for c in context_chunks}
        return {
            "question": question,
            "context": context,
            "allowed_ids": allowed_ids,
            "context_chunks": context_chunks,
            "scope": scope,
        }

    def _maybe_attach_general_answer(
        self, question: str, validated: dict, *, scope: RagScope | None = None
    ) -> None:
        validated.setdefault("general_answer", None)
        validated.setdefault("used_general_knowledge", False)
        validated.setdefault("general_model", None)
        if not self.settings.general_fallback_enabled:
            return
        if not validated.get("insufficient_context"):
            return
        try:
            general = self.general_chat.answer_general(question)
        except AppError:
            logger.exception("general_fallback_failed", extra={"stage": "general"})
            return
        validated["general_answer"] = general.get("answer_markdown") or ""
        validated["used_general_knowledge"] = bool(validated["general_answer"])
        validated["general_model"] = general.get("model")
        self._record_generation_usage(
            {"model": general.get("model")},
            general,
            operation_type="general_fallback",
            scope=scope,
        )

    def _stream_general_fallback(
        self,
        question: str,
        validated: dict,
        *,
        scope: RagScope | None = None,
    ) -> Iterator[dict[str, Any]]:
        validated.setdefault("general_answer", None)
        validated.setdefault("used_general_knowledge", False)
        validated.setdefault("general_model", None)
        if not self.settings.general_fallback_enabled:
            return
        if not validated.get("insufficient_context"):
            return

        yield {"event": "status", "data": {"stage": "general"}}
        general_result: dict | None = None
        try:
            for event in self.general_chat.answer_general_stream(question):
                etype = event.get("type")
                if etype == "delta":
                    yield {"event": "general_token", "data": {"text": event.get("text") or ""}}
                elif etype == "replace":
                    yield {"event": "general_replace", "data": {"text": event.get("text") or ""}}
                elif etype == "done":
                    general_result = event.get("result")
        except AppError:
            logger.exception("general_fallback_stream_failed", extra={"stage": "general"})
            return

        if not general_result:
            return
        validated["general_answer"] = general_result.get("answer_markdown") or ""
        validated["used_general_knowledge"] = bool(validated["general_answer"])
        validated["general_model"] = general_result.get("model")
        self._record_generation_usage(
            {"model": general_result.get("model")},
            general_result,
            operation_type="general_fallback",
            scope=scope,
        )

    def _prepare_context(
        self,
        question: str,
        *,
        scope: RagScope,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise AppError(ErrorCategory.VALIDATION, "question is required")

        ready_docs = self._ready_documents_for_scope(scope, document_ids)
        if document_ids and not ready_docs:
            # Indistinguishable not-found (may include cross-tenant IDs).
            raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "No ready documents match the filter")
        if not ready_docs:
            raise AppError(ErrorCategory.VALIDATION, "No ready documents available to query")

        # If caller supplied document_ids, every ID must resolve in-scope (no partial leak).
        if document_ids:
            found = {d.id for d in ready_docs}
            missing = [str(i) for i in document_ids if i not in found]
            if missing:
                raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "No ready documents match the filter")

        ready_ids = [str(d.id) for d in ready_docs]
        ready_uuids = [d.id for d in ready_docs]
        # "All" semantics = all ready docs in this population only.
        doc_filter = ready_ids

        retrieval_question = expand_article_query(question)
        normalized_q = normalize_search(retrieval_question)
        query_vec = self.embedder.embed_query(normalized_q)
        k = top_k or self.settings.retrieval_top_k

        if isinstance(scope, WorkspaceRagScope):
            hits = self.vectors.search_workspace(
                workspace_id=scope.workspace_id,
                vector=query_vec,
                top_k=k,
                document_ids=doc_filter,
            )
        elif isinstance(scope, LegacyRagScope):
            # Internal / historical only — production HTTP always uses WorkspaceRagScope.
            hits = self.vectors.search_legacy(
                vector=query_vec,
                top_k=k,
                document_ids=doc_filter,
            )
        else:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Unsupported RAG scope; WorkspaceRagScope is required for tenant retrieval.",
            )

        # Enrich from DB (source of truth). Tenant isolation before rerank/LLM.
        enriched = []
        seen_ids: set[str] = set()
        allowed_doc_ids = set(ready_uuids)
        for hit in hits:
            chunk_id = hit.get("chunk_id")
            if not chunk_id:
                continue
            chunk = self.db.get(Chunk, uuid.UUID(str(chunk_id)))
            if not chunk or chunk.document_id not in allowed_doc_ids:
                continue
            doc = self.db.get(Document, chunk.document_id)
            if not self._document_in_scope(doc, scope):
                continue
            seen_ids.add(str(chunk.id))
            enriched.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "document_title": doc.title,
                    "page": chunk.page_number,
                    "ordinal": chunk.ordinal,
                    "heading_path": chunk.heading_path or [],
                    "canonical_text": chunk.canonical_text,
                    "search_text": chunk.search_text,
                    "token_count": chunk.token_count,
                    "vector_score": hit.get("vector_score"),
                }
            )

        for lexical in self._lexical_article_chunks(question, ready_uuids):
            if lexical["chunk_id"] in seen_ids:
                continue
            seen_ids.add(lexical["chunk_id"])
            enriched.insert(0, lexical)

        ranked = self.reranker.rerank(normalized_q, enriched, top_n=self.settings.rerank_top_n)
        expanded = self._expand_neighbors(ranked)
        # Neighbor expansion must not introduce out-of-scope chunks.
        expanded = [
            c
            for c in expanded
            if uuid.UUID(str(c["document_id"])) in allowed_doc_ids
        ]
        context_chunks = self._apply_token_budget(expanded)
        context = build_source_xml(context_chunks)
        allowed_ids = {c["chunk_id"] for c in context_chunks}
        return {
            "question": question,
            "context": context,
            "allowed_ids": allowed_ids,
            "context_chunks": context_chunks,
            "scope": scope,
        }

    def _ready_documents_for_scope(
        self,
        scope: RagScope,
        document_ids: list[uuid.UUID] | None,
    ) -> list[Document]:
        ready_filter = [
            Document.status == "ready",
            Document.deleted_at.is_(None),
        ]
        if isinstance(scope, WorkspaceRagScope):
            ready_filter.append(Document.workspace_id == scope.workspace_id)
        else:
            ready_filter.append(Document.workspace_id.is_(None))
        if document_ids:
            ready_filter.append(Document.id.in_(document_ids))
        return list(self.db.scalars(select(Document).where(*ready_filter)))

    def _document_in_scope(self, doc: Document | None, scope: RagScope) -> bool:
        if doc is None or doc.deleted_at is not None or doc.status != "ready":
            return False
        if isinstance(scope, WorkspaceRagScope):
            return doc.workspace_id == scope.workspace_id
        return doc.workspace_id is None


    def _needs_citation_retry(self, validated: dict) -> bool:
        return bool(
            not validated["insufficient_context"]
            and not validated["citations"]
            and (validated.get("answer") or "").strip()
        )

    def _record_generation_usage(
        self,
        validated: dict,
        result: dict,
        *,
        operation_type: str = "generation",
        scope: RagScope | None = None,
    ) -> uuid.UUID | None:
        cost_metadata: dict[str, Any] = {
            "prompt_version": (
                self.settings.general_prompt_version
                if operation_type == "general_fallback"
                else self.settings.prompt_version
            )
        }
        if isinstance(scope, ExpertRagScope):
            # Attribute cost to the consumer Workspace (the tenant footing the
            # bill), NOT the knowledge Workspace (which for Platform Experts is
            # a system Workspace that must never appear in tenant billing).
            cost_metadata["workspace_id"] = str(scope.consumer_workspace_id)
            cost_metadata["expert_id"] = str(scope.expert_id)
            cost_metadata["knowledge_workspace_id"] = str(scope.knowledge_workspace_id)
            cost_metadata["expert_type"] = scope.expert_type
            cost_metadata["population"] = "expert"
        elif isinstance(scope, WorkspaceRagScope):
            cost_metadata["workspace_id"] = str(scope.workspace_id)
            cost_metadata["population"] = "workspace"
        elif isinstance(scope, LegacyRagScope):
            cost_metadata["population"] = "legacy"

        event_id = uuid.uuid4()
        self.db.add(
            UsageEvent(
                id=event_id,
                operation_type=operation_type,
                model=validated.get("model"),
                cost_metadata=cost_metadata,
                request_id=(result.get("_meta") or {}).get("request_id"),
            )
        )
        self.db.commit()
        return event_id

    def _lexical_article_chunks(
        self,
        question: str,
        document_ids: list[uuid.UUID],
    ) -> list[dict]:
        nums = extract_article_numbers(question)
        if not nums or not document_ids:
            return []
        out: list[dict] = []
        for n in nums:
            for pattern in article_lexical_patterns(n):
                rows = list(
                    self.db.scalars(
                        select(Chunk)
                        .where(
                            Chunk.document_id.in_(document_ids),
                            Chunk.canonical_text.ilike(f"%{pattern}%"),
                        )
                        .limit(5)
                    )
                )
                for chunk in rows:
                    doc = self.db.get(Document, chunk.document_id)
                    if not doc or doc.status != "ready" or doc.deleted_at is not None:
                        continue
                    out.append(
                        {
                            "chunk_id": str(chunk.id),
                            "document_id": str(chunk.document_id),
                            "document_title": doc.title,
                            "page": chunk.page_number,
                            "ordinal": chunk.ordinal,
                            "heading_path": chunk.heading_path or [],
                            "canonical_text": chunk.canonical_text,
                            "search_text": chunk.search_text,
                            "token_count": chunk.token_count,
                            "vector_score": 1.0,
                        }
                    )
        return out

    def _expand_neighbors(self, ranked: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []

        def add_chunk_row(chunk: Chunk, doc_title: str, supporting: bool = False) -> None:
            cid = str(chunk.id)
            if cid in seen:
                return
            seen.add(cid)
            out.append(
                {
                    "chunk_id": cid,
                    "document_id": str(chunk.document_id),
                    "document_title": doc_title,
                    "page": chunk.page_number,
                    "ordinal": chunk.ordinal,
                    "heading_path": chunk.heading_path or [],
                    "canonical_text": chunk.canonical_text,
                    "search_text": chunk.search_text,
                    "token_count": chunk.token_count,
                    "supporting": supporting,
                }
            )

        for item in ranked:
            chunk = self.db.get(Chunk, uuid.UUID(item["chunk_id"]))
            if not chunk:
                continue
            doc = self.db.get(Document, chunk.document_id)
            title = doc.title if doc else item.get("document_title") or ""
            add_chunk_row(chunk, title, supporting=False)

            # same-page neighbors
            neighbors = list(
                self.db.scalars(
                    select(Chunk).where(
                        Chunk.document_id == chunk.document_id,
                        Chunk.page_number == chunk.page_number,
                    )
                )
            )
            by_ord = {c.ordinal: c for c in neighbors}
            for ord_n in (chunk.ordinal - 1, chunk.ordinal + 1):
                if ord_n in by_ord:
                    add_chunk_row(by_ord[ord_n], title, supporting=True)

            # cross-page edge neighbors
            if chunk.ordinal == 0:
                prev_page_chunks = list(
                    self.db.scalars(
                        select(Chunk)
                        .where(
                            Chunk.document_id == chunk.document_id,
                            Chunk.page_number == chunk.page_number - 1,
                        )
                        .order_by(Chunk.ordinal.desc())
                    )
                )
                if prev_page_chunks:
                    add_chunk_row(prev_page_chunks[0], title, supporting=True)
            max_ord = max((c.ordinal for c in neighbors), default=chunk.ordinal)
            if chunk.ordinal == max_ord:
                next_page_chunks = list(
                    self.db.scalars(
                        select(Chunk)
                        .where(
                            Chunk.document_id == chunk.document_id,
                            Chunk.page_number == chunk.page_number + 1,
                        )
                        .order_by(Chunk.ordinal.asc())
                    )
                )
                if next_page_chunks:
                    add_chunk_row(next_page_chunks[0], title, supporting=True)

        return out

    def _apply_token_budget(self, chunks: list[dict]) -> list[dict]:
        budget = self.settings.max_context_tokens
        selected: list[dict] = []
        used = 0
        for c in chunks:
            tokens = c.get("token_count") or self.chunker.count_tokens(c.get("canonical_text") or "")
            if selected and used + tokens > budget:
                continue
            selected.append(c)
            used += tokens
        return selected

    def _validate_citations(
        self,
        result: dict,
        allowed_ids: set[str],
        context_chunks: list[dict],
    ) -> dict:
        by_id = {c["chunk_id"]: c for c in context_chunks}
        citations = []
        invalid = []
        for cid in result.get("citation_chunk_ids") or []:
            cid = str(cid)
            if cid not in allowed_ids or cid not in by_id:
                invalid.append(cid)
                logger.warning(
                    "citation_validation_failed",
                    extra={"status": "invalid_chunk_id", "stage": "citation"},
                )
                continue
            c = by_id[cid]
            snippet = (c.get("canonical_text") or "")[:400]
            citations.append(
                {
                    "chunk_id": cid,
                    "document_id": c["document_id"],
                    "document_title": c["document_title"],
                    "page": c["page"],
                    "snippet": snippet,
                }
            )

        insufficient = bool(result.get("insufficient_context"))
        if not citations and not insufficient:
            # If model answered factually without valid citations, mark insufficient
            if invalid or not result.get("citation_chunk_ids"):
                pass  # caller may retry

        return {
            "answer": result.get("answer_markdown") or "",
            "insufficient_context": insufficient,
            "citations": citations,
            "model": result.get("model") or self.settings.openrouter_chat_model,
            "prompt_version": result.get("prompt_version") or self.settings.prompt_version,
            "_invalid_citation_ids": invalid,
            "general_answer": None,
            "used_general_knowledge": False,
            "general_model": None,
        }
