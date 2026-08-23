"""Platform Admin App Store orchestration (Phase 12E)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.admin_grants import AppAdminGrantService
from app.apps_catalog.commerce import AppCommerceService
from app.apps_catalog.entitlement_keys import (
    entitlement_catalog_for_app,
    validate_entitlement_key,
)
from app.apps_catalog.models import (
    AppBillingType,
    AppCategory,
    AppCommercialSource,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.seed import APP_SPECS
from app.apps_catalog.service import AppInstallationService
from app.audit import AuditAction, AuditEntityType, record_audit
from app.billing.money import parse_decimal_money, quantize_money, require_sar
from app.common.security_log import security_log
from app.connectors.registry import connector_registry
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.repository import PlatformAdminRepository
from app.platform_admin.schemas import (
    PlatformAppCategoryListResponse,
    PlatformAppCategoryOut,
    PlatformAppCategoryUpdateRequest,
    PlatformAppCommercialGrantResponse,
    PlatformAppCreateRequest,
    PlatformAppDetailOut,
    PlatformAppEntitlementCatalogItem,
    PlatformAppEntitlementCatalogResponse,
    PlatformAppLicenseGrantRequest,
    PlatformAppLicenseRevokeRequest,
    PlatformAppLifecycleRequest,
    PlatformAppListItem,
    PlatformAppListResponse,
    PlatformAppPlanCreateRequest,
    PlatformAppPlanDetailOut,
    PlatformAppPlanEntitlementIn,
    PlatformAppPlanEntitlementOut,
    PlatformAppPlanListItem,
    PlatformAppPlanListResponse,
    PlatformAppPlanUpdateRequest,
    PlatformAppSubscriptionExtendRequest,
    PlatformAppSubscriptionGrantRequest,
    PlatformAppSubscriptionRevokeRequest,
    PlatformAppUpdateRequest,
    PlatformAppWorkspaceEntitlementListResponse,
    PlatformAppWorkspaceEntitlementOut,
    PlatformWorkspaceAppOut,
    PlatformWorkspaceAppsResponse,
)
from app.workspaces.models import Workspace, WorkspaceKind

SEEDED_APP_SLUGS = frozenset(spec.slug for spec in APP_SPECS)


class PlatformAdminAppsService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = AppCatalogRepository(db)
        self.admin_repo = PlatformAdminRepository(db)
        self.access = AppAccessService(db)
        self.grants = AppAdminGrantService(db)
        self.commerce = AppCommerceService(db, self.settings, billing=False)
        self.installations = AppInstallationService(db, self.settings)

    def _audit_and_commit(
        self,
        *,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        metadata: dict[str, Any],
        allowlist: frozenset[str],
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        record_audit(
            self.db,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            metadata=metadata,
            allowlist=allowlist,
        )
        self.db.commit()

    # --- Categories (read + safe deactivate) ---

    def list_categories(self, actor: User) -> PlatformAppCategoryListResponse:
        require_platform_admin_user(actor)
        items = [
            PlatformAppCategoryOut(
                id=c.id,
                slug=c.slug,
                name_key=c.name_key,
                description_key=c.description_key,
                icon=c.icon,
                sort_order=c.sort_order,
                is_active=c.is_active,
            )
            for c in self.repo.list_all_categories()
        ]
        return PlatformAppCategoryListResponse(items=items)

    def update_category(
        self,
        actor: User,
        category_id: uuid.UUID,
        body: PlatformAppCategoryUpdateRequest,
    ) -> PlatformAppCategoryOut:
        require_platform_admin_user(actor)
        row = self.db.get(AppCategory, category_id)
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "App category not found.")
        before = {"is_active": row.is_active, "sort_order": row.sort_order}
        if body.is_active is not None:
            row.is_active = body.is_active
        if body.sort_order is not None:
            row.sort_order = body.sort_order
        self.db.flush()
        self._audit_and_commit(
            action=AuditAction.APP_UPDATED,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=row.id,
            actor_user_id=actor.id,
            metadata={
                "category_id": str(row.id),
                "slug": row.slug,
                "before": before,
                "after": {"is_active": row.is_active, "sort_order": row.sort_order},
            },
            allowlist=frozenset({"category_id", "slug", "before", "after"}),
        )
        return PlatformAppCategoryOut(
            id=row.id,
            slug=row.slug,
            name_key=row.name_key,
            description_key=row.description_key,
            icon=row.icon,
            sort_order=row.sort_order,
            is_active=row.is_active,
        )

    def app_entitlement_catalog(
        self, actor: User, app_id: uuid.UUID
    ) -> PlatformAppEntitlementCatalogResponse:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        items = [
            PlatformAppEntitlementCatalogItem(
                key=spec.key, value_type=spec.value_type, unit=spec.unit
            )
            for spec in entitlement_catalog_for_app(app)
        ]
        return PlatformAppEntitlementCatalogResponse(items=items)

    # --- Apps catalog ---

    def list_apps(
        self,
        actor: User,
        *,
        limit: int = 25,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        billing_type: str | None = None,
        category: str | None = None,
        connector_kind: str | None = None,
    ) -> PlatformAppListResponse:
        require_platform_admin_user(actor)
        total = self.repo.count_admin_apps(
            search=search,
            status=status,
            billing_type=billing_type,
            category_slug=category,
            connector_kind=connector_kind,
        )
        rows = self.repo.list_admin_apps(
            limit=limit,
            offset=offset,
            search=search,
            status=status,
            billing_type=billing_type,
            category_slug=category,
            connector_kind=connector_kind,
        )
        app_ids = [a.id for a in rows]
        installs = self.repo.count_installations_by_app_ids(app_ids)
        entitlements = self.repo.count_active_entitlements_by_app_ids(app_ids)
        items = [
            PlatformAppListItem(
                id=app.id,
                slug=app.slug,
                name=app.name,
                short_description=app.short_description,
                category_slug=app.category.slug,
                category_name_key=app.category.name_key,
                billing_type=app.billing_type,
                status=app.status,
                icon_url=app.icon_url,
                connector_key=app.connector_key,
                connector_kind=app.connector_kind,
                plans_count=len(app.plans or []),
                installations_count=installs.get(app.id, 0),
                active_entitlements_count=entitlements.get(app.id, 0),
                created_at=app.created_at,
                updated_at=app.updated_at,
            )
            for app in rows
        ]
        return PlatformAppListResponse(items=items, total=total, limit=limit, offset=offset)

    def get_app(self, actor: User, app_id: uuid.UUID) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        return self._app_detail(app)

    def create_app(self, actor: User, body: PlatformAppCreateRequest) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        self._validate_billing_type(body.billing_type)
        category = self.db.get(AppCategory, body.category_id)
        if category is None:
            raise AppError(ErrorCategory.NOT_FOUND, "App category not found.")
        if self.repo.get_app_by_slug(body.slug):
            raise AppError(ErrorCategory.CONFLICT, "App slug already exists.")
        self._validate_connector_fields(
            connector_key=body.connector_key,
            connector_kind=body.connector_kind,
            billing_type=body.billing_type,
        )
        row = CatalogApp(
            slug=body.slug.strip().lower(),
            name=body.name.strip(),
            short_description=body.short_description.strip(),
            description=body.description,
            category_id=body.category_id,
            icon_url=body.icon_url,
            billing_type=body.billing_type,
            status=AppStatus.DRAFT.value,
            is_featured=body.is_featured,
            sort_order=body.sort_order,
            connector_key=body.connector_key,
            connector_kind=body.connector_kind,
            extra={"source": "platform_admin"},
        )
        try:
            self.repo.upsert_app(row)
            self.db.flush()
        except IntegrityError as exc:
            raise AppError(ErrorCategory.CONFLICT, "App slug already exists.") from exc
        self._audit_and_commit(
            action=AuditAction.APP_CREATED,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=row.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(row.id),
                "slug": row.slug,
                "name": row.name,
                "billing_type": row.billing_type,
                "status": row.status,
            },
            allowlist=frozenset({"app_id", "slug", "name", "billing_type", "status"}),
        )
        return self._app_detail(self._require_app(row.id))

    def update_app(
        self, actor: User, app_id: uuid.UUID, body: PlatformAppUpdateRequest
    ) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        before = self._app_snapshot(app)
        slug_locked = self._slug_locked(app)
        billing_locked = self._billing_type_locked(app)
        connector_locked = self._connector_locked(app)
        billing_type_changed = False

        if body.slug is not None and body.slug != app.slug:
            if slug_locked:
                raise AppError(ErrorCategory.VALIDATION, "App slug cannot be changed.")
            if self.repo.get_app_by_slug(body.slug):
                raise AppError(ErrorCategory.CONFLICT, "App slug already exists.")
            app.slug = body.slug.strip().lower()
        if body.billing_type is not None and body.billing_type != app.billing_type:
            if billing_locked:
                raise AppError(ErrorCategory.VALIDATION, "App billing type cannot be changed.")
            self._validate_billing_type(body.billing_type)
            app.billing_type = body.billing_type
            billing_type_changed = True
        if body.connector_key is not None or body.connector_kind is not None:
            new_key = body.connector_key if body.connector_key is not None else app.connector_key
            new_kind = (
                body.connector_kind if body.connector_kind is not None else app.connector_kind
            )
            if connector_locked and (
                new_key != app.connector_key or new_kind != app.connector_kind
            ):
                raise AppError(
                    ErrorCategory.VALIDATION, "Connector identity cannot be changed."
                )
            self._validate_connector_fields(
                connector_key=new_key,
                connector_kind=new_kind,
                billing_type=app.billing_type,
            )
            app.connector_key = new_key
            app.connector_kind = new_kind
        if body.name is not None:
            app.name = body.name.strip()
        if body.short_description is not None:
            app.short_description = body.short_description.strip()
        if body.description is not None:
            app.description = body.description
        if body.category_id is not None:
            if self.db.get(AppCategory, body.category_id) is None:
                raise AppError(ErrorCategory.NOT_FOUND, "App category not found.")
            app.category_id = body.category_id
        if body.icon_url is not None:
            app.icon_url = body.icon_url
        if body.is_featured is not None:
            app.is_featured = body.is_featured
        if body.sort_order is not None:
            app.sort_order = body.sort_order
        if billing_type_changed:
            self._normalize_plans_for_billing_type(app)
        self.db.flush()
        after = self._app_snapshot(app)
        self._audit_and_commit(
            action=AuditAction.APP_UPDATED,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=app.id,
            actor_user_id=actor.id,
            metadata={"app_id": str(app.id), "before": before, "after": after},
            allowlist=frozenset({"app_id", "before", "after"}),
        )
        return self._app_detail(self._require_app(app.id))

    def publish_app(
        self, actor: User, app_id: uuid.UUID, body: PlatformAppLifecycleRequest
    ) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        _ = AppAdminGrantService.normalize_reason(body.reason)
        app = self._require_app(app_id)
        self._validate_publish_ready(app)
        old = app.status
        app.status = AppStatus.PUBLISHED.value
        self.db.flush()
        self._audit_and_commit(
            action=AuditAction.APP_PUBLISHED,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=app.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(app.id),
                "old_status": old,
                "new_status": app.status,
                "reason": body.reason.strip(),
            },
            allowlist=frozenset({"app_id", "old_status", "new_status", "reason"}),
        )
        return self._app_detail(self._require_app(app.id))

    def unpublish_app(
        self, actor: User, app_id: uuid.UUID, body: PlatformAppLifecycleRequest
    ) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        _ = AppAdminGrantService.normalize_reason(body.reason)
        app = self._require_app(app_id)
        old = app.status
        app.status = AppStatus.DRAFT.value
        self.db.flush()
        self._audit_and_commit(
            action=AuditAction.APP_UNPUBLISHED,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=app.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(app.id),
                "old_status": old,
                "new_status": app.status,
                "reason": body.reason.strip(),
            },
            allowlist=frozenset({"app_id", "old_status", "new_status", "reason"}),
        )
        return self._app_detail(self._require_app(app.id))

    def set_coming_soon(
        self, actor: User, app_id: uuid.UUID, body: PlatformAppLifecycleRequest
    ) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        _ = AppAdminGrantService.normalize_reason(body.reason)
        app = self._require_app(app_id)
        old = app.status
        app.status = AppStatus.COMING_SOON.value
        self.db.flush()
        self._audit_and_commit(
            action=AuditAction.APP_COMING_SOON,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=app.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(app.id),
                "old_status": old,
                "new_status": app.status,
                "reason": body.reason.strip(),
            },
            allowlist=frozenset({"app_id", "old_status", "new_status", "reason"}),
        )
        return self._app_detail(self._require_app(app.id))

    def disable_app(
        self, actor: User, app_id: uuid.UUID, body: PlatformAppLifecycleRequest
    ) -> PlatformAppDetailOut:
        require_platform_admin_user(actor)
        _ = AppAdminGrantService.normalize_reason(body.reason)
        app = self._require_app(app_id)
        if self._is_seeded(app):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Seeded catalog apps cannot be disabled. Use unpublish instead.",
                details={"app_slug": app.slug},
            )
        old = app.status
        app.status = AppStatus.DISABLED.value
        self.db.flush()
        self._audit_and_commit(
            action=AuditAction.APP_DISABLED,
            entity_type=AuditEntityType.CATALOG_APP,
            entity_id=app.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(app.id),
                "old_status": old,
                "new_status": app.status,
                "reason": body.reason.strip(),
            },
            allowlist=frozenset({"app_id", "old_status", "new_status", "reason"}),
        )
        return self._app_detail(self._require_app(app.id))

    # --- Plans ---

    def list_plans(
        self, actor: User, app_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> PlatformAppPlanListResponse:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        plans = sorted(app.plans or [], key=lambda p: (p.sort_order, p.code))
        total = len(plans)
        page = plans[offset : offset + limit]
        counts = self.repo.count_plan_commercial_by_plan_ids([p.id for p in page])
        items = [self._plan_item(p, counts.get(p.id, 0)) for p in page]
        return PlatformAppPlanListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def create_plan(
        self, actor: User, app_id: uuid.UUID, body: PlatformAppPlanCreateRequest
    ) -> PlatformAppPlanDetailOut:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        if self.repo.get_plan_by_code(app.id, body.code):
            raise AppError(ErrorCategory.CONFLICT, "App plan code already exists.")
        amount = parse_decimal_money(body.price_amount)
        currency = require_sar(body.currency)
        interval = body.billing_interval
        plan = AppPlan(
            app_id=app.id,
            code=body.code.strip(),
            name=body.name.strip(),
            description=body.description,
            billing_interval=interval,
            price_amount=amount,
            currency=currency,
            is_default=body.is_default,
            is_active=True,
            sort_order=0,
        )
        self._apply_plan_billing_rules(app, plan)
        self.commerce._validate_plan_matches_billing(app, plan)
        self.repo.upsert_plan(plan)
        self._sync_entitlements(app, plan, body.entitlements, replace=False)
        if body.is_default:
            self._set_default_plan(app, plan)
        self.db.flush()
        self._audit_and_commit(
            action=AuditAction.APP_PLAN_CREATED,
            entity_type=AuditEntityType.APP_PLAN,
            entity_id=plan.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(app.id),
                "plan_id": str(plan.id),
                "code": plan.code,
                "price_amount": str(plan.price_amount),
            },
            allowlist=frozenset({"app_id", "plan_id", "code", "price_amount"}),
        )
        return self._plan_item(plan, 0)

    def update_plan(
        self,
        actor: User,
        app_id: uuid.UUID,
        plan_id: uuid.UUID,
        body: PlatformAppPlanUpdateRequest,
    ) -> PlatformAppPlanDetailOut:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        plan = self._require_plan(app, plan_id)
        before = self._plan_snapshot(plan)
        if body.code is not None:
            new_code = body.code.strip()
            if new_code != plan.code:
                if self.repo.get_plan_by_code(app.id, new_code):
                    raise AppError(ErrorCategory.CONFLICT, "App plan code already exists.")
                plan.code = new_code
        if body.name is not None:
            plan.name = body.name.strip()
        if body.description is not None:
            plan.description = body.description
        if body.price_amount is not None:
            plan.price_amount = parse_decimal_money(body.price_amount)
        if body.currency is not None:
            plan.currency = require_sar(body.currency)
        if body.is_default is not None and body.is_default:
            self._set_default_plan(app, plan)
        if body.is_active is not None:
            if not body.is_active and self.repo.plan_has_commercial_history(plan.id):
                plan.is_active = False
            else:
                plan.is_active = body.is_active
        if body.billing_interval is not None:
            plan.billing_interval = body.billing_interval
        self._apply_plan_billing_rules(app, plan)
        self.commerce._validate_plan_matches_billing(app, plan)
        ent_changed = False
        if body.entitlements is not None and self._entitlements_changed(
            plan, body.entitlements
        ):
            if self.repo.plan_has_commercial_history(plan.id):
                reason = (body.reason or "").strip()
                if not reason:
                    raise AppError(
                        ErrorCategory.VALIDATION,
                        "A reason is required when changing entitlements on an in-use plan.",
                    )
            self._sync_entitlements(app, plan, body.entitlements, replace=True)
            ent_changed = True
        self.db.flush()
        after = self._plan_snapshot(plan)
        action = AuditAction.APP_PLAN_UPDATED
        if body.is_active is False:
            action = AuditAction.APP_PLAN_DEACTIVATED
        elif body.is_active is True:
            action = AuditAction.APP_PLAN_ACTIVATED
        if ent_changed:
            action = AuditAction.APP_PLAN_ENTITLEMENTS_UPDATED
        self._audit_and_commit(
            action=action,
            entity_type=AuditEntityType.APP_PLAN,
            entity_id=plan.id,
            actor_user_id=actor.id,
            metadata={
                "app_id": str(app.id),
                "plan_id": str(plan.id),
                "before": before,
                "after": after,
                "reason": (body.reason or "").strip() or None,
            },
            allowlist=frozenset({"app_id", "plan_id", "before", "after", "reason"}),
        )
        count = self.repo.count_plan_commercial_by_plan_ids([plan.id]).get(plan.id, 0)
        return self._plan_item(plan, count)

    def activate_plan(
        self, actor: User, app_id: uuid.UUID, plan_id: uuid.UUID
    ) -> PlatformAppPlanDetailOut:
        body = PlatformAppPlanUpdateRequest(is_active=True)
        return self.update_plan(actor, app_id, plan_id, body)

    def deactivate_plan(
        self,
        actor: User,
        app_id: uuid.UUID,
        plan_id: uuid.UUID,
        body: PlatformAppLifecycleRequest,
    ) -> PlatformAppPlanDetailOut:
        update = PlatformAppPlanUpdateRequest(
            is_active=False, reason=body.reason.strip()
        )
        return self.update_plan(actor, app_id, plan_id, update)

    # --- Workspace apps ---

    def list_workspace_apps(
        self, actor: User, workspace_id: uuid.UUID
    ) -> PlatformWorkspaceAppsResponse:
        require_platform_admin_user(actor)
        workspace = self._require_workspace(workspace_id)
        apps = list(
            self.db.scalars(
                select(CatalogApp)
                .options(
                    selectinload(CatalogApp.plans).selectinload(AppPlan.entitlements),
                )
                .order_by(CatalogApp.sort_order.asc(), CatalogApp.name.asc())
            )
        )

        app_ids = [a.id for a in apps]
        install_map = self.repo.map_installations_by_app_id(workspace.id, app_ids)
        license_map = self.repo.map_licenses_by_app_id(workspace.id, app_ids)
        sub_map = self.repo.map_subscriptions_by_app_id(workspace.id, app_ids)
        items: list[PlatformWorkspaceAppOut] = []
        for app in apps:
            inst = install_map.get(app.id)
            lic = license_map.get(app.id)
            sub = sub_map.get(app.id)
            access = self.access.resolve(
                workspace.id,
                app=app,
                can_manage=True,
                installation=inst,
                license_row=lic,
                subscription=sub,
            )
            entitlements = self._effective_entitlements(access.plan_id, app)
            usage = self._usage_counts(workspace.id, app, inst, access)
            items.append(
                PlatformWorkspaceAppOut(
                    app_id=app.id,
                    app_slug=app.slug,
                    app_name=app.name,
                    billing_type=app.billing_type,
                    catalog_status=app.status,
                    access_status=access.status.value,
                    installed=access.installed,
                    installation_status=inst.status if inst else None,
                    plan_id=access.plan_id,
                    plan_code=access.plan_code,
                    plan_name=access.plan_name,
                    license_status=lic.status if lic else None,
                    license_source=lic.source if lic else None,
                    subscription_status=sub.status if sub else None,
                    subscription_source=sub.source if sub else None,
                    current_period_start=access.current_period_start,
                    current_period_end=access.current_period_end,
                    entitlements=entitlements,
                    connections_used=usage.get("connections_used"),
                    connections_limit=usage.get("connections_limit"),
                    widgets_used=usage.get("widgets_used"),
                    widgets_limit=usage.get("widgets_limit"),
                )
            )
        return PlatformWorkspaceAppsResponse(items=items)

    def list_app_workspaces(
        self,
        actor: User,
        app_id: uuid.UUID,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> PlatformAppWorkspaceEntitlementListResponse:
        require_platform_admin_user(actor)
        app = self._require_app(app_id)
        rows, total = self.repo.list_app_workspace_entitlements(
            app.id, limit=limit, offset=offset
        )
        items: list[PlatformAppWorkspaceEntitlementOut] = []
        for workspace_id, lic, sub in rows:
            ws = self.admin_repo.get_workspace(workspace_id)
            if ws is None:
                continue
            inst = self.repo.get_installation_by_app(workspace_id, app.id)
            access = self.access.resolve(
                workspace_id,
                app=app,
                can_manage=True,
                installation=inst,
                license_row=lic,
                subscription=sub,
            )
            items.append(
                PlatformAppWorkspaceEntitlementOut(
                    workspace_id=workspace_id,
                    workspace_name=ws.name,
                    workspace_slug=ws.slug,
                    access_status=access.status.value,
                    installed=access.installed,
                    plan_id=access.plan_id,
                    plan_code=access.plan_code,
                    plan_name=access.plan_name,
                    license_status=lic.status if lic else None,
                    license_source=lic.source if lic else None,
                    subscription_status=sub.status if sub else None,
                    subscription_source=sub.source if sub else None,
                    current_period_start=access.current_period_start,
                    current_period_end=access.current_period_end,
                    entitlements=self._effective_entitlements(access.plan_id, app),
                )
            )
        return PlatformAppWorkspaceEntitlementListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def grant_license(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        body: PlatformAppLicenseGrantRequest,
    ) -> PlatformAppCommercialGrantResponse:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        app = self._require_app(app_id)
        plan = self._require_plan(app, body.app_plan_id)
        reason = AppAdminGrantService.normalize_reason(body.reason)
        idem = AppAdminGrantService.normalize_idempotency_key(
            body.idempotency_key, prefix=f"platform-app-license:{workspace.id}:{app.id}"
        )
        lic, replay = self.grants.grant_license(
            workspace=workspace,
            app=app,
            plan=plan,
            actor=actor,
            reason=reason,
            idempotency_key=idem,
        )
        if not replay:
            self._audit_and_commit(
                action=AuditAction.APP_LICENSE_GRANTED,
                entity_type=AuditEntityType.APP_LICENSE,
                entity_id=lic.id,
                actor_user_id=actor.id,
                workspace_id=workspace.id,
                metadata={
                    "workspace_id": str(workspace.id),
                    "app_id": str(app.id),
                    "app_plan_id": str(plan.id),
                    "license_id": str(lic.id),
                    "reason": reason,
                    "idempotency_key": idem,
                },
                allowlist=frozenset(
                    {
                        "workspace_id",
                        "app_id",
                        "app_plan_id",
                        "license_id",
                        "reason",
                        "idempotency_key",
                    }
                ),
            )
        else:
            self.db.commit()
        access = self.access.resolve(workspace.id, app=app)
        return PlatformAppCommercialGrantResponse(
            workspace_id=workspace.id,
            app_id=app.id,
            license_id=lic.id,
            access_status=access.status.value,
            idempotent_replay=replay,
        )

    def revoke_license(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        body: PlatformAppLicenseRevokeRequest,
    ) -> PlatformAppCommercialGrantResponse:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        app = self._require_app(app_id)
        reason = AppAdminGrantService.normalize_reason(body.reason)
        lic = self.grants.revoke_license(
            workspace=workspace, app=app, actor=actor, reason=reason
        )
        self._audit_and_commit(
            action=AuditAction.APP_LICENSE_REVOKED,
            entity_type=AuditEntityType.APP_LICENSE,
            entity_id=lic.id,
            actor_user_id=actor.id,
            workspace_id=workspace.id,
            metadata={
                "workspace_id": str(workspace.id),
                "app_id": str(app.id),
                "license_id": str(lic.id),
                "reason": reason,
            },
            allowlist=frozenset({"workspace_id", "app_id", "license_id", "reason"}),
        )
        access = self.access.resolve(workspace.id, app=app)
        return PlatformAppCommercialGrantResponse(
            workspace_id=workspace.id,
            app_id=app.id,
            license_id=lic.id,
            access_status=access.status.value,
        )

    def grant_subscription(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        body: PlatformAppSubscriptionGrantRequest,
    ) -> PlatformAppCommercialGrantResponse:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        app = self._require_app(app_id)
        plan = self._require_plan(app, body.app_plan_id)
        reason = AppAdminGrantService.normalize_reason(body.reason)
        idem = AppAdminGrantService.normalize_idempotency_key(
            body.idempotency_key,
            prefix=f"platform-app-subscription:{workspace.id}:{app.id}",
        )
        sub, replay = self.grants.grant_subscription(
            workspace=workspace,
            app=app,
            plan=plan,
            actor=actor,
            reason=reason,
            idempotency_key=idem,
        )
        if not replay:
            self._audit_and_commit(
                action=AuditAction.APP_SUBSCRIPTION_GRANTED,
                entity_type=AuditEntityType.APP_SUBSCRIPTION,
                entity_id=sub.id,
                actor_user_id=actor.id,
                workspace_id=workspace.id,
                metadata={
                    "workspace_id": str(workspace.id),
                    "app_id": str(app.id),
                    "app_plan_id": str(plan.id),
                    "subscription_id": str(sub.id),
                    "period_start": sub.current_period_start.isoformat(),
                    "period_end": sub.current_period_end.isoformat(),
                    "reason": reason,
                    "idempotency_key": idem,
                },
                allowlist=frozenset(
                    {
                        "workspace_id",
                        "app_id",
                        "app_plan_id",
                        "subscription_id",
                        "period_start",
                        "period_end",
                        "reason",
                        "idempotency_key",
                    }
                ),
            )
        else:
            self.db.commit()
        access = self.access.resolve(workspace.id, app=app)
        return PlatformAppCommercialGrantResponse(
            workspace_id=workspace.id,
            app_id=app.id,
            subscription_id=sub.id,
            access_status=access.status.value,
            idempotent_replay=replay,
        )

    def extend_subscription(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        body: PlatformAppSubscriptionExtendRequest,
    ) -> PlatformAppCommercialGrantResponse:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        app = self._require_app(app_id)
        reason = AppAdminGrantService.normalize_reason(body.reason)
        idem = AppAdminGrantService.normalize_idempotency_key(
            body.idempotency_key,
            prefix=f"platform-app-subscription-extend:{workspace.id}:{app.id}",
        )
        sub, replay = self.grants.extend_subscription(
            workspace=workspace,
            app=app,
            actor=actor,
            reason=reason,
            idempotency_key=idem,
        )
        if not replay:
            self._audit_and_commit(
                action=AuditAction.APP_SUBSCRIPTION_EXTENDED,
                entity_type=AuditEntityType.APP_SUBSCRIPTION,
                entity_id=sub.id,
                actor_user_id=actor.id,
                workspace_id=workspace.id,
                metadata={
                    "workspace_id": str(workspace.id),
                    "app_id": str(app.id),
                    "subscription_id": str(sub.id),
                    "period_start": sub.current_period_start.isoformat(),
                    "period_end": sub.current_period_end.isoformat(),
                    "reason": reason,
                    "idempotency_key": idem,
                },
                allowlist=frozenset(
                    {
                        "workspace_id",
                        "app_id",
                        "subscription_id",
                        "period_start",
                        "period_end",
                        "reason",
                        "idempotency_key",
                    }
                ),
            )
        else:
            self.db.commit()
        access = self.access.resolve(workspace.id, app=app)
        return PlatformAppCommercialGrantResponse(
            workspace_id=workspace.id,
            app_id=app.id,
            subscription_id=sub.id,
            access_status=access.status.value,
            idempotent_replay=replay,
        )

    def revoke_subscription(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        body: PlatformAppSubscriptionRevokeRequest,
    ) -> PlatformAppCommercialGrantResponse:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        app = self._require_app(app_id)
        reason = AppAdminGrantService.normalize_reason(body.reason)
        sub = self.grants.revoke_subscription(
            workspace=workspace, app=app, actor=actor, reason=reason
        )
        self._audit_and_commit(
            action=AuditAction.APP_SUBSCRIPTION_REVOKED,
            entity_type=AuditEntityType.APP_SUBSCRIPTION,
            entity_id=sub.id,
            actor_user_id=actor.id,
            workspace_id=workspace.id,
            metadata={
                "workspace_id": str(workspace.id),
                "app_id": str(app.id),
                "subscription_id": str(sub.id),
                "reason": reason,
            },
            allowlist=frozenset({"workspace_id", "app_id", "subscription_id", "reason"}),
        )
        access = self.access.resolve(workspace.id, app=app)
        return PlatformAppCommercialGrantResponse(
            workspace_id=workspace.id,
            app_id=app.id,
            subscription_id=sub.id,
            access_status=access.status.value,
        )

    def admin_install_app(
        self, actor: User, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> PlatformWorkspaceAppOut:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        app = self._require_app(app_id)
        installation_out = self.installations.install_app(
            workspace=workspace, actor_id=actor.id, slug=app.slug
        )
        self._audit_and_commit(
            action=AuditAction.APP_INSTALLATION_ADMIN,
            entity_type=AuditEntityType.APP_INSTALLATION,
            entity_id=installation_out.id,
            actor_user_id=actor.id,
            workspace_id=workspace.id,
            metadata={
                "workspace_id": str(workspace.id),
                "app_id": str(app.id),
                "installation_id": str(installation_out.id),
            },
            allowlist=frozenset({"workspace_id", "app_id", "installation_id"}),
        )
        items = self.list_workspace_apps(actor, workspace.id).items
        match = next((i for i in items if i.app_id == app.id), None)
        if match is None:
            raise AppError(ErrorCategory.NOT_FOUND, "App not found after install.")
        return match

    # --- helpers ---

    def _require_app(self, app_id: uuid.UUID) -> CatalogApp:
        app = self.repo.get_app_by_id(app_id)
        if app is None:
            raise AppError(ErrorCategory.NOT_FOUND, "App not found.")
        return app

    def _require_plan(self, app: CatalogApp, plan_id: uuid.UUID) -> AppPlan:
        plan = self.repo.get_plan_by_id(plan_id)
        if plan is None or plan.app_id != app.id:
            raise AppError(ErrorCategory.APP_PLAN_NOT_FOUND, "App plan not found.")
        return plan

    def _require_workspace(self, workspace_id: uuid.UUID) -> Workspace:
        ws = self.admin_repo.get_workspace(workspace_id)
        if ws is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        return ws

    def _require_tenant_workspace(self, workspace_id: uuid.UUID) -> Workspace:
        ws = self._require_workspace(workspace_id)
        if ws.kind == WorkspaceKind.SYSTEM.value:
            raise AppError(
                ErrorCategory.SYSTEM_WORKSPACE_NOT_BILLABLE,
                "System workspaces cannot receive App commercial entitlements.",
            )
        return ws

    def _app_detail(self, app: CatalogApp) -> PlatformAppDetailOut:
        installs = self.repo.count_installations_by_app_ids([app.id])
        licenses = self.repo.count_active_licenses_by_app_ids([app.id])
        subs = self.repo.count_active_subscriptions_by_app_ids([app.id])
        plan_counts = self.repo.count_plan_commercial_by_plan_ids(
            [p.id for p in (app.plans or [])]
        )
        plans = [
            self._plan_item(p, plan_counts.get(p.id, 0))
            for p in sorted(app.plans or [], key=lambda x: (x.sort_order, x.code))
        ]
        return PlatformAppDetailOut(
            id=app.id,
            slug=app.slug,
            name=app.name,
            short_description=app.short_description,
            description=app.description,
            category_id=app.category_id,
            category_slug=app.category.slug,
            category_name_key=app.category.name_key,
            billing_type=app.billing_type,
            status=app.status,
            is_featured=app.is_featured,
            icon_url=app.icon_url,
            connector_key=app.connector_key,
            connector_kind=app.connector_kind,
            sort_order=app.sort_order,
            slug_locked=self._slug_locked(app),
            billing_type_locked=self._billing_type_locked(app),
            connector_locked=self._connector_locked(app),
            is_seeded=self._is_seeded(app),
            disable_allowed=not self._is_seeded(app),
            plans=plans,
            installations_count=installs.get(app.id, 0),
            active_licenses_count=licenses.get(app.id, 0),
            active_subscriptions_count=subs.get(app.id, 0),
            created_at=app.created_at,
            updated_at=app.updated_at,
        )

    def _plan_item(self, plan: AppPlan, active_count: int) -> PlatformAppPlanListItem:
        return PlatformAppPlanListItem(
            id=plan.id,
            app_id=plan.app_id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            billing_interval=plan.billing_interval,
            price_amount=str(parse_decimal_money(plan.price_amount)),
            currency=plan.currency,
            is_default=plan.is_default,
            is_active=plan.is_active,
            active_entitlement_count=active_count,
            entitlements=[
                PlatformAppPlanEntitlementOut(key=e.key, value=e.value)
                for e in (plan.entitlements or [])
            ],
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    def _sync_entitlements(
        self,
        app: CatalogApp,
        plan: AppPlan,
        entitlements: list[PlatformAppPlanEntitlementIn],
        *,
        replace: bool,
    ) -> None:
        new_keys: set[str] = set()
        for item in entitlements:
            validate_entitlement_key(app, item.key)
            new_keys.add(item.key)
            existing = self.repo.get_entitlement(plan.id, item.key)
            if existing is None:
                self.repo.upsert_entitlement(
                    AppPlanEntitlement(
                        app_plan_id=plan.id, key=item.key, value=item.value
                    )
                )
            else:
                existing.value = item.value
        if replace:
            for existing in list(plan.entitlements or []):
                if existing.key not in new_keys:
                    self.repo.delete_entitlement(plan.id, existing.key)

    @staticmethod
    def _is_seeded(app: CatalogApp) -> bool:
        return app.slug in SEEDED_APP_SLUGS

    def _apply_plan_billing_rules(self, app: CatalogApp, plan: AppPlan) -> None:
        if app.billing_type == AppBillingType.FREE.value:
            plan.price_amount = Decimal("0.00")
            plan.billing_interval = AppPlanBillingInterval.NONE.value
        elif app.billing_type == AppBillingType.ONE_TIME.value:
            plan.billing_interval = AppPlanBillingInterval.NONE.value

    def _normalize_plans_for_billing_type(self, app: CatalogApp) -> None:
        for plan in app.plans or []:
            self._apply_plan_billing_rules(app, plan)

    @staticmethod
    def _entitlements_changed(
        plan: AppPlan, entitlements: list[PlatformAppPlanEntitlementIn]
    ) -> bool:
        current = {e.key: e.value for e in (plan.entitlements or [])}
        incoming = {item.key: item.value for item in entitlements}
        return current != incoming

    def _set_default_plan(self, app: CatalogApp, plan: AppPlan) -> None:
        for other in app.plans or []:
            other.is_default = other.id == plan.id
        plan.is_default = True

    def _validate_publish_ready(self, app: CatalogApp) -> None:
        active_plans = [p for p in (app.plans or []) if p.is_active]
        if not active_plans:
            raise AppError(
                ErrorCategory.VALIDATION, "App must have at least one active plan."
            )
        if app.billing_type == AppBillingType.FREE.value:
            for plan in active_plans:
                self.commerce._validate_plan_matches_billing(app, plan)
        elif app.billing_type == AppBillingType.ONE_TIME.value:
            priced = [
                p
                for p in active_plans
                if parse_decimal_money(p.price_amount) > Decimal("0.00")
            ]
            if not priced:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "One-time app must have at least one active priced plan.",
                )
        elif app.billing_type == AppBillingType.SUBSCRIPTION.value:
            monthly = [
                p
                for p in active_plans
                if p.billing_interval == AppPlanBillingInterval.MONTHLY.value
                and parse_decimal_money(p.price_amount) > Decimal("0.00")
            ]
            if not monthly:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Subscription app must have at least one active monthly plan.",
                )
        if app.connector_key and not connector_registry.has(app.connector_key):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Connector key is not registered.",
                details={"connector_key": app.connector_key},
            )

    @staticmethod
    def _validate_billing_type(value: str) -> None:
        if value not in {
            AppBillingType.FREE.value,
            AppBillingType.ONE_TIME.value,
            AppBillingType.SUBSCRIPTION.value,
        }:
            raise AppError(ErrorCategory.VALIDATION, "Invalid app billing type.")

    @staticmethod
    def _validate_connector_fields(
        *,
        connector_key: str | None,
        connector_kind: str | None,
        billing_type: str,
    ) -> None:
        if connector_key and not connector_kind:
            raise AppError(
                ErrorCategory.VALIDATION,
                "connector_kind is required when connector_key is set.",
            )
        if connector_kind and not connector_key:
            raise AppError(
                ErrorCategory.VALIDATION,
                "connector_key is required when connector_kind is set.",
            )

    def _slug_locked(self, app: CatalogApp) -> bool:
        if self._is_seeded(app):
            return True
        if app.status != AppStatus.DRAFT.value:
            return True
        return self.repo.app_has_commercial_history(app.id)

    def _billing_type_locked(self, app: CatalogApp) -> bool:
        if self._is_seeded(app):
            return False
        if app.status != AppStatus.DRAFT.value:
            return True
        return self.repo.app_has_commercial_history(app.id)

    def _connector_locked(self, app: CatalogApp) -> bool:
        if self._is_seeded(app):
            return True
        return self.repo.app_has_commercial_history(app.id)

    @staticmethod
    def _app_snapshot(app: CatalogApp) -> dict[str, Any]:
        return {
            "slug": app.slug,
            "name": app.name,
            "billing_type": app.billing_type,
            "status": app.status,
            "connector_key": app.connector_key,
            "connector_kind": app.connector_kind,
        }

    @staticmethod
    def _plan_snapshot(plan: AppPlan) -> dict[str, Any]:
        return {
            "code": plan.code,
            "name": plan.name,
            "price_amount": str(plan.price_amount),
            "is_active": plan.is_active,
            "entitlements": {
                e.key: e.value for e in (plan.entitlements or [])
            },
        }

    def _effective_entitlements(
        self, plan_id: uuid.UUID | None, app: CatalogApp
    ) -> dict[str, Any]:
        if plan_id is None:
            return {}
        plan = self.repo.get_plan_by_id(plan_id)
        if plan is None:
            return {}
        return {e.key: e.value for e in (plan.entitlements or [])}

    def _usage_counts(
        self,
        workspace_id: uuid.UUID,
        app: CatalogApp,
        inst,
        access,
    ) -> dict[str, int | None]:
        out: dict[str, int | None] = {
            "connections_used": None,
            "connections_limit": None,
            "widgets_used": None,
            "widgets_limit": None,
        }
        if not access.commercially_entitled and app.billing_type != AppBillingType.FREE.value:
            return out
        plan = self.repo.get_plan_by_id(access.plan_id) if access.plan_id else None
        if plan is None:
            return out
        ent = {e.key: e.value for e in (plan.entitlements or [])}
        if "connections" in ent and inst is not None:
            from app.connectors.repository import ConnectorRepository

            out["connections_used"] = ConnectorRepository(
                self.db
            ).count_limit_connections(workspace_id, app_installation_id=inst.id)
            try:
                out["connections_limit"] = int(ent["connections"])
            except (TypeError, ValueError):
                pass
        if "widgets" in ent and inst is not None:
            from app.widgets.models import WidgetInstance, WidgetInstanceStatus

            out["widgets_used"] = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(WidgetInstance)
                    .where(
                        WidgetInstance.workspace_id == workspace_id,
                        WidgetInstance.app_installation_id == inst.id,
                        WidgetInstance.status == WidgetInstanceStatus.ACTIVE.value,
                    )
                )
                or 0
            )
            try:
                out["widgets_limit"] = int(ent["widgets"])
            except (TypeError, ValueError):
                pass
        return out
