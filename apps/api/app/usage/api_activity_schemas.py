"""DTOs for Workspace API usage (Phase 7C). Session-auth management UI only."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.billing.schemas import MeterOut


class ApiRateLimitOut(BaseModel):
    requests_per_minute: int


class ApiTokensOut(BaseModel):
    billed: int


class ApiUsageKeyOut(BaseModel):
    api_key_id: uuid.UUID
    name: str
    prefix: str
    last_four: str
    billed_tokens: int
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiUsagePeriodOut(BaseModel):
    key: str
    from_at: datetime
    to_at: datetime


class ApiUsageSummaryOut(BaseModel):
    rate_limit: ApiRateLimitOut
    ai_tokens: ApiTokensOut
    workspace_ai_monthly: MeterOut
    period: ApiUsagePeriodOut
    keys: list[ApiUsageKeyOut]


class ApiUsageHistoryItemOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    api_key_id: uuid.UUID
    api_key_name: str | None
    prefix: str | None
    last_four: str | None
    expert_id: uuid.UUID | None
    family: str
    model: str | None
    billed_tokens: int
    operation_type: str | None


class ApiUsageHistoryOut(BaseModel):
    items: list[ApiUsageHistoryItemOut]
    total: int
    limit: int
    offset: int
    period: ApiUsagePeriodOut
