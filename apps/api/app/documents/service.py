from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document, DocumentPage, IngestionJob
from app.documents.repository import DocumentRepository
from app.ingestion.parsers import (
    DocumentFormat,
    DocumentFormatDescriptor,
    detect_document_format,
)
from app.ingestion.pdf_utils import validate_pdf_bytes
from app.storage.document_keys import resolve_document_storage_key
from app.storage.minio_storage import MinioObjectStorage
from app.storage.qdrant_store import QdrantVectorStore
from app.workspaces.models import Workspace, WorkspaceStatus

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    base = PurePosixPath(name).name
    base = re.sub(r"[^\w.\-()\u0600-\u06FF ]+", "_", base)
    return base[:200] or "document.pdf"


@dataclass(frozen=True, slots=True)
class UploadInspection:
    """Post-validation inspection details for a Workspace upload."""

    safe_name: str
    descriptor: DocumentFormatDescriptor
    page_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class WorkspaceUploadResult:
    """Result of ``upload_for_workspace_or_link_existing``.

    ``reused`` is True when a Document with the same sha256 already existed in
    the Workspace and the upload was linked to that Document instead of
    creating a new one.
    """

    document: Document
    reused: bool


def compute_document_progress(
    document: Document, job: IngestionJob | None
) -> dict:
    """DB-only progress snapshot — safe for list endpoints (no storage/vector clients)."""
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
        self.repo = DocumentRepository(db)

    # ------------------------------------------------------------------
    # Workspace-scoped (SaaS) — workspace comes from trusted RequestContext
    # ------------------------------------------------------------------

    def upload_for_workspace(
        self,
        workspace: Workspace,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        declared_mime_type: str | None = None,
    ) -> Document:
        self._require_active_workspace(workspace)
        inspection = self._validate_upload(
            file_bytes, filename, declared_mime_type=declared_mime_type
        )

        from app.usage.storage import StorageQuotaService

        quota = StorageQuotaService(self.db, self.settings)
        if not workspace.is_system:
            quota.heal_stale_committed(workspace.id)
            quota.lock(workspace.id)
        existing = self.repo.find_active_by_sha256_for_workspace(workspace.id, inspection.sha256)
        if existing and existing.status != "deleting":
            raise AppError(
                ErrorCategory.DOCUMENT_ALREADY_EXISTS,
                "Duplicate document already uploaded in this workspace",
                details={"id": str(existing.id), "status": existing.status},
            )

        document = self._charge_and_persist(
            workspace=workspace,
            file_bytes=file_bytes,
            inspection=inspection,
            title=title,
            quota=quota,
        )
        security_log(
            "document.uploaded",
            workspace_id=str(workspace.id),
            document_id=str(document.id),
            action="upload",
            byte_size=document.byte_size,
            mime_type=document.mime_type,
        )
        return document

    def upload_for_workspace_or_link_existing(
        self,
        workspace: Workspace,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        declared_mime_type: str | None = None,
    ) -> WorkspaceUploadResult:
        """Idempotent Workspace upload: re-use an existing Document on hash hit.

        Used by the Expert upload endpoints (Phase 3B) so a member can re-upload
        the same file to link it to another Expert without hitting the
        DOCUMENT_ALREADY_EXISTS error the strict ``upload_for_workspace``
        raises.
        """
        self._require_active_workspace(workspace)
        inspection = self._validate_upload(
            file_bytes, filename, declared_mime_type=declared_mime_type
        )

        from app.usage.storage import StorageQuotaService

        quota = StorageQuotaService(self.db, self.settings)
        if not workspace.is_system:
            quota.heal_stale_committed(workspace.id)
            quota.lock(workspace.id)
        existing = self.repo.find_active_by_sha256_for_workspace(workspace.id, inspection.sha256)
        if existing and existing.status != "deleting":
            security_log(
                "document.upload_reused",
                workspace_id=str(workspace.id),
                document_id=str(existing.id),
                action="upload_reuse",
                mime_type=existing.mime_type,
            )
            return WorkspaceUploadResult(document=existing, reused=True)

        document = self._charge_and_persist(
            workspace=workspace,
            file_bytes=file_bytes,
            inspection=inspection,
            title=title,
            quota=quota,
        )
        security_log(
            "document.uploaded",
            workspace_id=str(workspace.id),
            document_id=str(document.id),
            action="upload",
            byte_size=document.byte_size,
            mime_type=document.mime_type,
        )
        return WorkspaceUploadResult(document=document, reused=False)

    def list_for_workspace(self, workspace: Workspace) -> list[Document]:
        self._require_active_workspace(workspace)
        return self.repo.list_for_workspace(workspace.id)

    def list_page_for_workspace(
        self,
        workspace: Workspace,
        *,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> tuple[list[Document], int, dict[uuid.UUID, list[tuple[uuid.UUID, str]]]]:
        self._require_active_workspace(workspace)
        items, total = self.repo.list_page_for_workspace(
            workspace.id, limit=limit, offset=offset, q=q
        )
        refs = self.repo.expert_refs_for_documents(
            workspace.id, [doc.id for doc in items]
        )
        return items, total, refs

    def get_for_workspace(self, workspace: Workspace, document_id: uuid.UUID) -> Document:
        self._require_active_workspace(workspace)
        document = self.repo.get_for_workspace(workspace.id, document_id)
        if document is None:
            raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "Document not found")
        return document

    def get_file_for_workspace(
        self, workspace: Workspace, document_id: uuid.UUID
    ) -> tuple[bytes, str, str]:
        document = self.get_for_workspace(workspace, document_id)
        data, used_key = self.storage.get_document_bytes(
            document_id=document.id,
            workspace_id=document.workspace_id,
            stored_key=document.storage_key,
        )
        security_log(
            "document.download",
            workspace_id=str(workspace.id),
            document_id=str(document.id),
            action="download",
            storage_key=used_key,
        )
        mime = (document.mime_type or "application/octet-stream").split(";", 1)[0].strip()
        return data, document.original_filename, mime or "application/octet-stream"

    def rename_for_workspace(
        self, workspace: Workspace, document_id: uuid.UUID, title: str
    ) -> Document:
        document = self.get_for_workspace(workspace, document_id)
        if document.status == "deleting":
            raise AppError(ErrorCategory.DOCUMENT_DELETED, "Document is being deleted")
        next_title = title.strip()
        if not next_title:
            raise AppError(ErrorCategory.VALIDATION, "Title is required.")
        if document.title != next_title:
            document.title = next_title
            self.db.commit()
            self.db.refresh(document)
        security_log(
            "document.renamed",
            workspace_id=str(workspace.id),
            document_id=str(document.id),
            action="rename",
        )
        return document

    def delete_for_workspace(self, workspace: Workspace, document_id: uuid.UUID) -> None:
        """Soft-delete a Workspace document and purge blob + vectors + derived RAG.

        The PG ``documents`` row stays for audit and old citations. Hash uniqueness
        is released so the same file can be uploaded again as a new document.
        Restore is not supported after this purge.
        """
        from sqlalchemy import select

        from app.experts.models import ExpertDocument
        from app.experts.status import ExpertStatusReconciler
        from app.usage.storage import StorageQuotaService

        document = self.get_for_workspace(workspace, document_id)
        if document.deleted_at is not None:
            raise AppError(ErrorCategory.DOCUMENT_DELETED, "Document is already deleted")

        document.status = "deleting"
        links = list(
            self.db.scalars(
                select(ExpertDocument).where(ExpertDocument.document_id == document.id)
            )
        )
        expert_ids = {link.expert_id for link in links}
        for link in links:
            self.db.delete(link)
        for chunk in list(document.chunks):
            self.db.delete(chunk)
        for page in list(document.pages):
            self.db.delete(page)

        document.soft_delete()
        StorageQuotaService(self.db, self.settings).record_logical_delete(
            workspace.id,
            document_id=document.id,
            byte_size=int(document.byte_size or 0),
        )
        self.db.commit()

        self._purge_object_and_vectors(document)
        reconciler = ExpertStatusReconciler(self.db)
        for expert_id in expert_ids:
            try:
                reconciler.reconcile(expert_id)
            except Exception as exc:  # noqa: BLE001 — status is derived; never undo purge
                logger.warning(
                    "document.expert_reconcile_failed",
                    extra={"document_id": str(document.id), "expert_id": str(expert_id), "error": str(exc)},
                )

        security_log(
            "document.purged",
            workspace_id=str(workspace.id),
            document_id=str(document_id),
            action="delete",
        )

    def _purge_object_and_vectors(self, document: Document) -> None:
        keys = resolve_document_storage_key(document.id, document.workspace_id)
        for key in keys.candidate_read_keys(document.storage_key, include_legacy_flat=True):
            try:
                self.storage.delete(key)
            except AppError as exc:
                logger.warning(
                    "document.minio_purge_failed",
                    extra={
                        "document_id": str(document.id),
                        "workspace_id": str(document.workspace_id) if document.workspace_id else None,
                        "key": key,
                        "error": str(exc),
                    },
                )
        try:
            self.vectors.delete_by_document(
                str(document.id),
                workspace_id=document.workspace_id,
            )
        except AppError as exc:
            logger.warning(
                "document.qdrant_purge_failed",
                extra={
                    "document_id": str(document.id),
                    "workspace_id": str(document.workspace_id) if document.workspace_id else None,
                    "error": str(exc),
                },
            )
            try:
                self.vectors.delete_by_document(
                    str(document.id),
                    workspace_id=document.workspace_id,
                )
            except AppError as retry_exc:
                logger.warning(
                    "document.qdrant_purge_retry_failed",
                    extra={
                        "document_id": str(document.id),
                        "error": str(retry_exc),
                    },
                )

    def restore_for_workspace(self, workspace: Workspace, document_id: uuid.UUID) -> Document:
        """Restore is closed after Phase 8 physical purge.

        Historical tests that resurrected a soft-deleted row after logical
        delete must re-upload instead.
        """
        self._require_active_workspace(workspace)
        document = self.repo.get_for_workspace(workspace.id, document_id, include_deleted=True)
        if document is None:
            raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "Document not found")
        if document.deleted_at is None:
            raise AppError(ErrorCategory.CONFLICT, "Document is not deleted")
        raise AppError(
            ErrorCategory.DOCUMENT_DELETED,
            "Document was purged and cannot be restored. Upload the file again.",
            details={"id": str(document.id)},
        )

    def reprocess_for_workspace(
        self, workspace: Workspace, document_id: uuid.UUID, mode: str = "failed_pages"
    ) -> IngestionJob:
        if mode not in {"failed_pages", "full"}:
            raise AppError(ErrorCategory.VALIDATION, "mode must be failed_pages or full")
        document = self.get_for_workspace(workspace, document_id)
        if document.status == "deleting":
            raise AppError(ErrorCategory.DOCUMENT_DELETED, "Document is being deleted")
        job = self._enqueue_reprocess_job(document)
        security_log(
            "document.reprocess",
            workspace_id=str(workspace.id),
            document_id=str(document_id),
            action="reprocess",
            mode=mode,
        )
        return job

    def failed_pages_for_workspace(
        self, workspace: Workspace, document_id: uuid.UUID
    ) -> list[DocumentPage]:
        self.get_for_workspace(workspace, document_id)
        return self.repo.failed_pages(document_id)

    # ------------------------------------------------------------------
    # Legacy MVP helpers — maintenance / tests only (not production HTTP)
    # ------------------------------------------------------------------

    def upload_legacy(
        self, file_bytes: bytes, filename: str, title: str | None = None
    ) -> Document:
        raise AppError(
            ErrorCategory.UNAUTHORIZED,
            "Legacy unauthenticated document population is retired (Phase 2C).",
        )

    def list_legacy(self) -> list[Document]:
        return self.repo.list_legacy()

    def get_legacy(self, document_id: uuid.UUID) -> Document:
        document = self.repo.get_legacy(document_id)
        if document is None:
            raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "Document not found")
        return document

    def get_file_legacy(self, document_id: uuid.UUID) -> tuple[bytes, str]:
        raise AppError(
            ErrorCategory.UNAUTHORIZED,
            "Legacy document file access is retired (Phase 2C).",
        )

    def delete_legacy(self, document_id: uuid.UUID) -> None:
        raise AppError(
            ErrorCategory.UNAUTHORIZED,
            "Legacy hard-delete path is retired; use Workspace soft-delete.",
        )

    def reprocess_legacy(
        self, document_id: uuid.UUID, mode: str = "failed_pages"
    ) -> IngestionJob:
        raise AppError(
            ErrorCategory.UNAUTHORIZED,
            "Legacy reprocess path is retired (Phase 2C).",
        )

    def failed_pages_legacy(self, document_id: uuid.UUID) -> list[DocumentPage]:
        raise AppError(
            ErrorCategory.UNAUTHORIZED,
            "Legacy document access is retired (Phase 2C).",
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def progress(self, document: Document) -> dict:
        return compute_document_progress(document, self.repo.latest_job(document.id))

    def pages_for_document(self, document_id: uuid.UUID) -> list[DocumentPage]:
        return self.repo.pages_for_document(document_id)

    # Retired aliases — keep names so callers fail closed instead of silently creating NULL rows.
    def upload(self, file_bytes: bytes, filename: str, title: str | None = None) -> Document:
        return self.upload_legacy(file_bytes, filename, title=title)

    def list_documents(self) -> list[Document]:
        return self.list_legacy()

    def get(self, document_id: uuid.UUID) -> Document:
        return self.get_legacy(document_id)

    def get_file(self, document_id: uuid.UUID) -> tuple[bytes, str]:
        return self.get_file_legacy(document_id)

    def delete(self, document_id: uuid.UUID) -> None:
        return self.delete_legacy(document_id)

    def reprocess(self, document_id: uuid.UUID, mode: str = "failed_pages") -> IngestionJob:
        return self.reprocess_legacy(document_id, mode=mode)

    def failed_pages(self, document_id: uuid.UUID) -> list[DocumentPage]:
        return self.failed_pages_legacy(document_id)

    def _require_active_workspace(self, workspace: Workspace) -> None:
        if workspace.deleted_at is not None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        if workspace.status != WorkspaceStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.WORKSPACE_ACCESS_DENIED,
                "Workspace is not active.",
                details={"status": workspace.status},
            )

    def _validate_upload(
        self,
        file_bytes: bytes,
        filename: str,
        *,
        declared_mime_type: str | None = None,
    ) -> UploadInspection:
        if len(file_bytes) > self.settings.max_upload_bytes:
            raise AppError(
                ErrorCategory.INVALID_DOCUMENT,
                f"Upload exceeds maximum size of {self.settings.max_upload_bytes} bytes",
            )
        safe_name = sanitize_filename(filename)
        descriptor = detect_document_format(
            file_bytes, safe_name, declared_mime_type=declared_mime_type
        )

        page_count = 1
        if descriptor.format == DocumentFormat.PDF:
            info = validate_pdf_bytes(
                file_bytes,
                max_bytes=self.settings.max_upload_bytes,
                max_pages=self.settings.max_pdf_pages,
            )
            page_count = info.page_count
        else:
            # Non-PDF formats parse into a single page — invoke the parser
            # eagerly so unsupported encodings / binary payloads fail closed
            # at upload time (not later inside the Celery pipeline).
            parsed = descriptor.parser.parse(file_bytes, safe_name)
            page_count = parsed.page_count or 1

        digest = hashlib.sha256(file_bytes).hexdigest()
        return UploadInspection(
            safe_name=safe_name,
            descriptor=descriptor,
            page_count=page_count,
            sha256=digest,
        )

    def _charge_and_persist(
        self,
        *,
        workspace: Workspace,
        file_bytes: bytes,
        inspection: UploadInspection,
        title: str | None,
        quota: object | None = None,
    ) -> Document:
        """Reserve storage (tenant Workspaces), persist blob+row, finalize or release.

        Hash reuse must be decided by the caller *under the same storage lock*
        before this method runs. SYSTEM workspaces skip quota.
        """
        from app.usage.storage import StorageHold, StorageQuotaService

        storage_quota = quota if isinstance(quota, StorageQuotaService) else StorageQuotaService(
            self.db, self.settings
        )
        hold: StorageHold | None = None
        try:
            hold = storage_quota.reserve(workspace, len(file_bytes))
            document = self._persist_new_document(
                file_bytes=file_bytes,
                inspection=inspection,
                title=title,
                workspace_id=workspace.id,
                commit=False,
            )
            storage_quota.finalize(hold, document_id=document.id)
            self.db.commit()
            self.db.refresh(document)
            return document
        except AppError:
            if hold is None:
                raise
            self.db.rollback()
            if not hold.skipped:
                try:
                    storage_quota.release(hold)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            if hold is not None and not hold.skipped:
                try:
                    storage_quota.release(hold)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            raise

    def _persist_new_document(
        self,
        *,
        file_bytes: bytes,
        inspection: UploadInspection,
        title: str | None,
        workspace_id: uuid.UUID,
        commit: bool = True,
    ) -> Document:
        if workspace_id is None:
            raise AppError(
                ErrorCategory.VALIDATION,
                "workspace_id is required for all Documents (Phase 2C).",
            )
        doc_id = uuid.uuid4()
        mime_type = inspection.descriptor.mime_type
        resolved = self.storage.put_document_bytes(
            document_id=doc_id,
            workspace_id=workspace_id,
            data=file_bytes,
            content_type=mime_type,
        )

        document = Document(
            id=doc_id,
            workspace_id=workspace_id,
            title=title or inspection.safe_name,
            original_filename=inspection.safe_name,
            storage_key=resolved.canonical,
            sha256=inspection.sha256,
            mime_type=mime_type,
            byte_size=len(file_bytes),
            page_count=inspection.page_count,
            status="queued",
        )
        job = IngestionJob(
            id=uuid.uuid4(),
            document_id=doc_id,
            status="queued",
            total_pages=inspection.page_count,
            processed_pages=0,
            failed_pages=0,
            current_stage="queued",
        )
        self.repo.create(document)
        self.db.add(job)
        if commit:
            self.db.commit()
            self.db.refresh(document)
        else:
            self.db.flush()
        return document

    def _enqueue_reprocess_job(self, document: Document) -> IngestionJob:
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

    def _record_storage_delta(
        self,
        workspace_id: uuid.UUID,
        *,
        delta_bytes: int,
        document_id: uuid.UUID,
        reason: str,
    ) -> None:
        from app.usage.meters import StorageUsageService

        StorageUsageService(self.db, self.settings).record_delta(
            workspace_id,
            delta_bytes=delta_bytes,
            reason=reason,
            document_id=document_id,
        )
