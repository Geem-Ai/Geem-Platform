"""Platform Admin HTTP surface.

All routes require:

- APP_ADMIN_HOST (enforced in production; relaxed in local/test)
- an authenticated human session (not a Workspace API key)
- users.platform_role == admin

Workspace membership / X-Workspace-* headers are ignored as grants.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.schemas import DocumentCreateResponse
from app.common.http import content_disposition
from app.db.session import get_db
from app.experts.schemas import (
    ExpertDocumentLinkOut,
    ExpertDocumentLinkRequest,
    ExpertUpdateRequest,
    ExpertUploadResponse,
    PlatformExpertCreateRequest,
    PlatformExpertGrantRequest,
)
from app.experts.service import ExpertService
from app.identity.models import User
from app.platform_admin.apps import PlatformAdminAppsService
from app.platform_admin.audit_logs import PlatformAuditLogsService
from app.platform_admin.billing import PlatformAdminBillingService
from app.platform_admin.dashboard import PlatformDashboardService
from app.platform_admin.dependencies import (
    require_platform_admin,
    require_platform_admin_host,
)
from app.platform_admin.experts import PlatformAdminExpertsService
from app.platform_admin.gateways import PlatformAdminGatewaysService
from app.platform_admin.purchases import PlatformAdminPurchasesService
from app.platform_admin.schemas import (
    PlatformAppCategoryListResponse,
    PlatformAppCategoryOut,
    PlatformAppCategoryUpdateRequest,
    PlatformAppCommercialGrantResponse,
    PlatformAppCreateRequest,
    PlatformAppDetailOut,
    PlatformAppEntitlementCatalogResponse,
    PlatformAppLicenseGrantRequest,
    PlatformAppLicenseRevokeRequest,
    PlatformAppLifecycleRequest,
    PlatformAppListResponse,
    PlatformAppPlanCreateRequest,
    PlatformAppPlanDetailOut,
    PlatformAppPlanListResponse,
    PlatformAppPlanUpdateRequest,
    PlatformAppSubscriptionExtendRequest,
    PlatformAppSubscriptionGrantRequest,
    PlatformAppSubscriptionRevokeRequest,
    PlatformAppUpdateRequest,
    PlatformAppWorkspaceEntitlementListResponse,
    PlatformAuditListResponse,
    PlatformAuditLogDetailOut,
    PlatformCreditGrantRequest,
    PlatformCreditGrantResponse,
    PlatformCreditHistoryResponse,
    PlatformDashboardSummaryOut,
    PlatformEntitlementCatalogResponse,
    PlatformExpertDetailOut,
    PlatformExpertGrantListResponse,
    PlatformExpertKnowledgeListResponse,
    PlatformExpertListResponse,
    PlatformExpertWorkspaceGrantOut,
    PlatformMeResponse,
    PlatformPlanCreateRequest,
    PlatformPlanDetailOut,
    PlatformPlanLifecycleRequest,
    PlatformPlanListResponse,
    PlatformPlanUpdateRequest,
    PlatformPaymentGatewayActivateRequest,
    PlatformPaymentGatewayCreateRequest,
    PlatformPaymentGatewayDetailOut,
    PlatformPaymentGatewayListResponse,
    PlatformPaymentGatewayUpdateRequest,
    PlatformPurchaseDetailOut,
    PlatformPurchaseListResponse,
    PlatformPurchaseReconcileResponse,
    PlatformUsageEventsResponse,
    PlatformUsageSummaryOut,
    PlatformUsageTrendResponse,
    PlatformUsageWorkspacesResponse,
    PlatformWorkspaceUsageSummaryOut,
    PlatformWorkspaceUsageTrendResponse,
    PlatformSubscriptionAssignRequest,
    PlatformSubscriptionDetailOut,
    PlatformSubscriptionHistoryResponse,
    PlatformUserDetailOut,
    PlatformUserDisableRequest,
    PlatformUserLifecycleRequest,
    PlatformUserListResponse,
    PlatformWorkspaceCreditsOut,
    PlatformWorkspaceDetailOut,
    PlatformWorkspaceEnableRequest,
    PlatformWorkspaceEntitlementsOut,
    PlatformWorkspaceLifecycleRequest,
    PlatformWorkspaceListResponse,
    PlatformWorkspaceMembersResponse,
    PlatformWorkspaceUsageOut,
    PlatformWorkspaceAppsResponse,
    PlatformWorkspaceAppOut,
)
from app.platform_admin.service import PlatformAdminService
from app.platform_admin.usage_analytics import PlatformUsageAnalyticsService, parse_usage_sort_field
from app.worker.tasks import enqueue_ingest

router = APIRouter(
    prefix="/api/platform",
    tags=["platform"],
    dependencies=[Depends(require_platform_admin_host)],
)


@router.get("/me", response_model=PlatformMeResponse)
def platform_me(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformMeResponse:
    """Authoritative Platform Admin identity bootstrap. No tenant Workspace."""
    return PlatformAdminService(db).get_me(actor=user)


# --- Phase 12G: Dashboard / Usage / Audit ---


@router.get("/dashboard/summary", response_model=PlatformDashboardSummaryOut)
def platform_dashboard_summary(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformDashboardSummaryOut:
    return PlatformDashboardService(db).summary(user)


@router.get("/usage/summary", response_model=PlatformUsageSummaryOut)
def platform_usage_summary(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
) -> PlatformUsageSummaryOut:
    return PlatformUsageAnalyticsService(db).summary(user, from_day=from_day, to_day=to_day)


@router.get("/usage/trend", response_model=PlatformUsageTrendResponse)
def platform_usage_trend(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
) -> PlatformUsageTrendResponse:
    return PlatformUsageAnalyticsService(db).trend(user, from_day=from_day, to_day=to_day)


@router.get("/usage/workspaces", response_model=PlatformUsageWorkspacesResponse)
def platform_usage_workspaces(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="billed_tokens", max_length=32),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
) -> PlatformUsageWorkspacesResponse:
    return PlatformUsageAnalyticsService(db).top_workspaces(
        user,
        from_day=from_day,
        to_day=to_day,
        limit=limit,
        offset=offset,
        search=search,
        sort=parse_usage_sort_field(sort),
    )


@router.get("/usage/events", response_model=PlatformUsageEventsResponse)
def platform_usage_events(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    from_day: date = Query(alias="from"),
    to_day: date = Query(alias="to"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workspace_id: uuid.UUID | None = Query(default=None),
    family: str | None = Query(default=None, max_length=32),
    operation_type: str | None = Query(default=None, max_length=64),
    api_key_id: uuid.UUID | None = Query(default=None),
) -> PlatformUsageEventsResponse:
    return PlatformUsageAnalyticsService(db).list_events(
        user,
        from_day=from_day,
        to_day=to_day,
        limit=limit,
        offset=offset,
        workspace_id=workspace_id,
        family=family,
        operation_type=operation_type,
        api_key_id=api_key_id,
    )


@router.get(
    "/workspaces/{workspace_id}/usage/summary",
    response_model=PlatformWorkspaceUsageSummaryOut,
)
def platform_workspace_usage_summary(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
) -> PlatformWorkspaceUsageSummaryOut:
    return PlatformUsageAnalyticsService(db).workspace_summary(
        user, workspace_id, from_day=from_day, to_day=to_day
    )


@router.get(
    "/workspaces/{workspace_id}/usage/trend",
    response_model=PlatformWorkspaceUsageTrendResponse,
)
def platform_workspace_usage_trend(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
) -> PlatformWorkspaceUsageTrendResponse:
    return PlatformUsageAnalyticsService(db).workspace_trend(
        user, workspace_id, from_day=from_day, to_day=to_day
    )


@router.get("/audit-logs", response_model=PlatformAuditListResponse)
def list_platform_audit_logs(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    actor_user_id: uuid.UUID | None = Query(default=None),
    workspace_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=128),
    entity_type: str | None = Query(default=None, max_length=64),
    entity_id: uuid.UUID | None = Query(default=None),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    scope: str | None = Query(default=None, max_length=32),
) -> PlatformAuditListResponse:
    return PlatformAuditLogsService(db).list_logs(
        user,
        limit=limit,
        offset=offset,
        search=search,
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
        scope=scope,
    )


@router.get("/audit-logs/{audit_id}", response_model=PlatformAuditLogDetailOut)
def get_platform_audit_log(
    audit_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAuditLogDetailOut:
    return PlatformAuditLogsService(db).get_log(user, audit_id)


# --- Phase 12B: Workspaces ---


@router.get("/workspaces", response_model=PlatformWorkspaceListResponse)
def list_platform_workspaces(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=32),
    kind: str | None = Query(default=None, max_length=32),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
) -> PlatformWorkspaceListResponse:
    return PlatformAdminService(db).list_workspaces(
        actor=user,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        kind=kind,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/workspaces/{workspace_id}", response_model=PlatformWorkspaceDetailOut)
def get_platform_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceDetailOut:
    return PlatformAdminService(db).get_workspace(actor=user, workspace_id=workspace_id)


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=PlatformWorkspaceMembersResponse,
)
def list_platform_workspace_members(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlatformWorkspaceMembersResponse:
    return PlatformAdminService(db).list_workspace_members(
        actor=user,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workspaces/{workspace_id}/disable",
    response_model=PlatformWorkspaceDetailOut,
)
def disable_platform_workspace(
    workspace_id: uuid.UUID,
    body: PlatformWorkspaceLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceDetailOut:
    return PlatformAdminService(db).disable_workspace(
        actor=user, workspace_id=workspace_id, reason=body.reason
    )


@router.post(
    "/workspaces/{workspace_id}/enable",
    response_model=PlatformWorkspaceDetailOut,
)
def enable_platform_workspace(
    workspace_id: uuid.UUID,
    body: PlatformWorkspaceEnableRequest = PlatformWorkspaceEnableRequest(),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceDetailOut:
    return PlatformAdminService(db).enable_workspace(
        actor=user, workspace_id=workspace_id, reason=body.reason
    )


# --- Phase 12B: Users ---


@router.get("/users", response_model=PlatformUserListResponse)
def list_platform_users(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=320),
    status: str | None = Query(default=None, max_length=32),
    platform_role: str | None = Query(default=None, max_length=32),
) -> PlatformUserListResponse:
    return PlatformAdminService(db).list_users(
        actor=user,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        platform_role=platform_role,
    )


@router.get("/users/{user_id}", response_model=PlatformUserDetailOut)
def get_platform_user(
    user_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformUserDetailOut:
    return PlatformAdminService(db).get_user(actor=user, user_id=user_id)


@router.post("/users/{user_id}/disable", response_model=PlatformUserDetailOut)
def disable_platform_user(
    user_id: uuid.UUID,
    body: PlatformUserDisableRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformUserDetailOut:
    return PlatformAdminService(db).disable_user(
        actor=user, user_id=user_id, reason=body.reason
    )


@router.post("/users/{user_id}/enable", response_model=PlatformUserDetailOut)
def enable_platform_user(
    user_id: uuid.UUID,
    body: PlatformUserLifecycleRequest = PlatformUserLifecycleRequest(),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformUserDetailOut:
    return PlatformAdminService(db).enable_user(
        actor=user, user_id=user_id, reason=body.reason
    )


# --- Phase 12C: Plans / Workspace billing / Credits ---


@router.get("/entitlement-catalog", response_model=PlatformEntitlementCatalogResponse)
def platform_entitlement_catalog(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformEntitlementCatalogResponse:
    return PlatformAdminBillingService(db).entitlement_catalog(actor=user)


@router.get("/plans", response_model=PlatformPlanListResponse)
def list_platform_plans(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=32),
    currency: str | None = Query(default=None, max_length=3),
) -> PlatformPlanListResponse:
    return PlatformAdminBillingService(db).list_plans(
        actor=user,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        currency=currency,
    )


@router.post("/plans", response_model=PlatformPlanDetailOut, status_code=201)
def create_platform_plan(
    body: PlatformPlanCreateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPlanDetailOut:
    return PlatformAdminBillingService(db).create_plan(actor=user, body=body)


@router.get("/plans/{plan_id}", response_model=PlatformPlanDetailOut)
def get_platform_plan(
    plan_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPlanDetailOut:
    return PlatformAdminBillingService(db).get_plan(actor=user, plan_id=plan_id)


@router.patch("/plans/{plan_id}", response_model=PlatformPlanDetailOut)
def update_platform_plan(
    plan_id: uuid.UUID,
    body: PlatformPlanUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPlanDetailOut:
    return PlatformAdminBillingService(db).update_plan(
        actor=user, plan_id=plan_id, body=body
    )


@router.post("/plans/{plan_id}/activate", response_model=PlatformPlanDetailOut)
def activate_platform_plan(
    plan_id: uuid.UUID,
    body: PlatformPlanLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPlanDetailOut:
    return PlatformAdminBillingService(db).activate_plan(
        actor=user, plan_id=plan_id, body=body
    )


@router.post("/plans/{plan_id}/deactivate", response_model=PlatformPlanDetailOut)
def deactivate_platform_plan(
    plan_id: uuid.UUID,
    body: PlatformPlanLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPlanDetailOut:
    return PlatformAdminBillingService(db).deactivate_plan(
        actor=user, plan_id=plan_id, body=body
    )


@router.get(
    "/workspaces/{workspace_id}/subscription",
    response_model=PlatformSubscriptionDetailOut | None,
)
def get_platform_workspace_subscription(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformSubscriptionDetailOut | None:
    return PlatformAdminBillingService(db).get_workspace_subscription(
        actor=user, workspace_id=workspace_id
    )


@router.get(
    "/workspaces/{workspace_id}/subscriptions",
    response_model=PlatformSubscriptionHistoryResponse,
)
def list_platform_workspace_subscriptions(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlatformSubscriptionHistoryResponse:
    return PlatformAdminBillingService(db).list_workspace_subscriptions(
        actor=user, workspace_id=workspace_id, limit=limit, offset=offset
    )


@router.post(
    "/workspaces/{workspace_id}/subscription/assign",
    response_model=PlatformSubscriptionDetailOut,
)
def assign_platform_workspace_subscription(
    workspace_id: uuid.UUID,
    body: PlatformSubscriptionAssignRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformSubscriptionDetailOut:
    return PlatformAdminBillingService(db).assign_workspace_subscription(
        actor=user, workspace_id=workspace_id, body=body
    )


@router.get(
    "/workspaces/{workspace_id}/entitlements",
    response_model=PlatformWorkspaceEntitlementsOut,
)
def get_platform_workspace_entitlements(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceEntitlementsOut:
    return PlatformAdminBillingService(db).get_workspace_entitlements(
        actor=user, workspace_id=workspace_id
    )


@router.get(
    "/workspaces/{workspace_id}/usage",
    response_model=PlatformWorkspaceUsageOut,
)
def get_platform_workspace_usage(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceUsageOut:
    return PlatformAdminBillingService(db).get_workspace_usage(
        actor=user, workspace_id=workspace_id
    )


@router.get(
    "/workspaces/{workspace_id}/credits",
    response_model=PlatformWorkspaceCreditsOut,
)
def get_platform_workspace_credits(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceCreditsOut:
    return PlatformAdminBillingService(db).get_workspace_credits(
        actor=user, workspace_id=workspace_id
    )


@router.get(
    "/workspaces/{workspace_id}/credits/history",
    response_model=PlatformCreditHistoryResponse,
)
def list_platform_workspace_credit_history(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlatformCreditHistoryResponse:
    return PlatformAdminBillingService(db).list_workspace_credit_history(
        actor=user, workspace_id=workspace_id, limit=limit, offset=offset
    )


@router.post(
    "/workspaces/{workspace_id}/credits/grant",
    response_model=PlatformCreditGrantResponse,
)
def grant_platform_workspace_credits(
    workspace_id: uuid.UUID,
    body: PlatformCreditGrantRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformCreditGrantResponse:
    return PlatformAdminBillingService(db).grant_workspace_credits(
        actor=user, workspace_id=workspace_id, body=body
    )


# --- Phase 12D: Platform Experts ---


@router.get("/experts", response_model=PlatformExpertListResponse)
def list_platform_experts(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=32),
    visibility: str | None = Query(default=None, max_length=32),
    knowledge_mode: str | None = Query(default=None, max_length=32),
    availability_mode: str | None = Query(default=None, max_length=32),
    published: bool | None = Query(default=None),
) -> PlatformExpertListResponse:
    return PlatformAdminExpertsService(db).list_experts(
        user,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        visibility=visibility,
        knowledge_mode=knowledge_mode,
        availability_mode=availability_mode,
        published=published,
    )


@router.post("/experts", response_model=PlatformExpertDetailOut, status_code=201)
def create_platform_expert(
    body: PlatformExpertCreateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).create_expert(user, body)


@router.get("/experts/{expert_id}", response_model=PlatformExpertDetailOut)
def get_platform_expert(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).get_expert(user, expert_id)


@router.patch("/experts/{expert_id}", response_model=PlatformExpertDetailOut)
def update_platform_expert(
    expert_id: uuid.UUID,
    body: ExpertUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).update_expert(user, expert_id, body)


@router.post("/experts/{expert_id}/publish", response_model=PlatformExpertDetailOut)
def publish_platform_expert(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).publish_expert(user, expert_id)


@router.post("/experts/{expert_id}/unpublish", response_model=PlatformExpertDetailOut)
def unpublish_platform_expert(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).unpublish_expert(user, expert_id)


@router.delete("/experts/{expert_id}", status_code=204)
def delete_platform_expert(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    PlatformAdminExpertsService(db).delete_expert(user, expert_id)


@router.get(
    "/experts/{expert_id}/workspace-grants",
    response_model=PlatformExpertGrantListResponse,
)
def list_platform_expert_workspace_grants(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
) -> PlatformExpertGrantListResponse:
    return PlatformAdminExpertsService(db).list_workspace_grants(
        user, expert_id, limit=limit, offset=offset, search=search
    )


@router.post(
    "/experts/{expert_id}/workspace-grants",
    response_model=PlatformExpertWorkspaceGrantOut,
    status_code=201,
)
def grant_platform_expert_workspace(
    expert_id: uuid.UUID,
    body: PlatformExpertGrantRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertWorkspaceGrantOut:
    return PlatformAdminExpertsService(db).grant_workspace(user, expert_id, body)


@router.delete(
    "/experts/{expert_id}/workspace-grants/{workspace_id}",
    status_code=204,
)
def revoke_platform_expert_workspace(
    expert_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    PlatformAdminExpertsService(db).revoke_workspace(user, expert_id, workspace_id)


@router.post(
    "/experts/{expert_id}/grants",
    response_model=PlatformExpertWorkspaceGrantOut,
    status_code=201,
)
def grant_platform_expert(
    expert_id: uuid.UUID,
    body: PlatformExpertGrantRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertWorkspaceGrantOut:
    return PlatformAdminExpertsService(db).grant_workspace(user, expert_id, body)


@router.delete("/experts/{expert_id}/grants/{workspace_id}", status_code=204)
def revoke_platform_expert(
    expert_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    PlatformAdminExpertsService(db).revoke_workspace(user, expert_id, workspace_id)


@router.post("/experts/{expert_id}/access/all", response_model=PlatformExpertDetailOut)
def enable_platform_expert_all_workspaces(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).enable_all_workspaces(user, expert_id)


@router.delete("/experts/{expert_id}/access/all", response_model=PlatformExpertDetailOut)
def disable_platform_expert_all_workspaces(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformExpertDetailOut:
    return PlatformAdminExpertsService(db).disable_all_workspaces(user, expert_id)


@router.get(
    "/experts/{expert_id}/knowledge",
    response_model=PlatformExpertKnowledgeListResponse,
)
def list_platform_expert_knowledge(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlatformExpertKnowledgeListResponse:
    return PlatformAdminExpertsService(db).list_knowledge(
        user, expert_id, limit=limit, offset=offset
    )


@router.post(
    "/experts/{expert_id}/documents",
    response_model=ExpertDocumentLinkOut,
    status_code=201,
)
def link_platform_expert_document(
    expert_id: uuid.UUID,
    body: ExpertDocumentLinkRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> ExpertDocumentLinkOut:
    link = PlatformAdminExpertsService(db).link_document(user, expert_id, body)
    return ExpertDocumentLinkOut.model_validate(link)


@router.post(
    "/experts/{expert_id}/knowledge",
    response_model=ExpertUploadResponse,
    status_code=201,
)
async def upload_platform_expert_knowledge(
    expert_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> ExpertUploadResponse:
    data = await file.read()
    result = PlatformAdminExpertsService(db).upload_knowledge(
        user,
        expert_id,
        file_bytes=data,
        filename=file.filename or "document",
        title=title,
        declared_mime_type=file.content_type,
    )
    return ExpertUploadResponse(
        expert_id=result.expert_id,
        source_id=result.source_id,
        document_id=result.document.id,
        status=result.document.status,
        mime_type=result.document.mime_type,
        page_count=result.document.page_count,
        reused=result.reused,
    )


@router.post(
    "/experts/{expert_id}/knowledge/{document_id}/reprocess",
    status_code=202,
)
def reprocess_platform_expert_knowledge(
    expert_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    mode: str = Query(default="full", max_length=32),
) -> dict[str, str]:
    job = PlatformAdminExpertsService(db).reprocess_knowledge(
        user, expert_id, document_id, mode=mode
    )
    return {"job_id": str(job.id), "status": job.status}


@router.delete("/experts/{expert_id}/knowledge/{document_id}", status_code=204)
def remove_platform_expert_knowledge(
    expert_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    PlatformAdminExpertsService(db).remove_knowledge(user, expert_id, document_id)


@router.post("/knowledge/documents", response_model=DocumentCreateResponse, status_code=201)
async def upload_platform_knowledge_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> DocumentCreateResponse:
    """Upload a Document into the Platform Knowledge system Workspace."""
    data = await file.read()
    svc = ExpertService(db)
    doc = svc.upload_platform_knowledge_document(
        actor=user,
        file_bytes=data,
        filename=file.filename or "document.pdf",
        title=title,
    )
    from app.workspaces.service import WorkspaceService

    pk = WorkspaceService(db).get_platform_knowledge_workspace()
    enqueue_ingest(
        str(doc.id),
        mode="full",
        workspace_id=str(pk.id),
        actor_id=str(user.id),
    )
    return DocumentCreateResponse(
        id=doc.id,
        status=doc.status,
        page_count=doc.page_count,
        byte_size=doc.byte_size,
    )


@router.post(
    "/experts/{expert_id}/upload",
    response_model=ExpertUploadResponse,
    status_code=201,
)
async def upload_platform_expert_document(
    expert_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> ExpertUploadResponse:
    """Privileged upload for a Platform Expert (Phase 3B legacy path)."""
    data = await file.read()
    result = PlatformAdminExpertsService(db).upload_knowledge(
        user,
        expert_id,
        file_bytes=data,
        filename=file.filename or "document",
        title=title,
        declared_mime_type=file.content_type,
    )
    return ExpertUploadResponse(
        expert_id=result.expert_id,
        source_id=result.source_id,
        document_id=result.document.id,
        status=result.document.status,
        mime_type=result.document.mime_type,
        page_count=result.document.page_count,
        reused=result.reused,
    )


# --- Phase 12E: App Store ---


@router.get("/app-categories", response_model=PlatformAppCategoryListResponse)
def list_platform_app_categories(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCategoryListResponse:
    return PlatformAdminAppsService(db).list_categories(user)


@router.patch("/app-categories/{category_id}", response_model=PlatformAppCategoryOut)
def update_platform_app_category(
    category_id: uuid.UUID,
    body: PlatformAppCategoryUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCategoryOut:
    return PlatformAdminAppsService(db).update_category(user, category_id, body)


@router.get("/apps", response_model=PlatformAppListResponse)
def list_platform_apps(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=32),
    billing_type: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=64),
    connector_kind: str | None = Query(default=None, max_length=32),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppListResponse:
    return PlatformAdminAppsService(db).list_apps(
        user,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        billing_type=billing_type,
        category=category,
        connector_kind=connector_kind,
    )


@router.post("/apps", response_model=PlatformAppDetailOut, status_code=201)
def create_platform_app(
    body: PlatformAppCreateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).create_app(user, body)


@router.get("/apps/{app_id}", response_model=PlatformAppDetailOut)
def get_platform_app(
    app_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).get_app(user, app_id)


@router.patch("/apps/{app_id}", response_model=PlatformAppDetailOut)
def update_platform_app(
    app_id: uuid.UUID,
    body: PlatformAppUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).update_app(user, app_id, body)


@router.post("/apps/{app_id}/publish", response_model=PlatformAppDetailOut)
def publish_platform_app(
    app_id: uuid.UUID,
    body: PlatformAppLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).publish_app(user, app_id, body)


@router.post("/apps/{app_id}/unpublish", response_model=PlatformAppDetailOut)
def unpublish_platform_app(
    app_id: uuid.UUID,
    body: PlatformAppLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).unpublish_app(user, app_id, body)


@router.post("/apps/{app_id}/set-coming-soon", response_model=PlatformAppDetailOut)
def set_platform_app_coming_soon(
    app_id: uuid.UUID,
    body: PlatformAppLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).set_coming_soon(user, app_id, body)


@router.post("/apps/{app_id}/disable", response_model=PlatformAppDetailOut)
def disable_platform_app(
    app_id: uuid.UUID,
    body: PlatformAppLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppDetailOut:
    return PlatformAdminAppsService(db).disable_app(user, app_id, body)


@router.get(
    "/apps/{app_id}/entitlement-catalog",
    response_model=PlatformAppEntitlementCatalogResponse,
)
def get_platform_app_entitlement_catalog(
    app_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppEntitlementCatalogResponse:
    return PlatformAdminAppsService(db).app_entitlement_catalog(user, app_id)


@router.get("/apps/{app_id}/plans", response_model=PlatformAppPlanListResponse)
def list_platform_app_plans(
    app_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppPlanListResponse:
    return PlatformAdminAppsService(db).list_plans(
        user, app_id, limit=limit, offset=offset
    )


@router.post("/apps/{app_id}/plans", response_model=PlatformAppPlanDetailOut, status_code=201)
def create_platform_app_plan(
    app_id: uuid.UUID,
    body: PlatformAppPlanCreateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppPlanDetailOut:
    return PlatformAdminAppsService(db).create_plan(user, app_id, body)


@router.patch("/apps/{app_id}/plans/{plan_id}", response_model=PlatformAppPlanDetailOut)
def update_platform_app_plan(
    app_id: uuid.UUID,
    plan_id: uuid.UUID,
    body: PlatformAppPlanUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppPlanDetailOut:
    return PlatformAdminAppsService(db).update_plan(user, app_id, plan_id, body)


@router.post("/apps/{app_id}/plans/{plan_id}/activate", response_model=PlatformAppPlanDetailOut)
def activate_platform_app_plan(
    app_id: uuid.UUID,
    plan_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppPlanDetailOut:
    return PlatformAdminAppsService(db).activate_plan(user, app_id, plan_id)


@router.post(
    "/apps/{app_id}/plans/{plan_id}/deactivate",
    response_model=PlatformAppPlanDetailOut,
)
def deactivate_platform_app_plan(
    app_id: uuid.UUID,
    plan_id: uuid.UUID,
    body: PlatformAppLifecycleRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppPlanDetailOut:
    return PlatformAdminAppsService(db).deactivate_plan(user, app_id, plan_id, body)


@router.get(
    "/apps/{app_id}/workspaces",
    response_model=PlatformAppWorkspaceEntitlementListResponse,
)
def list_platform_app_workspaces(
    app_id: uuid.UUID,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppWorkspaceEntitlementListResponse:
    return PlatformAdminAppsService(db).list_app_workspaces(
        user, app_id, limit=limit, offset=offset
    )


@router.get(
    "/workspaces/{workspace_id}/apps",
    response_model=PlatformWorkspaceAppsResponse,
)
def list_platform_workspace_apps(
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceAppsResponse:
    return PlatformAdminAppsService(db).list_workspace_apps(user, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/license/grant",
    response_model=PlatformAppCommercialGrantResponse,
)
def grant_platform_app_license(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    body: PlatformAppLicenseGrantRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCommercialGrantResponse:
    return PlatformAdminAppsService(db).grant_license(user, workspace_id, app_id, body)


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/license/revoke",
    response_model=PlatformAppCommercialGrantResponse,
)
def revoke_platform_app_license(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    body: PlatformAppLicenseRevokeRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCommercialGrantResponse:
    return PlatformAdminAppsService(db).revoke_license(user, workspace_id, app_id, body)


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/subscription/grant",
    response_model=PlatformAppCommercialGrantResponse,
)
def grant_platform_app_subscription(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    body: PlatformAppSubscriptionGrantRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCommercialGrantResponse:
    return PlatformAdminAppsService(db).grant_subscription(
        user, workspace_id, app_id, body
    )


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/subscription/extend",
    response_model=PlatformAppCommercialGrantResponse,
)
def extend_platform_app_subscription(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    body: PlatformAppSubscriptionExtendRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCommercialGrantResponse:
    return PlatformAdminAppsService(db).extend_subscription(
        user, workspace_id, app_id, body
    )


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/subscription/revoke",
    response_model=PlatformAppCommercialGrantResponse,
)
def revoke_platform_app_subscription(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    body: PlatformAppSubscriptionRevokeRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformAppCommercialGrantResponse:
    return PlatformAdminAppsService(db).revoke_subscription(
        user, workspace_id, app_id, body
    )


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/install",
    response_model=PlatformWorkspaceAppOut,
)
def admin_install_platform_app(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformWorkspaceAppOut:
    return PlatformAdminAppsService(db).admin_install_app(user, workspace_id, app_id)


# --- Phase 12F: Payment gateways ---


@router.get("/payment-gateways", response_model=PlatformPaymentGatewayListResponse)
def list_platform_payment_gateways(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPaymentGatewayListResponse:
    return PlatformAdminGatewaysService(db).list_gateways(user)


@router.post("/payment-gateways", response_model=PlatformPaymentGatewayDetailOut, status_code=201)
def create_platform_payment_gateway(
    body: PlatformPaymentGatewayCreateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPaymentGatewayDetailOut:
    return PlatformAdminGatewaysService(db).create_gateway(user, body)


@router.get(
    "/payment-gateways/{gateway_config_id}",
    response_model=PlatformPaymentGatewayDetailOut,
)
def get_platform_payment_gateway(
    gateway_config_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPaymentGatewayDetailOut:
    return PlatformAdminGatewaysService(db).get_gateway(user, gateway_config_id)


@router.patch(
    "/payment-gateways/{gateway_config_id}",
    response_model=PlatformPaymentGatewayDetailOut,
)
def update_platform_payment_gateway(
    gateway_config_id: uuid.UUID,
    body: PlatformPaymentGatewayUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPaymentGatewayDetailOut:
    return PlatformAdminGatewaysService(db).update_gateway(user, gateway_config_id, body)


@router.post(
    "/payment-gateways/{gateway_config_id}/activate",
    response_model=PlatformPaymentGatewayDetailOut,
)
def activate_platform_payment_gateway(
    gateway_config_id: uuid.UUID,
    body: PlatformPaymentGatewayActivateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPaymentGatewayDetailOut:
    return PlatformAdminGatewaysService(db).activate_gateway(user, gateway_config_id, body)


# --- Phase 12F: Purchases ---


@router.get("/purchases", response_model=PlatformPurchaseListResponse)
def list_platform_purchases(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    workspace_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None, max_length=32),
    kind: str | None = Query(default=None, max_length=32),
    gateway: str | None = Query(default=None, max_length=64),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
) -> PlatformPurchaseListResponse:
    return PlatformAdminPurchasesService(db).list_purchases(
        user,
        limit=limit,
        offset=offset,
        search=search,
        workspace_id=workspace_id,
        status=status,
        kind=kind,
        gateway=gateway,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/purchases/{purchase_id}", response_model=PlatformPurchaseDetailOut)
def get_platform_purchase(
    purchase_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPurchaseDetailOut:
    return PlatformAdminPurchasesService(db).get_purchase(user, purchase_id)


@router.post(
    "/purchases/{purchase_id}/reconcile",
    response_model=PlatformPurchaseReconcileResponse,
)
def reconcile_platform_purchase(
    purchase_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformPurchaseReconcileResponse:
    return PlatformAdminPurchasesService(db).reconcile_purchase(user, purchase_id)


@router.get("/purchases/{purchase_id}/invoice")
def download_platform_purchase_invoice(
    purchase_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> Response:
    pdf, filename = PlatformAdminPurchasesService(db).purchase_invoice(user, purchase_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )
