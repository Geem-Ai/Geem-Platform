from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document, DocumentPage, IngestionJob, UsageEvent
from app.ingestion.arabic_normalize import normalize_canonical, normalize_search, page_quality_diagnostics
from app.ingestion.chunker import PageChunker, detect_repeated_headers_footers
from app.ingestion.pdf_utils import split_page
from app.openrouter.embeddings import OpenRouterEmbeddingProvider
from app.openrouter.parser import OpenRouterDocumentParser
from app.storage.minio_storage import MinioObjectStorage
from app.storage.qdrant_store import QdrantVectorStore, deterministic_point_id

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def pipeline_versions(settings: Settings) -> dict:
    return {
        "pipeline": settings.rag_pipeline_version,
        "parser": settings.parser_version,
        "normalizer": settings.normalizer_version,
        "chunker": settings.chunker_version,
        "embedding": settings.openrouter_embedding_model,
        "prompt": settings.prompt_version,
    }


class IngestionPipeline:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        storage: MinioObjectStorage | None = None,
        parser: OpenRouterDocumentParser | None = None,
        embedder: OpenRouterEmbeddingProvider | None = None,
        vectors: QdrantVectorStore | None = None,
        chunker: PageChunker | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage or MinioObjectStorage(self.settings)
        self.parser = parser or OpenRouterDocumentParser(settings=self.settings)
        self.embedder = embedder or OpenRouterEmbeddingProvider(settings=self.settings)
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self.chunker = chunker or PageChunker(self.settings)

    def run(self, document_id: uuid.UUID, mode: str = "full") -> None:
        document = self.db.get(Document, document_id)
        if not document:
            raise AppError(ErrorCategory.NOT_FOUND, f"Document {document_id} not found")

        job = self._latest_job(document_id)
        if not job:
            job = IngestionJob(
                id=uuid.uuid4(),
                document_id=document_id,
                status="queued",
                total_pages=document.page_count,
            )
            self.db.add(job)
            self.db.commit()

        document.status = "processing"
        job.status = "processing"
        job.started_at = job.started_at or _utcnow()
        job.attempt_count += 1
        job.current_stage = "ocr"
        self.db.commit()

        try:
            if mode == "full":
                self._reset_derived(document)
            self._ensure_page_rows(document)
            self._ocr_pages(document, job, failed_only=(mode == "failed_pages"))
            self.db.refresh(document)
            failed = (
                self.db.scalar(
                    select(DocumentPage).where(
                        DocumentPage.document_id == document.id,
                        DocumentPage.status == "failed",
                    ).limit(1)
                )
                is not None
            )
            if failed:
                raise AppError(ErrorCategory.PARSER_FAILED, "One or more pages failed OCR")

            job.current_stage = "chunking"
            self.db.commit()
            self._chunk_and_embed(document, job)

            document.status = "ready"
            document.completed_at = _utcnow()
            document.failure_reason = None
            document.processing_version = pipeline_versions(self.settings)
            job.status = "completed"
            job.current_stage = "ready"
            job.completed_at = _utcnow()
            job.last_error = None
            self.db.commit()
        except Exception as exc:
            logger.exception("ingestion_failed", extra={"document_id": str(document_id)})
            document.status = "failed"
            document.failure_reason = str(exc)[:2000]
            job.status = "failed"
            job.last_error = str(exc)[:2000]
            job.completed_at = _utcnow()
            self.db.commit()
            raise

    def _latest_job(self, document_id: uuid.UUID) -> IngestionJob | None:
        return self.db.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )

    def _reset_derived(self, document: Document) -> None:
        # Delete vectors first
        self.vectors.delete_by_document(str(document.id))
        for chunk in list(document.chunks):
            self.db.delete(chunk)
        for page in list(document.pages):
            self.db.delete(page)
        self.db.commit()

    def _ensure_page_rows(self, document: Document) -> None:
        existing = {
            p.page_number: p
            for p in self.db.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document.id)
            )
        }
        for n in range(1, document.page_count + 1):
            if n not in existing:
                self.db.add(
                    DocumentPage(
                        id=uuid.uuid4(),
                        document_id=document.id,
                        page_number=n,
                        status="pending",
                    )
                )
        self.db.commit()

    def _ocr_pages(self, document: Document, job: IngestionJob, failed_only: bool) -> None:
        pdf_bytes = self.storage.get_bytes(document.storage_key)
        pages = list(
            self.db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document.id)
                .order_by(DocumentPage.page_number)
            )
        )
        targets = []
        for page in pages:
            if page.status == "parsed" and page.parser_hash:
                continue
            if failed_only and page.status not in {"failed", "pending"}:
                continue
            targets.append(page)

        concurrency = max(1, self.settings.ocr_page_concurrency)

        def process_one(page_id: uuid.UUID, page_number: int) -> tuple[uuid.UUID, dict | Exception]:
            try:
                page_pdf = split_page(pdf_bytes, page_number)
                parsed = self.parser.parse_page(
                    page_pdf,
                    filename=f"{document.id}-p{page_number}.pdf",
                    page_number=page_number,
                )
                diagnostics = page_quality_diagnostics(parsed.plain_text or parsed.raw_markdown)
                # Strip file-wrapper noise when judging emptiness
                meaningful = (parsed.plain_text or "").strip(" .\t\n")
                if (
                    diagnostics["empty_output"]
                    or diagnostics["replacement_char_count"] > 20
                    or len(meaningful) < 8
                ):
                    raise AppError(
                        ErrorCategory.EMPTY_PAGE,
                        f"Empty/corrupt OCR for page {page_number}",
                    )
                canonical = normalize_canonical(parsed.raw_markdown)
                search = normalize_search(canonical)
                return page_id, {
                    "raw_markdown": parsed.raw_markdown,
                    "canonical_text": canonical,
                    "search_text": search,
                    "parser": parsed.parser,
                    "parser_hash": parsed.parser_hash,
                    "text_length": diagnostics["text_length"],
                    "arabic_ratio": diagnostics["arabic_ratio"],
                    "metadata": parsed.metadata,
                }
            except Exception as exc:
                return page_id, exc

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(process_one, page.id, page.page_number): page for page in targets
            }
            for fut in as_completed(futures):
                page = futures[fut]
                page_id, result = fut.result()
                db_page = self.db.get(DocumentPage, page_id)
                if not db_page:
                    continue
                db_page.attempt_count += 1
                db_page.started_at = db_page.started_at or _utcnow()
                if isinstance(result, Exception):
                    db_page.status = "failed"
                    db_page.last_error = str(result)[:2000]
                else:
                    db_page.status = "parsed"
                    db_page.raw_markdown = result["raw_markdown"]
                    db_page.canonical_text = result["canonical_text"]
                    db_page.search_text = result["search_text"]
                    db_page.parser = result["parser"]
                    db_page.parser_hash = result["parser_hash"]
                    db_page.text_length = result["text_length"]
                    db_page.arabic_ratio = result["arabic_ratio"]
                    db_page.last_error = None
                    db_page.completed_at = _utcnow()
                    usage = result["metadata"].get("usage") or {}
                    self.db.add(
                        UsageEvent(
                            id=uuid.uuid4(),
                            operation_type="pdf_parse",
                            model=result["metadata"].get("model"),
                            input_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                            cost_metadata=usage if usage else None,
                            document_id=document.id,
                            page_number=db_page.page_number,
                            request_id=result["metadata"].get("request_id"),
                        )
                    )
# Refresh progress
                all_pages = list(
                    self.db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id))
                )
                job.processed_pages = sum(1 for p in all_pages if p.status == "parsed")
                job.failed_pages = sum(1 for p in all_pages if p.status == "failed")
                self.db.commit()

    def _chunk_and_embed(self, document: Document, job: IngestionJob) -> None:
        pages = list(
            self.db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document.id, DocumentPage.status == "parsed")
                .order_by(DocumentPage.page_number)
            )
        )
        page_texts = [p.canonical_text or "" for p in pages]
        skip = detect_repeated_headers_footers(page_texts)

        # Remove existing chunks for pages we're rebuilding
        existing_chunks = list(
            self.db.scalars(select(Chunk).where(Chunk.document_id == document.id))
        )
        existing_by_key = {
            (c.document_page_id, c.ordinal, c.embedding_version): c for c in existing_chunks
        }

        new_chunk_rows: list[Chunk] = []
        for page in pages:
            drafts = self.chunker.chunk_page(page.page_number, page.raw_markdown or "", skip_headers=skip)
            for draft in drafts:
                key = (page.id, draft.ordinal, self.settings.embedding_version)
                existing = existing_by_key.get(key)
                if existing and existing.content_hash == draft.content_hash:
                    continue
                if existing:
                    self.db.delete(existing)
                    self.db.flush()
                chunk_id = uuid.uuid4()
                point_id = deterministic_point_id(chunk_id)
                chunk = Chunk(
                    id=chunk_id,
                    document_id=document.id,
                    document_page_id=page.id,
                    page_number=draft.page_number,
                    ordinal=draft.ordinal,
                    heading_path=draft.heading_path or None,
                    canonical_text=draft.canonical_text,
                    search_text=draft.search_text,
                    token_count=draft.token_count,
                    content_hash=draft.content_hash,
                    qdrant_point_id=point_id,
                    embedding_model=self.embedder.model_id,
                    embedding_version=self.settings.embedding_version,
                )
                self.db.add(chunk)
                new_chunk_rows.append(chunk)
        self.db.commit()

        # Embed all chunks that need vectors: new ones + any without confirmation
        all_chunks = list(
            self.db.scalars(
                select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.page_number, Chunk.ordinal)
            )
        )
        if not all_chunks:
            raise AppError(ErrorCategory.EMPTY_PAGE, "No chunks produced from document")

        job.current_stage = "embedding"
        self.db.commit()

        texts = [c.search_text for c in all_chunks]
        vectors = self.embedder.embed_documents(texts)
        if not vectors:
            raise AppError(ErrorCategory.EMBEDDING_FAILED, "No embeddings returned")
        dim = len(vectors[0])
        self.vectors.ensure_collection(dim)
        for v in vectors:
            if len(v) != dim:
                raise AppError(ErrorCategory.EMBEDDING_FAILED, "Inconsistent embedding dimensions")

        points = []
        for chunk, vector in zip(all_chunks, vectors, strict=True):
            points.append(
                {
                    "id": str(chunk.qdrant_point_id),
                    "vector": vector,
                    "payload": {
                        "chunk_id": str(chunk.id),
                        "document_id": str(document.id),
                        "document_title": document.title,
                        "page": chunk.page_number,
                        "ordinal": chunk.ordinal,
                        "heading_path": chunk.heading_path or [],
                        "embedding_model": chunk.embedding_model,
                        "canonical_text": chunk.canonical_text,
                        "search_text": chunk.search_text,
                    },
                }
            )
        # Batch upsert
        batch = 64
        for i in range(0, len(points), batch):
            self.vectors.upsert(points[i : i + batch])

        self.db.add(
            UsageEvent(
                id=uuid.uuid4(),
                operation_type="embedding",
                model=self.embedder.model_id,
                input_tokens=None,
                output_tokens=None,
                cost_metadata={"chunk_count": len(all_chunks)},
                document_id=document.id,
            )
        )
        job.current_stage = "indexed"
        self.db.commit()
