"""Expert knowledge sources backed by connectors (Phase 9D)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.items import ConnectorItemService
from app.connectors.models import AppConnection, ConnectorItem, ConnectorSyncRun
from app.connectors.providers.google_drive.client import GoogleDriveClient
from app.connectors.providers.google_drive.formats import require_supported_mime
from app.connectors.providers.google_drive.ingest import safe_provenance
from app.connectors.providers.google_drive.token import ensure_fresh_access
from app.connectors.registry import connector_registry
from app.connectors.repository import ConnectorRepository
from app.connectors.service import ConnectorConnectionService
from app.connectors.types import (
    ConnectorItemStatus,
    ConnectorItemType,
    SyncRunStatus,
    SyncTrigger,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.access import ExpertAccessService
from app.experts.models import (
    ExpertDocument,
    ExpertSource,
    ExpertSourceStatus,
    ExpertSourceType,
    ExpertType,
)
from app.experts.policy import ExpertAction
from app.experts.repository import ExpertRepository
from app.experts.service import ExpertService
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_KEY = "google_drive"


@dataclass(frozen=True, slots=True)
class ConnectorSourceSelection:
    external_id: str
    resource_key: str | None = None


@dataclass(frozen=True, slots=True)
class AddConnectorSourcesResult:
    sources: list[ExpertSource]
    sync_run_id: uuid.UUID | None
    status: str


class ExpertConnectorSourceService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = ExpertRepository(db)
        self.access = ExpertAccessService(db)
        self.connections = ConnectorConnectionService(db)
        self.cred = ConnectorCredentialService(db, settings=self.settings)
        self.items = ConnectorItemService(db)
        self.conn_repo = ConnectorRepository(db)
        self.app_access = AppAccessService(db)
        self.experts = ExpertService(db, self.settings)

    def add_connector_sources(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        connection_id: uuid.UUID,
        items: list[ConnectorSourceSelection],
        enqueue: bool = True,
    ) -> AddConnectorSourcesResult:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        expert = auth.expert
        if expert.type != ExpertType.WORKSPACE.value:
            raise AppError(
                ErrorCategory.EXPERT_IMMUTABLE,
                "Platform Experts cannot attach connector sources via Workspace APIs.",
            )
        if not items:
            raise AppError(ErrorCategory.VALIDATION, "At least one item is required.")

        row, app, _inst = self.connections.require_usable_connection(
            workspace.id, connection_id
        )
        if row.connector_key != GOOGLE_DRIVE_KEY:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Only Google Drive connections are supported for connector sources.",
                details={"connector_key": row.connector_key},
            )
        if not connector_registry.is_available(GOOGLE_DRIVE_KEY):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "Google Drive connector is not available.",
            )
        self.app_access.require_active(workspace.id, app_slug=app.slug)

        credentials = self.cred.get_credentials(row)
        if not credentials:
            raise AppError(
                ErrorCategory.CONNECTOR_CREDENTIALS_INVALID,
                "Connection credentials are missing.",
            )
        credentials = ensure_fresh_access(self.db, row, credentials, self.settings)

        client = GoogleDriveClient(
            settings=self.settings, access_token=str(credentials["access_token"])
        )
        created_sources: list[ExpertSource] = []
        try:
            for selection in items:
                external_id = (selection.external_id or "").strip()
                if not external_id:
                    raise AppError(
                        ErrorCategory.VALIDATION, "external_id is required."
                    )
                meta = client.get_file_metadata(
                    external_id, resource_key=selection.resource_key
                )
                require_supported_mime(meta.get("mimeType"))
                provenance = safe_provenance(meta)
                if selection.resource_key:
                    provenance["resourceKey"] = selection.resource_key
                elif meta.get("resourceKey"):
                    provenance["resourceKey"] = meta["resourceKey"]

                item = self.items.upsert_item(
                    workspace_id=workspace.id,
                    connection_id=row.id,
                    external_id=external_id,
                    name=str(meta.get("name") or external_id),
                    item_type=ConnectorItemType.FILE.value,
                    mime_type=meta.get("mimeType"),
                    size_bytes=int(meta["size"]) if str(meta.get("size") or "").isdigit() else None,
                    external_version=str(meta.get("version") or meta.get("md5Checksum") or "")
                    or None,
                    external_etag=meta.get("md5Checksum"),
                    metadata=provenance,
                    status=ConnectorItemStatus.ACTIVE.value,
                )

                existing = self._find_source_for_item(expert.id, item.id)
                if existing is not None:
                    # Revive sources left unavailable/failed after disconnect or errors.
                    if existing.status in {
                        ExpertSourceStatus.UNAVAILABLE.value,
                        ExpertSourceStatus.FAILED.value,
                        ExpertSourceStatus.DISABLED.value,
                    }:
                        existing.status = ExpertSourceStatus.PENDING.value
                        existing.name = item.name
                        cfg = dict(existing.config or {})
                        cfg.update(
                            {
                                "connector_key": GOOGLE_DRIVE_KEY,
                                "connection_id": str(row.id),
                                "connector_item_id": str(item.id),
                                "external_id": external_id,
                                "provenance": provenance,
                            }
                        )
                        existing.config = cfg
                        # Force re-ingest: disconnect cleared Expert membership but may
                        # have left a stale document pointer on the ConnectorItem.
                        item.current_document_id = None
                        item.status = ConnectorItemStatus.ACTIVE.value
                        item.deleted_at_provider = None
                    created_sources.append(existing)
                    continue

                source = ExpertSource(
                    expert_id=expert.id,
                    type=ExpertSourceType.CONNECTOR.value,
                    name=item.name,
                    status=ExpertSourceStatus.PENDING.value,
                    config={
                        "connector_key": GOOGLE_DRIVE_KEY,
                        "connection_id": str(row.id),
                        "connector_item_id": str(item.id),
                        "external_id": external_id,
                        "provenance": provenance,
                    },
                    created_by=actor.id,
                )
                self.repo.create_source(source)
                created_sources.append(source)
        finally:
            client.close()

        sync_run_id: uuid.UUID | None = None
        status = ExpertSourceStatus.PROCESSING.value
        for source in created_sources:
            if source.status == ExpertSourceStatus.PENDING.value:
                source.status = ExpertSourceStatus.PROCESSING.value

        # Create initial sync run (coalesce if one already active).
        # Always enqueue *after commit* — workers racing an open transaction
        # leave runs stuck in pending (sync_run_not_found) and block future syncs.
        from app.connectors.enqueue import enqueue_connector_sync_after_commit

        if self.conn_repo.has_active_sync(row.id):
            active = self.db.execute(
                select(ConnectorSyncRun)
                .where(
                    ConnectorSyncRun.app_connection_id == row.id,
                    ConnectorSyncRun.status.in_(
                        [SyncRunStatus.PENDING.value, SyncRunStatus.RUNNING.value]
                    ),
                )
                .order_by(ConnectorSyncRun.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            sync_run_id = active.id if active else None
            # Re-enqueue stuck/pending runs so a prior pre-commit race can recover.
            if (
                enqueue
                and active is not None
                and active.status == SyncRunStatus.PENDING.value
            ):
                enqueue_connector_sync_after_commit(
                    self.db,
                    workspace_id=workspace.id,
                    connection_id=row.id,
                    sync_run_id=active.id,
                    actor_id=actor.id,
                )
        else:
            run = ConnectorSyncRun(
                workspace_id=workspace.id,
                app_connection_id=row.id,
                trigger=SyncTrigger.INITIAL.value,
                status=SyncRunStatus.PENDING.value,
                created_by_user_id=actor.id,
            )
            self.conn_repo.add_sync_run(run)
            sync_run_id = run.id
            self.db.flush()
            if enqueue:
                enqueue_connector_sync_after_commit(
                    self.db,
                    workspace_id=workspace.id,
                    connection_id=row.id,
                    sync_run_id=run.id,
                    actor_id=actor.id,
                )

        self.db.flush()
        return AddConnectorSourcesResult(
            sources=created_sources,
            sync_run_id=sync_run_id,
            status=status,
        )

    def remove_connector_source(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> None:
        """Soft-delete connector source and unlink its ExpertDocument membership."""
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        source = self.repo.get_source(auth.expert.id, source_id)
        if source is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Expert source not found.")
        if source.type != ExpertSourceType.CONNECTOR.value:
            # Fall back to generic soft-delete.
            self.experts.soft_delete_source(
                workspace=workspace,
                membership=membership,
                actor=actor,
                expert_id=expert_id,
                source_id=source_id,
            )
            return

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
        cfg = source.config if isinstance(source.config, dict) else {}
        item_id_raw = cfg.get("connector_item_id")
        source.soft_delete()
        self.db.flush()
        if item_id_raw:
            try:
                item_uuid = uuid.UUID(str(item_id_raw))
            except ValueError:
                item_uuid = None
            if item_uuid is not None:
                item = self.db.get(ConnectorItem, item_uuid)
                if item is not None and not self._item_has_active_expert_link(item_uuid):
                    item.current_document_id = None
                    self.db.flush()
        self.experts._reconcile_status(auth.expert.id)

    def mark_sources_unavailable_for_connection(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> int:
        """Mark ExpertSources bound to a connection as unavailable (on disconnect)."""
        conn_str = str(connection_id)
        rows = list(
            self.db.scalars(
                select(ExpertSource).where(
                    ExpertSource.type == ExpertSourceType.CONNECTOR.value,
                    ExpertSource.deleted_at.is_(None),
                )
            ).all()
        )
        count = 0
        for source in rows:
            cfg = source.config if isinstance(source.config, dict) else {}
            if str(cfg.get("connection_id") or "") != conn_str:
                continue
            # Ensure source belongs to an expert in this workspace.
            expert = self.repo.get_by_id(source.expert_id)
            if expert is None or expert.workspace_id != workspace_id:
                continue
            source.status = ExpertSourceStatus.UNAVAILABLE.value
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
            # Clear shared item document pointer when no active Expert still links it
            # via a connector source for this connection.
            item_id_raw = cfg.get("connector_item_id")
            if item_id_raw:
                try:
                    item_uuid = uuid.UUID(str(item_id_raw))
                except ValueError:
                    item_uuid = None
                if item_uuid is not None:
                    item = self.db.get(ConnectorItem, item_uuid)
                    if (
                        item is not None
                        and item.app_connection_id == connection_id
                        and not self._item_has_active_expert_link(item_uuid)
                    ):
                        item.current_document_id = None
            self.experts._reconcile_status(source.expert_id)
            count += 1
        self.db.flush()
        return count

    def _item_has_active_expert_link(self, item_id: uuid.UUID) -> bool:
        """True if any non-deleted, usable connector source still points at the item."""
        item_str = str(item_id)
        rows = list(
            self.db.scalars(
                select(ExpertSource).where(
                    ExpertSource.type == ExpertSourceType.CONNECTOR.value,
                    ExpertSource.deleted_at.is_(None),
                    ExpertSource.status.notin_(
                        [
                            ExpertSourceStatus.UNAVAILABLE.value,
                            ExpertSourceStatus.DISABLED.value,
                        ]
                    ),
                )
            ).all()
        )
        for source in rows:
            cfg = source.config if isinstance(source.config, dict) else {}
            if str(cfg.get("connector_item_id") or "") == item_str:
                return True
        return False

    def _find_source_for_item(
        self, expert_id: uuid.UUID, item_id: uuid.UUID
    ) -> ExpertSource | None:
        item_str = str(item_id)
        for source in self.repo.list_sources(expert_id):
            if source.type != ExpertSourceType.CONNECTOR.value:
                continue
            cfg = source.config if isinstance(source.config, dict) else {}
            if str(cfg.get("connector_item_id") or "") == item_str:
                return source
        return None
