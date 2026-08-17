"""Resolved external item + adapter dispatch for Expert connector sources."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.models import AppConnection
from app.core.errors import AppError, ErrorCategory


@dataclass(frozen=True, slots=True)
class ResolvedExternalItem:
    """Authoritative provider metadata after server-side revalidation."""

    external_id: str
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    external_version: str | None = None
    external_etag: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def resolve_selections_via_adapter(
    *,
    adapter: Any,
    db: Session,
    connection: AppConnection,
    credentials: dict[str, Any],
    selections: list[Any],
    settings: Any,
) -> list[ResolvedExternalItem]:
    """Ask the knowledge adapter to resolve picker selections.

    Adapters implement ``resolve_selected_items``. Google Drive keeps a
    compatibility path via ``resolve_google_drive_selections`` when missing.
    """
    resolver = getattr(adapter, "resolve_selected_items", None)
    if callable(resolver):
        return list(
            resolver(
                db=db,
                connection=connection,
                credentials=credentials,
                selections=selections,
                settings=settings,
            )
        )
    # Legacy Google-only fallback (pre-9E).
    if connection.connector_key == "google_drive":
        from app.connectors.providers.google_drive.resolve import (
            resolve_google_drive_selections,
        )

        return resolve_google_drive_selections(
            db=db,
            connection=connection,
            credentials=credentials,
            selections=selections,
            settings=settings,
        )
    raise AppError(
        ErrorCategory.CONNECTOR_NOT_SUPPORTED,
        "Connector does not support knowledge source selection.",
        details={"connector_key": connection.connector_key},
    )
