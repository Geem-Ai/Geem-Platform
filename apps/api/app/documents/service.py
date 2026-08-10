from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document, DocumentPage, IngestionJob
from app.ingestion.pdf_utils import validate_pdf_bytes
from app.storage.minio_storage import MinioObjectStorage, document_storage_key
from app.storage.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    base = PurePosixPath(name).name
    base = re.sub(r"[^\w.\-()\u0600-\u06FF ]+", "_", base)
    return base[:200] or "document.pdf"


class DocumentService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        storage: MinioObjectStorage | None = None,
        vectors: QdrantVectorStore | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage or MinioObjectStorage(self.settings)
        self.vectors = vectors or QdrantVectorStore(self.settings)

    def upload(self, file_bytes: bytes, filename: str, title: str | None = None) -> Document:
        safe_name = sanitize_filename(filename)
        if not safe_name.lower().endswith(".pdf") and not file_bytes.startswith(b"%PDF"):
            raise AppError(ErrorCategory.INVALID_PDF, "Only PDF uploads are supported")

        info = validate_pdf_bytes(
            file_bytes,
            max_bytes=self.settings.max_upload_bytes,
            max_pages=self.settings.max_pdf_pages,
        )
        digest = hashlib.sha256(file_bytes).hexdigest()
        existing = self.db.scalar(select(Document).where(Document.sha256 == digest))
        if existing and existing.status != "deleting":
            raise AppError(
                ErrorCategory.CONFLICT,
                "Duplicate PDF already uploaded",
                details={"id": str(existing.id), "status": existing.status},
            )

        doc_id = uuid.uuid4()
        storage_key = document_storage_key(str(doc_id))
        self.storage.ensure_bucket()
        self.storage.put_bytes(storage_key, file_bytes, "application/pdf")

        document = Document(
            id=doc_id,
            title=title or safe_name,
            original_filename=safe_name,
            storage_key=storage_key,
            sha256=digest,
            mime_type="application/pdf",
            page_count=info.page_count,
            status="queued",
        )
        job = IngestionJob(
            id=uuid.uuid4(),
            document_id=doc_id,
            status="queued",
            total_pages=info.page_count,
            processed_pages=0,
            failed_pages=0,
            current_stage="queued",
        )
        self.db.add(document)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(document)
        return document

    def list_documents(self) -> list[Document]:
        return list(
            self.db.scalars(select(Document).order_by(Document.created_at.desc()))
        )

    def get(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if not document:
            raise AppError(ErrorCategory.NOT_FOUND, "Document not found")
        return document

    def progress(self, document: Document) -> dict:
        job = self.db.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document.id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        processed = job.processed_pages if job else 0
        failed = job.failed_pages if job else 0
        total = document.page_count or 1
        progress = min(1.0, processed / total) if document.status != "ready" else 1.0
        if document.status == "ready":
            progress = 1.0
        return {
            "processed_pages": processed,
            "failed_pages": failed,
            "current_stage": job.current_stage if job else None,
            "progress": progress,
            "job_id": str(job.id) if job else None,
        }

    def get_file(self, document_id: uuid.UUID) -> tuple[bytes, str]:
        document = self.get(document_id)
        data = self.storage.get_bytes(document.storage_key)
        return data, document.original_filename

    def delete(self, document_id: uuid.UUID) -> None:
        document = self.get(document_id)
        document.status = "deleting"
        self.db.commit()
        try:
            self.vectors.delete_by_document(str(document.id))
        except AppError:
            logger.exception("qdrant_delete_failed", extra={"document_id": str(document_id)})
        try:
            self.storage.delete(document.storage_key)
        except AppError:
            logger.exception("minio_delete_failed", extra={"document_id": str(document_id)})
        self.db.delete(document)
        self.db.commit()

    def reprocess(self, document_id: uuid.UUID, mode: str = "failed_pages") -> IngestionJob:
        if mode not in {"failed_pages", "full"}:
            raise AppError(ErrorCategory.VALIDATION, "mode must be failed_pages or full")
        document = self.get(document_id)
        if document.status == "deleting":
            raise AppError(ErrorCategory.CONFLICT, "Document is being deleted")
        job = IngestionJob(
            id=uuid.uuid4(),
            document_id=document.id,
            status="queued",
            total_pages=document.page_count,
            processed_pages=0,
            failed_pages=0,
            current_stage="queued",
        )
        document.status = "queued"
        document.failure_reason = None
        self.db.add(job)
        self.db.commit()
        return job

    def failed_pages(self, document_id: uuid.UUID) -> list[DocumentPage]:
        return list(
            self.db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id, DocumentPage.status == "failed")
                .order_by(DocumentPage.page_number)
            )
        )
