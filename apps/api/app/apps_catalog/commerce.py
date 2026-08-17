"""App Store checkout + fulfillment (Phase 9B).

Uses BillingService / BillingGateway — no parallel payment subsystem.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService, AppAccessStatus
from app.apps_catalog.calendar import (
    compute_renewal_period,
    ensure_utc,
    initial_period,
)
from app.apps_catalog.models import (
    AppBillingType,
    AppInstallation,
    AppInstallationStatus,
    AppLicense,
    AppLicenseStatus,
    AppPlan,
    AppPlanBillingInterval,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.apps_catalog.repository import AppCatalogRepository
from app.billing.checkout import BillingService
from app.billing.models import Purchase, PurchaseKind
from app.billing.money import normalize_currency, quantize_money
from app.billing.repository import PurchaseRepository
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.usage.locks import workspace_app_advisory_lock
from app.workspaces.models import Workspace, WorkspaceKind

logger = logging.getLogger(__name__)


class AppCommerceService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        billing: BillingService | None | bool = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = AppCatalogRepository(db)
        self.purchases = PurchaseRepository(db)
        self.access = AppAccessService(db)
        if billing is False:
            self.billing = None
        else:
            self.billing = billing or BillingService(db, self.settings)

    def _require_billing(self) -> BillingService:
        if self.billing is None:
            self.billing = BillingService(self.db, self.settings)
        return self.billing

    def create_checkout(
        self,
        workspace: Workspace,
        user: User,
        *,
        app_slug: str,
        plan_id: uuid.UUID,
        customer_ip: str | None = None,
        spa_origin: str | None = None,
    ) -> tuple[Purchase, str]:
        self._assert_tenant(workspace)
        app, plan = self._require_purchasable_plan(app_slug, plan_id)
        workspace_app_advisory_lock(self.db, workspace.id, app.id)
        access = self.access.resolve(
            workspace.id, app=app, app_slug=app.slug, can_manage=True
        )

        if app.billing_type == AppBillingType.ONE_TIME.value:
            if access.commercially_entitled:
                raise AppError(
                    ErrorCategory.APP_ALREADY_LICENSED,
                    "This workspace already owns a license for this app.",
                    details={"app_slug": app.slug},
                )
            kind = PurchaseKind.APP_ONE_TIME
            action = "purchase"
            open_kinds = [PurchaseKind.APP_ONE_TIME.value]
        elif app.billing_type == AppBillingType.SUBSCRIPTION.value:
            if access.status in {
                AppAccessStatus.ACTIVE,
                AppAccessStatus.ENTITLED_NOT_INSTALLED,
            }:
                raise AppError(
                    ErrorCategory.APP_SUBSCRIPTION_ALREADY_ACTIVE,
                    "An active App subscription already exists. Use renew instead.",
                    details={"app_slug": app.slug},
                )
            kind = PurchaseKind.APP_SUBSCRIPTION
            action = "subscribe"
            open_kinds = [PurchaseKind.APP_SUBSCRIPTION.value]
        else:
            raise AppError(
                ErrorCategory.APP_CHECKOUT_FORBIDDEN,
                "This app does not require checkout.",
                details={"app_slug": app.slug, "billing_type": app.billing_type},
            )

        self._assert_no_open_checkout(workspace.id, app.id, open_kinds, app.slug)

        amount, currency = self._canonical_price(plan)
        payload = self._snapshot_payload(
            app=app,
            plan=plan,
            kind=kind.value,
            action=action,
            amount=amount,
            currency=currency,
        )
        description = f"Geem App: {app.name} — {plan.name}"
        return self._require_billing().start_external_checkout(
            workspace,
            user,
            kind=kind,
            amount=amount,
            currency=currency,
            payload=payload,
            description=description,
            customer_ip=customer_ip,
            spa_origin=spa_origin,
        )

    def create_renewal_checkout(
        self,
        workspace: Workspace,
        user: User,
        *,
        app_slug: str,
        customer_ip: str | None = None,
        spa_origin: str | None = None,
        plan_id: uuid.UUID | None = None,
    ) -> tuple[Purchase, str]:
        self._assert_tenant(workspace)
        app = self._require_published_app(app_slug)
        if app.billing_type != AppBillingType.SUBSCRIPTION.value:
            raise AppError(
                ErrorCategory.APP_RENEWAL_NOT_ALLOWED,
                "Only subscription apps can be renewed.",
                details={"app_slug": app.slug},
            )
        workspace_app_advisory_lock(self.db, workspace.id, app.id)
        sub = self.repo.get_subscription(workspace.id, app.id)
        if sub is None:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                "No App subscription exists to renew.",
                details={"app_slug": app.slug},
            )

        plan = self.repo.get_plan_by_id(sub.app_plan_id)
        if plan is None:
            raise AppError(ErrorCategory.APP_PLAN_NOT_FOUND, "App plan not found.")
        if plan_id is not None and plan_id != plan.id:
            raise AppError(
                ErrorCategory.APP_PLAN_MISMATCH,
                "Renewal must use the current subscription plan.",
                details={
                    "app_slug": app.slug,
                    "current_plan_id": str(plan.id),
                    "requested_plan_id": str(plan_id),
                },
            )

        # Renewal allowed for active or expired; not mid-cycle plan switch.
        # Multiple open renewals are allowed — each paid renewal adds a month.
        amount, currency = self._canonical_price(plan, allow_inactive_plan=True)
        kind = PurchaseKind.APP_SUBSCRIPTION_RENEWAL
        payload = self._snapshot_payload(
            app=app,
            plan=plan,
            kind=kind.value,
            action="renew",
            amount=amount,
            currency=currency,
            subscription_id=str(sub.id),
        )
        description = f"Geem App renewal: {app.name} — {plan.name}"
        return self._require_billing().start_external_checkout(
            workspace,
            user,
            kind=kind,
            amount=amount,
            currency=currency,
            payload=payload,
            description=description,
            customer_ip=customer_ip,
            spa_origin=spa_origin,
        )

    def fulfill_purchase(self, purchase: Purchase) -> None:
        """Idempotent App fulfillment from immutable purchase snapshot."""
        kind = (purchase.payload or {}).get("kind") or purchase.kind
        if kind == PurchaseKind.APP_ONE_TIME.value:
            self.fulfill_one_time_purchase(purchase)
            return
        if kind in {
            PurchaseKind.APP_SUBSCRIPTION.value,
            PurchaseKind.APP_SUBSCRIPTION_RENEWAL.value,
        }:
            self.fulfill_subscription_purchase(purchase)
            return
        raise AppError(ErrorCategory.INVALID_PURCHASE, "Unknown App purchase kind.")

    def fulfill_one_time_purchase(self, purchase: Purchase) -> None:
        payload = purchase.payload or {}
        app_id = _uuid(payload.get("app_id"), "app_id")
        plan_id = _uuid(payload.get("app_plan_id") or payload.get("plan_id"), "plan_id")
        if purchase.workspace_id is None:
            raise AppError(ErrorCategory.INVALID_PURCHASE, "Purchase missing workspace.")

        workspace_app_advisory_lock(self.db, purchase.workspace_id, app_id)
        locked = self.repo.get_license_for_update(purchase.workspace_id, app_id)
        if locked is not None:
            if locked.purchase_id == purchase.id:
                self._activate_installation(
                    workspace_id=purchase.workspace_id,
                    app_id=app_id,
                    actor_id=purchase.actor_id,
                )
                return
            if locked.status == AppLicenseStatus.ACTIVE.value:
                # Duplicate paid grant (should be rare after checkout guard).
                logger.warning(
                    "app_license_duplicate_purchase",
                    extra={
                        "purchase_id": str(purchase.id),
                        "existing_purchase_id": str(locked.purchase_id),
                        "workspace_id": str(purchase.workspace_id),
                        "app_id": str(app_id),
                    },
                )
                self._activate_installation(
                    workspace_id=purchase.workspace_id,
                    app_id=app_id,
                    actor_id=purchase.actor_id,
                )
                return
            # Revoked (or other non-active) — re-activate the same unique row.
            now = datetime.now(timezone.utc)
            locked.status = AppLicenseStatus.ACTIVE.value
            locked.app_plan_id = plan_id
            locked.purchase_id = purchase.id
            locked.granted_at = now
            locked.revoked_at = None
            self.db.flush()
            self._activate_installation(
                workspace_id=purchase.workspace_id,
                app_id=app_id,
                actor_id=purchase.actor_id,
            )
            logger.info(
                "app_license_reactivated",
                extra={
                    "purchase_id": str(purchase.id),
                    "workspace_id": str(purchase.workspace_id),
                    "app_id": str(app_id),
                },
            )
            return

        license_row = AppLicense(
            workspace_id=purchase.workspace_id,
            app_id=app_id,
            app_plan_id=plan_id,
            purchase_id=purchase.id,
            status=AppLicenseStatus.ACTIVE.value,
            granted_at=datetime.now(timezone.utc),
        )
        try:
            with self.db.begin_nested():
                self.repo.create_license(license_row)
        except IntegrityError:
            locked = self.repo.get_license_for_update(purchase.workspace_id, app_id)
            if locked is None:
                raise
            if locked.purchase_id != purchase.id:
                logger.warning(
                    "app_license_duplicate_purchase",
                    extra={
                        "purchase_id": str(purchase.id),
                        "existing_purchase_id": str(locked.purchase_id),
                        "workspace_id": str(purchase.workspace_id),
                        "app_id": str(app_id),
                    },
                )
            self._activate_installation(
                workspace_id=purchase.workspace_id,
                app_id=app_id,
                actor_id=purchase.actor_id,
            )
            return

        self._activate_installation(
            workspace_id=purchase.workspace_id,
            app_id=app_id,
            actor_id=purchase.actor_id,
        )
        logger.info(
            "app_license_granted",
            extra={
                "purchase_id": str(purchase.id),
                "workspace_id": str(purchase.workspace_id),
                "app_id": str(app_id),
            },
        )

    def fulfill_subscription_purchase(self, purchase: Purchase) -> None:
        payload = purchase.payload or {}
        app_id = _uuid(payload.get("app_id"), "app_id")
        plan_id = _uuid(payload.get("app_plan_id") or payload.get("plan_id"), "plan_id")
        now = datetime.now(timezone.utc)
        action = str(payload.get("commercial_action") or "subscribe")
        if purchase.workspace_id is None:
            raise AppError(ErrorCategory.INVALID_PURCHASE, "Purchase missing workspace.")

        workspace_app_advisory_lock(self.db, purchase.workspace_id, app_id)
        sub = self.repo.get_subscription_for_update(purchase.workspace_id, app_id)
        if sub is not None and sub.latest_purchase_id == purchase.id:
            self._activate_installation(
                workspace_id=purchase.workspace_id,
                app_id=app_id,
                actor_id=purchase.actor_id,
            )
            return

        if sub is None:
            start, end = initial_period(now)
            sub = AppSubscription(
                workspace_id=purchase.workspace_id,
                app_id=app_id,
                app_plan_id=plan_id,
                status=AppSubscriptionStatus.ACTIVE.value,
                current_period_start=start,
                current_period_end=end,
                latest_purchase_id=purchase.id,
            )
            try:
                with self.db.begin_nested():
                    self.repo.create_subscription(sub)
            except IntegrityError:
                sub = self.repo.get_subscription_for_update(
                    purchase.workspace_id, app_id
                )
                if sub is None:
                    raise
                if sub.latest_purchase_id == purchase.id:
                    self._activate_installation(
                        workspace_id=purchase.workspace_id,
                        app_id=app_id,
                        actor_id=purchase.actor_id,
                    )
                    return
                self._apply_subscription_period(
                    sub, plan_id=plan_id, action=action, now=now, purchase=purchase
                )
        else:
            self._apply_subscription_period(
                sub, plan_id=plan_id, action=action, now=now, purchase=purchase
            )

        self._activate_installation(
            workspace_id=purchase.workspace_id,
            app_id=app_id,
            actor_id=purchase.actor_id,
        )
        logger.info(
            "app_subscription_fulfilled",
            extra={
                "purchase_id": str(purchase.id),
                "workspace_id": str(purchase.workspace_id),
                "app_id": str(app_id),
                "action": action,
                "period_end": sub.current_period_end.isoformat(),
            },
        )

    def _apply_subscription_period(
        self,
        sub: AppSubscription,
        *,
        plan_id: uuid.UUID,
        action: str,
        now: datetime,
        purchase: Purchase,
    ) -> None:
        if action == "renew" and sub.app_plan_id != plan_id:
            raise AppError(
                ErrorCategory.APP_PLAN_MISMATCH,
                "Renewal plan does not match the current subscription plan.",
            )
        period_still_valid = ensure_utc(sub.current_period_end) > ensure_utc(now)
        if action == "subscribe" and period_still_valid:
            # Concurrent/duplicate initial subscribe while period is live:
            # stack a paid month instead of resetting the anniversary.
            start, end = compute_renewal_period(
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                now=now,
            )
        elif action == "subscribe":
            start, end = initial_period(now)
            sub.app_plan_id = plan_id
        else:
            start, end = compute_renewal_period(
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                now=now,
            )
        sub.current_period_start = start
        sub.current_period_end = end
        sub.status = AppSubscriptionStatus.ACTIVE.value
        sub.latest_purchase_id = purchase.id
        self.db.flush()

    def _activate_installation(
        self,
        *,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> AppInstallation:
        now = datetime.now(timezone.utc)
        existing = self.repo.get_installation_for_update(workspace_id, app_id)
        if existing is None:
            row = AppInstallation(
                workspace_id=workspace_id,
                app_id=app_id,
                status=AppInstallationStatus.ACTIVE.value,
                installed_by_user_id=actor_id,
                installed_at=now,
                config_encrypted=None,
            )
            try:
                with self.db.begin_nested():
                    return self.repo.create_installation(row)
            except IntegrityError:
                existing = self.repo.get_installation_for_update(workspace_id, app_id)
                if existing is None:
                    raise
        if existing.status != AppInstallationStatus.ACTIVE.value:
            existing.status = AppInstallationStatus.ACTIVE.value
            existing.installed_by_user_id = actor_id
            existing.installed_at = now
            existing.uninstalled_at = None
            self.db.flush()
        return existing

    def _assert_no_open_checkout(
        self,
        workspace_id: uuid.UUID,
        app_id: uuid.UUID,
        kinds: list[str],
        app_slug: str,
    ) -> None:
        open_row = self.purchases.find_open_app_checkout(
            workspace_id, app_id=app_id, kinds=kinds
        )
        if open_row is not None:
            raise AppError(
                ErrorCategory.APP_CHECKOUT_IN_PROGRESS,
                "A checkout for this app is already in progress.",
                details={
                    "app_slug": app_slug,
                    "purchase_id": str(open_row.id),
                    "status": open_row.status,
                },
            )

    def _require_purchasable_plan(
        self, app_slug: str, plan_id: uuid.UUID
    ) -> tuple[CatalogApp, AppPlan]:
        app = self._require_published_app(app_slug)
        plan = self.repo.get_plan_by_id(plan_id)
        if plan is None or plan.app_id != app.id:
            raise AppError(ErrorCategory.APP_PLAN_NOT_FOUND, "App plan not found.")
        if not plan.is_active:
            raise AppError(
                ErrorCategory.APP_PLAN_INACTIVE,
                "App plan is inactive.",
                details={"plan_id": str(plan_id)},
            )
        self._validate_plan_matches_billing(app, plan)
        return app, plan

    def _require_published_app(self, app_slug: str) -> CatalogApp:
        app = self.repo.get_app_by_slug(app_slug)
        if app is None or app.status in {
            AppStatus.DRAFT.value,
            AppStatus.DISABLED.value,
        }:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        if app.status == AppStatus.COMING_SOON.value:
            raise AppError(
                ErrorCategory.APP_NOT_AVAILABLE,
                "App is not available for purchase yet.",
                details={"app_slug": app_slug},
            )
        if app.status != AppStatus.PUBLISHED.value:
            raise AppError(
                ErrorCategory.APP_NOT_AVAILABLE,
                "App is not available for purchase.",
                details={"app_slug": app_slug},
            )
        return app

    def _validate_plan_matches_billing(self, app: CatalogApp, plan: AppPlan) -> None:
        amount = quantize_money(plan.price_amount)
        if app.billing_type == AppBillingType.FREE.value:
            if amount != Decimal("0.00") or plan.billing_interval != AppPlanBillingInterval.NONE.value:
                raise AppError(
                    ErrorCategory.APP_PLAN_MISMATCH,
                    "Free app plan metadata is invalid.",
                )
            return
        if app.billing_type == AppBillingType.ONE_TIME.value:
            if (
                amount <= 0
                or plan.billing_interval != AppPlanBillingInterval.NONE.value
            ):
                raise AppError(
                    ErrorCategory.APP_PLAN_MISMATCH,
                    "One-time app plan must have a positive price and no interval.",
                )
            return
        if app.billing_type == AppBillingType.SUBSCRIPTION.value:
            if (
                amount <= 0
                or plan.billing_interval != AppPlanBillingInterval.MONTHLY.value
            ):
                raise AppError(
                    ErrorCategory.APP_PLAN_MISMATCH,
                    "Subscription app plan must be monthly with a positive price.",
                )
            return
        raise AppError(
            ErrorCategory.APP_PLAN_MISMATCH,
            "Unknown app billing type.",
            details={"billing_type": app.billing_type},
        )

    def _canonical_price(
        self, plan: AppPlan, *, allow_inactive_plan: bool = False
    ) -> tuple[Decimal, str]:
        if not plan.is_active and not allow_inactive_plan:
            raise AppError(ErrorCategory.APP_PLAN_INACTIVE, "App plan is inactive.")
        amount = quantize_money(plan.price_amount)
        if amount <= 0:
            raise AppError(
                ErrorCategory.APP_PURCHASE_NOT_PAYABLE,
                "App plan is not payable.",
            )
        currency = normalize_currency(plan.currency or self.settings.billing_currency)
        supported = {
            c.strip().upper()
            for c in (self.settings.billing_currency, "SAR")
            if c
        }
        # ClickPay v1 is SAR-only in this codebase.
        if currency != "SAR":
            raise AppError(
                ErrorCategory.APP_CURRENCY_NOT_SUPPORTED,
                "App checkout currency is not supported by the enabled gateway.",
                details={"currency": currency, "supported": ["SAR"]},
            )
        _ = supported
        return amount, currency

    @staticmethod
    def _snapshot_payload(
        *,
        app: CatalogApp,
        plan: AppPlan,
        kind: str,
        action: str,
        amount: Decimal,
        currency: str,
        subscription_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": kind,
            "commercial_action": action,
            "app_id": str(app.id),
            "app_slug": app.slug,
            "app_name": app.name,
            "app_billing_type": app.billing_type,
            "app_plan_id": str(plan.id),
            "plan_id": str(plan.id),
            "plan_code": plan.code,
            "plan_name": plan.name,
            "billing_interval": plan.billing_interval,
            "amount": str(amount),
            "currency": currency,
        }
        if subscription_id:
            payload["subscription_id"] = subscription_id
        return payload

    @staticmethod
    def _assert_tenant(workspace: Workspace) -> None:
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(
                ErrorCategory.SYSTEM_WORKSPACE_CHECKOUT_FORBIDDEN,
                "System workspaces cannot checkout.",
            )


def _uuid(raw: Any, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise AppError(
            ErrorCategory.INVALID_PURCHASE,
            f"Purchase snapshot is missing {field}.",
        ) from exc
