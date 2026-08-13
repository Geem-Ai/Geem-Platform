"""Document data access — tenant-scoped queries by default.

Tenant-facing methods always filter by workspace_id (+ soft-delete).
Legacy MVP methods only see rows with workspace_id IS NULL.
Never mix populations in a single query path.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentPage, IngestionJob
from app.experts.models import Expert, ExpertDocument, ExpertType

# PostgreSQL LIKE / ILIKE metacharacters (escape with backslash).
_LIKE_META = re.compile(r"([\\%_])")


def ilike_contains_pattern(needle: str) -> str:
    """Build a case-insensitive contains pattern with `%` / `_` / `\\` escaped."""
    escaped = _LIKE_META.sub(r"\\\1", needle)
    return f"%{escaped}%"


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
        items, _total = self.list_page_for_workspace(workspace_id, limit=10_000, offset=0)
        return items

    def list_page_for_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> tuple[list[Document], int]:
        filters = [
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        ]
        needle = (q or "").strip()
        if needle:
            pattern = ilike_contains_pattern(needle)
            filters.append(
                or_(
                    Document.title.ilike(pattern, escape="\\"),
                    Document.original_filename.ilike(pattern, escape="\\"),
                )
            )
        total = int(
            self.db.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
        )
        items = list(
            self.db.scalars(
                select(Document)
                .where(*filters)
                .order_by(Document.byte_size.desc().nulls_last(), Document.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def expert_refs_for_documents(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
        """Active Workspace Expert names linked to the given documents.

        Scoped to ``workspace_id`` so a corrupt cross-tenant link cannot leak
        another Workspace's Expert names into the inventory.
        """
        if not document_ids:
            return {}
        rows = self.db.execute(
            select(ExpertDocument.document_id, Expert.id, Expert.name)
            .join(Expert, Expert.id == ExpertDocument.expert_id)
            .where(
                ExpertDocument.document_id.in_(document_ids),
                Expert.workspace_id == workspace_id,
                Expert.deleted_at.is_(None),
                Expert.type == ExpertType.WORKSPACE.value,
            )
            .order_by(Expert.name.asc())
        ).all()
        out: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {doc_id: [] for doc_id in document_ids}
        for document_id, expert_id, name in rows:
            out.setdefault(document_id, []).append((expert_id, name))
        return out

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

    def sum_active_byte_size(self, workspace_id: uuid.UUID) -> int:
        """Billable logical storage: active Workspace documents only."""
        value = self.db.scalar(
            select(func.coalesce(func.sum(Document.byte_size), 0)).where(
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
        return int(value or 0)

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
