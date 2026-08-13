"""QuotaService — single domain entry for resource-limit lookup.

AI token reserve/settle lives in ``app.usage.ai_usage.AiUsageService``.
Expert allowance: ``app.entitlements.experts.ExpertQuotaService``.
Storage quota: ``app.usage.storage.StorageQuotaService``.
Never branch on plan name/code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey
from app.entitlements.service import EntitlementService
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
