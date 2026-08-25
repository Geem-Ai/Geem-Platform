"""Authoritative App commercial access resolution (Phase 9B).

Connectors (9C+) should ask this service — not licenses/subscriptions directly.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType

from sqlalchemy import and_, bindparam, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.calendar import ensure_utc
from app.apps_catalog.models import (
    AppBillingType,
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
from app.apps_catalog.repository import AppCatalogRepository
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace, WorkspaceKind, WorkspaceStatus

logger = logging.getLogger(__name__)


class AppAccessStatus(StrEnum):
    NOT_ENTITLED = "not_entitled"
    ENTITLED_NOT_INSTALLED = "entitled_not_installed"
    ACTIVE = "active"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AppAccessSnapshot:
    status: AppAccessStatus
    app_id: uuid.UUID
    app_slug: str
    billing_type: str
    plan_id: uuid.UUID | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    commercially_entitled: bool = False
    installed: bool = False
    can_purchase: bool = False
    can_renew: bool = False
    can_install: bool = False
    can_uninstall: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeAppAccessSnapshot:
    """Compact, request-local authority returned by the one fresh data SELECT."""

    decision_at: datetime
    workspace_id: uuid.UUID
    app_id: uuid.UUID
    app_slug: str
    installation_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    plan_code: str
    current_period_start: datetime
    current_period_end: datetime
    entitlements: Mapping[str, int]

    def entitlement(self, key: str) -> int:
        return int(self.entitlements[key])


class AppAccessService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AppCatalogRepository(db)

    def resolve(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str | None = None,
        app_id: uuid.UUID | None = None,
        can_manage: bool = False,
        now: datetime | None = None,
        app: CatalogApp | None = None,
        installation: AppInstallation | None = None,
        license_row: AppLicense | None = None,
        subscription: AppSubscription | None = None,
        normalize_subscription_status: bool = True,
    ) -> AppAccessSnapshot:
        moment = ensure_utc(now or datetime.now(timezone.utc))
        catalog = app or self._load_app(app_slug=app_slug, app_id=app_id)
        if catalog is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")

        inst = installation
        if inst is None:
            inst = self.repo.get_installation_by_app(workspace_id, catalog.id)
        installed = (
            inst is not None and inst.status == AppInstallationStatus.ACTIVE.value
        )

        if catalog.status in {AppStatus.DRAFT.value, AppStatus.DISABLED.value}:
            return AppAccessSnapshot(
                status=AppAccessStatus.UNAVAILABLE,
                app_id=catalog.id,
                app_slug=catalog.slug,
                billing_type=catalog.billing_type,
                installed=installed,
                can_uninstall=bool(can_manage and installed),
            )
        if catalog.status == AppStatus.COMING_SOON.value:
            return AppAccessSnapshot(
                status=AppAccessStatus.UNAVAILABLE,
                app_id=catalog.id,
                app_slug=catalog.slug,
                billing_type=catalog.billing_type,
                installed=installed,
                can_uninstall=bool(can_manage and installed),
            )

        billing = catalog.billing_type
        if billing == AppBillingType.FREE.value:
            return self._resolve_free(
                catalog, installed=installed, can_manage=can_manage
            )
        if billing == AppBillingType.ONE_TIME.value:
            lic = license_row
            if lic is None:
                lic = self.repo.get_license(workspace_id, catalog.id)
            return self._resolve_one_time(
                catalog, lic, installed=installed, can_manage=can_manage
            )
        if billing == AppBillingType.SUBSCRIPTION.value:
            sub = subscription
            if sub is None:
                sub = self.repo.get_subscription(workspace_id, catalog.id)
            if sub is not None and normalize_subscription_status:
                self._normalize_subscription_status(sub, moment)
            return self._resolve_subscription(
                catalog,
                sub,
                installed=installed,
                can_manage=can_manage,
                now=moment,
            )
        return AppAccessSnapshot(
            status=AppAccessStatus.UNAVAILABLE,
            app_id=catalog.id,
            app_slug=catalog.slug,
            billing_type=billing,
            installed=installed,
        )

    def require_active(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str,
        now: datetime | None = None,
    ) -> AppAccessSnapshot:
        access = self.resolve(workspace_id, app_slug=app_slug, now=now)
        if access.status == AppAccessStatus.ACTIVE:
            return access
        if access.status == AppAccessStatus.EXPIRED:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
                "App subscription has expired.",
                details={"app_slug": app_slug},
            )
        if access.status == AppAccessStatus.ENTITLED_NOT_INSTALLED:
            raise AppError(
                ErrorCategory.APP_NOT_INSTALLED,
                "App is not installed in this workspace.",
                details={"app_slug": app_slug},
            )
        if access.status == AppAccessStatus.UNAVAILABLE:
            raise AppError(
                ErrorCategory.APP_NOT_AVAILABLE,
                "App is not available.",
                details={"app_slug": app_slug},
            )
        if access.billing_type == AppBillingType.SUBSCRIPTION.value:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                "A valid App subscription is required.",
                details={"app_slug": app_slug},
            )
        raise AppError(
            ErrorCategory.APP_BILLING_REQUIRED,
            "This app requires a purchase or subscription before use.",
            details={"app_slug": app_slug, "billing_type": access.billing_type},
        )

    def require_runtime_active(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str,
        entitlement_keys: Sequence[str] = (),
    ) -> RuntimeAppAccessSnapshot:
        """Resolve current paid access and requested limits in one fresh SELECT.

        This method performs no writes and deliberately uses Core column tuples,
        not ORM entities, so loaded identity-map state cannot authorize access.
        The caller owns the short admission transaction and advisory fences.
        """
        slug = (app_slug or "").strip().lower()
        keys = tuple(dict.fromkeys((key or "").strip() for key in entitlement_keys))
        if not slug or any(not key for key in keys):
            raise AppError(ErrorCategory.VALIDATION, "App slug and entitlement keys are required.")

        clock = select(func.statement_timestamp().label("decision_at")).cte(
            "runtime_clock"
        )
        if keys:
            entitlement_values = (
                select(
                    func.coalesce(
                        func.jsonb_object_agg(
                            AppPlanEntitlement.key, AppPlanEntitlement.value
                        ),
                        literal({}, type_=JSONB),
                    )
                )
                .where(
                    AppPlanEntitlement.app_plan_id == AppPlan.id,
                    AppPlanEntitlement.key.in_(bindparam("entitlement_keys", expanding=True)),
                )
                .correlate(AppPlan)
                .scalar_subquery()
            )
        else:
            entitlement_values = literal({}, type_=JSONB)

        stmt = (
            select(
                clock.c.decision_at,
                Workspace.id.label("workspace_id"),
                Workspace.kind.label("workspace_kind"),
                Workspace.status.label("workspace_status"),
                Workspace.deleted_at.label("workspace_deleted_at"),
                CatalogApp.id.label("app_id"),
                CatalogApp.status.label("app_status"),
                CatalogApp.billing_type.label("app_billing_type"),
                AppInstallation.id.label("installation_id"),
                AppInstallation.status.label("installation_status"),
                AppSubscription.id.label("subscription_id"),
                AppSubscription.status.label("subscription_status"),
                AppSubscription.current_period_start,
                AppSubscription.current_period_end,
                AppPlan.id.label("plan_id"),
                AppPlan.app_id.label("plan_app_id"),
                AppPlan.code.label("plan_code"),
                entitlement_values.label("entitlements"),
            )
            .select_from(clock)
            .outerjoin(Workspace, Workspace.id == bindparam("workspace_id"))
            .outerjoin(CatalogApp, CatalogApp.slug == bindparam("app_slug"))
            .outerjoin(
                AppInstallation,
                and_(
                    AppInstallation.workspace_id == Workspace.id,
                    AppInstallation.app_id == CatalogApp.id,
                ),
            )
            .outerjoin(
                AppSubscription,
                and_(
                    AppSubscription.workspace_id == Workspace.id,
                    AppSubscription.app_id == CatalogApp.id,
                ),
            )
            .outerjoin(
                AppPlan,
                and_(
                    AppPlan.id == AppSubscription.app_plan_id,
                    AppPlan.app_id == CatalogApp.id,
                ),
            )
        )
        params: dict[str, object] = {
            "workspace_id": workspace_id,
            "app_slug": slug,
        }
        if keys:
            params["entitlement_keys"] = list(keys)
        select_started = time.perf_counter()
        try:
            row = self.db.execute(stmt, params).mappings().one()
        except SQLAlchemyError as exc:
            logger.warning(
                "app_runtime_access_select",
                extra={
                    "workspace_id": str(workspace_id),
                    "app_slug": slug,
                    "status": "database_error",
                    "data_select_count": 1,
                    "entitlement_key_count": len(keys),
                    "latency_ms": round(
                        (time.perf_counter() - select_started) * 1_000,
                        2,
                    ),
                },
            )
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Paid App runtime access is temporarily unavailable.",
                retryable=True,
            ) from exc
        logger.info(
            "app_runtime_access_select",
            extra={
                "workspace_id": str(workspace_id),
                "app_slug": slug,
                "status": "resolved",
                "data_select_count": 1,
                "entitlement_key_count": len(keys),
                "latency_ms": round(
                    (time.perf_counter() - select_started) * 1_000,
                    2,
                ),
            },
        )

        decision_at = ensure_utc(row["decision_at"])
        if (
            row["workspace_id"] is None
            or row["workspace_kind"] != WorkspaceKind.TENANT.value
            or row["workspace_status"] != WorkspaceStatus.ACTIVE.value
            or row["workspace_deleted_at"] is not None
        ):
            raise AppError(ErrorCategory.WORKSPACE_ACCESS_DENIED, "Workspace access denied.")
        if (
            row["app_id"] is None
            or row["app_status"] != AppStatus.PUBLISHED.value
            or row["app_billing_type"] != AppBillingType.SUBSCRIPTION.value
        ):
            raise AppError(
                ErrorCategory.APP_NOT_AVAILABLE,
                "App is not available.",
                details={"app_slug": slug},
            )
        if (
            row["installation_id"] is None
            or row["installation_status"] != AppInstallationStatus.ACTIVE.value
        ):
            raise AppError(
                ErrorCategory.APP_NOT_INSTALLED,
                "App is not installed in this workspace.",
                details={"app_slug": slug},
            )
        if row["subscription_id"] is None:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                "A valid App subscription is required.",
                details={"app_slug": slug},
            )
        start = row["current_period_start"]
        end = row["current_period_end"]
        if (
            row["subscription_status"] != AppSubscriptionStatus.ACTIVE.value
            or start is None
            or end is None
            or not (ensure_utc(start) <= decision_at < ensure_utc(end))
        ):
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
                "App subscription has expired.",
                details={"app_slug": slug},
            )
        if row["plan_id"] is None or row["plan_app_id"] != row["app_id"]:
            raise AppError(
                ErrorCategory.ENTITLEMENT_INVALID,
                "The subscribed App plan is invalid.",
                details={"app_slug": slug},
            )

        raw_entitlements = dict(row["entitlements"] or {})
        parsed_entitlements: dict[str, int] = {}
        for key in keys:
            value = raw_entitlements.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise AppError(
                    ErrorCategory.ENTITLEMENT_INVALID,
                    "A positive App plan entitlement is required.",
                    details={"app_slug": slug, "key": key},
                )
            parsed_entitlements[key] = value

        return RuntimeAppAccessSnapshot(
            decision_at=decision_at,
            workspace_id=row["workspace_id"],
            app_id=row["app_id"],
            app_slug=slug,
            installation_id=row["installation_id"],
            subscription_id=row["subscription_id"],
            plan_id=row["plan_id"],
            plan_code=row["plan_code"],
            current_period_start=ensure_utc(start),
            current_period_end=ensure_utc(end),
            entitlements=MappingProxyType(parsed_entitlements),
        )

    def effective_plan(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str | None = None,
        app_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> AppPlan | None:
        access = self.resolve(
            workspace_id, app_slug=app_slug, app_id=app_id, now=now
        )
        if not access.commercially_entitled or access.plan_id is None:
            return None
        return self.repo.get_plan_by_id(access.plan_id)

    def _load_app(
        self, *, app_slug: str | None, app_id: uuid.UUID | None
    ) -> CatalogApp | None:
        if app_slug:
            return self.repo.get_app_by_slug(app_slug)
        if app_id:
            return self.repo.get_app_by_id(app_id)
        raise AppError(ErrorCategory.VALIDATION, "App slug or id is required.")

    @staticmethod
    def _resolve_free(
        app: CatalogApp, *, installed: bool, can_manage: bool
    ) -> AppAccessSnapshot:
        default_plan = _default_plan(app)
        if installed:
            status = AppAccessStatus.ACTIVE
        else:
            status = AppAccessStatus.ENTITLED_NOT_INSTALLED
        return AppAccessSnapshot(
            status=status,
            app_id=app.id,
            app_slug=app.slug,
            billing_type=app.billing_type,
            plan_id=default_plan.id if default_plan else None,
            plan_code=default_plan.code if default_plan else None,
            plan_name=default_plan.name if default_plan else None,
            commercially_entitled=True,
            installed=installed,
            can_purchase=False,
            can_renew=False,
            can_install=bool(can_manage and not installed),
            can_uninstall=bool(can_manage and installed),
        )

    @staticmethod
    def _resolve_one_time(
        app: CatalogApp,
        license_row: AppLicense | None,
        *,
        installed: bool,
        can_manage: bool,
    ) -> AppAccessSnapshot:
        active_license = (
            license_row is not None
            and license_row.status == AppLicenseStatus.ACTIVE.value
        )
        plan = license_row.plan if license_row is not None else None
        if not active_license:
            return AppAccessSnapshot(
                status=AppAccessStatus.NOT_ENTITLED,
                app_id=app.id,
                app_slug=app.slug,
                billing_type=app.billing_type,
                installed=installed,
                commercially_entitled=False,
                can_purchase=bool(can_manage and app.status == AppStatus.PUBLISHED.value),
                can_install=False,
                can_uninstall=bool(can_manage and installed),
            )
        if installed:
            status = AppAccessStatus.ACTIVE
        else:
            status = AppAccessStatus.ENTITLED_NOT_INSTALLED
        return AppAccessSnapshot(
            status=status,
            app_id=app.id,
            app_slug=app.slug,
            billing_type=app.billing_type,
            plan_id=license_row.app_plan_id if license_row else None,
            plan_code=plan.code if plan else None,
            plan_name=plan.name if plan else None,
            commercially_entitled=True,
            installed=installed,
            can_purchase=False,
            can_renew=False,
            can_install=bool(can_manage and not installed),
            can_uninstall=bool(can_manage and installed),
        )

    @staticmethod
    def _resolve_subscription(
        app: CatalogApp,
        subscription: AppSubscription | None,
        *,
        installed: bool,
        can_manage: bool,
        now: datetime,
    ) -> AppAccessSnapshot:
        published = app.status == AppStatus.PUBLISHED.value
        if subscription is None:
            return AppAccessSnapshot(
                status=AppAccessStatus.NOT_ENTITLED,
                app_id=app.id,
                app_slug=app.slug,
                billing_type=app.billing_type,
                installed=installed,
                can_purchase=bool(can_manage and published),
                can_renew=False,
                can_install=False,
                can_uninstall=bool(can_manage and installed),
            )

        period_end = ensure_utc(subscription.current_period_end)
        period_start = ensure_utc(subscription.current_period_start)
        plan = subscription.plan
        valid = (
            subscription.status == AppSubscriptionStatus.ACTIVE.value
            and period_end > now
        )
        if valid:
            if installed:
                status = AppAccessStatus.ACTIVE
            else:
                status = AppAccessStatus.ENTITLED_NOT_INSTALLED
            return AppAccessSnapshot(
                status=status,
                app_id=app.id,
                app_slug=app.slug,
                billing_type=app.billing_type,
                plan_id=subscription.app_plan_id,
                plan_code=plan.code if plan else None,
                plan_name=plan.name if plan else None,
                current_period_start=period_start,
                current_period_end=period_end,
                commercially_entitled=True,
                installed=installed,
                can_purchase=False,
                can_renew=bool(can_manage),
                can_install=bool(can_manage and not installed),
                can_uninstall=bool(can_manage and installed),
            )

        return AppAccessSnapshot(
            status=AppAccessStatus.EXPIRED,
            app_id=app.id,
            app_slug=app.slug,
            billing_type=app.billing_type,
            plan_id=subscription.app_plan_id,
            plan_code=plan.code if plan else None,
            plan_name=plan.name if plan else None,
            current_period_start=period_start,
            current_period_end=period_end,
            commercially_entitled=False,
            installed=installed,
            can_purchase=False,
            can_renew=bool(can_manage and published),
            can_install=False,
            can_uninstall=bool(can_manage and installed),
        )

    @staticmethod
    def _normalize_subscription_status(
        subscription: AppSubscription, now: datetime
    ) -> None:
        if (
            subscription.status == AppSubscriptionStatus.ACTIVE.value
            and ensure_utc(subscription.current_period_end) <= now
        ):
            subscription.status = AppSubscriptionStatus.EXPIRED.value


def _default_plan(app: CatalogApp) -> AppPlan | None:
    plans = [p for p in (app.plans or []) if p.is_active]
    if not plans:
        return None
    for plan in plans:
        if plan.is_default:
            return plan
    return sorted(plans, key=lambda p: (p.sort_order, p.code))[0]
