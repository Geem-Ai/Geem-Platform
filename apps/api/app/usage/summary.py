"""Workspace usage summary for the current authenticated tenant."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.entitlements.experts import ExpertQuotaService
from app.entitlements.quota import QuotaService
from app.usage.credits import CreditService
from app.usage.meters import UsageMeterService
from app.usage.metrics import UsageMetric
from app.usage.periods import PeriodType
from app.usage.storage import StorageQuotaService, StorageSnapshot


@dataclass(frozen=True, slots=True)
class MeterSnapshot:
    limit: int
    used: int
    reserved: int
    period_start: datetime | None
    period_end: datetime | None

    @property
    def remaining(self) -> int:
        return max(0, int(self.limit) - int(self.used) - int(self.reserved))


@dataclass(frozen=True, slots=True)
class UsageSummary:
    ai_daily: MeterSnapshot
    ai_weekly: MeterSnapshot
    ai_monthly: MeterSnapshot
    experts: MeterSnapshot
    storage: MeterSnapshot
    storage_detail: StorageSnapshot
    credit_balance: int


class UsageSummaryService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.quota = QuotaService(db, self.settings)
        self.meters = UsageMeterService(db, self.settings)
        self.credits = CreditService(db, self.settings)
        self.expert_quota = ExpertQuotaService(db, self.settings)
        self.storage_quota = StorageQuotaService(db, self.settings)

    def summarize(self, workspace_id: uuid.UUID) -> UsageSummary:
        limits = self.quota.get_ai_limits(workspace_id)
        daily = self._ai_snapshot(workspace_id, PeriodType.DAILY, limits.daily)
        weekly = self._ai_snapshot(workspace_id, PeriodType.WEEKLY, limits.weekly)
        monthly = self._ai_snapshot(workspace_id, PeriodType.MONTHLY, limits.monthly)
        expert_snap = self.expert_quota.snapshot(workspace_id)
        storage_snap = self.storage_quota.snapshot(workspace_id)
        return UsageSummary(
            ai_daily=daily,
            ai_weekly=weekly,
            ai_monthly=monthly,
            experts=MeterSnapshot(
                limit=expert_snap.limit,
                used=expert_snap.used,
                reserved=0,
                period_start=None,
                period_end=None,
            ),
            storage=MeterSnapshot(
                limit=storage_snap.limit_bytes,
                used=storage_snap.used_bytes,
                reserved=storage_snap.reserved_bytes,
                period_start=None,
                period_end=None,
            ),
            storage_detail=storage_snap,
            credit_balance=self.quota.get_credit_balance(workspace_id),
        )

    def _ai_snapshot(
        self, workspace_id: uuid.UUID, period_type: PeriodType, limit: int
    ) -> MeterSnapshot:
        window, used, reserved = self.meters.snapshot(
            workspace_id,
            metric=UsageMetric.AI_TOKENS,
            period_type=period_type,
        )
        return MeterSnapshot(
            limit=limit,
            used=used,
            reserved=reserved,
            period_start=window.start,
            period_end=window.end,
        )

