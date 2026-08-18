"""Workspace role and permission catalog HTTP API (Phase 10C)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.workspaces.role_service import UNSET, RoleService
from app.workspaces.schemas import (
    PermissionCatalogOut,
    RoleCreateRequest,
    RoleListOut,
    RoleOut,
    RoleUpdateRequest,
)

router = APIRouter(prefix="/api/workspaces", tags=["roles"])


def get_role_service(db: Session = Depends(get_db)) -> RoleService:
    return RoleService(db)


@router.get("/{workspace_id}/permissions", response_model=PermissionCatalogOut)
def list_permissions(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> PermissionCatalogOut:
    return PermissionCatalogOut(items=svc.list_catalog(workspace_id=workspace_id, actor_id=user.id))


@router.get("/{workspace_id}/roles", response_model=RoleListOut)
def list_roles(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> RoleListOut:
    return RoleListOut(items=svc.list_roles(workspace_id=workspace_id, actor_id=user.id))


@router.get("/{workspace_id}/roles/assignable", response_model=RoleListOut)
def list_assignable_roles(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> RoleListOut:
    return RoleListOut(items=svc.assignable_roles(workspace_id=workspace_id, actor_id=user.id))


@router.post("/{workspace_id}/roles", response_model=RoleOut, status_code=201)
def create_role(
    workspace_id: uuid.UUID,
    body: RoleCreateRequest,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> RoleOut:
    return svc.create_role(
        workspace_id=workspace_id,
        actor_id=user.id,
        name=body.name,
        description=body.description,
        permission_keys=body.permissions,
    )


@router.get("/{workspace_id}/roles/{role_id}", response_model=RoleOut)
def get_role(
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> RoleOut:
    return svc.get_role(workspace_id=workspace_id, actor_id=user.id, role_id=role_id)


@router.patch("/{workspace_id}/roles/{role_id}", response_model=RoleOut)
def update_role(
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    body: RoleUpdateRequest,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> RoleOut:
    data = body.model_dump(exclude_unset=True)
    return svc.update_role(
        workspace_id=workspace_id,
        actor_id=user.id,
        role_id=role_id,
        name=data.get("name"),
        description=data["description"] if "description" in data else UNSET,
        permission_keys=data.get("permissions"),
    )


@router.delete("/{workspace_id}/roles/{role_id}", status_code=204)
def delete_role(
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
) -> None:
    svc.delete_role(workspace_id=workspace_id, actor_id=user.id, role_id=role_id)
