from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.schemas import (
    MemberOut,
    MemberRoleUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceOut,
    WorkspaceUpdateRequest,
    to_member_out,
    to_workspace_out,
)
from app.workspaces.service import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceOut]:
    pairs = WorkspaceService(db).list_for_user(user.id)
    return [to_workspace_out(w, m) for w, m in pairs]


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    body: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    workspace, membership = WorkspaceService(db).create_workspace(
        name=body.name,
        slug=body.slug,
        created_by=user.id,
        settings=body.settings,
    )
    return to_workspace_out(workspace, membership)


@router.get("/current", response_model=WorkspaceOut)
def current_workspace(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
) -> WorkspaceOut:
    """Resolve the current workspace from Host / local header hints + membership."""
    workspace, membership = pair
    return to_workspace_out(workspace, membership)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    workspace, membership = WorkspaceService(db).get_workspace_for_user(workspace_id, user.id)
    return to_workspace_out(workspace, membership)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    workspace = WorkspaceService(db).update_workspace(
        workspace_id=workspace_id,
        actor_id=user.id,
        name=body.name,
        settings=body.settings,
    )
    _, membership = WorkspaceService(db).get_workspace_for_user(workspace_id, user.id)
    return to_workspace_out(workspace, membership)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    members = WorkspaceService(db).list_members(workspace_id=workspace_id, actor_id=user.id)
    return [to_member_out(m) for m in members]


@router.patch("/{workspace_id}/members/{target_user_id}", response_model=MemberOut)
def update_member_role(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    body: MemberRoleUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberOut:
    m = WorkspaceService(db).update_member_role(
        workspace_id=workspace_id,
        actor_id=user.id,
        target_user_id=target_user_id,
        new_role_id=body.role_id,
    )
    loaded = WorkspaceService(db).memberships.get(workspace_id, target_user_id)
    return to_member_out(loaded or m)


@router.delete("/{workspace_id}/members/{target_user_id}", status_code=204)
def remove_member(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    WorkspaceService(db).remove_member(
        workspace_id=workspace_id,
        actor_id=user.id,
        target_user_id=target_user_id,
    )
