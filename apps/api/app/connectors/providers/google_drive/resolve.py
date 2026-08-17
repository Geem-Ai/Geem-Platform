"""Resolve Google Drive picker selections against live Drive metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.connectors.knowledge.resolve import ResolvedExternalItem
from app.connectors.models import AppConnection
from app.connectors.providers.google_drive.client import GoogleDriveClient
from app.connectors.providers.google_drive.formats import require_supported_mime
from app.connectors.providers.google_drive.ingest import safe_provenance
from app.connectors.providers.google_drive.token import ensure_fresh_access
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def resolve_google_drive_selections(
    *,
    db: Session,
    connection: AppConnection,
    credentials: dict[str, Any],
    selections: list[Any],
    settings: Settings,
) -> list[ResolvedExternalItem]:
    credentials = ensure_fresh_access(db, connection, credentials, settings)
    client = GoogleDriveClient(
        settings=settings, access_token=str(credentials["access_token"])
    )
    resolved: list[ResolvedExternalItem] = []
    try:
        for selection in selections:
            external_id = (getattr(selection, "external_id", None) or "").strip()
            if not external_id:
                raise AppError(
                    ErrorCategory.VALIDATION, "external_id is required."
                )
            resource_key = getattr(selection, "resource_key", None)
            meta = client.get_file_metadata(external_id, resource_key=resource_key)
            require_supported_mime(meta.get("mimeType"))
            provenance = safe_provenance(meta)
            if resource_key:
                provenance["resourceKey"] = resource_key
            elif meta.get("resourceKey"):
                provenance["resourceKey"] = meta["resourceKey"]
            size_bytes = None
            if str(meta.get("size") or "").isdigit():
                size_bytes = int(meta["size"])
            resolved.append(
                ResolvedExternalItem(
                    external_id=external_id,
                    name=str(meta.get("name") or external_id),
                    mime_type=meta.get("mimeType"),
                    size_bytes=size_bytes,
                    external_version=str(
                        meta.get("version") or meta.get("md5Checksum") or ""
                    )
                    or None,
                    external_etag=meta.get("md5Checksum"),
                    provenance=provenance,
                    extra={"resourceKey": provenance.get("resourceKey")}
                    if provenance.get("resourceKey")
                    else {},
                )
            )
    finally:
        client.close()
    return resolved
