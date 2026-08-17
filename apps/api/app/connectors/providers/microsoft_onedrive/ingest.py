"""Bridge Microsoft OneDrive content into Geem Documents (Phase 9E)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.knowledge.ingest import KnowledgeIngestBridge
from app.connectors.models import ConnectorItem
from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
from app.connectors.providers.microsoft_onedrive.formats import (
    MIME_PDF,
    needs_pdf_conversion,
    require_supported_mime,
    suggested_filename,
)
from app.connectors.providers.microsoft_onedrive.identity import parse_external_id
from app.connectors.types import ConnectorItemStatus
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertSource, ExpertSourceStatus

logger = logging.getLogger(__name__)

_SAFE_PROVENANCE_KEYS = frozenset(
    {
        "webUrl",
        "mimeType",
        "lastModifiedDateTime",
        "size",
        "name",
        "eTag",
        "cTag",
        "driveId",
        "itemId",
        "driveType",
    }
)


def safe_provenance(meta: dict[str, Any], *, drive_id: str, item_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "driveId": drive_id,
        "itemId": item_id,
    }
    file_facet = meta.get("file") if isinstance(meta.get("file"), dict) else {}
    mime = file_facet.get("mimeType") or meta.get("mimeType")
    if mime:
        out["mimeType"] = mime
    for key in _SAFE_PROVENANCE_KEYS:
        if key in {"mimeType", "driveId", "itemId"}:
            continue
        if key in meta and meta[key] is not None:
            out[key] = meta[key]
    parent = meta.get("parentReference")
    if isinstance(parent, dict) and parent.get("driveType"):
        out["driveType"] = parent["driveType"]
    # Never persist @microsoft.graph.downloadUrl or similar secrets.
    return out


def content_version_from_meta(meta: dict[str, Any]) -> str | None:
    for key in ("cTag", "eTag"):
        val = meta.get(key)
        if val:
            return str(val)
    modified = meta.get("lastModifiedDateTime")
    size = meta.get("size")
    if modified or size is not None:
        return f"{modified or ''}:{size if size is not None else ''}"
    return None


class MicrosoftOneDriveIngestBridge:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        connected_drive_id: str | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.connected_drive_id = connected_drive_id
        self.bridge = KnowledgeIngestBridge(
            db,
            connector_key="microsoft_onedrive",
            settings=self.settings,
            not_found_errors=frozenset(
                {ErrorCategory.MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND}
            ),
            access_denied_errors=frozenset(
                {ErrorCategory.MICROSOFT_ONEDRIVE_ACCESS_DENIED}
            ),
        )

    def sources_for_item(self, item: ConnectorItem) -> list[ExpertSource]:
        return self.bridge.sources_for_item(item)

    def mark_item_unavailable(
        self, item: ConnectorItem, sources: list[ExpertSource] | None = None
    ) -> None:
        self.bridge.mark_item_unavailable(item, sources)

    def ingest_tracked_item(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        item: ConnectorItem,
        client: MicrosoftOneDriveClient,
        actor_id: uuid.UUID | None = None,
        force: bool = False,
    ) -> str:
        sources = self.bridge.sources_for_item(item)
        if not sources and not force:
            return "skipped"

        try:
            drive_id, item_id = parse_external_id(item.external_id)
        except AppError as exc:
            self.bridge.fail_sources(sources, exc)
            return "failed"

        if self.connected_drive_id and drive_id != self.connected_drive_id:
            exc = AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
                "OneDrive item is not from the connected drive.",
            )
            self.bridge.fail_sources(sources, exc)
            return "failed"

        try:
            meta = client.get_item(drive_id=drive_id, item_id=item_id)
        except AppError as exc:
            self.bridge.fail_sources(sources, exc)
            if exc.category in {
                ErrorCategory.MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND,
                ErrorCategory.MICROSOFT_ONEDRIVE_ACCESS_DENIED,
            }:
                item.status = ConnectorItemStatus.UNAVAILABLE.value
                for source in sources:
                    source.status = ExpertSourceStatus.UNAVAILABLE.value
                self.db.flush()
            return "failed"

        if meta.get("deleted") is not None:
            self.mark_item_unavailable(item, sources)
            return "updated"

        if meta.get("folder") is not None and meta.get("file") is None:
            exc = AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_FILE_TYPE_UNSUPPORTED,
                "OneDrive folders are not supported as knowledge sources.",
            )
            self.bridge.fail_sources(sources, exc)
            return "failed"

        parent = meta.get("parentReference") if isinstance(meta.get("parentReference"), dict) else {}
        drive_type = str(parent.get("driveType") or "").lower()
        if drive_type and drive_type not in {"personal", "business", "onedrive", ""}:
            # documentLibrary / SharePoint libraries are out of 9E scope.
            if drive_type in {"documentlibrary", "document_library"}:
                exc = AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
                    "SharePoint document libraries are not supported in OneDrive connector.",
                )
                self.bridge.fail_sources(sources, exc)
                return "failed"

        file_facet = meta.get("file") if isinstance(meta.get("file"), dict) else {}
        try:
            mime = require_supported_mime(
                file_facet.get("mimeType") or meta.get("mimeType"),
                name=meta.get("name"),
            )
        except AppError as exc:
            self.bridge.fail_sources(sources, exc)
            return "failed"

        item.name = str(meta.get("name") or item.name)
        item.mime_type = mime
        if meta.get("size") is not None:
            try:
                item.size_bytes = int(meta["size"])
            except (TypeError, ValueError):
                pass

        provenance = safe_provenance(meta, drive_id=drive_id, item_id=item_id)
        version = content_version_from_meta(meta)

        content_changed = force or (
            version is not None and str(version) != (item.external_version or "")
        ) or (item.current_document_id is None)

        if isinstance(item.extra, dict):
            item.extra = {**item.extra, **provenance}
        else:
            item.extra = provenance

        if not content_changed and item.current_document_id is not None:
            item.external_version = str(version) if version is not None else item.external_version
            item.last_seen_at = datetime.now(timezone.utc)
            self.db.flush()
            return "skipped"

        try:
            if needs_pdf_conversion(mime):
                try:
                    data = client.convert_content_to_pdf(
                        drive_id=drive_id,
                        item_id=item_id,
                        max_bytes=self.settings.max_upload_bytes,
                    )
                except AppError as exc:
                    if exc.category not in {
                        ErrorCategory.MICROSOFT_ONEDRIVE_RATE_LIMITED,
                        ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                        ErrorCategory.MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND,
                        ErrorCategory.MICROSOFT_ONEDRIVE_ACCESS_DENIED,
                    }:
                        raise AppError(
                            ErrorCategory.MICROSOFT_ONEDRIVE_CONVERSION_FAILED,
                            "OneDrive Office-to-PDF conversion failed.",
                        ) from exc
                    raise
                filename = suggested_filename(meta.get("name"), MIME_PDF)
                declared_mime = MIME_PDF
            else:
                size_raw = meta.get("size")
                if size_raw is not None:
                    try:
                        if int(size_raw) > self.settings.max_upload_bytes:
                            raise AppError(
                                ErrorCategory.UPLOAD_TOO_LARGE,
                                "OneDrive file exceeds maximum upload size.",
                                details={
                                    "max_bytes": self.settings.max_upload_bytes,
                                    "size": int(size_raw),
                                },
                            )
                    except (TypeError, ValueError):
                        pass
                data = client.download_content(
                    drive_id=drive_id,
                    item_id=item_id,
                    max_bytes=self.settings.max_upload_bytes,
                )
                filename = suggested_filename(meta.get("name"), mime)
                declared_mime = mime
        except AppError as exc:
            self.bridge.fail_sources(sources, exc)
            return "failed"

        return self.bridge.ingest_bytes(
            workspace_id=workspace_id,
            connection_id=connection_id,
            item=item,
            file_bytes=data,
            filename=filename,
            declared_mime_type=declared_mime,
            provenance=provenance,
            content_version=version,
            content_etag=meta.get("eTag"),
            actor_id=actor_id,
            force=True,  # content already determined changed
            sources=sources,
        )
