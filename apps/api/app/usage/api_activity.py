"""Read-only public-API usage for the Workspace UI (Phase 7C).

Counts only ``usage_events`` with ``api_key_id IS NOT NULL`` — internal
Workspace Chat (``api_key_id IS NULL``) is excluded. Rate-limit value comes
from EntitlementService via QuotaService, never from plan names.

There is no durable request counter (7B rate limits are Redis windows);
this surface reports AI token attribution, key last-used, and history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey
from app.billing.schemas import MeterOut
from app.common.public_model import public_model_or_none
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.entitlements.quota import QuotaService
from app.usage.api_activity_schemas import (
    ApiRateLimitOut,
    ApiTokensOut,
    ApiUsageHistoryItemOut,
    ApiUsageHistoryOut,
    ApiUsageKeyOut,
    ApiUsagePeriodOut,
    ApiUsageSummaryOut,
)
from app.usage.summary import UsageSummaryService
from app.usage.weights import OPERATION_FAMILY, OpenRouterFamily

ALLOWED_PERIODS = ("24h", "7d", "30d")
DEFAULT_PERIOD = "30d"
_PERIOD_DELTA: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@dataclass(frozen=True, slots=True)
class _Window:
    key: str
    start: datetime
    end: datetime


def normalize_api_usage_period(raw: str | None) -> str:
    value = (raw or DEFAULT_PERIOD).strip().lower()
    if value not in _PERIOD_DELTA:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Invalid API usage period.",
            details={"allowed": list(ALLOWED_PERIODS)},
        )
    return value


def _window(period: str, *, now: datetime | None = None) -> _Window:
    key = normalize_api_usage_period(period)
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return _Window(key=key, start=end - _PERIOD_DELTA[key], end=end)


def _billed_expr():
    """Prefer cost_metadata billed_tokens (pool charge); else input+output."""
    from_meta = cast(UsageEvent.cost_metadata["billed_tokens"].astext, Integer)
    fallback = func.coalesce(UsageEvent.input_tokens, 0) + func.coalesce(
        UsageEvent.output_tokens, 0
    )
    return func.coalesce(from_meta, fallback)


def _family_for_row(family: str | None, operation_type: str | None) -> str:
    raw = (family or "").strip()
    if raw in {item.value for item in OpenRouterFamily}:
        return raw
    mapped = OPERATION_FAMILY.get((operation_type or "").strip())
    if mapped is not None:
        return mapped.value
    return OpenRouterFamily.CHAT.value


def _period_out(window: _Window) -> ApiUsagePeriodOut:
    return ApiUsagePeriodOut(key=window.key, from_at=window.start, to_at=window.end)


class ApiActivityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.quota = QuotaService(db)

    def summarize(
        self,
        workspace_id: uuid.UUID,
        *,
        period: str | None = None,
    ) -> ApiUsageSummaryOut:
        window = _window(period)
        billed_expr = _billed_expr()
        api_filter = (
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.api_key_id.is_not(None),
            UsageEvent.created_at >= window.start,
            UsageEvent.created_at < window.end,
        )

        billed = int(
            self.db.scalar(select(func.coalesce(func.sum(billed_expr), 0)).where(*api_filter))
            or 0
        )
        grouped = self.db.execute(
            select(
                UsageEvent.api_key_id,
                func.coalesce(func.sum(billed_expr), 0).label("billed_tokens"),
            )
            .where(*api_filter)
            .group_by(UsageEvent.api_key_id)
        ).all()
        billed_by_key = {row.api_key_id: int(row.billed_tokens or 0) for row in grouped}

        keys = list(
            self.db.scalars(
                select(ApiKey)
                .where(ApiKey.workspace_id == workspace_id)
                .order_by(ApiKey.created_at.desc())
            )
        )
        key_out: list[ApiUsageKeyOut] = []
        seen: set[uuid.UUID] = set()
        for row in keys:
            seen.add(row.id)
            key_out.append(
                ApiUsageKeyOut(
                    api_key_id=row.id,
                    name=row.name,
                    prefix=row.key_prefix,
                    last_four=row.last_four,
                    billed_tokens=billed_by_key.get(row.id, 0),
                    last_used_at=row.last_used_at,
                    expires_at=row.expires_at,
                    revoked_at=row.revoked_at,
                )
            )
        # Historical attribution after a key row is gone (ON DELETE SET NULL
        # would drop api_key_id; leftover ids still listed as unknown).
        for key_id, tokens in billed_by_key.items():
            if key_id in seen:
                continue
            key_out.append(
                ApiUsageKeyOut(
                    api_key_id=key_id,
                    name="",
                    prefix="",
                    last_four="",
                    billed_tokens=tokens,
                    last_used_at=None,
                    expires_at=None,
                    revoked_at=None,
                )
            )

        monthly = UsageSummaryService(self.db).summarize(workspace_id).ai_monthly
        return ApiUsageSummaryOut(
            rate_limit=ApiRateLimitOut(
                requests_per_minute=self.quota.get_api_requests_per_minute(workspace_id)
            ),
            ai_tokens=ApiTokensOut(billed=billed),
            workspace_ai_monthly=MeterOut(
                limit=monthly.limit,
                used=monthly.used,
                reserved=monthly.reserved,
                remaining=monthly.remaining,
                period_start=monthly.period_start,
                period_end=monthly.period_end,
            ),
            period=_period_out(window),
            keys=key_out,
        )

    def history(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        period: str | None = None,
        api_key_id: uuid.UUID | None = None,
    ) -> ApiUsageHistoryOut:
        window = _window(period)
        cap = max(1, min(int(limit), 100))
        skip = max(0, int(offset))
        billed_expr = _billed_expr()
        family_expr = UsageEvent.cost_metadata["family"].astext

        filters = [
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.api_key_id.is_not(None),
            UsageEvent.created_at >= window.start,
            UsageEvent.created_at < window.end,
        ]
        if api_key_id is not None:
            # Workspace-scoped: a foreign key id yields an empty page, not B's data.
            filters.append(UsageEvent.api_key_id == api_key_id)

        base = (
            select(
                UsageEvent.id,
                UsageEvent.created_at,
                UsageEvent.api_key_id,
                ApiKey.name.label("api_key_name"),
                ApiKey.key_prefix.label("prefix"),
                ApiKey.last_four.label("last_four"),
                UsageEvent.expert_id,
                family_expr.label("family"),
                UsageEvent.model,
                billed_expr.label("billed_tokens"),
                UsageEvent.operation_type,
            )
            .select_from(UsageEvent)
            .outerjoin(
                ApiKey,
                (ApiKey.id == UsageEvent.api_key_id)
                & (ApiKey.workspace_id == workspace_id),
            )
            .where(*filters)
        )
        total = int(
            self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        rows = self.db.execute(
            base.order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
            .offset(skip)
            .limit(cap)
        ).all()
        items = [
            ApiUsageHistoryItemOut(
                id=row.id,
                created_at=row.created_at,
                api_key_id=row.api_key_id,
                api_key_name=row.api_key_name or None,
                prefix=row.prefix or None,
                last_four=row.last_four or None,
                expert_id=row.expert_id,
                family=_family_for_row(row.family, row.operation_type),
                model=public_model_or_none(row.model),
                billed_tokens=max(0, int(row.billed_tokens or 0)),
                operation_type=row.operation_type,
            )
            for row in rows
        ]
        return ApiUsageHistoryOut(
            items=items,
            total=total,
            limit=cap,
            offset=skip,
            period=_period_out(window),
        )
