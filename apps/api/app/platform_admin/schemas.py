from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.identity.schemas import UserOut


class PlatformMeResponse(BaseModel):
    """Authoritative Platform Admin bootstrap payload (Phase 12A)."""

    user: UserOut
    platform_role: str
    authorized: bool = True


# --- Shared pagination ---


class PlatformPageMeta(BaseModel):
    total: int
    limit: int
    offset: int


# --- Workspaces ---


class PlatformWorkspaceListItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    kind: str
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    deleted_at: datetime | None = None
    members_count: int = 0
    experts_count: int = 0
    current_plan_code: str | None = None
    current_plan_name: str | None = None
    subscription_status: str | None = None


class PlatformWorkspaceListResponse(BaseModel):
    items: list[PlatformWorkspaceListItem]
    total: int
    limit: int
    offset: int


class PlatformWorkspaceOwnerOut(BaseModel):
    user_id: uuid.UUID
    email: str
    status: str
    membership_id: uuid.UUID
    role_id: uuid.UUID
    role_name: str


class PlatformSubscriptionSummaryOut(BaseModel):
    subscription_id: uuid.UUID
    status: str
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    starts_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    ends_at: datetime | None = None


class PlatformResourceSummaryOut(BaseModel):
    members_count: int
    experts_count: int
    api_keys_count: int
    app_installations_count: int
    storage_used_bytes: int | None = None
    storage_limit_bytes: int | None = None


class PlatformWorkspaceDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    kind: str
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    deleted_at: datetime | None = None
    purged_at: datetime | None = None
    members_count: int
    owners: list[PlatformWorkspaceOwnerOut]
    subscription: PlatformSubscriptionSummaryOut | None = None
    resources: PlatformResourceSummaryOut


class PlatformWorkspaceMemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    user_status: str
    role_id: uuid.UUID
    role_name: str
    is_owner_role: bool
    created_at: datetime


class PlatformWorkspaceMembersResponse(BaseModel):
    items: list[PlatformWorkspaceMemberOut]
    total: int
    limit: int
    offset: int


class PlatformWorkspaceLifecycleRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class PlatformWorkspaceEnableRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# --- Users ---


class PlatformUserListItem(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    platform_role: str
    created_at: datetime
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    workspace_memberships_count: int = 0


class PlatformUserListResponse(BaseModel):
    items: list[PlatformUserListItem]
    total: int
    limit: int
    offset: int


class PlatformUserMembershipOut(BaseModel):
    membership_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    workspace_status: str
    role_id: uuid.UUID
    role_name: str
    is_owner_role: bool
    created_at: datetime


class PlatformUserDetailOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    platform_role: str
    created_at: datetime
    updated_at: datetime
    email_verified_at: datetime | None = None
    deleted_at: datetime | None = None
    last_login_at: datetime | None = None
    active_session_count: int = 0
    memberships: list[PlatformUserMembershipOut]


class PlatformUserLifecycleRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PlatformUserDisableRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# --- Phase 12C: Plans ---


class PlatformEntitlementValueIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: int = Field(..., ge=0)


class PlatformPlanEntitlementOut(BaseModel):
    key: str
    value: int | bool | str
    value_type: str


class PlatformPlanListItem(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    status: str
    price_amount: str | None = None
    currency: str
    is_bootstrap: bool = False
    is_commercial: bool = False
    subscriber_count: int = 0
    entitlements: list[PlatformPlanEntitlementOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PlatformPlanListResponse(BaseModel):
    items: list[PlatformPlanListItem]
    total: int
    limit: int
    offset: int


class PlatformPlanDetailOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    status: str
    price_amount: str | None = None
    currency: str
    is_bootstrap: bool = False
    is_commercial: bool = False
    subscriber_count: int = 0
    entitlements: list[PlatformPlanEntitlementOut]
    created_at: datetime
    updated_at: datetime


class PlatformPlanCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price_amount: str | None = None
    currency: str = Field(default="SAR", min_length=3, max_length=3)
    entitlements: list[PlatformEntitlementValueIn] = Field(default_factory=list)


class PlatformPlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price_amount: str | None = None
    clear_price: bool = False
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    entitlements: list[PlatformEntitlementValueIn] | None = None
    reason: str | None = Field(default=None, max_length=500)


class PlatformPlanLifecycleRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# --- Phase 12C: Workspace billing ---


class PlatformSubscriptionDetailOut(BaseModel):
    subscription_id: uuid.UUID
    status: str
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    plan_status: str
    starts_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    ends_at: datetime | None = None
    source: str | None = None
    created_at: datetime


class PlatformSubscriptionHistoryItem(BaseModel):
    subscription_id: uuid.UUID
    status: str
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    starts_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    ends_at: datetime | None = None
    source: str | None = None
    created_at: datetime


class PlatformSubscriptionHistoryResponse(BaseModel):
    items: list[PlatformSubscriptionHistoryItem]
    total: int
    limit: int
    offset: int


class PlatformSubscriptionAssignRequest(BaseModel):
    plan_id: uuid.UUID
    reason: str = Field(..., min_length=1, max_length=500)


class PlatformEntitlementItemOut(BaseModel):
    key: str
    value: int | bool | str
    value_type: str


class PlatformWorkspaceEntitlementsOut(BaseModel):
    workspace_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    plan_status: str
    items: list[PlatformEntitlementItemOut]


class PlatformUsageMeterOut(BaseModel):
    limit: int
    used: int
    reserved: int = 0
    remaining: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None


class PlatformWorkspaceUsageOut(BaseModel):
    ai_tokens_daily: PlatformUsageMeterOut
    ai_tokens_weekly: PlatformUsageMeterOut
    ai_tokens_monthly: PlatformUsageMeterOut
    experts: PlatformUsageMeterOut
    storage_bytes: PlatformUsageMeterOut
    credit_balance: int


class PlatformCreditLedgerItemOut(BaseModel):
    id: uuid.UUID
    entry_type: str
    amount: int
    remaining_amount: int | None = None
    request_id: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    reason: str | None = None
    created_at: datetime


class PlatformWorkspaceCreditsOut(BaseModel):
    workspace_id: uuid.UUID
    balance: int
    recent: list[PlatformCreditLedgerItemOut] = Field(default_factory=list)


class PlatformCreditHistoryResponse(BaseModel):
    items: list[PlatformCreditLedgerItemOut]
    total: int
    limit: int
    offset: int


class PlatformCreditGrantRequest(BaseModel):
    amount: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=500)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class PlatformCreditGrantResponse(BaseModel):
    workspace_id: uuid.UUID
    balance: int
    entry: PlatformCreditLedgerItemOut
    idempotent_replay: bool = False


class PlatformEntitlementCatalogItem(BaseModel):
    key: str
    value_type: str
    unit: str


class PlatformEntitlementCatalogResponse(BaseModel):
    items: list[PlatformEntitlementCatalogItem]
