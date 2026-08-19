from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class OkResponse(BaseModel):
    ok: bool = True


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    platform_role: str
    created_at: datetime
    email_verified_at: datetime | None = None

    model_config = {"from_attributes": True}


from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.rbac_service import get_effective_permissions
from app.workspaces.schemas import RoleSummaryOut, to_role_summary


def workspace_summary_out(workspace: Workspace, membership: WorkspaceMembership) -> WorkspaceSummaryOut:
    summary = to_role_summary(membership.workspace_role)
    assert summary is not None
    return WorkspaceSummaryOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        status=workspace.status,
        role=summary,
        permissions=sorted(get_effective_permissions(membership)),
    )


def membership_out(membership: WorkspaceMembership) -> MembershipOut:
    summary = to_role_summary(membership.workspace_role)
    assert summary is not None
    return MembershipOut(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=membership.user_id,
        role=summary,
        created_at=membership.created_at,
        permissions=sorted(get_effective_permissions(membership)),
    )


class WorkspaceSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    role: RoleSummaryOut
    permissions: list[str] = Field(default_factory=list)


class MembershipOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: RoleSummaryOut
    created_at: datetime
    permissions: list[str] = Field(default_factory=list)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class RegisterResponse(BaseModel):
    verification_required: bool
    access_token: str | None = None
    token_type: str = "bearer"
    expires_at: datetime | None = None
    user: UserOut | None = None


class MeResponse(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceSummaryOut]
    current_workspace: WorkspaceSummaryOut | None = None
    membership: MembershipOut | None = None
