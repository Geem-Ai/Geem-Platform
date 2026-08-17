"""Connector repository — always Workspace-scoped."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.connectors.models import (
    AppConnection,
    ConnectorItem,
    ConnectorSyncRun,
    ConnectorWebhookEvent,
)
from app.connectors.types import CONNECTION_LIMIT_STATUSES, SyncRunStatus


def hash_routing_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_routing_token() -> str:
    return secrets.token_urlsafe(32)


class ConnectorRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- connections ---

    def get_connection(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AppConnection | None:
        stmt = select(AppConnection).where(
            AppConnection.workspace_id == workspace_id,
            AppConnection.id == connection_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def list_connections(
        self,
        workspace_id: uuid.UUID,
        *,
        app_installation_id: uuid.UUID | None = None,
        connector_key: str | None = None,
        statuses: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AppConnection], int]:
        filters = [AppConnection.workspace_id == workspace_id]
        if app_installation_id is not None:
            filters.append(AppConnection.app_installation_id == app_installation_id)
        if connector_key is not None:
            filters.append(AppConnection.connector_key == connector_key)
        if statuses is not None:
            filters.append(AppConnection.status.in_(statuses))

        total = self.db.execute(
            select(func.count()).select_from(AppConnection).where(*filters)
        ).scalar_one()
        rows = list(
            self.db.execute(
                select(AppConnection)
                .where(*filters)
                .order_by(AppConnection.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).scalars()
        )
        return rows, int(total)

    def count_limit_connections(
        self,
        workspace_id: uuid.UUID,
        *,
        app_installation_id: uuid.UUID,
    ) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(AppConnection)
                .where(
                    AppConnection.workspace_id == workspace_id,
                    AppConnection.app_installation_id == app_installation_id,
                    AppConnection.status.in_(list(CONNECTION_LIMIT_STATUSES)),
                )
            ).scalar_one()
        )

    def add_connection(self, row: AppConnection) -> AppConnection:
        self.db.add(row)
        self.db.flush()
        return row

    def get_by_routing_token_hash(self, token_hash: str) -> AppConnection | None:
        return self.db.execute(
            select(AppConnection).where(
                AppConnection.webhook_routing_token_hash == token_hash
            )
        ).scalar_one_or_none()

    # --- sync runs ---

    def get_sync_run(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> ConnectorSyncRun | None:
        return self.db.execute(
            select(ConnectorSyncRun).where(
                ConnectorSyncRun.workspace_id == workspace_id,
                ConnectorSyncRun.app_connection_id == connection_id,
                ConnectorSyncRun.id == run_id,
            )
        ).scalar_one_or_none()

    def get_sync_run_by_idempotency(
        self,
        connection_id: uuid.UUID,
        idempotency_key: str,
    ) -> ConnectorSyncRun | None:
        return self.db.execute(
            select(ConnectorSyncRun).where(
                ConnectorSyncRun.app_connection_id == connection_id,
                ConnectorSyncRun.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()

    def list_sync_runs(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ConnectorSyncRun], int]:
        filters = [
            ConnectorSyncRun.workspace_id == workspace_id,
            ConnectorSyncRun.app_connection_id == connection_id,
        ]
        total = self.db.execute(
            select(func.count()).select_from(ConnectorSyncRun).where(*filters)
        ).scalar_one()
        rows = list(
            self.db.execute(
                select(ConnectorSyncRun)
                .where(*filters)
                .order_by(ConnectorSyncRun.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).scalars()
        )
        return rows, int(total)

    def add_sync_run(self, row: ConnectorSyncRun) -> ConnectorSyncRun:
        self.db.add(row)
        self.db.flush()
        return row

    def has_active_sync(self, connection_id: uuid.UUID) -> bool:
        row = self.db.execute(
            select(ConnectorSyncRun.id)
            .where(
                ConnectorSyncRun.app_connection_id == connection_id,
                ConnectorSyncRun.status.in_(
                    [SyncRunStatus.PENDING.value, SyncRunStatus.RUNNING.value]
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        return row is not None

    # --- items ---

    def get_item_by_external(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        external_id: str,
    ) -> ConnectorItem | None:
        return self.db.execute(
            select(ConnectorItem).where(
                ConnectorItem.workspace_id == workspace_id,
                ConnectorItem.app_connection_id == connection_id,
                ConnectorItem.external_id == external_id,
            )
        ).scalar_one_or_none()

    def add_item(self, row: ConnectorItem) -> ConnectorItem:
        self.db.add(row)
        self.db.flush()
        return row

    # --- webhooks ---

    def get_webhook_by_provider_event(
        self,
        connection_id: uuid.UUID,
        provider_event_id: str,
    ) -> ConnectorWebhookEvent | None:
        return self.db.execute(
            select(ConnectorWebhookEvent).where(
                ConnectorWebhookEvent.app_connection_id == connection_id,
                ConnectorWebhookEvent.provider_event_id == provider_event_id,
            )
        ).scalar_one_or_none()

    def get_webhook_by_idempotency(
        self,
        connection_id: uuid.UUID,
        idempotency_key: str,
    ) -> ConnectorWebhookEvent | None:
        return self.db.execute(
            select(ConnectorWebhookEvent).where(
                ConnectorWebhookEvent.app_connection_id == connection_id,
                ConnectorWebhookEvent.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()

    def add_webhook_event(self, row: ConnectorWebhookEvent) -> ConnectorWebhookEvent:
        self.db.add(row)
        self.db.flush()
        return row
