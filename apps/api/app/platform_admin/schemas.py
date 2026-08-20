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
