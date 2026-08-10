from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document, UsageEvent
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

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "rag_answer_v1.txt"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


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
        prompt = load_system_prompt()
        self.chat = chat or OpenRouterChatProvider(settings=self.settings, system_prompt=prompt)

    def query(
        self,
        question: str,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int | None = None,
    ) -> dict:
        question = (question or "").strip()
        if not question:
            raise AppError(ErrorCategory.VALIDATION, "question is required")

        ready_filter = [Document.status == "ready"]
        if document_ids:
            ready_filter.append(Document.id.in_(document_ids))
        ready_docs = list(self.db.scalars(select(Document).where(*ready_filter)))
        if document_ids and not ready_docs:
            raise AppError(ErrorCategory.NOT_FOUND, "No ready documents match the filter")
        if not ready_docs:
            raise AppError(ErrorCategory.VALIDATION, "No ready documents available to query")

        ready_ids = [str(d.id) for d in ready_docs]
        doc_filter = document_ids and [str(d) for d in document_ids] or ready_ids
        ready_uuids = [d.id for d in ready_docs]

        # Expand المادة ١٤ → المادة الرابعة عشرة for dense retrieval
        retrieval_question = expand_article_query(question)
        normalized_q = normalize_search(retrieval_question)
        query_vec = self.embedder.embed_query(normalized_q)
        k = top_k or self.settings.retrieval_top_k
        hits = self.vectors.search(query_vec, top_k=k, document_ids=doc_filter)

        # Enrich from DB (source of truth for canonical text)
        enriched = []
        seen_ids: set[str] = set()
        for hit in hits:
            chunk_id = hit.get("chunk_id")
            if not chunk_id:
                continue
            chunk = self.db.get(Chunk, uuid.UUID(str(chunk_id)))
            if not chunk:
                continue
            doc = self.db.get(Document, chunk.document_id)
            if not doc or doc.status != "ready":
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

        # Lexical boost for exact article headings (digit vs ordinal mismatch)
        for lexical in self._lexical_article_chunks(question, ready_uuids):
            if lexical["chunk_id"] in seen_ids:
                continue
            seen_ids.add(lexical["chunk_id"])
            enriched.insert(0, lexical)

        ranked = self.reranker.rerank(normalized_q, enriched, top_n=self.settings.rerank_top_n)
        expanded = self._expand_neighbors(ranked)
        context_chunks = self._apply_token_budget(expanded)
        context = build_source_xml(context_chunks)
        allowed_ids = {c["chunk_id"] for c in context_chunks}

        result = self.chat.answer(question, context)
        validated = self._validate_citations(result, allowed_ids, context_chunks)

        # Retry once with stricter prompt if factual answer lacks citations
        if (
            not validated["insufficient_context"]
            and not validated["citations"]
            and (validated.get("answer") or "").strip()
        ):
            stricter = (
                load_system_prompt()
                + "\n\nSTRICT: You must cite at least one valid SOURCE id, or set insufficient_context=true."
            )
            retry_chat = OpenRouterChatProvider(settings=self.settings, system_prompt=stricter)
            result = retry_chat.answer(question, context)
            validated = self._validate_citations(result, allowed_ids, context_chunks)
            if not validated["citations"]:
                validated["insufficient_context"] = True

        self.db.add(
            UsageEvent(
                id=uuid.uuid4(),
                operation_type="generation",
                model=validated.get("model"),
                cost_metadata={"prompt_version": self.settings.prompt_version},
                request_id=(result.get("_meta") or {}).get("request_id"),
            )
        )
        self.db.commit()
        return validated

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
                    if not doc or doc.status != "ready":
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
        }
