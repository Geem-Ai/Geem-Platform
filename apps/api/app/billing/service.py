"""Plan catalog + manual subscription assignment (Phase 5A).

No payment gateways. Product limits are never inferred from plan code/name.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.models import (
    CreditPack,
    Plan,
    PlanEntitlement,
    PlanStatus,
    Subscription,
    SubscriptionStatus,
)
from app.billing.money import normalize_currency, quantize_money
from app.billing.repository import CreditPackRepository, PlanRepository, SubscriptionRepository
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey, EntitlementValueType
from app.entitlements.values import serialize_entitlement_value
from app.usage.periods import PeriodType, PeriodWindow, current_period

BOOTSTRAP_PLAN_METADATA = {
    "kind": "bootstrap_dev",
    "commercial": False,
    "note": "Development/bootstrap default — not Geem product pricing.",
}


class PlanService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.plans = PlanRepository(db)

    def ensure_bootstrap_plan(self) -> Plan:
        """Idempotent seed of the development/bootstrap plan + quota keys.

        Existing entitlement values are never overwritten so operators can
        tune the bootstrap plan without the next boot resetting them.
        Concurrent first-insert uses a savepoint so a unique race reloads.
        """
        code = self.settings.bootstrap_plan_code.strip().lower()
        plan = self.plans.get_by_code(code)
        if plan is None:
            try:
                with self.db.begin_nested():
                    plan = Plan(
                        code=code,
                        name=self.settings.bootstrap_plan_name,
                        description=self.settings.bootstrap_plan_description,
                        status=PlanStatus.ACTIVE.value,
                        extra=dict(BOOTSTRAP_PLAN_METADATA),
                    )
                    self.plans.create(plan)
            except IntegrityError:
                plan = self.plans.get_by_code(code)
                if plan is None:
                    raise

        defaults: dict[EntitlementKey, int] = {
            EntitlementKey.AI_TOKENS_DAILY: self.settings.bootstrap_ai_tokens_daily,
            EntitlementKey.AI_TOKENS_WEEKLY: self.settings.bootstrap_ai_tokens_weekly,
            EntitlementKey.AI_TOKENS_MONTHLY: self.settings.bootstrap_ai_tokens_monthly,
            EntitlementKey.EXPERTS_LIMIT: self.settings.bootstrap_experts_limit,
            EntitlementKey.STORAGE_BYTES: self.settings.bootstrap_storage_bytes,
            EntitlementKey.API_REQUESTS_PER_MINUTE: (
                self.settings.bootstrap_api_requests_per_minute
            ),
        }
        for key, value in defaults.items():
            if self.plans.get_entitlement(plan.id, key.value) is not None:
                continue
            try:
                with self.db.begin_nested():
                    self.plans.create_entitlement(
                        PlanEntitlement(
                            plan_id=plan.id,
                            key=key.value,
                            value=serialize_entitlement_value(value, EntitlementValueType.INTEGER),
                            value_type=EntitlementValueType.INTEGER.value,
                        )
                    )
            except IntegrityError:
                continue
        self.db.flush()
        return self.plans.get_by_id(plan.id) or plan

    def resync_bootstrap_plan(self) -> Plan:
        """Overwrite bootstrap plan name/description/entitlements from Settings.

        Normal boot still uses :meth:`ensure_bootstrap_plan` (insert-only) so
        operator edits survive. Call this from ``python -m app.identity.bootstrap
        --resync-bootstrap-plan`` when you want env values applied.
        """
        plan = self.ensure_bootstrap_plan()
        plan.name = self.settings.bootstrap_plan_name
        plan.description = self.settings.bootstrap_plan_description
        defaults: dict[EntitlementKey, int] = {
            EntitlementKey.AI_TOKENS_DAILY: self.settings.bootstrap_ai_tokens_daily,
            EntitlementKey.AI_TOKENS_WEEKLY: self.settings.bootstrap_ai_tokens_weekly,
            EntitlementKey.AI_TOKENS_MONTHLY: self.settings.bootstrap_ai_tokens_monthly,
            EntitlementKey.EXPERTS_LIMIT: self.settings.bootstrap_experts_limit,
            EntitlementKey.STORAGE_BYTES: self.settings.bootstrap_storage_bytes,
            EntitlementKey.API_REQUESTS_PER_MINUTE: (
                self.settings.bootstrap_api_requests_per_minute
            ),
        }
        for key, value in defaults.items():
            self.set_entitlement(plan.id, key.value, value)
        self.db.flush()
        return self.plans.get_by_id(plan.id) or plan

    def create_plan(
        self,
        *,
        code: str,
        name: str,
        description: str | None = None,
        entitlements: dict[str, int | bool | str] | None = None,
        extra: dict | None = None,
        price_amount: Decimal | int | float | str | None = None,
        currency: str = "SAR",
    ) -> Plan:
        """Manual catalog insert (tests / later platform admin)."""
        clean = code.strip().lower()
        if not clean or len(clean) > 64:
            raise AppError(ErrorCategory.VALIDATION, "Plan code is required (max 64).")
        if self.plans.get_by_code(clean) is not None:
            raise AppError(ErrorCategory.CONFLICT, "Plan code already exists.")
        price = quantize_money(price_amount) if price_amount is not None else None
        plan = Plan(
            code=clean,
            name=name.strip(),
            description=description,
            status=PlanStatus.ACTIVE.value,
            price_amount=price,
            currency=normalize_currency(currency),
            extra=extra or {},
        )
        self.plans.create(plan)
        for key, value in (entitlements or {}).items():
            self.set_entitlement(plan.id, key, value)
        self.db.flush()
        return self.plans.get_by_id(plan.id) or plan

    def set_entitlement(
        self,
        plan_id: uuid.UUID,
        key: str,
        value: int | bool | str,
        *,
        value_type: EntitlementValueType | None = None,
    ) -> PlanEntitlement:
        if isinstance(value, bool):
            vtype = value_type or EntitlementValueType.BOOLEAN
        elif isinstance(value, int):
            vtype = value_type or EntitlementValueType.INTEGER
        else:
            vtype = value_type or EntitlementValueType.STRING
        raw = serialize_entitlement_value(value, vtype)
        existing = self.plans.get_entitlement(plan_id, key)
        if existing is None:
            return self.plans.create_entitlement(
                PlanEntitlement(
                    plan_id=plan_id,
                    key=key,
                    value=raw,
                    value_type=vtype.value,
                )
            )
        existing.value = raw
        existing.value_type = vtype.value
        self.db.flush()
        return existing


class SubscriptionService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.plans = PlanRepository(db)
        self.subscriptions = SubscriptionRepository(db)
        self.plan_service = PlanService(db, self.settings)

    def get_current(self, workspace_id: uuid.UUID) -> Subscription | None:
        return self.subscriptions.get_current(workspace_id)

    def require_current(self, workspace_id: uuid.UUID) -> Subscription:
        sub = self.subscriptions.get_current(workspace_id)
        if sub is None:
            raise AppError(
                ErrorCategory.SUBSCRIPTION_NOT_FOUND,
                "No active subscription for this workspace.",
            )
        return sub

    def assign_plan(
        self,
        workspace_id: uuid.UUID,
        plan_id: uuid.UUID,
        *,
        now: datetime | None = None,
        extra: dict | None = None,
        require_active: bool = True,
    ) -> Subscription:
        """Manually assign a plan. Cancels any current active subscription."""
        moment = now or datetime.now(timezone.utc)
        plan = self.plans.get_by_id(plan_id)
        if plan is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Plan not found.")
        if require_active and plan.status != PlanStatus.ACTIVE.value:
            raise AppError(ErrorCategory.NOT_FOUND, "Plan not found.")

        current = self.subscriptions.get_active_for_update(workspace_id)
        if current is not None:
            current.status = SubscriptionStatus.CANCELED.value
            current.ends_at = moment
            self.db.flush()

        month = current_period(PeriodType.MONTHLY, now=moment)
        subscription = self._new_subscription(
            workspace_id, plan.id, moment, month, extra=extra
        )
        try:
            with self.db.begin_nested():
                self.subscriptions.create(subscription)
                self.db.flush()
        except IntegrityError:
            winner = self.subscriptions.get_current(workspace_id)
            if winner is not None and winner.plan_id == plan.id:
                self._invalidate_entitlement_cache(workspace_id)
                return winner
            locked = self.subscriptions.get_active_for_update(workspace_id)
            if locked is not None:
                if locked.plan_id == plan.id:
                    self._invalidate_entitlement_cache(workspace_id)
                    return locked
                locked.status = SubscriptionStatus.CANCELED.value
                locked.ends_at = moment
                self.db.flush()
            subscription = self._new_subscription(
                workspace_id, plan.id, moment, month, extra=extra
            )
            self.subscriptions.create(subscription)
            self.db.flush()
        self._invalidate_entitlement_cache(workspace_id)
        return subscription

    def ensure_bootstrap_subscription(self, workspace_id: uuid.UUID) -> Subscription:
        current = self.subscriptions.get_current(workspace_id)
        if current is not None:
            return current
        plan = self.plan_service.ensure_bootstrap_plan()
        try:
            assigned = self.assign_plan(
                workspace_id,
                plan.id,
                extra={"source": "bootstrap_dev"},
            )
        except IntegrityError:
            current = self.subscriptions.get_current(workspace_id)
            if current is None:
                raise
            return current
        current = self.subscriptions.get_current(workspace_id) or assigned
        if current is None:
            raise AppError(
                ErrorCategory.SUBSCRIPTION_NOT_FOUND,
                "Failed to assign bootstrap subscription.",
            )
        return current

    @staticmethod
    def _new_subscription(
        workspace_id: uuid.UUID,
        plan_id: uuid.UUID,
        moment: datetime,
        month: PeriodWindow,
        *,
        extra: dict | None,
    ) -> Subscription:
        return Subscription(
            workspace_id=workspace_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE.value,
            starts_at=moment,
            current_period_start=month.start,
            current_period_end=month.end,
            ends_at=None,
            extra=extra or {"source": "manual"},
        )

    def _invalidate_entitlement_cache(self, workspace_id: uuid.UUID) -> None:
        from app.entitlements.cache import invalidate_entitlements

        invalidate_entitlements(workspace_id, settings=self.settings)


class CreditPackService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.packs = CreditPackRepository(db)

    def create_pack(
        self,
        *,
        code: str,
        name: str,
        credits: int,
        price_amount: Decimal | int | float | str,
        currency: str = "SAR",
        description: str | None = None,
        active: bool = True,
        extra: dict | None = None,
    ) -> CreditPack:
        clean = code.strip().lower()
        if not clean or len(clean) > 64:
            raise AppError(ErrorCategory.VALIDATION, "Credit pack code is required (max 64).")
        if credits <= 0:
            raise AppError(ErrorCategory.VALIDATION, "Credit pack credits must be positive.")
        if self.packs.get_by_code(clean) is not None:
            raise AppError(ErrorCategory.CONFLICT, "Credit pack code already exists.")
        pack = CreditPack(
            code=clean,
            name=name.strip(),
            description=description,
            credits=int(credits),
            price_amount=quantize_money(price_amount),
            currency=normalize_currency(currency),
            active=active,
            extra=extra or {},
        )
        return self.packs.create(pack)

    def list_active(self) -> list[CreditPack]:
        return self.packs.list_active()
