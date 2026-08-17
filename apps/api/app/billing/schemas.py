from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlanSummaryOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: str


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    status: str
    plan: PlanSummaryOut
    starts_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    ends_at: datetime | None


class EntitlementItemOut(BaseModel):
    key: str
    value: int | bool | str
    value_type: str


class EntitlementsOut(BaseModel):
    subscription_id: uuid.UUID
    plan: PlanSummaryOut
    items: list[EntitlementItemOut]


class MeterOut(BaseModel):
    limit: int
    used: int
    reserved: int = 0
    remaining: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None


class AiTokensUsageOut(BaseModel):
    daily: MeterOut
    weekly: MeterOut
    monthly: MeterOut


class CreditsUsageOut(BaseModel):
    balance: int


class StorageUsageOut(BaseModel):
    limit_bytes: int
    used_bytes: int
    remaining_bytes: int
    reserved_bytes: int = 0
    percentage: float


class UsageSummaryOut(BaseModel):
    ai_tokens: AiTokensUsageOut
    ai: AiTokensUsageOut
    experts: MeterOut
    storage_bytes: MeterOut
    storage: StorageUsageOut
    credits: CreditsUsageOut
    extra: dict[str, Any] | None = None


class UsageHistoryItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    tokens: int | None = None
    credits: int | None = None
    created_at: datetime
    operation_type: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None
    source_type: str | None = None


class UsageHistoryCountsOut(BaseModel):
    all: int = 0
    ai: int = 0
    credits: int = 0


class UsageHistoryTokensOut(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class UsageHistoryOut(BaseModel):
    items: list[UsageHistoryItemOut]
    total: int = 0
    limit: int = 50
    offset: int = 0
    counts: UsageHistoryCountsOut = UsageHistoryCountsOut()
    tokens: UsageHistoryTokensOut = UsageHistoryTokensOut()


class PurchasablePlanOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    status: str
    price_amount: str
    currency: str
    entitlements: list[EntitlementItemOut] = []


class CreditPackOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    credits: int
    price_amount: str
    currency: str
    active: bool


class SubscriptionCheckoutRequest(BaseModel):
    plan_id: uuid.UUID


class CreditPackCheckoutRequest(BaseModel):
    credit_pack_id: uuid.UUID


class CheckoutOut(BaseModel):
    purchase_id: uuid.UUID
    status: str
    kind: str
    amount: str
    currency: str
    redirect_url: str


class PurchaseOut(BaseModel):
    id: uuid.UUID
    status: str
    kind: str
    amount: str
    currency: str
    item_name: str | None = None
    item_code: str | None = None
    credits: int | None = None
    app_slug: str | None = None
    app_name: str | None = None
    commercial_action: str | None = None
    billing_interval: str | None = None
    paid_at: datetime | None = None
    created_at: datetime


class PurchaseListOut(BaseModel):
    items: list[PurchaseOut]
    total: int = 0
    limit: int = 25
    offset: int = 0
