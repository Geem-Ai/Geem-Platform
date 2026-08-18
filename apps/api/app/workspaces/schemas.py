from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.workspaces.models import WorkspaceMembership, WorkspaceRoleDef
from app.workspaces.rbac_service import get_effective_permissions


class RoleSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    name: str
    is_system: bool
    is_owner_role: bool
    system_key: str | None = None


class PermissionCatalogItemOut(BaseModel):
    key: str
    group: str
    name_key: str
    description_key: str
    owner_only: bool = False


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=3, max_length=63)
    settings: dict[str, Any] | None = None


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: dict[str, Any] | None = None


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_by: uuid.UUID | None
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    role: RoleSummaryOut | None = None
    permissions: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str | None = None
    role: RoleSummaryOut
    created_at: datetime


class MemberRoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: uuid.UUID


class RoleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] | None = None


class RoleOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    is_owner_role: bool
    system_key: str | None
    permissions: list[str]
    assigned_count: int = 0
    created_at: datetime
    updated_at: datetime


class RoleListOut(BaseModel):
    items: list[RoleOut]


class PermissionCatalogOut(BaseModel):
    items: list[PermissionCatalogItemOut]


def to_role_summary(role: WorkspaceRoleDef | None) -> RoleSummaryOut | None:
    if role is None:
        return None
    return RoleSummaryOut(
        id=role.id,
        name=role.name,
        is_system=role.is_system,
        is_owner_role=role.is_owner_role,
        system_key=role.system_key,
    )


def to_workspace_out(workspace, membership: WorkspaceMembership | None = None) -> WorkspaceOut:
    role = membership.workspace_role if membership is not None else None
    perms = sorted(get_effective_permissions(membership)) if membership is not None else []
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        status=workspace.status,
        created_by=workspace.created_by,
        settings=workspace.settings or {},
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        role=to_role_summary(role),
        permissions=perms,
    )


def to_member_out(membership: WorkspaceMembership) -> MemberOut:
    user = membership.user
    summary = to_role_summary(membership.workspace_role)
    assert summary is not None
    return MemberOut(
        id=membership.id,
        user_id=membership.user_id,
        email=user.email if user is not None else None,
        role=summary,
        created_at=membership.created_at,
    )
