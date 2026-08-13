"""Usage period counters and storage-event append.

AI token reserve/settle is ``AiUsageService`` (Phase 5B). This module creates
counter rows that 5B locks by unique key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.usage.metrics import StorageUsageReason, UsageMetric
from app.usage.models import StorageUsageEvent, UsagePeriodCounter
from app.usage.periods import PeriodType, PeriodWindow, current_period, utcnow
from app.usage.repository import StorageUsageRepository, UsageCounterRepository


class UsageMeterService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.counters = UsageCounterRepository(db)

    def get_window(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: UsageMetric | str = UsageMetric.AI_TOKENS,
        period_type: PeriodType | str = PeriodType.DAILY,
        now: datetime | None = None,
    ) -> UsagePeriodCounter | None:
        window = current_period(period_type, now=now or utcnow())
        metric_name = metric.value if isinstance(metric, UsageMetric) else metric
        return self.counters.get(
            workspace_id,
            metric=metric_name,
            period_type=window.period_type.value,
            period_start=window.start,
        )

    def get_or_create_window(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: UsageMetric | str = UsageMetric.AI_TOKENS,
        period_type: PeriodType | str = PeriodType.DAILY,
        now: datetime | None = None,
    ) -> UsagePeriodCounter:
        window = current_period(period_type, now=now or utcnow())
        return self.ensure_counter(workspace_id, metric=metric, window=window)

    def ensure_counter(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: UsageMetric | str,
        window: PeriodWindow,
    ) -> UsagePeriodCounter:
        metric_name = metric.value if isinstance(metric, UsageMetric) else metric
        existing = self.counters.get(
            workspace_id,
            metric=metric_name,
            period_type=window.period_type.value,
            period_start=window.start,
        )
        if existing is not None:
            return existing
        try:
            with self.db.begin_nested():
                row = self.counters.create(
                    UsagePeriodCounter(
                        workspace_id=workspace_id,
                        metric=metric_name,
                        period_type=window.period_type.value,
                        period_start=window.start,
                        period_end=window.end,
                        used=0,
                        reserved=0,
                    )
                )
                return row
        except IntegrityError:
            found = self.counters.get(
                workspace_id,
                metric=metric_name,
                period_type=window.period_type.value,
                period_start=window.start,
            )
            if found is None:
                raise
            return found

    def snapshot(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: UsageMetric | str = UsageMetric.AI_TOKENS,
        period_type: PeriodType | str = PeriodType.DAILY,
        now: datetime | None = None,
    ) -> tuple[PeriodWindow, int, int]:
        """Return (window, used, reserved) without inserting on a cache miss."""
        window = current_period(period_type, now=now or utcnow())
        row = self.get_window(
            workspace_id, metric=metric, period_type=period_type, now=now
        )
        if row is None:
            return window, 0, 0
        return window, int(row.used), int(row.reserved)


class StorageUsageService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = StorageUsageRepository(db)

    def record_delta(
        self,
        workspace_id: uuid.UUID,
        *,
        delta_bytes: int,
        reason: StorageUsageReason | str,
        document_id: uuid.UUID | None = None,
        request_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> StorageUsageEvent:
        parsed = (
            reason if isinstance(reason, StorageUsageReason) else StorageUsageReason(reason)
        )
        return self.repo.append(
            StorageUsageEvent(
                workspace_id=workspace_id,
                document_id=document_id,
                delta_bytes=delta_bytes,
                reason=parsed.value,
                request_id=request_id,
                extra=extra or {},
            )
        )

    def list_for_workspace(
        self, workspace_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[StorageUsageEvent]:
        return self.repo.list_for_workspace(workspace_id, limit=limit, offset=offset)
