"""App Store catalog + installation services (Phase 9A/9B)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService, AppAccessStatus
from app.audit import AuditAction, AuditEntityType, record_audit
from app.apps_catalog.encryption import AppConfigEncryptionService
from app.apps_catalog.models import (
    AppBillingType,
    AppInstallation,
    AppInstallationStatus,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.policy import can_manage_apps
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.schemas import (
    AppCategoryOut,
    AppInstallationListOut,
    AppInstallationOut,
    CatalogAppListOut,
    CatalogAppOut,
    ConnectionSummaryOut,
    ConnectionUsageOut,
    to_catalog_app_out,
    to_category_out,
    to_installation_out,
)
from app.common.security_log import security_log
from app.connectors.types import CONNECTION_USABLE_STATUSES, ConnectionStatus
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace, WorkspaceKind

# Prefer attention-needed statuses when summarizing multiple connections.
_CONNECTION_STATUS_RANK: dict[str, int] = {
    ConnectionStatus.ERROR.value: 0,
    ConnectionStatus.REVOKED.value: 1,
    ConnectionStatus.CONNECTING.value: 2,
    ConnectionStatus.PENDING.value: 3,
    ConnectionStatus.DEGRADED.value: 4,
    ConnectionStatus.ACTIVE.value: 5,
    ConnectionStatus.DISCONNECTED.value: 6,
}


def _connection_status_by_installation(
    db: Session, workspace_id: uuid.UUID, installation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Return a single summary connection status per installation."""
    if not installation_ids:
        return {}
    from sqlalchemy import select

    from app.connectors.models import AppConnection

    rows = db.execute(
        select(
            AppConnection.app_installation_id,
            AppConnection.status,
        ).where(
            AppConnection.workspace_id == workspace_id,
            AppConnection.app_installation_id.in_(installation_ids),
        )
    ).all()
    chosen: dict[uuid.UUID, str] = {}
    for install_id, status in rows:
        if install_id is None or not status:
            continue
        current = chosen.get(install_id)
        if current is None:
            chosen[install_id] = status
            continue
        if _CONNECTION_STATUS_RANK.get(status, 99) < _CONNECTION_STATUS_RANK.get(
            current, 99
        ):
            chosen[install_id] = status
    return chosen


def _connection_summaries_by_installation(
    db: Session,
    workspace_id: uuid.UUID,
    installation_ids: list[uuid.UUID],
    *,
    per_installation_limit: int = 10,
) -> dict[uuid.UUID, list[ConnectionSummaryOut]]:
    """Safe connection summaries for installed-apps management (no secrets)."""
    if not installation_ids:
        return {}
    from sqlalchemy import select

    from app.connectors.models import AppConnection
    from app.connectors.types import ConnectionHealth

    rows = list(
        db.execute(
            select(AppConnection)
            .where(
                AppConnection.workspace_id == workspace_id,
                AppConnection.app_installation_id.in_(installation_ids),
            )
            .order_by(AppConnection.created_at.desc())
        ).scalars()
    )
    grouped: dict[uuid.UUID, list[ConnectionSummaryOut]] = {}
    for row in rows:
        install_id = row.app_installation_id
        if install_id is None:
            continue
        bucket = grouped.setdefault(install_id, [])
        if len(bucket) >= per_installation_limit:
            continue
        bucket.append(
            ConnectionSummaryOut(
                id=row.id,
                display_name=row.display_name,
                status=row.status,
                health=row.health or ConnectionHealth.UNKNOWN.value,
                external_account_name=row.external_account_name,
                connector_key=row.connector_key,
            )
        )
    return grouped


def _connection_usage_for_installation(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    app_slug: str,
    installation_id: uuid.UUID | None,
    commercially_entitled: bool,
) -> ConnectionUsageOut | None:
    """Return used/limit when the workspace is commercially entitled for the app."""
    if not commercially_entitled or installation_id is None:
        return None
    from app.apps_catalog.entitlements import AppEntitlementService
    from app.connectors.repository import ConnectorRepository

    used = ConnectorRepository(db).count_limit_connections(
        workspace_id, app_installation_id=installation_id
    )
    raw_limit = AppEntitlementService(db).get(
        workspace_id, app_slug=app_slug, key="connections"
    )
    limit: int | None
    try:
        limit = int(raw_limit) if raw_limit is not None else None
    except (TypeError, ValueError):
        limit = None
    return ConnectionUsageOut(used=used, limit=limit)


def _active_connection_installation_ids(
    db: Session, workspace_id: uuid.UUID, installation_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    statuses = _connection_status_by_installation(db, workspace_id, installation_ids)
    return {
        install_id
        for install_id, status in statuses.items()
        if status in CONNECTION_USABLE_STATUSES
    }


class AppCatalogService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = AppCatalogRepository(db)
        self.access = AppAccessService(db)

    def list_categories(self) -> list[AppCategoryOut]:
        return [to_category_out(c) for c in self.repo.list_active_categories()]

    def list_apps(
        self,
        *,
        workspace: Workspace,
        membership,
        category: str | None = None,
        billing_type: str | None = None,
        installed: bool | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CatalogAppListOut:
        self._require_tenant(workspace)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        manage = can_manage_apps(membership)

        items, total = self.repo.list_catalog_apps(
            category_slug=category,
            billing_type=billing_type,
            q=q,
            limit=limit if installed is None else 500,
            offset=0 if installed is not None else offset,
        )
        app_ids = [a.id for a in items]
        install_map = self.repo.map_installations_by_app_id(workspace.id, app_ids)
        license_map = self.repo.map_licenses_by_app_id(workspace.id, app_ids)
        sub_map = self.repo.map_subscriptions_by_app_id(workspace.id, app_ids)
        install_ids = [i.id for i in install_map.values() if i is not None]
        connection_statuses = _connection_status_by_installation(
            self.db,
            workspace.id,
            install_ids,
        )
        connection_summaries = _connection_summaries_by_installation(
            self.db, workspace.id, install_ids
        )

        outs: list[CatalogAppOut] = []
        for app in items:
            inst = install_map.get(app.id)
            active = (
                inst is not None and inst.status == AppInstallationStatus.ACTIVE.value
            )
            if installed is True and not active:
                continue
            if installed is False and active:
                continue
            access = self.access.resolve(
                workspace.id,
                app=app,
                can_manage=manage,
                installation=inst,
                license_row=license_map.get(app.id),
                subscription=sub_map.get(app.id),
            )
            conn_status = (
                connection_statuses.get(inst.id) if inst is not None else None
            )
            usage = _connection_usage_for_installation(
                self.db,
                workspace.id,
                app_slug=app.slug,
                installation_id=inst.id if active and inst is not None else None,
                commercially_entitled=access.commercially_entitled,
            )
            summaries = (
                connection_summaries.get(inst.id, [])
                if active and inst is not None
                else []
            )
            outs.append(
                to_catalog_app_out(
                    app,
                    installation=inst if active else None,
                    can_manage=manage,
                    include_description=False,
                    access=access,
                    has_active_connection=bool(
                        conn_status is not None
                        and conn_status in CONNECTION_USABLE_STATUSES
                    ),
                    connection_status=conn_status,
                    connection_usage=usage,
                    connections=summaries,
                )
            )

        if installed is not None:
            total = len(outs)
            outs = outs[offset : offset + limit]

        return CatalogAppListOut(items=outs, total=total, limit=limit, offset=offset)

    def get_app(
        self,
        *,
        workspace: Workspace,
        membership,
        slug: str,
    ) -> CatalogAppOut:
        self._require_tenant(workspace)
        app = self.repo.get_app_by_slug(slug)
        if app is None or app.status in {
            AppStatus.DRAFT.value,
            AppStatus.DISABLED.value,
        }:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        manage = can_manage_apps(membership)
        inst = self.repo.get_installation_by_app(workspace.id, app.id)
        active = (
            inst is not None and inst.status == AppInstallationStatus.ACTIVE.value
        )
        access = self.access.resolve(
            workspace.id, app=app, can_manage=manage, installation=inst
        )
        conn_status = None
        usage = None
        summaries: list[ConnectionSummaryOut] = []
        if inst is not None:
            conn_status = _connection_status_by_installation(
                self.db, workspace.id, [inst.id]
            ).get(inst.id)
            if active:
                usage = _connection_usage_for_installation(
                    self.db,
                    workspace.id,
                    app_slug=app.slug,
                    installation_id=inst.id,
                    commercially_entitled=access.commercially_entitled,
                )
                summaries = _connection_summaries_by_installation(
                    self.db, workspace.id, [inst.id]
                ).get(inst.id, [])
        return to_catalog_app_out(
            app,
            installation=inst if active else None,
            can_manage=manage,
            include_description=True,
            access=access,
            has_active_connection=bool(
                conn_status is not None and conn_status in CONNECTION_USABLE_STATUSES
            ),
            connection_status=conn_status,
            connection_usage=usage,
            connections=summaries,
        )

    @staticmethod
    def _require_tenant(workspace: Workspace) -> None:
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")


class AppInstallationService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = AppCatalogRepository(db)
        self.crypto = AppConfigEncryptionService(self.settings)
        self.access = AppAccessService(db)

    def list_installations(
        self,
        *,
        workspace: Workspace,
        membership,
        limit: int = 50,
        offset: int = 0,
    ) -> AppInstallationListOut:
        self._require_tenant(workspace)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        rows, total = self.repo.list_installations(
            workspace.id,
            status=AppInstallationStatus.ACTIVE.value,
            limit=limit,
            offset=offset,
        )
        manage = can_manage_apps(membership)
        connection_statuses = _connection_status_by_installation(
            self.db, workspace.id, [r.id for r in rows]
        )
        connection_summaries = _connection_summaries_by_installation(
            self.db, workspace.id, [r.id for r in rows]
        )
        items: list[AppInstallationOut] = []
        for row in rows:
            access = self.access.resolve(
                workspace.id,
                app=row.app,
                can_manage=manage,
                installation=row,
            )
            conn_status = connection_statuses.get(row.id)
            usage = _connection_usage_for_installation(
                self.db,
                workspace.id,
                app_slug=row.app.slug,
                installation_id=row.id,
                commercially_entitled=access.commercially_entitled,
            )
            items.append(
                to_installation_out(
                    row,
                    can_manage=manage,
                    access=access,
                    has_active_connection=bool(
                        conn_status is not None
                        and conn_status in CONNECTION_USABLE_STATUSES
                    ),
                    connection_status=conn_status,
                    connection_usage=usage,
                    connections=connection_summaries.get(row.id, []),
                )
            )
        return AppInstallationListOut(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_installation(
        self,
        *,
        workspace: Workspace,
        membership,
        installation_id: uuid.UUID,
    ) -> AppInstallationOut:
        self._require_tenant(workspace)
        row = self.repo.get_installation_for_workspace(workspace.id, installation_id)
        if row is None:
            raise AppError(
                ErrorCategory.APP_INSTALLATION_NOT_FOUND,
                "App installation not found.",
            )
        manage = can_manage_apps(membership)
        access = self.access.resolve(
            workspace.id, app=row.app, can_manage=manage, installation=row
        )
        conn_status = _connection_status_by_installation(
            self.db, workspace.id, [row.id]
        ).get(row.id)
        usage = _connection_usage_for_installation(
            self.db,
            workspace.id,
            app_slug=row.app.slug,
            installation_id=row.id,
            commercially_entitled=access.commercially_entitled,
        )
        summaries = _connection_summaries_by_installation(
            self.db, workspace.id, [row.id]
        ).get(row.id, [])
        return to_installation_out(
            row,
            can_manage=manage,
            access=access,
            has_active_connection=bool(
                conn_status is not None and conn_status in CONNECTION_USABLE_STATUSES
            ),
            connection_status=conn_status,
            connection_usage=usage,
            connections=summaries,
        )

    def install_app(
        self,
        *,
        workspace: Workspace,
        actor_id: uuid.UUID,
        slug: str,
    ) -> AppInstallationOut:
        self._require_tenant(workspace)
        security_log(
            "app_install_started",
            workspace_id=str(workspace.id),
            actor_id=str(actor_id),
            app_slug=slug,
        )
        app = self._require_installable_app(workspace.id, slug)
        existing = self.repo.get_installation_by_app(workspace.id, app.id)
        now = datetime.now(timezone.utc)

        if existing is not None:
            if existing.status == AppInstallationStatus.ACTIVE.value:
                raise AppError(
                    ErrorCategory.APP_ALREADY_INSTALLED,
                    "App is already installed in this workspace.",
                    details={"app_slug": slug},
                )
            existing.status = AppInstallationStatus.ACTIVE.value
            existing.installed_by_user_id = actor_id
            existing.installed_at = now
            existing.uninstalled_at = None
            record_audit(
                self.db,
                action=AuditAction.APP_INSTALLED,
                entity_type=AuditEntityType.APP_INSTALLATION,
                entity_id=existing.id,
                workspace_id=workspace.id,
                actor_user_id=actor_id,
                metadata={"app_slug": slug, "reinstall": True},
                allowlist=frozenset({"app_slug", "reinstall"}),
            )
            self.db.commit()
            self.db.refresh(existing)
            row = self.repo.get_installation_for_workspace(workspace.id, existing.id)
            assert row is not None
            self._run_install_hooks(workspace_id=workspace.id, installation=row, app=app)
            security_log(
                "app_installed",
                workspace_id=str(workspace.id),
                actor_id=str(actor_id),
                app_id=str(app.id),
                installation_id=str(row.id),
                reinstall=True,
            )
            access = self.access.resolve(
                workspace.id, app=row.app, can_manage=True, installation=row
            )
            return to_installation_out(row, can_manage=True, access=access)

        row = AppInstallation(
            workspace_id=workspace.id,
            app_id=app.id,
            status=AppInstallationStatus.ACTIVE.value,
            installed_by_user_id=actor_id,
            installed_at=now,
            config_encrypted=None,
        )
        self.repo.create_installation(row)
        record_audit(
            self.db,
            action=AuditAction.APP_INSTALLED,
            entity_type=AuditEntityType.APP_INSTALLATION,
            entity_id=row.id,
            workspace_id=workspace.id,
            actor_user_id=actor_id,
            metadata={"app_slug": slug, "reinstall": False},
            allowlist=frozenset({"app_slug", "reinstall"}),
        )
        self.db.commit()
        loaded = self.repo.get_installation_for_workspace(workspace.id, row.id)
        assert loaded is not None
        self._run_install_hooks(workspace_id=workspace.id, installation=loaded, app=app)
        security_log(
            "app_installed",
            workspace_id=str(workspace.id),
            actor_id=str(actor_id),
            app_id=str(app.id),
            installation_id=str(loaded.id),
            reinstall=False,
        )
        access = self.access.resolve(
            workspace.id, app=loaded.app, can_manage=True, installation=loaded
        )
        return to_installation_out(loaded, can_manage=True, access=access)

    def uninstall_app(
        self,
        *,
        workspace: Workspace,
        actor_id: uuid.UUID,
        slug: str,
    ) -> AppInstallationOut:
        self._require_tenant(workspace)
        app = self.repo.get_app_by_slug(slug)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        row = self.repo.get_installation_by_app(workspace.id, app.id)
        if row is None or row.status != AppInstallationStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.APP_NOT_INSTALLED,
                "App is not installed in this workspace.",
                details={"app_slug": slug},
            )

        # Future phases attach connector cleanup hooks here (9C+).
        # Uninstall must NOT revoke licenses or cancel subscriptions.
        self._run_uninstall_hooks(workspace_id=workspace.id, installation=row, app=app)

        now = datetime.now(timezone.utc)
        row.status = AppInstallationStatus.UNINSTALLED.value
        row.uninstalled_at = now
        record_audit(
            self.db,
            action=AuditAction.APP_UNINSTALLED,
            entity_type=AuditEntityType.APP_INSTALLATION,
            entity_id=row.id,
            workspace_id=workspace.id,
            actor_user_id=actor_id,
            metadata={"app_slug": slug},
            allowlist=frozenset({"app_slug"}),
        )
        self.db.commit()
        loaded = self.repo.get_installation_for_workspace(workspace.id, row.id)
        assert loaded is not None
        security_log(
            "app_uninstalled",
            workspace_id=str(workspace.id),
            actor_id=str(actor_id),
            app_id=str(app.id),
            installation_id=str(loaded.id),
        )
        access = self.access.resolve(
            workspace.id, app=loaded.app, can_manage=True, installation=loaded
        )
        return to_installation_out(loaded, can_manage=True, access=access)

    def set_encrypted_config(
        self,
        *,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Service-boundary write for future connectors. Not exposed via 9A API."""
        row = self.repo.get_installation_for_workspace(workspace_id, installation_id)
        if row is None:
            raise AppError(
                ErrorCategory.APP_INSTALLATION_NOT_FOUND,
                "App installation not found.",
            )
        row.config_encrypted = self.crypto.encrypt(payload)
        self.db.flush()

    def get_decrypted_config(
        self,
        *,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
    ) -> dict | None:
        row = self.repo.get_installation_for_workspace(workspace_id, installation_id)
        if row is None:
            raise AppError(
                ErrorCategory.APP_INSTALLATION_NOT_FOUND,
                "App installation not found.",
            )
        if not row.config_encrypted:
            return None
        return self.crypto.decrypt(row.config_encrypted)

    def _require_installable_app(
        self, workspace_id: uuid.UUID, slug: str
    ) -> CatalogApp:
        app = self.repo.get_app_by_slug(slug)
        if app is None or app.status == AppStatus.DISABLED.value:
            security_log("app_install_rejected", reason="not_found", app_slug=slug)
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        if app.status == AppStatus.DRAFT.value:
            security_log("app_install_rejected", reason="draft", app_slug=slug)
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")

        # Paid entitlement survives catalog unpublish — allow reinstall when licensed.
        if app.billing_type != AppBillingType.FREE.value and self._has_live_commercial_access(
            workspace_id, app
        ):
            return app

        if app.status == AppStatus.COMING_SOON.value:
            security_log("app_install_rejected", reason="coming_soon", app_slug=slug)
            raise AppError(
                ErrorCategory.APP_NOT_AVAILABLE,
                "App is not available for installation yet.",
                details={"app_slug": slug, "status": app.status},
            )
        if app.status != AppStatus.PUBLISHED.value:
            security_log("app_install_rejected", reason="status", app_slug=slug)
            raise AppError(
                ErrorCategory.APP_NOT_AVAILABLE,
                "App is not available for installation.",
                details={"app_slug": slug, "status": app.status},
            )

        if app.billing_type == AppBillingType.FREE.value:
            return app

        access = self.access.resolve(workspace_id, app=app, can_manage=True)
        if access.status == AppAccessStatus.EXPIRED:
            security_log(
                "app_install_rejected",
                reason="subscription_expired",
                app_slug=slug,
            )
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
                "App subscription has expired. Renew before installing.",
                details={"app_slug": slug},
            )
        if app.billing_type == AppBillingType.ONE_TIME.value:
            security_log(
                "app_install_rejected",
                reason="billing_required",
                app_slug=slug,
                billing_type=app.billing_type,
            )
            raise AppError(
                ErrorCategory.APP_BILLING_REQUIRED,
                "This app requires a purchase before installation.",
                details={
                    "app_slug": slug,
                    "billing_type": app.billing_type,
                    "access_requirement": app.billing_type,
                },
            )
        security_log(
            "app_install_rejected",
            reason="subscription_required",
            app_slug=slug,
        )
        raise AppError(
            ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
            "A valid App subscription is required before installation.",
            details={"app_slug": slug, "billing_type": app.billing_type},
        )

    def _has_live_commercial_access(
        self, workspace_id: uuid.UUID, app: CatalogApp
    ) -> bool:
        """True when license/sub still grants access, even if catalog is unpublished."""
        from app.apps_catalog.calendar import ensure_utc

        if app.billing_type == AppBillingType.ONE_TIME.value:
            return self.repo.get_active_license(workspace_id, app.id) is not None
        if app.billing_type == AppBillingType.SUBSCRIPTION.value:
            sub = self.repo.get_subscription(workspace_id, app.id)
            if sub is None:
                return False
            return ensure_utc(sub.current_period_end) > datetime.now(timezone.utc)
        return False

    def _run_install_hooks(
        self,
        *,
        workspace_id: uuid.UUID,
        installation: AppInstallation,
        app: CatalogApp,
    ) -> None:
        """Best-effort connector follow-up after install (e.g. OpenWA webhook register)."""
        if app.connector_key != "openwa":
            return
        from app.connectors.providers.openwa.service import OpenWAChannelService

        OpenWAChannelService(self.db).register_webhooks_for_installation(
            workspace_id=workspace_id,
            installation_id=installation.id,
            app_slug=app.slug,
        )

    def _run_uninstall_hooks(
        self,
        *,
        workspace_id: uuid.UUID,
        installation: AppInstallation,
        app: CatalogApp,
    ) -> None:
        """Best-effort connector cleanup on uninstall (keeps licenses/subscriptions)."""
        if app.connector_key != "openwa":
            return
        from app.connectors.providers.openwa.service import OpenWAChannelService

        OpenWAChannelService(self.db).remove_webhooks_for_installation(
            workspace_id=workspace_id,
            installation_id=installation.id,
        )

    @staticmethod
    def _require_tenant(workspace: Workspace) -> None:
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
