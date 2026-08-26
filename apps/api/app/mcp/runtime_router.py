"""Workspace APIs for Phase 13E MCP bindings, approvals, usage, and delivery."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.apps_catalog.policy import require_browse
from app.conversations.service import ConversationService
from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access
from app.experts.policy import ExpertAction, ExpertPolicy
from app.mcp.surfaces import (
    McpApprovalListOut,
    McpApprovalOut,
    McpDecisionIn,
    McpDeliveryListOut,
    McpDeliveryOut,
    McpDeliveryReconcileIn,
    McpExternalOperationsService,
    McpSurfaceBindingCreateIn,
    McpSurfaceBindingOut,
    McpSurfaceBindingService,
    McpUsageOut,
)
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import require_permission


_PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def _private_no_store(response: Response) -> None:
    response.headers.update(_PRIVATE_NO_STORE_HEADERS)


router = APIRouter(
    tags=["mcp-runtime"],
    dependencies=[Depends(_private_no_store)],
)


@router.get(
    "/api/experts/{expert_id}/mcp-surface-bindings",
    response_model=list[McpSurfaceBindingOut],
)
def list_mcp_surface_bindings(
    expert_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> list[McpSurfaceBindingOut]:
    ExpertPolicy.require(access.membership, ExpertAction.UPDATE)
    return McpSurfaceBindingService(db).list_bindings(
        workspace_id=access.workspace.id,
        expert_id=expert_id,
    )


@router.post(
    "/api/experts/{expert_id}/mcp-surface-bindings",
    response_model=McpSurfaceBindingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_mcp_surface_binding(
    expert_id: uuid.UUID,
    body: McpSurfaceBindingCreateIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpSurfaceBindingOut:
    ExpertPolicy.require(access.membership, ExpertAction.UPDATE)
    return McpSurfaceBindingService(db).create_binding(
        workspace_id=access.workspace.id,
        expert_id=expert_id,
        actor_id=access.user.id,
        body=body,
    )


@router.delete(
    "/api/experts/{expert_id}/mcp-surface-bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_mcp_surface_binding(
    expert_id: uuid.UUID,
    binding_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> Response:
    ExpertPolicy.require(access.membership, ExpertAction.UPDATE)
    McpSurfaceBindingService(db).revoke_binding(
        workspace_id=access.workspace.id,
        expert_id=expert_id,
        binding_id=binding_id,
        actor_id=access.user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/apps/mcp/usage", response_model=McpUsageOut)
def get_mcp_usage(
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpUsageOut:
    require_browse(access.membership)
    return McpExternalOperationsService(db).usage(
        workspace_id=access.workspace.id,
    )


@router.get(
    "/api/apps/mcp/external-approvals",
    response_model=McpApprovalListOut,
)
def list_mcp_external_approvals(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpApprovalListOut:
    require_permission(
        access.membership,
        WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL,
    )
    return McpExternalOperationsService(db).list_approvals(
        workspace_id=access.workspace.id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/apps/mcp/external-approvals/{approval_id}",
    response_model=McpApprovalOut,
)
def decide_mcp_external_approval(
    approval_id: uuid.UUID,
    body: McpDecisionIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpApprovalOut:
    require_permission(
        access.membership,
        WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL,
    )
    return McpExternalOperationsService(db).decide_external(
        workspace_id=access.workspace.id,
        approval_id=approval_id,
        operator_user_id=access.user.id,
        decision=body.decision,
    )


@router.get(
    "/api/apps/mcp/external-deliveries",
    response_model=McpDeliveryListOut,
)
def list_mcp_external_deliveries(
    delivery_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpDeliveryListOut:
    require_permission(
        access.membership,
        WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL,
    )
    return McpExternalOperationsService(db).list_deliveries(
        workspace_id=access.workspace.id,
        status=delivery_status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/apps/mcp/external-deliveries/{delivery_id}/reconcile",
    response_model=McpDeliveryOut,
)
def reconcile_mcp_external_delivery(
    delivery_id: uuid.UUID,
    body: McpDeliveryReconcileIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpDeliveryOut:
    require_permission(
        access.membership,
        WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL,
    )
    return McpExternalOperationsService(db).reconcile_delivery(
        workspace_id=access.workspace.id,
        delivery_id=delivery_id,
        operator_user_id=access.user.id,
        resolution=body.resolution,
    )


@router.post(
    "/api/conversations/{conversation_id}/tool-approvals/{approval_id}",
)
def decide_workspace_mcp_approval(
    conversation_id: uuid.UUID,
    approval_id: uuid.UUID,
    body: McpDecisionIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # This lookup enforces both current ``chat.use`` and exact user ownership.
    ConversationService(db).get_for_actor(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        conversation_id=conversation_id,
    )
    result = McpExternalOperationsService(db).decide_workspace(
        workspace_id=access.workspace.id,
        conversation_id=conversation_id,
        approval_id=approval_id,
        actor_user_id=access.user.id,
        decision=body.decision,
    )
    return {"id": str(result.pending_id), "status": result.status}


__all__ = ["router"]
