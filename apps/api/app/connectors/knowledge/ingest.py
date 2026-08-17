"""Shared Expert ↔ Document linking for knowledge connectors (Phase 9E).

Provider adapters download/convert content; this bridge owns Document upload,
ExpertSource linking, version-swap purge, and shared-document safety.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.models import ConnectorItem
from app.connectors.types import ConnectorItemStatus
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.documents.service import DocumentService
from app.experts.models import (
    ExpertDocument,
    ExpertSource,
    ExpertSourceStatus,
    ExpertSourceType,
)
from app.experts.repository import ExpertRepository
from app.experts.service import ExpertService, _enqueue_ingest
from app.workspaces.models import Workspace
from app.workspaces.repository import WorkspaceRepository

logger = logging.getLogger(__name__)


class KnowledgeIngestBridge:
    """Provider-neutral Document / ExpertSource projection for connector items."""

    def __init__(
        self,
        db: Session,
        *,
        connector_key: str,
        settings: Settings | None = None,
        not_found_errors: frozenset[ErrorCategory] | None = None,
        access_denied_errors: frozenset[ErrorCategory] | None = None,
    ) -> None:
        self.db = db
        self.connector_key = connector_key
        self.settings = settings or get_settings()
        self.experts = ExpertService(db, self.settings)
        self.expert_repo = ExpertRepository(db)
        self.workspaces = WorkspaceRepository(db)
        self.not_found_errors = not_found_errors or frozenset()
        self.access_denied_errors = access_denied_errors or frozenset()

    def sources_for_item(self, item: ConnectorItem) -> list[ExpertSource]:
        item_id = str(item.id)
        rows = list(
            self.db.scalars(
                select(ExpertSource).where(
                    ExpertSource.type == ExpertSourceType.CONNECTOR.value,
                    ExpertSource.deleted_at.is_(None),
                )
            ).all()
        )
        return [
            s
            for s in rows
            if isinstance(s.config, dict)
            and str(s.config.get("connector_item_id") or "") == item_id
        ]

    def ingest_bytes(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        item: ConnectorItem,
        file_bytes: bytes,
        filename: str,
        declared_mime_type: str | None,
        provenance: dict[str, Any],
        content_version: str | None,
        content_etag: str | None = None,
        actor_id: uuid.UUID | None = None,
        force: bool = False,
        sources: list[ExpertSource] | None = None,
    ) -> str:
        """Upload/link document and bind Expert sources. Returns action label."""
        workspace = self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")

        bound = sources if sources is not None else self.sources_for_item(item)
        if not bound and not force:
            return "skipped"

        content_changed = force or (
            content_version is not None
            and str(content_version) != (item.external_version or "")
        ) or (item.current_document_id is None)

        if isinstance(item.extra, dict):
            item.extra = {**item.extra, **provenance}
        else:
            item.extra = dict(provenance)

        if not content_changed and item.current_document_id is not None:
            if content_version is not None:
                item.external_version = str(content_version)
            item.last_seen_at = datetime.now(timezone.utc)
            self.db.flush()
            return "skipped"

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(filename).suffix or ".bin"
            ) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)

            data = tmp_path.read_bytes()
            docs = DocumentService(self.db, self.settings)
            old_document_id = item.current_document_id
            try:
                upload = docs.upload_for_workspace_or_link_existing(
                    workspace,
                    data,
                    filename,
                    title=item.name or filename,
                    declared_mime_type=declared_mime_type,
                )
            except AppError as exc:
                if exc.category in {
                    ErrorCategory.STORAGE_QUOTA_EXCEEDED,
                    ErrorCategory.UPLOAD_TOO_LARGE,
                    ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
                    ErrorCategory.INVALID_DOCUMENT,
                }:
                    self.fail_sources(bound, exc)
                    return "failed"
                raise

            document = upload.document
            for source in bound:
                self.link_source_document(
                    workspace=workspace,
                    source=source,
                    document_id=document.id,
                    actor_id=actor_id or source.created_by,
                    provenance=provenance,
                    connection_id=connection_id,
                    item=item,
                )

            item.current_document_id = document.id
            if content_version is not None:
                item.external_version = str(content_version)
            if content_etag is not None:
                item.external_etag = content_etag
            item.status = ConnectorItemStatus.ACTIVE.value
            item.last_seen_at = datetime.now(timezone.utc)
            self.db.flush()

            if not upload.reused:
                _enqueue_ingest(
                    document_id=str(document.id),
                    workspace_id=str(workspace_id),
                    actor_id=str(actor_id) if actor_id else "",
                )
                for source in bound:
                    source.status = ExpertSourceStatus.PROCESSING.value
            else:
                for source in bound:
                    if document.status == "ready":
                        source.status = ExpertSourceStatus.READY.value
                    elif document.status == "failed":
                        source.status = ExpertSourceStatus.FAILED.value
                    else:
                        source.status = ExpertSourceStatus.PROCESSING.value
            self.db.flush()

            if old_document_id is not None and old_document_id != document.id:
                self.maybe_purge_old_document(workspace, old_document_id)

            return "created" if old_document_id is None else "updated"
        except AppError as exc:
            self.fail_sources(bound, exc)
            logger.warning(
                "knowledge_ingest_item_failed connector=%s error=%s external_id=%s",
                self.connector_key,
                exc.category.value,
                item.external_id,
            )
            return "failed"
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def mark_item_unavailable(
        self, item: ConnectorItem, sources: list[ExpertSource] | None = None
    ) -> None:
        item.status = ConnectorItemStatus.UNAVAILABLE.value
        item.deleted_at_provider = datetime.now(timezone.utc)
        for source in sources or self.sources_for_item(item):
            source.status = ExpertSourceStatus.UNAVAILABLE.value
            if source.id:
                links = list(
                    self.db.scalars(
                        select(ExpertDocument).where(
                            ExpertDocument.source_id == source.id
                        )
                    ).all()
                )
                for link in links:
                    doc_id = link.document_id
                    self.db.delete(link)
                    self.db.flush()
                    self.experts._sync_document_membership(doc_id)
                    self.experts._reconcile_status(source.expert_id)
        self.db.flush()

    def link_source_document(
        self,
        *,
        workspace: Workspace,
        source: ExpertSource,
        document_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        provenance: dict[str, Any],
        connection_id: uuid.UUID,
        item: ConnectorItem,
    ) -> None:
        _ = workspace, actor_id
        expert = self.expert_repo.get_by_id(source.expert_id)
        if expert is None:
            return
        cfg = dict(source.config or {})
        cfg.update(
            {
                "connector_key": self.connector_key,
                "connection_id": str(connection_id),
                "connector_item_id": str(item.id),
                "external_id": item.external_id,
                "provenance": provenance,
            }
        )
        source.config = cfg
        source.name = item.name or source.name

        existing = self.expert_repo.get_document_link(expert.id, document_id)
        if existing is None:
            link = ExpertDocument(
                expert_id=expert.id,
                document_id=document_id,
                source_id=source.id,
            )
            self.expert_repo.create_document_link(link)
            self.db.flush()
            self.experts._sync_document_membership(document_id)
            self.experts._reconcile_status(expert.id)
        else:
            existing.source_id = source.id
            self.db.flush()
            self.experts._sync_document_membership(document_id)
            self.experts._reconcile_status(expert.id)

        stale = list(
            self.db.scalars(
                select(ExpertDocument).where(
                    ExpertDocument.source_id == source.id,
                    ExpertDocument.document_id != document_id,
                )
            ).all()
        )
        for link in stale:
            old_id = link.document_id
            self.db.delete(link)
            self.db.flush()
            self.experts._sync_document_membership(old_id)

    def maybe_purge_old_document(
        self, workspace: Workspace, document_id: uuid.UUID
    ) -> None:
        remaining = self.db.scalar(
            select(ExpertDocument.id)
            .where(ExpertDocument.document_id == document_id)
            .limit(1)
        )
        if remaining is not None:
            return
        other_item = self.db.scalar(
            select(ConnectorItem.id)
            .where(ConnectorItem.current_document_id == document_id)
            .limit(1)
        )
        if other_item is not None:
            return
        try:
            DocumentService(self.db, self.settings).delete_for_workspace(
                workspace, document_id
            )
        except AppError:
            logger.info(
                "knowledge_old_document_purge_skipped connector=%s document_id=%s",
                self.connector_key,
                str(document_id),
            )

    def fail_sources(self, sources: list[ExpertSource], exc: AppError) -> None:
        unavailable = self.not_found_errors | self.access_denied_errors
        for source in sources:
            if exc.category in unavailable:
                source.status = ExpertSourceStatus.UNAVAILABLE.value
            else:
                source.status = ExpertSourceStatus.FAILED.value
            cfg = dict(source.config or {})
            cfg["last_error_code"] = exc.category.value
            cfg["last_error_message"] = exc.message
            source.config = cfg
        self.db.flush()
