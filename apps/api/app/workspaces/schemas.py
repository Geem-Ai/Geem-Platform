from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    role: str | None = None

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str | None = None
    role: str
    created_at: datetime


class MemberRoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(owner|admin|member)$")
