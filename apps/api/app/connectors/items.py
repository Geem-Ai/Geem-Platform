"""Connector item helpers (Phase 9C) — external resource mapping for 9D/9E."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.models import ConnectorItem
from app.connectors.repository import ConnectorRepository
from app.connectors.types import ConnectorItemStatus, ConnectorItemType
from app.core.errors import AppError, ErrorCategory


class ConnectorItemService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ConnectorRepository(db)

    def upsert_item(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        external_id: str,
        name: str,
        item_type: str = ConnectorItemType.FILE.value,
        parent_external_id: str | None = None,
        path: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        external_version: str | None = None,
        external_etag: str | None = None,
        provider_modified_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        current_document_id: uuid.UUID | None = None,
        status: str = ConnectorItemStatus.ACTIVE.value,
    ) -> ConnectorItem:
        if metadata and any(
            k in metadata
            for k in ("access_token", "refresh_token", "credentials", "api_key")
        ):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Connector item metadata must not contain secrets.",
            )

        existing = self.repo.get_item_by_external(
            workspace_id, connection_id, external_id
        )
        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.name = name
            existing.item_type = item_type
            existing.parent_external_id = parent_external_id
            existing.path = path
            existing.mime_type = mime_type
            existing.size_bytes = size_bytes
            existing.external_version = external_version
            existing.external_etag = external_etag
            existing.provider_modified_at = provider_modified_at
            if metadata is not None:
                existing.extra = metadata
            if current_document_id is not None:
                existing.current_document_id = current_document_id
            existing.status = status
            existing.last_seen_at = now
            if status == ConnectorItemStatus.DELETED.value:
                existing.deleted_at_provider = now
            self.db.flush()
            return existing

        row = ConnectorItem(
            workspace_id=workspace_id,
            app_connection_id=connection_id,
            external_id=external_id,
            parent_external_id=parent_external_id,
            item_type=item_type,
            name=name,
            path=path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            external_version=external_version,
            external_etag=external_etag,
            provider_modified_at=provider_modified_at,
            status=status,
            current_document_id=current_document_id,
            extra=metadata or {},
            last_seen_at=now,
        )
        try:
            return self.repo.add_item(row)
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                ErrorCategory.CONFLICT,
                "Connector item already exists for this external id.",
                details={"external_id": external_id},
            ) from exc

    def mark_deleted_at_provider(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        external_id: str,
    ) -> ConnectorItem | None:
        row = self.repo.get_item_by_external(workspace_id, connection_id, external_id)
        if row is None:
            return None
        row.status = ConnectorItemStatus.DELETED.value
        row.deleted_at_provider = datetime.now(timezone.utc)
        self.db.flush()
        return row
