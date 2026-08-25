"""QuotaService — single domain entry for resource-limit lookup.

AI token reserve/settle lives in ``app.usage.ai_usage.AiUsageService``.
Expert allowance: ``app.entitlements.experts.ExpertQuotaService``.
Storage quota: ``app.usage.storage.StorageQuotaService``.
Never branch on plan name/code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.billing.models import PlanEntitlement, Subscription, SubscriptionStatus
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey
from app.entitlements.service import EntitlementService
from app.entitlements.values import entitlement_value_from_row
from app.usage.credits import CreditService


@dataclass(frozen=True, slots=True)
class AiTokenLimits:
    daily: int
    weekly: int
    monthly: int


class QuotaService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.entitlements = EntitlementService(db, self.settings)
        self.credits = CreditService(db, self.settings)

    def get_ai_limits(self, workspace_id: uuid.UUID) -> AiTokenLimits:
        return AiTokenLimits(
            daily=self._int_or_zero(workspace_id, EntitlementKey.AI_TOKENS_DAILY),
            weekly=self._int_or_zero(workspace_id, EntitlementKey.AI_TOKENS_WEEKLY),
            monthly=self._int_or_zero(workspace_id, EntitlementKey.AI_TOKENS_MONTHLY),
        )

    def get_ai_limits_db_only(self, workspace_id: uuid.UUID) -> AiTokenLimits:
        """Resolve current Workspace AI limits without cache, provisioning, or I/O.

        Paid runtime admission calls this while its short database transaction
        and advisory fences are held. Missing subscription/key rows fail closed
        to zero; malformed stored values remain operator-visible typed errors.
        """
        keys = (
            EntitlementKey.AI_TOKENS_DAILY,
            EntitlementKey.AI_TOKENS_WEEKLY,
            EntitlementKey.AI_TOKENS_MONTHLY,
        )
        clock = select(func.statement_timestamp().label("decision_at")).cte(
            "workspace_ai_clock"
        )
        stmt = (
            select(
                PlanEntitlement.key,
                PlanEntitlement.value,
                PlanEntitlement.value_type,
            )
            .select_from(clock)
            .join(
                Subscription,
                (Subscription.workspace_id == workspace_id)
                & (Subscription.status == SubscriptionStatus.ACTIVE.value)
                & (Subscription.starts_at <= clock.c.decision_at)
                & (
                    Subscription.ends_at.is_(None)
                    | (Subscription.ends_at > clock.c.decision_at)
                ),
            )
            .join(
                PlanEntitlement,
                (PlanEntitlement.plan_id == Subscription.plan_id)
                & (PlanEntitlement.key.in_([key.value for key in keys])),
            )
        )
        try:
            rows = self.db.execute(stmt).all()
        except SQLAlchemyError as exc:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Workspace AI limits are temporarily unavailable.",
                retryable=True,
            ) from exc

        resolved: dict[str, int] = {}
        for key, raw, value_type in rows:
            parsed = entitlement_value_from_row(
                key=str(key), raw=str(raw), value_type=str(value_type)
            ).as_int()
            resolved[str(key)] = max(0, parsed)
        return AiTokenLimits(
            daily=resolved.get(EntitlementKey.AI_TOKENS_DAILY.value, 0),
            weekly=resolved.get(EntitlementKey.AI_TOKENS_WEEKLY.value, 0),
            monthly=resolved.get(EntitlementKey.AI_TOKENS_MONTHLY.value, 0),
        )

    def get_storage_limit(self, workspace_id: uuid.UUID) -> int:
        return self._int_or_zero(workspace_id, EntitlementKey.STORAGE_BYTES)

    def get_expert_limit(self, workspace_id: uuid.UUID) -> int:
        return self._int_or_zero(workspace_id, EntitlementKey.EXPERTS_LIMIT)

    def get_api_requests_per_minute(self, workspace_id: uuid.UUID) -> int:
        """Missing key fails closed (0) — never unlimited public API usage."""
        return self._int_or_zero(workspace_id, EntitlementKey.API_REQUESTS_PER_MINUTE)

    def get_credit_balance(self, workspace_id: uuid.UUID) -> int:
        return self.credits.get_balance(workspace_id)

    def _int_or_zero(self, workspace_id: uuid.UUID, key: EntitlementKey) -> int:
        """Missing quota keys fail closed (0). Invalid values still raise."""
        item = self.entitlements.get_entitlement(workspace_id, key)
        if item is None:
            return 0
        try:
            value = item.as_int()
        except AppError as exc:
            if exc.category == ErrorCategory.ENTITLEMENT_TYPE_MISMATCH:
                raise
            raise
        return max(0, value)
