"""App Store repository — catalog is global; installations are workspace-scoped."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.apps_catalog.models import (
    AppCategory,
    AppInstallation,
    AppInstallationStatus,
    AppLicense,
    AppLicenseStatus,
    AppPlan,
    AppPlanEntitlement,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)


class AppCatalogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- categories ---

    def get_category_by_slug(self, slug: str) -> AppCategory | None:
        return self.db.scalar(select(AppCategory).where(AppCategory.slug == slug))

    def list_active_categories(self) -> list[AppCategory]:
        return list(
            self.db.scalars(
                select(AppCategory)
                .where(AppCategory.is_active.is_(True))
                .order_by(AppCategory.sort_order.asc(), AppCategory.slug.asc())
            )
        )

    def upsert_category(self, row: AppCategory) -> AppCategory:
        self.db.add(row)
        self.db.flush()
        return row

    # --- apps ---

    def get_app_by_slug(self, slug: str) -> CatalogApp | None:
        return self.db.scalar(
            select(CatalogApp)
            .options(
                joinedload(CatalogApp.category),
                selectinload(CatalogApp.plans).selectinload(AppPlan.entitlements),
            )
            .where(CatalogApp.slug == slug)
        )

    def get_app_by_id(self, app_id: uuid.UUID) -> CatalogApp | None:
        return self.db.scalar(
            select(CatalogApp)
            .options(
                joinedload(CatalogApp.category),
                selectinload(CatalogApp.plans).selectinload(AppPlan.entitlements),
            )
            .where(CatalogApp.id == app_id)
        )

    def list_catalog_apps(
        self,
        *,
        category_slug: str | None = None,
        billing_type: str | None = None,
        q: str | None = None,
        include_statuses: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CatalogApp], int]:
        statuses = include_statuses or [
            AppStatus.PUBLISHED.value,
            AppStatus.COMING_SOON.value,
        ]
        filters: list[Any] = [CatalogApp.status.in_(statuses)]
        if category_slug:
            filters.append(AppCategory.slug == category_slug)
        if billing_type:
            filters.append(CatalogApp.billing_type == billing_type)
        if q:
            term = f"%{q.strip()}%"
            filters.append(
                or_(
                    CatalogApp.name.ilike(term),
                    CatalogApp.short_description.ilike(term),
                    CatalogApp.slug.ilike(term),
                )
            )

        base = (
            select(CatalogApp)
            .join(AppCategory, CatalogApp.category_id == AppCategory.id)
            .where(and_(*filters))
        )
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        items = list(
            self.db.scalars(
                base.options(
                    joinedload(CatalogApp.category),
                    selectinload(CatalogApp.plans).selectinload(AppPlan.entitlements),
                )
                .order_by(
                    CatalogApp.is_featured.desc(),
                    CatalogApp.sort_order.asc(),
                    CatalogApp.name.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def upsert_app(self, row: CatalogApp) -> CatalogApp:
        self.db.add(row)
        self.db.flush()
        return row

    def get_plan_by_id(self, plan_id: uuid.UUID) -> AppPlan | None:
        return self.db.scalar(
            select(AppPlan)
            .options(selectinload(AppPlan.entitlements), joinedload(AppPlan.app))
            .where(AppPlan.id == plan_id)
        )

    def get_plan_by_code(self, app_id: uuid.UUID, code: str) -> AppPlan | None:
        return self.db.scalar(
            select(AppPlan)
            .options(selectinload(AppPlan.entitlements))
            .where(AppPlan.app_id == app_id, AppPlan.code == code)
        )

    def upsert_plan(self, row: AppPlan) -> AppPlan:
        self.db.add(row)
        self.db.flush()
        return row

    def upsert_entitlement(self, row: AppPlanEntitlement) -> AppPlanEntitlement:
        self.db.add(row)
        self.db.flush()
        return row

    def get_entitlement(self, plan_id: uuid.UUID, key: str) -> AppPlanEntitlement | None:
        return self.db.scalar(
            select(AppPlanEntitlement).where(
                AppPlanEntitlement.app_plan_id == plan_id,
                AppPlanEntitlement.key == key,
            )
        )

    def delete_entitlement(self, plan_id: uuid.UUID, key: str) -> None:
        row = self.get_entitlement(plan_id, key)
        if row is not None:
            self.db.delete(row)
            self.db.flush()

    # --- installations (always workspace-scoped) ---

    def get_installation_for_workspace(
        self, workspace_id: uuid.UUID, installation_id: uuid.UUID
    ) -> AppInstallation | None:
        return self.db.scalar(
            select(AppInstallation)
            .options(
                joinedload(AppInstallation.app).joinedload(CatalogApp.category),
                joinedload(AppInstallation.app)
                .selectinload(CatalogApp.plans)
                .selectinload(AppPlan.entitlements),
            )
            .where(
                AppInstallation.id == installation_id,
                AppInstallation.workspace_id == workspace_id,
            )
        )

    def get_installation_by_id(self, installation_id: uuid.UUID) -> AppInstallation | None:
        return self.db.scalar(
            select(AppInstallation).where(AppInstallation.id == installation_id)
        )

    def get_installation_by_app(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppInstallation | None:
        return self.db.scalar(
            select(AppInstallation).where(
                AppInstallation.workspace_id == workspace_id,
                AppInstallation.app_id == app_id,
            )
        )

    def get_installation_for_update(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppInstallation | None:
        return self.db.scalar(
            select(AppInstallation)
            .where(
                AppInstallation.workspace_id == workspace_id,
                AppInstallation.app_id == app_id,
            )
            .with_for_update()
        )

    def list_installations(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None = AppInstallationStatus.ACTIVE.value,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AppInstallation], int]:
        filters: list[Any] = [AppInstallation.workspace_id == workspace_id]
        if status:
            filters.append(AppInstallation.status == status)
        base = select(AppInstallation).where(and_(*filters))
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        items = list(
            self.db.scalars(
                base.options(
                    joinedload(AppInstallation.app).joinedload(CatalogApp.category),
                    joinedload(AppInstallation.app)
                    .selectinload(CatalogApp.plans)
                    .selectinload(AppPlan.entitlements),
                )
                .order_by(AppInstallation.installed_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def map_active_installations_by_app_id(
        self, workspace_id: uuid.UUID, app_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AppInstallation]:
        if not app_ids:
            return {}
        rows = list(
            self.db.scalars(
                select(AppInstallation).where(
                    AppInstallation.workspace_id == workspace_id,
                    AppInstallation.app_id.in_(app_ids),
                    AppInstallation.status == AppInstallationStatus.ACTIVE.value,
                )
            )
        )
        return {row.app_id: row for row in rows}

    def map_installations_by_app_id(
        self, workspace_id: uuid.UUID, app_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AppInstallation]:
        if not app_ids:
            return {}
        rows = list(
            self.db.scalars(
                select(AppInstallation).where(
                    AppInstallation.workspace_id == workspace_id,
                    AppInstallation.app_id.in_(app_ids),
                )
            )
        )
        return {row.app_id: row for row in rows}

    def create_installation(self, row: AppInstallation) -> AppInstallation:
        self.db.add(row)
        self.db.flush()
        return row

    # --- licenses / subscriptions (workspace-scoped) ---

    def get_license(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppLicense | None:
        return self.db.scalar(
            select(AppLicense)
            .options(joinedload(AppLicense.plan))
            .where(
                AppLicense.workspace_id == workspace_id,
                AppLicense.app_id == app_id,
            )
        )

    def get_license_for_update(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppLicense | None:
        return self.db.scalar(
            select(AppLicense)
            .where(
                AppLicense.workspace_id == workspace_id,
                AppLicense.app_id == app_id,
            )
            .with_for_update()
        )

    def get_active_license(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppLicense | None:
        return self.db.scalar(
            select(AppLicense)
            .options(joinedload(AppLicense.plan))
            .where(
                AppLicense.workspace_id == workspace_id,
                AppLicense.app_id == app_id,
                AppLicense.status == AppLicenseStatus.ACTIVE.value,
            )
        )

    def create_license(self, row: AppLicense) -> AppLicense:
        self.db.add(row)
        self.db.flush()
        return row

    def get_subscription(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppSubscription | None:
        return self.db.scalar(
            select(AppSubscription)
            .options(joinedload(AppSubscription.plan))
            .where(
                AppSubscription.workspace_id == workspace_id,
                AppSubscription.app_id == app_id,
            )
        )

    def get_subscription_for_update(
        self, workspace_id: uuid.UUID, app_id: uuid.UUID
    ) -> AppSubscription | None:
        return self.db.scalar(
            select(AppSubscription)
            .where(
                AppSubscription.workspace_id == workspace_id,
                AppSubscription.app_id == app_id,
            )
            .with_for_update()
        )

    def create_subscription(self, row: AppSubscription) -> AppSubscription:
        self.db.add(row)
        self.db.flush()
        return row

    def map_licenses_by_app_id(
        self, workspace_id: uuid.UUID, app_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AppLicense]:
        if not app_ids:
            return {}
        rows = list(
            self.db.scalars(
                select(AppLicense)
                .options(joinedload(AppLicense.plan))
                .where(
                    AppLicense.workspace_id == workspace_id,
                    AppLicense.app_id.in_(app_ids),
                )
            )
        )
        return {row.app_id: row for row in rows}

    def map_subscriptions_by_app_id(
        self, workspace_id: uuid.UUID, app_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AppSubscription]:
        if not app_ids:
            return {}
        rows = list(
            self.db.scalars(
                select(AppSubscription)
                .options(joinedload(AppSubscription.plan))
                .where(
                    AppSubscription.workspace_id == workspace_id,
                    AppSubscription.app_id.in_(app_ids),
                )
            )
        )
        return {row.app_id: row for row in rows}

    # --- platform admin ---

    def get_license_by_idempotency_key(self, key: str) -> AppLicense | None:
        return self.db.scalar(
            select(AppLicense)
            .options(joinedload(AppLicense.plan))
            .where(AppLicense.grant_idempotency_key == key)
        )

    def get_subscription_by_idempotency_key(self, key: str) -> AppSubscription | None:
        return self.db.scalar(
            select(AppSubscription)
            .options(joinedload(AppSubscription.plan))
            .where(AppSubscription.grant_idempotency_key == key)
        )

    def count_admin_apps(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        billing_type: str | None = None,
        category_slug: str | None = None,
        connector_kind: str | None = None,
    ) -> int:
        base = self._admin_apps_base(
            search=search,
            status=status,
            billing_type=billing_type,
            category_slug=category_slug,
            connector_kind=connector_kind,
        )
        return int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)

    def list_admin_apps(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        billing_type: str | None = None,
        category_slug: str | None = None,
        connector_kind: str | None = None,
    ) -> list[CatalogApp]:
        base = self._admin_apps_base(
            search=search,
            status=status,
            billing_type=billing_type,
            category_slug=category_slug,
            connector_kind=connector_kind,
        )
        return list(
            self.db.scalars(
                base.options(
                    joinedload(CatalogApp.category),
                    selectinload(CatalogApp.plans),
                )
                .order_by(CatalogApp.sort_order.asc(), CatalogApp.name.asc())
                .limit(limit)
                .offset(offset)
            )
        )

    def count_installations_by_app_ids(self, app_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not app_ids:
            return {}
        rows = self.db.execute(
            select(AppInstallation.app_id, func.count())
            .where(
                AppInstallation.app_id.in_(app_ids),
                AppInstallation.status == AppInstallationStatus.ACTIVE.value,
            )
            .group_by(AppInstallation.app_id)
        ).all()
        return {app_id: int(count) for app_id, count in rows}

    def count_active_licenses_by_app_ids(self, app_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not app_ids:
            return {}
        rows = self.db.execute(
            select(AppLicense.app_id, func.count())
            .where(
                AppLicense.app_id.in_(app_ids),
                AppLicense.status == AppLicenseStatus.ACTIVE.value,
            )
            .group_by(AppLicense.app_id)
        ).all()
        return {app_id: int(count) for app_id, count in rows}

    def count_active_subscriptions_by_app_ids(
        self, app_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not app_ids:
            return {}
        rows = self.db.execute(
            select(AppSubscription.app_id, func.count())
            .where(
                AppSubscription.app_id.in_(app_ids),
                AppSubscription.status == AppSubscriptionStatus.ACTIVE.value,
            )
            .group_by(AppSubscription.app_id)
        ).all()
        return {app_id: int(count) for app_id, count in rows}

    def count_active_entitlements_by_app_ids(
        self, app_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        lic = self.count_active_licenses_by_app_ids(app_ids)
        sub = self.count_active_subscriptions_by_app_ids(app_ids)
        return {app_id: lic.get(app_id, 0) + sub.get(app_id, 0) for app_id in app_ids}

    def count_plan_commercial_by_plan_ids(
        self, plan_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not plan_ids:
            return {}
        out: dict[uuid.UUID, int] = {pid: 0 for pid in plan_ids}
        lic_rows = self.db.execute(
            select(AppLicense.app_plan_id, func.count())
            .where(
                AppLicense.app_plan_id.in_(plan_ids),
                AppLicense.status == AppLicenseStatus.ACTIVE.value,
            )
            .group_by(AppLicense.app_plan_id)
        ).all()
        sub_rows = self.db.execute(
            select(AppSubscription.app_plan_id, func.count())
            .where(
                AppSubscription.app_plan_id.in_(plan_ids),
                AppSubscription.status == AppSubscriptionStatus.ACTIVE.value,
            )
            .group_by(AppSubscription.app_plan_id)
        ).all()
        for plan_id, count in lic_rows:
            out[plan_id] = out.get(plan_id, 0) + int(count)
        for plan_id, count in sub_rows:
            out[plan_id] = out.get(plan_id, 0) + int(count)
        return out

    def app_has_commercial_history(self, app_id: uuid.UUID) -> bool:
        if int(
            self.db.scalar(
                select(func.count()).select_from(AppLicense).where(AppLicense.app_id == app_id)
            )
            or 0
        ):
            return True
        if int(
            self.db.scalar(
                select(func.count())
                .select_from(AppSubscription)
                .where(AppSubscription.app_id == app_id)
            )
            or 0
        ):
            return True
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(AppInstallation)
                .where(
                    AppInstallation.app_id == app_id,
                    AppInstallation.status != AppInstallationStatus.UNINSTALLED.value,
                )
            )
            or 0
        ) > 0

    def plan_has_commercial_history(self, plan_id: uuid.UUID) -> bool:
        if int(
            self.db.scalar(
                select(func.count())
                .select_from(AppLicense)
                .where(AppLicense.app_plan_id == plan_id)
            )
            or 0
        ):
            return True
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(AppSubscription)
                .where(AppSubscription.app_plan_id == plan_id)
            )
            or 0
        ) > 0

    def list_all_categories(self) -> list[AppCategory]:
        return list(
            self.db.scalars(
                select(AppCategory).order_by(
                    AppCategory.sort_order.asc(), AppCategory.slug.asc()
                )
            )
        )

    def list_app_workspace_entitlements(
        self,
        app_id: uuid.UUID,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[tuple[uuid.UUID, AppLicense | None, AppSubscription | None]], int]:
        from app.workspaces.models import Workspace

        lic_rows = list(
            self.db.scalars(
                select(AppLicense)
                .options(joinedload(AppLicense.plan))
                .where(AppLicense.app_id == app_id)
                .order_by(AppLicense.granted_at.desc())
            )
        )
        sub_rows = list(
            self.db.scalars(
                select(AppSubscription)
                .options(joinedload(AppSubscription.plan))
                .where(AppSubscription.app_id == app_id)
                .order_by(AppSubscription.created_at.desc())
            )
        )
        by_ws: dict[uuid.UUID, tuple[AppLicense | None, AppSubscription | None]] = {}
        for lic in lic_rows:
            bucket = by_ws.setdefault(lic.workspace_id, (None, None))
            by_ws[lic.workspace_id] = (lic, bucket[1])
        for sub in sub_rows:
            bucket = by_ws.setdefault(sub.workspace_id, (None, None))
            by_ws[sub.workspace_id] = (bucket[0], sub)
        if not by_ws:
            return [], 0
        live_workspace_ids = set(
            self.db.scalars(
                select(Workspace.id).where(
                    Workspace.id.in_(by_ws.keys()),
                    Workspace.deleted_at.is_(None),
                )
            )
        )
        workspace_ids = sorted(
            (ws_id for ws_id in by_ws if ws_id in live_workspace_ids),
            reverse=True,
        )
        total = len(workspace_ids)
        page = workspace_ids[offset : offset + limit]
        items = [(ws_id, *by_ws[ws_id]) for ws_id in page]
        return items, total

    @staticmethod
    def _admin_apps_base(
        *,
        search: str | None,
        status: str | None,
        billing_type: str | None,
        category_slug: str | None,
        connector_kind: str | None,
    ):
        filters: list[Any] = []
        if status:
            filters.append(CatalogApp.status == status.strip().lower())
        if billing_type:
            filters.append(CatalogApp.billing_type == billing_type.strip().lower())
        if connector_kind:
            filters.append(CatalogApp.connector_kind == connector_kind.strip().lower())
        if category_slug:
            filters.append(AppCategory.slug == category_slug.strip().lower())
        if search:
            from app.documents.repository import ilike_contains_pattern

            pattern = ilike_contains_pattern(search)
            filters.append(
                or_(
                    CatalogApp.name.ilike(pattern),
                    CatalogApp.short_description.ilike(pattern),
                    CatalogApp.slug.ilike(pattern),
                    CatalogApp.description.ilike(pattern),
                )
            )
        stmt = select(CatalogApp).join(
            AppCategory, CatalogApp.category_id == AppCategory.id
        )
        if filters:
            stmt = stmt.where(and_(*filters))
        return stmt
