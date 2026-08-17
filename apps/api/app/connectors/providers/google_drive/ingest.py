"""Bridge Google Drive file content into Geem Documents / ExpertSources (Phase 9D)."""

from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.items import ConnectorItemService
from app.connectors.models import ConnectorItem
from app.connectors.providers.google_drive.client import GoogleDriveClient
from app.connectors.providers.google_drive.formats import (
    is_google_workspace_doc,
    require_supported_mime,
    suggested_filename,
)
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

_SAFE_PROVENANCE_KEYS = frozenset(
    {
        "webViewLink",
        "mimeType",
        "modifiedTime",
        "version",
        "md5Checksum",
        "size",
        "name",
        "resourceKey",
    }
)


def safe_provenance(meta: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _SAFE_PROVENANCE_KEYS:
        if key in meta and meta[key] is not None:
            out[key] = meta[key]
    return out


def fetch_file_bytes(
    client: GoogleDriveClient,
    meta: dict[str, Any],
    *,
    max_bytes: int,
    resource_key: str | None = None,
) -> tuple[bytes, str]:
    """Download or export file content; return (bytes, suggested_filename)."""
    file_id = str(meta["id"])
    mime = require_supported_mime(meta.get("mimeType"))
    rk = resource_key or meta.get("resourceKey")
    if is_google_workspace_doc(mime):
        data = client.export_workspace_file(
            file_id,
            export_mime="text/markdown",
            max_bytes=max_bytes,
            resource_key=rk,
        )
        # After export, store as markdown locally.
        filename = suggested_filename(meta.get("name"), "text/markdown")
        return data, filename

    size_raw = meta.get("size")
    if size_raw is not None:
        try:
            if int(size_raw) > max_bytes:
                raise AppError(
                    ErrorCategory.GOOGLE_DRIVE_EXPORT_TOO_LARGE,
                    "Google Drive file exceeds maximum upload size.",
                    details={"max_bytes": max_bytes, "size": int(size_raw)},
                )
        except (TypeError, ValueError):
            pass

    data = client.download_blob(
        file_id,
        max_bytes=max_bytes,
        resource_key=rk,
    )
    filename = suggested_filename(meta.get("name"), mime)
    return data, filename


class GoogleDriveIngestBridge:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.items = ConnectorItemService(db)
        self.experts = ExpertService(db, self.settings)
        self.expert_repo = ExpertRepository(db)
        self.workspaces = WorkspaceRepository(db)

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

    def ingest_tracked_item(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        item: ConnectorItem,
        client: GoogleDriveClient,
        actor_id: uuid.UUID | None = None,
        force: bool = False,
    ) -> str:
        """Ingest or re-ingest one tracked item. Returns action: created|updated|skipped|failed."""
        workspace = self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")

        sources = self.sources_for_item(item)
        if not sources and not force:
            return "skipped"

        resource_key = None
        if isinstance(item.extra, dict):
            resource_key = item.extra.get("resourceKey") or item.extra.get("resource_key")

        try:
            meta = client.get_file_metadata(
                item.external_id, resource_key=resource_key
            )
        except AppError as exc:
            self._fail_sources(sources, exc)
            if exc.category in {
                ErrorCategory.GOOGLE_DRIVE_FILE_NOT_FOUND,
                ErrorCategory.GOOGLE_DRIVE_FILE_ACCESS_DENIED,
            }:
                item.status = ConnectorItemStatus.UNAVAILABLE.value
                for source in sources:
                    source.status = ExpertSourceStatus.UNAVAILABLE.value
                self.db.flush()
            return "failed"

        if meta.get("trashed"):
            self.mark_item_unavailable(item, sources)
            return "updated"

        try:
            require_supported_mime(meta.get("mimeType"))
        except AppError as exc:
            self._fail_sources(sources, exc)
            return "failed"

        # Metadata-only rename / soft fields.
        item.name = str(meta.get("name") or item.name)
        item.mime_type = meta.get("mimeType")
        if meta.get("size") is not None:
            try:
                item.size_bytes = int(meta["size"])
            except (TypeError, ValueError):
                pass
        version = meta.get("version") or meta.get("md5Checksum")
        provider_modified = meta.get("modifiedTime")
        content_changed = force or (
            version is not None and str(version) != (item.external_version or "")
        ) or (item.current_document_id is None)

        provenance = safe_provenance(meta)
        if isinstance(item.extra, dict):
            item.extra = {**item.extra, **provenance}
        else:
            item.extra = provenance

        if not content_changed and item.current_document_id is not None:
            item.external_version = str(version) if version is not None else item.external_version
            item.last_seen_at = datetime.now(timezone.utc)
            self.db.flush()
            return "skipped"

        tmp_path: Path | None = None
        try:
            data, filename = fetch_file_bytes(
                client,
                meta,
                max_bytes=self.settings.max_upload_bytes,
                resource_key=resource_key,
            )
            # Stream via tempfile for large payloads / cleanup guarantee.
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)

            file_bytes = tmp_path.read_bytes()
            declared_mime = (
                "text/markdown"
                if is_google_workspace_doc(meta.get("mimeType"))
                else meta.get("mimeType")
            )
            docs = DocumentService(self.db, self.settings)
            old_document_id = item.current_document_id
            try:
                upload = docs.upload_for_workspace_or_link_existing(
                    workspace,
                    file_bytes,
                    filename,
                    title=meta.get("name"),
                    declared_mime_type=declared_mime,
                )
            except AppError as exc:
                if exc.category in {
                    ErrorCategory.STORAGE_QUOTA_EXCEEDED,
                    ErrorCategory.UPLOAD_TOO_LARGE,
                    ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
                    ErrorCategory.INVALID_DOCUMENT,
                }:
                    self._fail_sources(sources, exc)
                    return "failed"
                raise

            document = upload.document
            # Link all ExpertSources pointing at this item.
            for source in sources:
                self._link_source_document(
                    workspace=workspace,
                    source=source,
                    document_id=document.id,
                    actor_id=actor_id or source.created_by,
                    provenance=provenance,
                    connection_id=connection_id,
                    item=item,
                )

            # Only after successful upload + links.
            item.current_document_id = document.id
            item.external_version = str(version) if version is not None else item.external_version
            item.external_etag = meta.get("md5Checksum")
            item.status = ConnectorItemStatus.ACTIVE.value
            item.last_seen_at = datetime.now(timezone.utc)
            self.db.flush()

            if not upload.reused:
                _enqueue_ingest(
                    document_id=str(document.id),
                    workspace_id=str(workspace_id),
                    actor_id=str(actor_id) if actor_id else "",
                )
                for source in sources:
                    source.status = ExpertSourceStatus.PROCESSING.value
            else:
                for source in sources:
                    if document.status == "ready":
                        source.status = ExpertSourceStatus.READY.value
                    elif document.status == "failed":
                        source.status = ExpertSourceStatus.FAILED.value
                    else:
                        source.status = ExpertSourceStatus.PROCESSING.value
            self.db.flush()

            # Version swap: purge old doc if unreferenced by any Expert.
            if (
                old_document_id is not None
                and old_document_id != document.id
            ):
                self._maybe_purge_old_document(workspace, old_document_id)

            return "created" if old_document_id is None else "updated"
        except AppError as exc:
            self._fail_sources(sources, exc)
            logger.warning(
                "google_drive_ingest_item_failed error=%s detail=%s external_id=%s",
                exc.category.value,
                exc.message,
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
            # Unlink ExpertDocument for this source; keep Document if shared.
            if source.id:
                links = list(
                    self.db.scalars(
                        select(ExpertDocument).where(ExpertDocument.source_id == source.id)
                    ).all()
                )
                for link in links:
                    doc_id = link.document_id
                    self.db.delete(link)
                    self.db.flush()
                    self.experts._sync_document_membership(doc_id)
                    self.experts._reconcile_status(source.expert_id)
        self.db.flush()

    def _link_source_document(
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
        expert = self.expert_repo.get_by_id(source.expert_id)
        if expert is None:
            return
        cfg = dict(source.config or {})
        cfg.update(
            {
                "connector_key": "google_drive",
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

        # Drop stale links for this source pointing at a different document.
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

    def _maybe_purge_old_document(
        self, workspace: Workspace, document_id: uuid.UUID
    ) -> None:
        remaining = self.db.scalar(
            select(ExpertDocument.id)
            .where(ExpertDocument.document_id == document_id)
            .limit(1)
        )
        if remaining is not None:
            return
        # Also skip if another connector item still points at it.
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
                "google_drive_old_document_purge_skipped",
                extra={"document_id": str(document_id)},
            )

    def _fail_sources(self, sources: list[ExpertSource], exc: AppError) -> None:
        for source in sources:
            if exc.category in {
                ErrorCategory.GOOGLE_DRIVE_FILE_NOT_FOUND,
                ErrorCategory.GOOGLE_DRIVE_FILE_ACCESS_DENIED,
            }:
                source.status = ExpertSourceStatus.UNAVAILABLE.value
            else:
                source.status = ExpertSourceStatus.FAILED.value
            cfg = dict(source.config or {})
            cfg["last_error_code"] = exc.category.value
            cfg["last_error_message"] = exc.message
            source.config = cfg
        self.db.flush()
