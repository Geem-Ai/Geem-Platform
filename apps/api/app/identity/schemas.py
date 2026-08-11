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


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    platform_role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    role: str


class MembershipOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceSummaryOut]
    current_workspace: WorkspaceSummaryOut | None = None
    membership: MembershipOut | None = None
