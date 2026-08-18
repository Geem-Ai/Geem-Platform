"""Invitation request/response DTOs. Never include token_hash or raw tokens."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.workspaces.models import WorkspaceInvitation
from app.workspaces.schemas import RoleSummaryOut, to_role_summary


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role_id: uuid.UUID


class InvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256)


class InvitationInviterOut(BaseModel):
    id: uuid.UUID
    email: str | None = None


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    role: RoleSummaryOut
    status: str
    expires_at: datetime
    created_at: datetime
    invited_by: InvitationInviterOut | None = None


class InvitationListOut(BaseModel):
    items: list[InvitationOut]
    total: int
    limit: int
    offset: int


class InvitationAcceptOut(BaseModel):
    invitation_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    role: RoleSummaryOut
    membership_id: uuid.UUID
    already_member: bool = False


def to_invitation_out(row: WorkspaceInvitation) -> InvitationOut:
    inviter = getattr(row, "inviter", None)
    invited_by = None
    if row.invited_by is not None:
        invited_by = InvitationInviterOut(
            id=row.invited_by,
            email=getattr(inviter, "email", None) if inviter is not None else None,
        )
    created = _utc(row.created_at)
    expires = _utc(row.expires_at)
    assert created is not None and expires is not None
    summary = to_role_summary(row.workspace_role)
    assert summary is not None
    return InvitationOut(
        id=row.id,
        workspace_id=row.workspace_id,
        email=row.email,
        role=summary,
        status=row.derived_status().value,
        expires_at=expires,
        created_at=created,
        invited_by=invited_by,
    )
