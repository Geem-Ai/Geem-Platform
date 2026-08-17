"""Resolve OneDrive picker selections against live Graph metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.connectors.credentials import ConnectorCredentialService
from app.connectors.knowledge.resolve import ResolvedExternalItem
from app.connectors.models import AppConnection
from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
from app.connectors.providers.microsoft_onedrive.formats import require_supported_mime
from app.connectors.providers.microsoft_onedrive.identity import (
    compose_external_id,
    parse_external_id,
)
from app.connectors.providers.microsoft_onedrive.ingest import safe_provenance
from app.connectors.providers.microsoft_onedrive.token import ensure_fresh_access
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def _locator_ids(selection: Any) -> tuple[str, str]:
    locator = getattr(selection, "provider_locator", None) or {}
    if not isinstance(locator, dict):
        locator = {}
    drive_id = (locator.get("drive_id") or "").strip()
    item_id = (locator.get("item_id") or "").strip()
    if drive_id and item_id:
        return drive_id, item_id
    external_id = (getattr(selection, "external_id", None) or "").strip()
    if external_id:
        return parse_external_id(external_id)
    raise AppError(
        ErrorCategory.VALIDATION,
        "OneDrive selections require drive_id and item_id.",
    )


def resolve_microsoft_onedrive_selections(
    *,
    db: Session,
    connection: AppConnection,
    credentials: dict[str, Any],
    selections: list[Any],
    settings: Settings,
) -> list[ResolvedExternalItem]:
    credentials = ensure_fresh_access(db, connection, credentials, settings)
    sync_state = ConnectorCredentialService(db, settings=settings).get_sync_state(
        connection
    ) or {}
    connected_drive_id = str(
        sync_state.get("drive_id")
        or credentials.get("drive_id")
        or ""
    ).strip()

    tenant = str(credentials.get("tenant_id") or settings.microsoft_onedrive_tenant)
    client = MicrosoftOneDriveClient(
        settings=settings,
        access_token=str(credentials["access_token"]),
        tenant=tenant,
    )
    resolved: list[ResolvedExternalItem] = []
    try:
        for selection in selections:
            drive_id, item_id = _locator_ids(selection)
            if connected_drive_id and drive_id != connected_drive_id:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
                    "Selected file is not from the connected OneDrive.",
                    details={"drive_id": drive_id},
                )
            meta = client.get_item(drive_id=drive_id, item_id=item_id)
            if meta.get("folder") is not None and meta.get("file") is None:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_FILE_TYPE_UNSUPPORTED,
                    "OneDrive folders are not supported.",
                )
            parent = (
                meta.get("parentReference")
                if isinstance(meta.get("parentReference"), dict)
                else {}
            )
            drive_type = str(parent.get("driveType") or "").lower()
            if drive_type in {"documentlibrary", "document_library"}:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
                    "SharePoint document libraries are not supported.",
                )
            # Ignore frontend-supplied name/mime — Graph is authoritative.
            file_facet = meta.get("file") if isinstance(meta.get("file"), dict) else {}
            mime = require_supported_mime(
                file_facet.get("mimeType") or meta.get("mimeType"),
                name=meta.get("name"),
            )
            external_id = compose_external_id(drive_id, item_id)
            provenance = safe_provenance(meta, drive_id=drive_id, item_id=item_id)
            size_bytes = None
            if meta.get("size") is not None:
                try:
                    size_bytes = int(meta["size"])
                except (TypeError, ValueError):
                    pass
            version = meta.get("cTag") or meta.get("eTag")
            resolved.append(
                ResolvedExternalItem(
                    external_id=external_id,
                    name=str(meta.get("name") or item_id),
                    mime_type=mime,
                    size_bytes=size_bytes,
                    external_version=str(version) if version else None,
                    external_etag=meta.get("eTag"),
                    provenance=provenance,
                    extra={"drive_id": drive_id, "item_id": item_id},
                )
            )
    finally:
        client.close()
    return resolved
