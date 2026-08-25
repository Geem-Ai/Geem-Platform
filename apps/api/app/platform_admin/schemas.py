from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

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


# --- Phase 12D: Platform Experts ---


class PlatformExpertListItem(BaseModel):
    id: uuid.UUID
    type: str
    ownership: str = "platform"
    workspace_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    icon_url: str | None = None
    status: str
    visibility: str
    availability_mode: str
    knowledge_mode: str = "rag"
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    knowledge_document_count: int = 0
    explicit_workspace_grant_count: int = 0
    is_protected: bool = False


class PlatformExpertDetailOut(PlatformExpertListItem):
    system_instructions: str | None = None
    rag_config: dict | None = None


class PlatformExpertListResponse(BaseModel):
    items: list[PlatformExpertListItem]
    total: int
    limit: int
    offset: int


class PlatformExpertWorkspaceGrantOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    workspace_status: str
    expert_id: uuid.UUID
    created_by: uuid.UUID | None = None
    created_at: datetime


class PlatformExpertGrantListResponse(BaseModel):
    items: list[PlatformExpertWorkspaceGrantOut]
    total: int
    limit: int
    offset: int


class PlatformExpertKnowledgeItemOut(BaseModel):
    id: uuid.UUID
    expert_id: uuid.UUID
    document_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    created_at: datetime
    title: str
    original_filename: str
    status: str
    mime_type: str | None = None
    byte_size: int | None = None
    page_count: int = 0
    failure_reason: str | None = None
    source_type: str = "upload"
    processed_pages: int = 0
    failed_pages: int = 0
    current_stage: str | None = None
    progress: float = 0.0


class PlatformExpertKnowledgeListResponse(BaseModel):
    items: list[PlatformExpertKnowledgeItemOut]
    total: int
    limit: int
    offset: int


# --- Phase 12E: App Store ---


class PlatformAppCategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    name_key: str
    description_key: str | None = None
    icon: str | None = None
    sort_order: int
    is_active: bool


class PlatformAppCategoryListResponse(BaseModel):
    items: list[PlatformAppCategoryOut]


class PlatformAppCategoryUpdateRequest(BaseModel):
    is_active: bool | None = None
    sort_order: int | None = None


class PlatformAppEntitlementCatalogItem(BaseModel):
    key: str
    value_type: str
    unit: str


class PlatformAppEntitlementCatalogResponse(BaseModel):
    items: list[PlatformAppEntitlementCatalogItem]


class PlatformAppPlanEntitlementOut(BaseModel):
    key: str
    value: int | bool | str


class PlatformAppPlanEntitlementIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: int = Field(..., ge=0)


class PlatformAppPlanListItem(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    billing_interval: str
    price_amount: str
    currency: str
    is_default: bool
    is_active: bool
    sort_order: int
    active_entitlement_count: int = 0
    entitlements: list[PlatformAppPlanEntitlementOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PlatformAppPlanListResponse(BaseModel):
    items: list[PlatformAppPlanListItem]
    total: int
    limit: int
    offset: int


class PlatformAppPlanDetailOut(PlatformAppPlanListItem):
    pass


class PlatformAppPlanCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price_amount: str = Field(default="0.00")
    currency: str = Field(default="SAR", min_length=3, max_length=3)
    billing_interval: str = Field(default="none")
    is_default: bool = False
    sort_order: int = Field(default=0, ge=0)
    entitlements: list[PlatformAppPlanEntitlementIn] = Field(default_factory=list)


class PlatformAppPlanUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price_amount: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_default: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    billing_interval: str | None = None
    entitlements: list[PlatformAppPlanEntitlementIn] | None = None
    reason: str | None = Field(default=None, max_length=500)


class PlatformAppListItem(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    short_description: str
    category_slug: str
    category_name_key: str
    billing_type: str
    status: str
    icon_url: str | None = None
    connector_key: str | None = None
    connector_kind: str | None = None
    plans_count: int = 0
    installations_count: int = 0
    active_entitlements_count: int = 0
    created_at: datetime
    updated_at: datetime


class PlatformAppListResponse(BaseModel):
    items: list[PlatformAppListItem]
    total: int
    limit: int
    offset: int


class PlatformAppDetailOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    short_description: str
    description: str | None = None
    category_id: uuid.UUID
    category_slug: str
    category_name_key: str
    billing_type: str
    status: str
    is_featured: bool
    icon_url: str | None = None
    connector_key: str | None = None
    connector_kind: str | None = None
    sort_order: int
    slug_locked: bool = False
    billing_type_locked: bool = False
    connector_locked: bool = False
    is_seeded: bool = False
    disable_allowed: bool = True
    plans: list[PlatformAppPlanListItem] = Field(default_factory=list)
    installations_count: int = 0
    active_licenses_count: int = 0
    active_subscriptions_count: int = 0
    created_at: datetime
    updated_at: datetime


class PlatformAppCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(..., min_length=1, max_length=200)
    short_description: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    category_id: uuid.UUID
    billing_type: str = Field(default="free")
    icon_url: str | None = Field(default=None, max_length=1024)
    connector_key: str | None = Field(default=None, max_length=64)
    connector_kind: str | None = Field(default=None, max_length=32)
    is_featured: bool = False
    sort_order: int = 0


class PlatformAppUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    short_description: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    category_id: uuid.UUID | None = None
    billing_type: str | None = None
    icon_url: str | None = Field(default=None, max_length=1024)
    connector_key: str | None = Field(default=None, max_length=64)
    connector_kind: str | None = Field(default=None, max_length=32)
    is_featured: bool | None = None
    sort_order: int | None = None


class PlatformAppLifecycleRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class PlatformAppWorkspaceEntitlementOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    access_status: str
    installed: bool
    plan_id: uuid.UUID | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    license_status: str | None = None
    license_source: str | None = None
    subscription_status: str | None = None
    subscription_source: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    entitlements: dict[str, Any] = Field(default_factory=dict)


class PlatformAppWorkspaceEntitlementListResponse(BaseModel):
    items: list[PlatformAppWorkspaceEntitlementOut]
    total: int
    limit: int
    offset: int


class PlatformWorkspaceAppOut(BaseModel):
    app_id: uuid.UUID
    app_slug: str
    app_name: str
    billing_type: str
    catalog_status: str
    access_status: str
    installed: bool
    installation_status: str | None = None
    plan_id: uuid.UUID | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    license_status: str | None = None
    license_source: str | None = None
    subscription_status: str | None = None
    subscription_source: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    entitlements: dict[str, Any] = Field(default_factory=dict)
    connections_used: int | None = None
    connections_limit: int | None = None
    widgets_used: int | None = None
    widgets_limit: int | None = None


class PlatformWorkspaceAppsResponse(BaseModel):
    items: list[PlatformWorkspaceAppOut]


class PlatformAppLicenseGrantRequest(BaseModel):
    app_plan_id: uuid.UUID
    reason: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=128)


class PlatformAppLicenseRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class PlatformAppSubscriptionGrantRequest(BaseModel):
    app_plan_id: uuid.UUID
    reason: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=128)


class PlatformAppSubscriptionExtendRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=128)


class PlatformAppSubscriptionRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class PlatformAppCommercialGrantResponse(BaseModel):
    workspace_id: uuid.UUID
    app_id: uuid.UUID
    license_id: uuid.UUID | None = None
    subscription_id: uuid.UUID | None = None
    access_status: str
    idempotent_replay: bool = False


# --- Phase 12F: Payment gateways ---


class PlatformGatewayCredentialStatusOut(BaseModel):
    profile_id_configured: bool | None = None
    server_key_configured: bool | None = None
    profile_id: str | None = None


class PlatformPaymentGatewayListItem(BaseModel):
    id: uuid.UUID | None = None
    code: str
    display_name: str
    enabled: bool
    test_mode: bool | None = None
    configured: bool
    credential_field_status: PlatformGatewayCredentialStatusOut
    created_at: datetime | None = None
    updated_at: datetime | None = None
    referenced_purchases_count: int = 0
    in_flight_purchases_count: int = 0


class PlatformPaymentGatewayListResponse(BaseModel):
    items: list[PlatformPaymentGatewayListItem]
    active_gateway_id: uuid.UUID | None = None


class PlatformPaymentGatewayDetailOut(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str
    enabled: bool
    test_mode: bool
    configured: bool
    credentials: PlatformGatewayCredentialStatusOut
    created_at: datetime
    updated_at: datetime
    referenced_purchases_count: int
    in_flight_purchases_count: int


class PlatformPaymentGatewayCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    test_mode: bool = True
    credentials: dict[str, str] | None = None


class PlatformPaymentGatewayUpdateRequest(BaseModel):
    test_mode: bool | None = None
    credentials: dict[str, str] | None = None
    profile_id: str | None = Field(default=None, max_length=128)


class PlatformPaymentGatewayActivateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# --- Phase 12F: Purchases ---


class PlatformPurchaseWorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class PlatformPurchaseActorOut(BaseModel):
    id: uuid.UUID
    email: str


class PlatformPurchaseTargetOut(BaseModel):
    kind: str
    item_name: str | None = None
    item_code: str | None = None
    credits: int | None = None
    app_id: str | None = None
    app_slug: str | None = None
    app_name: str | None = None


class PlatformPurchaseListItem(BaseModel):
    id: uuid.UUID
    workspace: PlatformPurchaseWorkspaceOut
    actor: PlatformPurchaseActorOut
    kind: str
    status: str
    amount: str
    currency: str
    gateway_code: str
    gateway_config_id: uuid.UUID
    cart_id: str
    tran_ref: str | None = None
    target: PlatformPurchaseTargetOut
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    reconcile_eligible: bool = False
    invoice_available: bool = False


class PlatformPurchaseListResponse(BaseModel):
    items: list[PlatformPurchaseListItem]
    total: int
    limit: int
    offset: int


class PlatformPurchaseFulfillmentOut(BaseModel):
    fulfilled: bool
    invoice_available: bool
    invoice_number: str | None = None


class PlatformPurchaseGatewayOut(BaseModel):
    code: str
    display_name: str
    gateway_config_id: uuid.UUID
    cart_id: str
    tran_ref: str | None = None
    provider_status: str | None = None
    last_query_status: str | None = None


class PlatformPurchaseDetailOut(BaseModel):
    id: uuid.UUID
    workspace: PlatformPurchaseWorkspaceOut
    actor: PlatformPurchaseActorOut
    kind: str
    status: str
    amount: str
    currency: str
    target: PlatformPurchaseTargetOut
    gateway: PlatformPurchaseGatewayOut
    fulfillment: PlatformPurchaseFulfillmentOut
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    reconcile_eligible: bool = False


class PlatformPurchaseReconcileResponse(BaseModel):
    purchase: PlatformPurchaseDetailOut
    prior_status: str
    resulting_status: str
    fulfillment_applied: bool
    provider_status: str | None = None
    idempotent_replay: bool = False


# --- Phase 12G: Dashboard / Usage analytics / Audit logs ---


class PlatformDashboardWorkspacesOut(BaseModel):
    total: int
    active: int
    disabled: int


class PlatformDashboardUsersOut(BaseModel):
    total: int
    active: int
    disabled: int


class PlatformDashboardExpertsOut(BaseModel):
    published: int
    draft: int


class PlatformDashboardUsageOut(BaseModel):
    billed_tokens_24h: int
    billed_tokens_7d: int
    billed_tokens_30d: int
    active_workspaces_30d: int
    outstanding_credit_balance: int


class PlatformDashboardBillingOut(BaseModel):
    active_subscriptions: int
    pending_purchases: int
    failed_purchases_30d: int
    paid_purchase_count_30d: int
    paid_purchase_volume_30d: str


class PlatformDashboardAppsOut(BaseModel):
    published: int
    active_subscriptions: int
    active_licenses: int
    installations: int


class PlatformDashboardGatewayOut(BaseModel):
    gateway_config_id: uuid.UUID
    code: str
    enabled: bool
    test_mode: bool


class PlatformAuditActorOut(BaseModel):
    user_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    email: str | None = None


class PlatformAuditWorkspaceOut(BaseModel):
    workspace_id: uuid.UUID
    name: str
    slug: str


class PlatformAuditResourceOut(BaseModel):
    entity_type: str
    entity_id: uuid.UUID | None = None


class PlatformAuditListItemOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor: PlatformAuditActorOut | None = None
    workspace: PlatformAuditWorkspaceOut | None = None
    action: str
    resource: PlatformAuditResourceOut
    request_id: str | None = None
    summary: str | None = None


class PlatformDashboardSummaryOut(BaseModel):
    workspaces: PlatformDashboardWorkspacesOut
    users: PlatformDashboardUsersOut
    experts: PlatformDashboardExpertsOut
    usage: PlatformDashboardUsageOut
    billing: PlatformDashboardBillingOut
    apps: PlatformDashboardAppsOut
    gateway: PlatformDashboardGatewayOut | None = None
    recent_activity: list[PlatformAuditListItemOut] = Field(default_factory=list)


class PlatformUsagePeakDayOut(BaseModel):
    day: date
    billed_tokens: int


class PlatformUsageFamilyBreakdownOut(BaseModel):
    family: str
    billed_tokens: int
    percentage: float


class PlatformUsageSourceBreakdownOut(BaseModel):
    source: str
    billed_tokens: int
    percentage: float


class PlatformUsageSummaryOut(BaseModel):
    from_day: date
    to_day: date
    total_billed_tokens: int
    active_workspaces: int
    average_daily_billed_tokens: int
    peak_day: PlatformUsagePeakDayOut | None = None
    families: list[PlatformUsageFamilyBreakdownOut] = Field(default_factory=list)
    sources: list[PlatformUsageSourceBreakdownOut] = Field(default_factory=list)


class PlatformUsageTrendPointOut(BaseModel):
    date: date
    billed_tokens: int
    active_workspaces: int


class PlatformUsageTrendResponse(BaseModel):
    from_day: date
    to_day: date
    points: list[PlatformUsageTrendPointOut]


class PlatformUsageWorkspaceItemOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    workspace_status: str
    billed_tokens: int
    percentage_of_platform_usage: float
    active_days: int
    current_plan_code: str | None = None
    current_plan_name: str | None = None


class PlatformUsageWorkspacesResponse(BaseModel):
    items: list[PlatformUsageWorkspaceItemOut]
    total: int
    limit: int
    offset: int
    from_day: date
    to_day: date
    platform_total_billed_tokens: int


class PlatformUsageEventItemOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    workspace_id: uuid.UUID | None = None
    workspace_name: str | None = None
    workspace_slug: str | None = None
    user_id: uuid.UUID | None = None
    expert_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    family: str
    operation_type: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    billed_tokens: int
    cost_metadata: dict[str, Any] = Field(default_factory=dict)


class PlatformUsageEventsResponse(BaseModel):
    items: list[PlatformUsageEventItemOut]
    total: int
    limit: int
    offset: int
    from_day: date
    to_day: date


class PlatformWorkspaceUsageSummaryOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    workspace_status: str
    workspace_kind: str
    from_day: date
    to_day: date
    total_billed_tokens: int
    families: list[PlatformUsageFamilyBreakdownOut] = Field(default_factory=list)
    sources: list[PlatformUsageSourceBreakdownOut] = Field(default_factory=list)


class PlatformWorkspaceUsageTrendResponse(BaseModel):
    workspace_id: uuid.UUID
    from_day: date
    to_day: date
    points: list[PlatformUsageTrendPointOut]


class PlatformAuditListResponse(BaseModel):
    items: list[PlatformAuditListItemOut]
    total: int
    limit: int
    offset: int


class PlatformAuditLogDetailOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor: PlatformAuditActorOut | None = None
    workspace: PlatformAuditWorkspaceOut | None = None
    action: str
    resource: PlatformAuditResourceOut
    request_id: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
