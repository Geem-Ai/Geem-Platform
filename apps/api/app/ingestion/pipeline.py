from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document, DocumentPage, IngestionJob, UsageEvent
from app.experts.membership_sync import ExpertVectorMembershipSynchronizer
from app.experts.status import ExpertStatusReconciler
from app.ingestion.arabic_normalize import normalize_canonical, normalize_search, page_quality_diagnostics
from app.ingestion.chunker import PageChunker, detect_repeated_headers_footers
from app.ingestion.parsers import DocumentFormat, get_parser_for_format
from app.ingestion.pdf_utils import split_page
from app.openrouter.embeddings import OpenRouterEmbeddingProvider
from app.openrouter.parser import OpenRouterDocumentParser
from app.storage.minio_storage import MinioObjectStorage
from app.storage.qdrant_store import QdrantVectorStore, deterministic_point_id

logger = logging.getLogger(__name__)


def _strip_file_wrappers(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"</?file\b[^>]*>", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


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
        membership_sync: ExpertVectorMembershipSynchronizer | None = None,
        status_reconciler: ExpertStatusReconciler | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage or MinioObjectStorage(self.settings)
        self.parser = parser or OpenRouterDocumentParser(settings=self.settings)
        self.embedder = embedder or OpenRouterEmbeddingProvider(settings=self.settings)
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self.chunker = chunker or PageChunker(self.settings)
        self._membership_sync = membership_sync
        self._status_reconciler = status_reconciler or ExpertStatusReconciler(db)

    @property
    def membership_sync(self) -> ExpertVectorMembershipSynchronizer:
        if self._membership_sync is None:
            self._membership_sync = ExpertVectorMembershipSynchronizer(
                self.db, self.settings, vectors=self.vectors
            )
        return self._membership_sync

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
        # OCR only applies to PDFs; text/markdown skip straight to parsing.
        job.current_stage = "ocr" if self._needs_ocr(document) else "parsing"
        self.db.commit()

        try:
            if mode == "full":
                self._reset_derived(document)
            self._ensure_page_rows(document)
            if self._needs_ocr(document):
                self._ocr_pages(document, job, failed_only=(mode == "failed_pages"))
            else:
                self._parse_text_document(document, job)
            self.db.refresh(document)
            pages = list(
                self.db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id))
            )
            hard_failed = [p for p in pages if p.status == "failed"]
            usable = [p for p in pages if p.status == "parsed" and (p.text_length or 0) > 0]
            if hard_failed and not usable:
                raise AppError(ErrorCategory.PARSER_FAILED, "All pages failed OCR")
            if hard_failed and usable:
                # Soft-fail: continue indexing usable pages; surface count in job
                job.failed_pages = len(hard_failed)
                job.last_error = (
                    f"{len(hard_failed)} page(s) failed OCR; continuing with "
                    f"{len(usable)} usable page(s)"
                )
            if not usable:
                raise AppError(ErrorCategory.EMPTY_PAGE, "No usable text extracted from any page")

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

            # After commit, project PG expert_documents onto Qdrant payload and
            # recompute Expert.status for every linked Expert. Soft-fail so a
            # transient Redis/Qdrant issue never rolls the pipeline back.
            self._reconcile_expert_membership_after_ready(document)
        except Exception as exc:
            logger.exception("ingestion_failed", extra={"document_id": str(document_id)})
            document.status = "failed"
            document.failure_reason = str(exc)[:2000]
            job.status = "failed"
            job.last_error = str(exc)[:2000]
            job.completed_at = _utcnow()
            self.db.commit()
            raise

    @staticmethod
    def _needs_ocr(document: Document) -> bool:
        mime = (document.mime_type or "").split(";", 1)[0].strip().lower()
        return mime == "application/pdf" or not mime

    def _latest_job(self, document_id: uuid.UUID) -> IngestionJob | None:
        return self.db.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )

    def _reset_derived(self, document: Document) -> None:
        # Delete vectors first (workspace-scoped when owned)
        self.vectors.delete_by_document(
            str(document.id),
            workspace_id=document.workspace_id,
        )
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
        target_count = max(1, document.page_count or 1)
        for n in range(1, target_count + 1):
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

    def _parse_text_document(self, document: Document, job: IngestionJob) -> None:
        """Parse a non-PDF (text / markdown) Document into a single page.

        Text uploads are pre-validated at HTTP upload time so this stays
        cheap; still, all parser errors are captured on the page row so the
        job surfaces the failure like an OCR failure would.
        """
        parser = get_parser_for_format(document.mime_type)
        file_bytes, used_key = self.storage.get_document_bytes(
            document_id=document.id,
            workspace_id=document.workspace_id,
            stored_key=document.storage_key,
        )
        logger.info(
            "ingest_text_loaded",
            extra={
                "document_id": str(document.id),
                "workspace_id": str(document.workspace_id) if document.workspace_id else None,
                "storage_key": used_key,
                "operation": "text_load",
                "mime_type": document.mime_type,
            },
        )
        page_row = self.db.scalar(
            select(DocumentPage)
            .where(DocumentPage.document_id == document.id, DocumentPage.page_number == 1)
        )
        if page_row is None:
            page_row = DocumentPage(
                id=uuid.uuid4(),
                document_id=document.id,
                page_number=1,
                status="pending",
            )
            self.db.add(page_row)
            self.db.flush()

        page_row.attempt_count += 1
        page_row.started_at = page_row.started_at or _utcnow()
        try:
            parsed = parser.parse(file_bytes, document.original_filename)
        except AppError as exc:
            page_row.status = "failed"
            page_row.last_error = str(exc)[:2000]
            job.failed_pages = 1
            job.last_error = str(exc)[:2000]
            self.db.commit()
            return

        if not parsed.pages:
            page_row.status = "failed"
            page_row.last_error = "empty_parser_output"
            job.failed_pages = 1
            self.db.commit()
            return

        parsed_page = parsed.pages[0]
        raw_markdown = parsed_page.raw_markdown or ""
        canonical = normalize_canonical(raw_markdown)
        search = normalize_search(canonical)
        diagnostics = page_quality_diagnostics(parsed_page.plain_text or canonical)

        page_row.status = "parsed"
        page_row.raw_markdown = raw_markdown
        page_row.canonical_text = canonical
        page_row.search_text = search
        page_row.parser = f"text:{parsed.mime_type}"
        page_row.parser_hash = _hash_text(raw_markdown)
        page_row.text_length = diagnostics["text_length"]
        page_row.arabic_ratio = diagnostics["arabic_ratio"]
        page_row.last_error = None
        page_row.completed_at = _utcnow()

        job.processed_pages = 1
        job.failed_pages = 0
        self.db.commit()

    def _ocr_pages(self, document: Document, job: IngestionJob, failed_only: bool) -> None:
        pdf_bytes, used_key = self.storage.get_document_bytes(
            document_id=document.id,
            workspace_id=document.workspace_id,
            stored_key=document.storage_key,
        )
        logger.info(
            "ingest_pdf_loaded",
            extra={
                "document_id": str(document.id),
                "workspace_id": str(document.workspace_id) if document.workspace_id else None,
                "storage_key": used_key,
                "operation": "ocr_load",
            },
        )
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
                # Drop file-parser wrapper tags before quality checks / storage
                cleaned_md = _strip_file_wrappers(parsed.raw_markdown)
                plain = _strip_file_wrappers(parsed.plain_text)
                diagnostics = page_quality_diagnostics(plain or cleaned_md)
                meaningful = (plain or "").strip(" .\t\n•·-_")
                empty = (
                    diagnostics["empty_output"]
                    or diagnostics["replacement_char_count"] > 20
                    or len(meaningful) < 8
                )
                if empty:
                    # Blank / graphics-only page: keep provenance, skip indexing text
                    return page_id, {
                        "raw_markdown": cleaned_md or "",
                        "canonical_text": "",
                        "search_text": "",
                        "parser": parsed.parser,
                        "parser_hash": parsed.parser_hash,
                        "text_length": 0,
                        "arabic_ratio": 0.0,
                        "metadata": parsed.metadata,
                        "empty_page": True,
                    }
                canonical = normalize_canonical(cleaned_md)
                search = normalize_search(canonical)
                return page_id, {
                    "raw_markdown": cleaned_md,
                    "canonical_text": canonical,
                    "search_text": search,
                    "parser": parsed.parser,
                    "parser_hash": parsed.parser_hash,
                    "text_length": diagnostics["text_length"],
                    "arabic_ratio": diagnostics["arabic_ratio"],
                    "metadata": parsed.metadata,
                    "empty_page": False,
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
                    db_page.last_error = (
                        "empty_page_skipped" if result.get("empty_page") else None
                    )
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
            if not (page.canonical_text or "").strip():
                continue
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
        # Document.workspace_id is authoritative — never take workspace from request bodies.
        workspace_payload = (
            str(document.workspace_id) if document.workspace_id is not None else None
        )
        # Phase 3B: seed Qdrant expert_ids from PG at upsert time so a query
        # that lands before the post-commit sync still filters correctly.
        expert_ids_payload = [
            str(eid)
            for eid in self.membership_sync.list_active_expert_ids_for_document(document.id)
        ]
        for chunk, vector in zip(all_chunks, vectors, strict=True):
            payload = {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_title": document.title,
                "page": chunk.page_number,
                "ordinal": chunk.ordinal,
                "heading_path": chunk.heading_path or [],
                "embedding_model": chunk.embedding_model,
                "canonical_text": chunk.canonical_text,
                "search_text": chunk.search_text,
                "expert_ids": expert_ids_payload,
            }
            if workspace_payload is not None:
                payload["workspace_id"] = workspace_payload
            points.append(
                {
                    "id": str(chunk.qdrant_point_id),
                    "vector": vector,
                    "payload": payload,
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

    def _reconcile_expert_membership_after_ready(self, document: Document) -> None:
        """Best-effort Qdrant + Expert.status reconciliation after commit.

        Sync failures are logged but never bubble up so a transient Redis /
        Qdrant issue can't roll the ingestion pipeline back — retrieval is
        still safe (mandatory workspace_id filter) and a background
        reconciliation job will catch up.
        """
        try:
            expert_ids = self.membership_sync.sync_document(document.id)
        except Exception as exc:  # noqa: BLE001 — best-effort background sync
            logger.warning(
                "expert_membership_sync.pipeline_deferred",
                extra={"document_id": str(document.id), "error": str(exc)},
            )
            expert_ids = [
                str(eid)
                for eid in self.membership_sync.list_active_expert_ids_for_document(document.id)
            ]

        for raw_id in expert_ids:
            try:
                expert_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError):
                continue
            try:
                self._status_reconciler.reconcile(expert_id)
            except Exception as exc:  # noqa: BLE001 — status derived from PG state
                logger.warning(
                    "expert.status_reconcile_pipeline_failed",
                    extra={"expert_id": str(expert_id), "error": str(exc)},
                )
