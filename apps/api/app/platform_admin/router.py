"""Platform Admin HTTP surface.

All routes require:

- APP_ADMIN_HOST (enforced in production; relaxed in local/test)
- an authenticated human session (not a Workspace API key)
- users.platform_role == admin

Workspace membership / X-Workspace-* headers are ignored as grants.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.schemas import DocumentCreateResponse
from app.db.session import get_db
from app.experts.models import Expert
from app.experts.schemas import (
    ExpertDocumentLinkOut,
    ExpertDocumentLinkRequest,
    ExpertOut,
    ExpertUpdateRequest,
    ExpertUploadResponse,
    PlatformExpertCreateRequest,
    PlatformExpertGrantRequest,
    WorkspaceExpertGrantOut,
)
from app.experts.service import ExpertService
from app.identity.models import User
from app.platform_admin.billing import PlatformAdminBillingService
from app.platform_admin.dependencies import (
    require_platform_admin,
    require_platform_admin_host,
)
from app.platform_admin.schemas import (
    PlatformCreditGrantRequest,
    PlatformCreditGrantResponse,
    PlatformCreditHistoryResponse,
    PlatformEntitlementCatalogResponse,
    PlatformMeResponse,
    PlatformPlanCreateRequest,
    PlatformPlanDetailOut,
    PlatformPlanLifecycleRequest,
    PlatformPlanListResponse,
    PlatformPlanUpdateRequest,
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
)
from app.platform_admin.service import PlatformAdminService
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


def _platform_out(expert: Expert) -> ExpertOut:
    return ExpertOut(
        id=expert.id,
        type=expert.type,
        ownership="platform",
        workspace_id=expert.workspace_id,
        name=expert.name,
        description=expert.description,
        icon_url=expert.icon_url,
        system_instructions=expert.system_instructions,
        rag_config=expert.rag_config or {},
        status=expert.status,
        visibility=expert.visibility,
        availability_mode=expert.availability_mode,
        knowledge_mode=getattr(expert, "knowledge_mode", None) or "rag",
        created_by=expert.created_by,
        created_at=expert.created_at,
        updated_at=expert.updated_at,
        knowledge_document_count=0,
    )


@router.get("/experts", response_model=list[ExpertOut])
def list_platform_experts(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[ExpertOut]:
    experts = ExpertService(db).list_platform_experts(actor=user)
    return [_platform_out(e) for e in experts]


@router.post("/experts", response_model=ExpertOut, status_code=201)
def create_platform_expert(
    body: PlatformExpertCreateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> ExpertOut:
    expert = ExpertService(db).create_platform_expert(
        actor=user,
        name=body.name,
        description=body.description,
        system_instructions=body.system_instructions,
        rag_config=body.rag_config,
        visibility=body.visibility,
        status=body.status,
        availability_mode=body.availability_mode,
        icon_url=body.icon_url,
    )
    return _platform_out(expert)


@router.patch("/experts/{expert_id}", response_model=ExpertOut)
def update_platform_expert(
    expert_id: uuid.UUID,
    body: ExpertUpdateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> ExpertOut:
    expert = ExpertService(db).update_platform_expert(
        actor=user,
        expert_id=expert_id,
        name=body.name,
        description=body.description,
        system_instructions=body.system_instructions,
        rag_config=body.rag_config,
        visibility=body.visibility,
        status=body.status,
        availability_mode=body.availability_mode,
        icon_url=body.icon_url,
    )
    return _platform_out(expert)


@router.delete("/experts/{expert_id}", status_code=204)
def delete_platform_expert(
    expert_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).delete_platform_expert(actor=user, expert_id=expert_id)


@router.post(
    "/experts/{expert_id}/grants",
    response_model=WorkspaceExpertGrantOut,
    status_code=201,
)
def grant_platform_expert(
    expert_id: uuid.UUID,
    body: PlatformExpertGrantRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> WorkspaceExpertGrantOut:
    grant = ExpertService(db).grant_platform_expert(
        actor=user,
        expert_id=expert_id,
        workspace_id=body.workspace_id,
    )
    return WorkspaceExpertGrantOut.model_validate(grant)


@router.delete("/experts/{expert_id}/grants/{workspace_id}", status_code=204)
def revoke_platform_expert(
    expert_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).revoke_platform_expert(
        actor=user,
        expert_id=expert_id,
        workspace_id=workspace_id,
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
    link = ExpertService(db).link_platform_document(
        actor=user,
        expert_id=expert_id,
        document_id=body.document_id,
        source_id=body.source_id,
    )
    return ExpertDocumentLinkOut.model_validate(link)


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
    """Privileged upload for a Platform Expert (Phase 3B).

    Requires platform admin. Uploads into the Platform Knowledge Workspace,
    dedupes on sha256, and links the (new or reused) Document to the Expert.
    """
    data = await file.read()
    result = ExpertService(db).upload_document_for_platform_expert(
        actor=user,
        expert_id=expert_id,
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
