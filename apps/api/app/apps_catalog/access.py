"""Authoritative App commercial access resolution (Phase 9B).

Connectors (9C+) should ask this service — not licenses/subscriptions directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy.orm import Session

from app.apps_catalog.calendar import ensure_utc
from app.apps_catalog.models import (
    AppBillingType,
    AppInstallation,
    AppInstallationStatus,
    AppLicense,
    AppLicenseStatus,
    AppPlan,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.apps_catalog.repository import AppCatalogRepository
from app.core.errors import AppError, ErrorCategory


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
            if sub is not None:
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
