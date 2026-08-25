"""Agents AI paid-request quota and Workspace UI usage snapshot."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import (
    AppAccessService,
    AppAccessSnapshot,
    AppAccessStatus,
    RuntimeAppAccessSnapshot,
)
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENT_REQUESTS_USAGE_METRIC,
    AGENTS_AI_APP_SLUG,
)
from app.apps_catalog.models import AppPlan, AppPlanEntitlement
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.usage.models import AiUsageReservation, UsagePeriodCounter
from app.usage.periods import PeriodType, PeriodWindow, current_period, period_containing, utcnow
from app.usage.repository import AiUsageReservationRepository

_RECEIPT_KEY = "agents_ai_request_quota"


@dataclass(frozen=True, slots=True)
class AgentRequestQuotaReceipt:
    request_id: str
    metric: str
    period_start: datetime
    period_end: datetime
    counter_id: uuid.UUID
    used: int
    limit: int


@dataclass(frozen=True, slots=True)
class AgentsAiUsageSnapshot:
    access: AppAccessSnapshot
    plan_price_amount: str | None
    plan_currency: str | None
    plan_billing_interval: str | None
    window: PeriodWindow
    used: int
    limit: int
    base_url: str
    model: str


class AgentsAiRequestQuotaService:
    """Atomically charge one committed Agents AI request per UTC day."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.reservations = AiUsageReservationRepository(db)

    def consume_in_transaction(
        self,
        *,
        workspace_id: uuid.UUID,
        request_id: str,
        access: RuntimeAppAccessSnapshot,
    ) -> AgentRequestQuotaReceipt:
        """Charge the reservation receipt once without committing.

        The caller must have already created the Workspace/request AI usage
        reservation in the same transaction. A conditional database UPDATE,
        not a read-then-write sequence, enforces the exact N/N+1 boundary.
        """
        rid = (request_id or "").strip()
        if not rid:
            raise AppError(ErrorCategory.VALIDATION, "request_id is required.")
        if access.workspace_id != workspace_id or access.app_slug != AGENTS_AI_APP_SLUG:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Paid App admission snapshot does not match this request.",
                retryable=True,
            )
        limit = access.entitlement(AGENT_REQUESTS_DAILY_ENTITLEMENT)
        window = period_containing(access.decision_at, PeriodType.DAILY)

        try:
            reservation = self.reservations.get_by_request_id_for_update(
                workspace_id, rid
            )
        except SQLAlchemyError as exc:
            self._unavailable(exc)
        if reservation is None:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "AI usage reservation is required before App quota admission.",
                retryable=True,
            )

        reservation_extra = reservation.extra or {}
        if not isinstance(reservation_extra, dict):
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Stored AI usage reservation metadata is invalid.",
                retryable=True,
            )
        existing = reservation_extra.get(_RECEIPT_KEY)
        if isinstance(existing, dict):
            return self._replay_receipt(reservation, existing, expected_limit=limit)
        if existing is not None:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Stored App quota receipt is invalid.",
                retryable=True,
            )

        counter_id = uuid.uuid4()
        try:
            self.db.execute(
                insert(UsagePeriodCounter)
                .values(
                    id=counter_id,
                    workspace_id=workspace_id,
                    metric=AGENT_REQUESTS_USAGE_METRIC,
                    period_type=PeriodType.DAILY.value,
                    period_start=window.start,
                    period_end=window.end,
                    used=0,
                    reserved=0,
                )
                .on_conflict_do_nothing(constraint="uq_usage_period_counter")
            )
            charged = self.db.execute(
                update(UsagePeriodCounter)
                .where(
                    UsagePeriodCounter.workspace_id == workspace_id,
                    UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
                    UsagePeriodCounter.period_type == PeriodType.DAILY.value,
                    UsagePeriodCounter.period_start == window.start,
                    UsagePeriodCounter.period_end == window.end,
                    UsagePeriodCounter.used >= 0,
                    UsagePeriodCounter.reserved >= 0,
                    UsagePeriodCounter.used + UsagePeriodCounter.reserved < limit,
                )
                .values(used=UsagePeriodCounter.used + 1)
                .returning(UsagePeriodCounter.id, UsagePeriodCounter.used)
            ).one_or_none()
        except SQLAlchemyError as exc:
            self._unavailable(exc)

        if charged is None:
            try:
                counter_state = self.db.execute(
                    select(
                        UsagePeriodCounter.used,
                        UsagePeriodCounter.reserved,
                        UsagePeriodCounter.period_end,
                    ).where(
                        UsagePeriodCounter.workspace_id == workspace_id,
                        UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
                        UsagePeriodCounter.period_type == PeriodType.DAILY.value,
                        UsagePeriodCounter.period_start == window.start,
                    )
                ).one_or_none()
            except SQLAlchemyError as exc:
                self._unavailable(exc)
            if (
                counter_state is None
                or int(counter_state.reserved) < 0
                or int(counter_state.used) < 0
                or counter_state.period_end != window.end
            ):
                self._unavailable(RuntimeError("Invalid App request counter state."))
            self._raise_exceeded(
                used=int(counter_state.used), limit=limit, reset_at=window.end,
                decision_at=access.decision_at,
            )

        charged_id, charged_used = charged
        metadata = dict(reservation_extra)
        metadata[_RECEIPT_KEY] = {
            "metric": AGENT_REQUESTS_USAGE_METRIC,
            "period_start": window.start.isoformat(),
            "period_end": window.end.isoformat(),
            "counter_id": str(charged_id),
            "charged": 1,
            "limit": limit,
        }
        reservation.extra = metadata
        self.db.flush()
        return AgentRequestQuotaReceipt(
            request_id=rid,
            metric=AGENT_REQUESTS_USAGE_METRIC,
            period_start=window.start,
            period_end=window.end,
            counter_id=charged_id,
            used=int(charged_used),
            limit=limit,
        )

    def _replay_receipt(
        self,
        reservation: AiUsageReservation,
        payload: dict,
        *,
        expected_limit: int,
    ) -> AgentRequestQuotaReceipt:
        try:
            if payload.get("metric") != AGENT_REQUESTS_USAGE_METRIC or payload.get("charged") != 1:
                raise ValueError
            counter_id = uuid.UUID(str(payload["counter_id"]))
            period_start = datetime.fromisoformat(str(payload["period_start"]))
            period_end = datetime.fromisoformat(str(payload["period_end"]))
            receipt_limit = int(payload.get("limit", expected_limit))
            if (
                period_start.tzinfo is None
                or period_end.tzinfo is None
                or period_end <= period_start
                or receipt_limit <= 0
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Stored App quota receipt is invalid.",
                retryable=True,
            ) from exc
        try:
            counter = self.db.execute(
                select(UsagePeriodCounter.used).where(
                    UsagePeriodCounter.id == counter_id,
                    UsagePeriodCounter.workspace_id == reservation.workspace_id,
                    UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
                    UsagePeriodCounter.period_start == period_start,
                    UsagePeriodCounter.period_end == period_end,
                )
            ).one_or_none()
        except SQLAlchemyError as exc:
            self._unavailable(exc)
        if counter is None:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Stored App quota receipt is unavailable.",
                retryable=True,
            )
        return AgentRequestQuotaReceipt(
            request_id=reservation.request_id,
            metric=AGENT_REQUESTS_USAGE_METRIC,
            period_start=period_start,
            period_end=period_end,
            counter_id=counter_id,
            used=int(counter[0]),
            limit=receipt_limit,
        )

    @staticmethod
    def _raise_exceeded(
        *, used: int, limit: int, reset_at: datetime, decision_at: datetime
    ) -> None:
        retry_after = max(1, math.ceil((reset_at - decision_at).total_seconds()))
        raise AppError(
            ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED,
            "Agents AI daily request quota exceeded.",
            details={
                "metric": AGENT_REQUESTS_USAGE_METRIC,
                "limit": limit,
                "used": used,
                "remaining": 0,
                "reset_at": reset_at.isoformat(),
            },
            retryable=True,
            headers={"Retry-After": str(retry_after)},
        )

    @staticmethod
    def _unavailable(exc: Exception) -> NoReturn:
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Agents AI request metering is temporarily unavailable.",
            retryable=True,
        ) from exc


class AgentsAiUsageService:
    """Read-only session surface for the Agents AI App detail UI."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def snapshot(self, workspace_id: uuid.UUID) -> AgentsAiUsageSnapshot:
        access = AppAccessService(self.db).resolve(
            workspace_id,
            app_slug=AGENTS_AI_APP_SLUG,
            normalize_subscription_status=False,
        )
        limit = 0
        plan_price_amount: str | None = None
        plan_currency: str | None = None
        plan_billing_interval: str | None = None
        if access.plan_id is not None:
            plan_state = self.db.execute(
                select(
                    AppPlan.price_amount,
                    AppPlan.currency,
                    AppPlan.billing_interval,
                    AppPlanEntitlement.value.label("daily_limit"),
                )
                .outerjoin(
                    AppPlanEntitlement,
                    (AppPlanEntitlement.app_plan_id == AppPlan.id)
                    & (
                        AppPlanEntitlement.key
                        == AGENT_REQUESTS_DAILY_ENTITLEMENT
                    ),
                )
                .where(
                    AppPlan.id == access.plan_id,
                    AppPlan.app_id == access.app_id,
                )
            ).one_or_none()
            raw = plan_state.daily_limit if plan_state is not None else None
            if plan_state is not None:
                plan_price_amount = f"{plan_state.price_amount:.2f}"
                plan_currency = str(plan_state.currency)
                plan_billing_interval = str(plan_state.billing_interval)
            if raw is None and access.status == AppAccessStatus.ACTIVE:
                raise AppError(
                    ErrorCategory.ENTITLEMENT_INVALID,
                    "Agents AI daily request entitlement is missing.",
                    details={"key": AGENT_REQUESTS_DAILY_ENTITLEMENT},
                )
            if raw is not None:
                if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
                    raise AppError(
                        ErrorCategory.ENTITLEMENT_INVALID,
                        "Agents AI daily request entitlement is invalid.",
                        details={"key": AGENT_REQUESTS_DAILY_ENTITLEMENT},
                    )
                limit = raw

        moment = utcnow()
        window = current_period(PeriodType.DAILY, now=moment)
        raw_used = self.db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == workspace_id,
                UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
                UsagePeriodCounter.period_type == PeriodType.DAILY.value,
                UsagePeriodCounter.period_start == window.start,
            )
        )
        used = int(raw_used or 0)
        if used < 0:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "Agents AI usage is temporarily unavailable.",
                retryable=True,
            )
        from app.common.public_model import PUBLIC_MODEL_ID

        return AgentsAiUsageSnapshot(
            access=access,
            plan_price_amount=plan_price_amount,
            plan_currency=plan_currency,
            plan_billing_interval=plan_billing_interval,
            window=window,
            used=used,
            limit=limit,
            base_url=f"{self.settings.app_url.rstrip('/')}/api/v1/agent",
            model=PUBLIC_MODEL_ID,
        )
