"""Platform Admin manual App commercial grants (Phase 12E).

Creates legitimate AppLicense / AppSubscription rows recognized by AppAccessService.
Does not fabricate purchases or payment records.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.calendar import compute_renewal_period, ensure_utc, initial_period
from app.apps_catalog.models import (
    AppBillingType,
    AppCommercialSource,
    AppLicense,
    AppLicenseStatus,
    AppPlan,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.runtime_locks import acquire_workspace_app_runtime_mutation_fence
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.usage.locks import workspace_app_advisory_lock
from app.workspaces.models import Workspace, WorkspaceKind


class AppAdminGrantService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AppCatalogRepository(db)
        self.access = AppAccessService(db)

    def grant_license(
        self,
        *,
        workspace: Workspace,
        app: CatalogApp,
        plan: AppPlan,
        actor: User,
        reason: str,
        idempotency_key: str,
    ) -> tuple[AppLicense, bool]:
        """Grant one-time license. Returns (license, idempotent_replay)."""
        self._assert_tenant(workspace)
        self._assert_one_time(app)
        self._validate_plan(app, plan, require_active=True)

        acquire_workspace_app_runtime_mutation_fence(
            self.db, workspace_id=workspace.id, app_slug=app.slug
        )
        workspace_app_advisory_lock(self.db, workspace.id, app.id)
        existing_by_key = self.repo.get_license_by_idempotency_key(idempotency_key)
        if existing_by_key is not None:
            if (
                existing_by_key.workspace_id != workspace.id
                or existing_by_key.app_id != app.id
            ):
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "Idempotency key already used for a different grant.",
                )
            return existing_by_key, True

        locked = self.repo.get_license_for_update(workspace.id, app.id)
        now = datetime.now(timezone.utc)
        if locked is not None:
            if locked.status == AppLicenseStatus.ACTIVE.value:
                raise AppError(
                    ErrorCategory.APP_ALREADY_LICENSED,
                    "This workspace already has an active license for this app.",
                )
            locked.status = AppLicenseStatus.ACTIVE.value
            locked.app_plan_id = plan.id
            locked.purchase_id = None
            locked.source = AppCommercialSource.PLATFORM_ADMIN.value
            locked.grant_idempotency_key = idempotency_key
            locked.granted_by_user_id = actor.id
            locked.granted_at = now
            locked.revoked_at = None
            self.db.flush()
            return locked, False

        row = AppLicense(
            workspace_id=workspace.id,
            app_id=app.id,
            app_plan_id=plan.id,
            purchase_id=None,
            source=AppCommercialSource.PLATFORM_ADMIN.value,
            grant_idempotency_key=idempotency_key,
            granted_by_user_id=actor.id,
            status=AppLicenseStatus.ACTIVE.value,
            granted_at=now,
        )
        try:
            with self.db.begin_nested():
                self.repo.create_license(row)
        except IntegrityError:
            replay = self.repo.get_license_by_idempotency_key(idempotency_key)
            if replay is not None:
                return replay, True
            locked = self.repo.get_license_for_update(workspace.id, app.id)
            if locked is not None:
                if locked.grant_idempotency_key == idempotency_key:
                    return locked, True
                if locked.status == AppLicenseStatus.ACTIVE.value:
                    return locked, False
            raise
        return row, False

    def revoke_license(
        self,
        *,
        workspace: Workspace,
        app: CatalogApp,
        actor: User,
        reason: str,
    ) -> AppLicense:
        self._assert_tenant(workspace)
        self._assert_one_time(app)
        acquire_workspace_app_runtime_mutation_fence(
            self.db, workspace_id=workspace.id, app_slug=app.slug
        )
        locked = self.repo.get_license_for_update(workspace.id, app.id)
        if locked is None or locked.status != AppLicenseStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.APP_BILLING_REQUIRED,
                "No active license exists for this workspace and app.",
            )
        now = datetime.now(timezone.utc)
        locked.status = AppLicenseStatus.REVOKED.value
        locked.revoked_at = now
        self.db.flush()
        return locked

    def grant_subscription(
        self,
        *,
        workspace: Workspace,
        app: CatalogApp,
        plan: AppPlan,
        actor: User,
        reason: str,
        idempotency_key: str,
    ) -> tuple[AppSubscription, bool]:
        self._assert_tenant(workspace)
        self._assert_subscription(app)
        self._validate_plan(app, plan, require_active=True)

        acquire_workspace_app_runtime_mutation_fence(
            self.db, workspace_id=workspace.id, app_slug=app.slug
        )
        workspace_app_advisory_lock(self.db, workspace.id, app.id)
        existing_by_key = self.repo.get_subscription_by_idempotency_key(idempotency_key)
        if existing_by_key is not None:
            if (
                existing_by_key.workspace_id != workspace.id
                or existing_by_key.app_id != app.id
            ):
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "Idempotency key already used for a different grant.",
                )
            return existing_by_key, True

        now = datetime.now(timezone.utc)
        sub = self.repo.get_subscription_for_update(workspace.id, app.id)
        if sub is None:
            start, end = initial_period(now)
            sub = AppSubscription(
                workspace_id=workspace.id,
                app_id=app.id,
                app_plan_id=plan.id,
                status=AppSubscriptionStatus.ACTIVE.value,
                current_period_start=start,
                current_period_end=end,
                latest_purchase_id=None,
                source=AppCommercialSource.PLATFORM_ADMIN.value,
                grant_idempotency_key=idempotency_key,
                granted_by_user_id=actor.id,
            )
            try:
                with self.db.begin_nested():
                    self.repo.create_subscription(sub)
            except IntegrityError:
                replay = self.repo.get_subscription_by_idempotency_key(idempotency_key)
                if replay is not None:
                    return replay, True
                sub = self.repo.get_subscription_for_update(workspace.id, app.id)
                if sub is None:
                    raise
        else:
            period_still_valid = ensure_utc(sub.current_period_end) > ensure_utc(now)
            if period_still_valid and sub.status == AppSubscriptionStatus.ACTIVE.value:
                raise AppError(
                    ErrorCategory.APP_SUBSCRIPTION_ALREADY_ACTIVE,
                    "An active App subscription already exists. Use extend instead.",
                )
            start, end = initial_period(now)
            sub.app_plan_id = plan.id
            sub.current_period_start = start
            sub.current_period_end = end
            sub.status = AppSubscriptionStatus.ACTIVE.value
            if sub.latest_purchase_id is None:
                sub.source = AppCommercialSource.PLATFORM_ADMIN.value
            sub.grant_idempotency_key = idempotency_key
            sub.granted_by_user_id = actor.id
            self.db.flush()
        return sub, False

    def extend_subscription(
        self,
        *,
        workspace: Workspace,
        app: CatalogApp,
        actor: User,
        reason: str,
        idempotency_key: str,
    ) -> tuple[AppSubscription, bool]:
        self._assert_tenant(workspace)
        self._assert_subscription(app)

        acquire_workspace_app_runtime_mutation_fence(
            self.db, workspace_id=workspace.id, app_slug=app.slug
        )
        workspace_app_advisory_lock(self.db, workspace.id, app.id)
        existing_by_key = self.repo.get_subscription_by_idempotency_key(idempotency_key)
        if existing_by_key is not None:
            if (
                existing_by_key.workspace_id != workspace.id
                or existing_by_key.app_id != app.id
            ):
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "Idempotency key already used for a different grant.",
                )
            return existing_by_key, True

        sub = self.repo.get_subscription_for_update(workspace.id, app.id)
        if sub is None:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                "No App subscription exists to extend.",
            )

        now = datetime.now(timezone.utc)
        before_end = ensure_utc(sub.current_period_end)
        start, end = compute_renewal_period(
            current_period_start=sub.current_period_start,
            current_period_end=sub.current_period_end,
            now=now,
        )
        sub.current_period_start = start
        sub.current_period_end = end
        sub.status = AppSubscriptionStatus.ACTIVE.value
        sub.grant_idempotency_key = idempotency_key
        sub.granted_by_user_id = actor.id
        self.db.flush()
        _ = before_end
        return sub, False

    def revoke_subscription(
        self,
        *,
        workspace: Workspace,
        app: CatalogApp,
        actor: User,
        reason: str,
    ) -> AppSubscription:
        self._assert_tenant(workspace)
        self._assert_subscription(app)
        acquire_workspace_app_runtime_mutation_fence(
            self.db, workspace_id=workspace.id, app_slug=app.slug
        )
        sub = self.repo.get_subscription_for_update(workspace.id, app.id)
        if sub is None:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                "No App subscription exists to revoke.",
            )
        if sub.status == AppSubscriptionStatus.CANCELLED.value:
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                "App subscription is already cancelled.",
            )
        sub.status = AppSubscriptionStatus.CANCELLED.value
        self.db.flush()
        return sub

    @staticmethod
    def _assert_tenant(workspace: Workspace) -> None:
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(
                ErrorCategory.SYSTEM_WORKSPACE_NOT_BILLABLE,
                "System workspaces cannot receive App commercial entitlements.",
            )

    @staticmethod
    def _assert_one_time(app: CatalogApp) -> None:
        if app.billing_type != AppBillingType.ONE_TIME.value:
            raise AppError(
                ErrorCategory.VALIDATION,
                "License grant is only valid for one-time apps.",
                details={"billing_type": app.billing_type},
            )

    @staticmethod
    def _assert_subscription(app: CatalogApp) -> None:
        if app.billing_type != AppBillingType.SUBSCRIPTION.value:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Subscription grant is only valid for subscription apps.",
                details={"billing_type": app.billing_type},
            )

    @staticmethod
    def _validate_plan(
        app: CatalogApp, plan: AppPlan, *, require_active: bool
    ) -> None:
        if plan.app_id != app.id:
            raise AppError(ErrorCategory.APP_PLAN_NOT_FOUND, "App plan not found.")
        if require_active and not plan.is_active:
            raise AppError(ErrorCategory.APP_PLAN_INACTIVE, "App plan is inactive.")

    @staticmethod
    def normalize_idempotency_key(raw: str | None, *, prefix: str) -> str:
        key = (raw or "").strip() or f"{prefix}:{uuid.uuid4()}"
        if len(key) > 128:
            raise AppError(
                ErrorCategory.VALIDATION, "idempotency_key must be at most 128 characters."
            )
        return key

    @staticmethod
    def normalize_reason(raw: str) -> str:
        reason = raw.strip()
        if not reason:
            raise AppError(ErrorCategory.VALIDATION, "A reason is required.")
        if len(reason) > 500:
            raise AppError(ErrorCategory.VALIDATION, "Reason must be at most 500 characters.")
        return reason
