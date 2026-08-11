"""Document data access — tenant-scoped queries by default.

Tenant-facing methods always filter by workspace_id (+ soft-delete).
Legacy MVP methods only see rows with workspace_id IS NULL.
Never mix populations in a single query path.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentPage, IngestionJob


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Workspace-scoped (SaaS) ---

    def get_for_workspace(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID, *, include_deleted: bool = False
    ) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
        if not include_deleted:
            stmt = stmt.where(Document.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def list_for_workspace(self, workspace_id: uuid.UUID) -> list[Document]:
        return list(
            self.db.scalars(
                select(Document)
                .where(
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.created_at.desc())
            )
        )

    def find_active_by_sha256_for_workspace(
        self, workspace_id: uuid.UUID, sha256: str
    ) -> Document | None:
        return self.db.scalar(
            select(Document).where(
                Document.workspace_id == workspace_id,
                Document.sha256 == sha256,
                Document.deleted_at.is_(None),
            )
        )

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.flush()
        return document

    # --- Legacy MVP (workspace_id IS NULL only) ---

    def get_legacy(
        self, document_id: uuid.UUID, *, include_deleted: bool = False
    ) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id.is_(None),
        )
        if not include_deleted:
            stmt = stmt.where(Document.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def list_legacy(self) -> list[Document]:
        return list(
            self.db.scalars(
                select(Document)
                .where(
                    Document.workspace_id.is_(None),
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.created_at.desc())
            )
        )

    def find_active_by_sha256_legacy(self, sha256: str) -> Document | None:
        return self.db.scalar(
            select(Document).where(
                Document.workspace_id.is_(None),
                Document.sha256 == sha256,
                Document.deleted_at.is_(None),
            )
        )

    # --- Shared helpers (always called with a pre-scoped document) ---

    def latest_job(self, document_id: uuid.UUID) -> IngestionJob | None:
        return self.db.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )

    def latest_jobs_by_document_ids(
        self, document_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, IngestionJob]:
        """Latest IngestionJob per document (Postgres DISTINCT ON)."""
        if not document_ids:
            return {}
        rows = self.db.scalars(
            select(IngestionJob)
            .where(IngestionJob.document_id.in_(document_ids))
            .distinct(IngestionJob.document_id)
            .order_by(IngestionJob.document_id, IngestionJob.created_at.desc())
        ).all()
        return {job.document_id: job for job in rows}

    def failed_pages(self, document_id: uuid.UUID) -> list[DocumentPage]:
        return list(
            self.db.scalars(
                select(DocumentPage)
                .where(
                    DocumentPage.document_id == document_id,
                    DocumentPage.status == "failed",
                )
                .order_by(DocumentPage.page_number)
            )
        )

    def pages_for_document(self, document_id: uuid.UUID) -> list[DocumentPage]:
        return list(
            self.db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
        )
