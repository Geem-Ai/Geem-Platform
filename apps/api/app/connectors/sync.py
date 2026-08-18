"""Connector sync-run orchestration (Phase 9C)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.policy import can_connect_apps, can_manage_apps
from app.apps_catalog.repository import AppCatalogRepository
from app.common.security_log import security_log
from app.connectors.adapters import KnowledgeSourceConnectorAdapter, SyncResult
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.locks import connection_sync_lock
from app.connectors.models import AppConnection, ConnectorSyncRun
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.repository import ConnectorRepository
from app.connectors.sanitize import sanitize_error_message
from app.connectors.schemas import (
    ConnectorSyncRunListOut,
    ConnectorSyncRunOut,
    to_sync_run_out,
)
from app.connectors.service import ConnectorConnectionService
from app.connectors.types import SyncRunStatus, SyncTrigger
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)


class ConnectorSyncService:
    def __init__(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or connector_registry
        self.repo = ConnectorRepository(db)
        self.catalog = AppCatalogRepository(db)
        self.access = AppAccessService(db)
        self.connections = ConnectorConnectionService(db, registry=self.registry)
        self.credentials = ConnectorCredentialService(db)

    def list_sync_runs(
        self,
        *,
        workspace: Workspace,
        membership,
        app_slug: str,
        connection_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorSyncRunListOut:
        _ = membership
        self._require_owned_connection(workspace.id, app_slug, connection_id)
        self.access.require_active(workspace.id, app_slug=app_slug)
        rows, total = self.repo.list_sync_runs(
            workspace.id, connection_id, limit=limit, offset=offset
        )
        return ConnectorSyncRunListOut(
            items=[to_sync_run_out(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_sync_run(
        self,
        *,
        workspace: Workspace,
        membership,
        app_slug: str,
        connection_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> ConnectorSyncRunOut:
        _ = membership
        self._require_owned_connection(workspace.id, app_slug, connection_id)
        self.access.require_active(workspace.id, app_slug=app_slug)
        run = self.repo.get_sync_run(workspace.id, connection_id, run_id)
        if run is None:
            raise AppError(ErrorCategory.CONNECTOR_SYNC_NOT_FOUND, "Sync run not found.")
        return to_sync_run_out(run)

    def request_manual_sync(
        self,
        *,
        workspace: Workspace,
        membership,
        actor_id: uuid.UUID,
        app_slug: str,
        connection_id: uuid.UUID,
        idempotency_key: str | None = None,
        enqueue: bool = True,
    ) -> ConnectorSyncRunOut:
        if not can_connect_apps(membership):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Only owners and admins can request sync.",
            )
        row, app, _inst = self.connections.require_usable_connection(
            workspace.id, connection_id, app_slug=app_slug
        )
        if not self.registry.is_available(row.connector_key):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "Connector adapter is not available.",
                details={"connector_key": row.connector_key},
            )
        caps = self.registry.capabilities(row.connector_key)
        if not caps or not caps.supports_sync:
            raise AppError(
                ErrorCategory.CONNECTOR_SYNC_NOT_SUPPORTED,
                "This connector does not support sync.",
            )

        connection_sync_lock(self.db, row.id)

        if idempotency_key:
            existing = self.repo.get_sync_run_by_idempotency(row.id, idempotency_key)
            if existing is not None:
                return to_sync_run_out(existing)

        if self.repo.has_active_sync(row.id):
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
            # Recover stuck pending runs (e.g. pre-commit enqueue race) by
            # re-queueing instead of hard-failing "already in progress".
            if (
                active is not None
                and active.status == SyncRunStatus.PENDING.value
                and enqueue
            ):
                from app.connectors.enqueue import enqueue_connector_sync_after_commit

                enqueue_connector_sync_after_commit(
                    self.db,
                    workspace_id=workspace.id,
                    connection_id=row.id,
                    sync_run_id=active.id,
                    actor_id=actor_id,
                )
                return to_sync_run_out(active)
            raise AppError(
                ErrorCategory.CONNECTOR_SYNC_IN_PROGRESS,
                "A sync is already in progress for this connection.",
            )

        run = ConnectorSyncRun(
            workspace_id=workspace.id,
            app_connection_id=row.id,
            trigger=SyncTrigger.MANUAL.value,
            status=SyncRunStatus.PENDING.value,
            idempotency_key=idempotency_key,
            created_by_user_id=actor_id,
        )
        self.repo.add_sync_run(run)
        security_log(
            "app.connection.sync_requested",
            workspace_id=str(workspace.id),
            actor_id=str(actor_id),
            app_id=str(app.id),
            installation_id=str(row.app_installation_id),
            connection_id=str(row.id),
            sync_run_id=str(run.id),
        )
        logger.info(
            "connector_sync_started",
            extra={
                "workspace_id": str(workspace.id),
                "connection_id": str(row.id),
                "sync_run_id": str(run.id),
            },
        )
        self.db.flush()
        if enqueue:
            from app.connectors.enqueue import enqueue_connector_sync_after_commit

            enqueue_connector_sync_after_commit(
                self.db,
                workspace_id=workspace.id,
                connection_id=row.id,
                sync_run_id=run.id,
                actor_id=actor_id,
            )
        return to_sync_run_out(run)

    def request_webhook_sync(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        enqueue: bool = True,
    ) -> ConnectorSyncRunOut | None:
        """Internal webhook-triggered sync — coalesces with an in-flight run."""
        try:
            row, _app, _inst = self.connections.require_usable_connection(
                workspace_id, connection_id
            )
        except AppError:
            return None
        if not self.registry.is_available(row.connector_key):
            return None
        caps = self.registry.capabilities(row.connector_key)
        if not caps or not caps.supports_sync:
            return None

        connection_sync_lock(self.db, row.id)
        if self.repo.has_active_sync(row.id):
            # Coalesce — an active sync will pick up changes.
            return None

        run = ConnectorSyncRun(
            workspace_id=workspace_id,
            app_connection_id=row.id,
            trigger=SyncTrigger.WEBHOOK.value,
            status=SyncRunStatus.PENDING.value,
            created_by_user_id=None,
        )
        self.repo.add_sync_run(run)
        self.db.flush()
        if enqueue:
            from app.connectors.enqueue import enqueue_connector_sync_after_commit

            enqueue_connector_sync_after_commit(
                self.db,
                workspace_id=workspace_id,
                connection_id=row.id,
                sync_run_id=run.id,
                actor_id=None,
            )
        return to_sync_run_out(run)

    def execute_sync_run(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        sync_run_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> ConnectorSyncRun:
        """Run inside Celery with tenant context already set by the task."""
        _ = actor_id
        connection_sync_lock(self.db, connection_id)
        run = self.repo.get_sync_run(workspace_id, connection_id, sync_run_id)
        if run is None:
            raise AppError(ErrorCategory.CONNECTOR_SYNC_NOT_FOUND, "Sync run not found.")
        if run.status not in {SyncRunStatus.PENDING.value, SyncRunStatus.RUNNING.value}:
            return run

        try:
            row, app, _inst = self.connections.require_usable_connection(
                workspace_id, connection_id
            )
            adapter = self.registry.get(row.connector_key)
            if not hasattr(adapter, "sync"):
                raise AppError(
                    ErrorCategory.CONNECTOR_SYNC_NOT_SUPPORTED,
                    "Connector does not support sync.",
                )
        except AppError as exc:
            self._fail_run_record(
                run,
                error_code=exc.category.value,
                error_message=str(exc.message),
            )
            raise

        creds = self.credentials.get_credentials(row)
        if creds is None:
            self._fail_run(
                run,
                row,
                error_code=ErrorCategory.CONNECTOR_CREDENTIALS_INVALID.value,
                error_message="Missing credentials.",
            )
            return run

        sync_state = self.credentials.get_sync_state(row)
        now = datetime.now(timezone.utc)
        run.status = SyncRunStatus.RUNNING.value
        run.started_at = now
        self.db.flush()

        try:
            result: SyncResult = adapter.sync(  # type: ignore[attr-defined]
                credentials=creds,
                sync_state=sync_state,
                connection_id=row.id,
                workspace_id=workspace_id,
                sync_run_id=run.id,
                db=self.db,
            )
        except TypeError:
            result = adapter.sync(  # type: ignore[attr-defined]
                credentials=creds,
                sync_state=sync_state,
                connection_id=row.id,
                workspace_id=workspace_id,
                sync_run_id=run.id,
            )
        except Exception as exc:  # noqa: BLE001
            # Never persist raw exception text (SQL dumps, stack traces) for users.
            code = (
                exc.category.value
                if isinstance(exc, AppError)
                else ErrorCategory.CONNECTOR_CONNECTION_FAILED.value
            )
            public_message = (
                str(exc.message)
                if isinstance(exc, AppError)
                else "Synchronization failed. Please try again."
            )
            self._fail_run(
                run,
                row,
                error_code=code,
                error_message=public_message,
            )
            logger.exception(
                "connector_sync_failed",
                extra={
                    "workspace_id": str(workspace_id),
                    "connection_id": str(connection_id),
                    "sync_run_id": str(sync_run_id),
                    "error_code": code,
                },
            )
            return run

        run.items_seen = int(result.items_seen)
        run.items_created = int(result.items_created)
        run.items_updated = int(result.items_updated)
        run.items_deleted = int(result.items_deleted)
        run.items_failed = int(result.items_failed)
        if result.sync_state is not None:
            self.credentials.set_sync_state(row, result.sync_state)
        run.completed_at = datetime.now(timezone.utc)
        if result.error_code or result.partial:
            run.status = SyncRunStatus.PARTIAL.value
            run.error_code = result.error_code
            run.error_message = sanitize_error_message(result.error_message)
        else:
            run.status = SyncRunStatus.SUCCEEDED.value
            row.last_success_at = run.completed_at
            self.connections.mark_healthy(row)
        self.db.flush()
        logger.info(
            "connector_sync_completed",
            extra={
                "workspace_id": str(workspace_id),
                "connection_id": str(connection_id),
                "sync_run_id": str(sync_run_id),
                "status": run.status,
                "app_slug": app.slug,
            },
        )
        return run

    def _require_owned_connection(
        self,
        workspace_id: uuid.UUID,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> AppConnection:
        app = self.catalog.get_app_by_slug(app_slug)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        row = self.repo.get_connection(workspace_id, connection_id)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        if app.connector_key and row.connector_key != app.connector_key:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        return row

    def _fail_run(
        self,
        run: ConnectorSyncRun,
        connection: AppConnection,
        *,
        error_code: str,
        error_message: str | None,
    ) -> None:
        self._fail_run_record(run, error_code=error_code, error_message=error_message)
        self.connections.record_error(
            connection,
            error_code=error_code,
            error_message=error_message,
            degrade=True,
        )
        self.db.flush()

    def _fail_run_record(
        self,
        run: ConnectorSyncRun,
        *,
        error_code: str,
        error_message: str | None,
    ) -> None:
        run.status = SyncRunStatus.FAILED.value
        run.error_code = error_code
        run.error_message = sanitize_error_message(error_message)
        run.completed_at = datetime.now(timezone.utc)
        self.db.flush()
