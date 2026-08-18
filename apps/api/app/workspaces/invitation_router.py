"""Workspace invitation HTTP API (Phase 10A)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.notifications.factory import get_email_provider
from app.notifications.protocol import EmailProvider
from app.workspaces.invitation_schemas import (
    InvitationAcceptOut,
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationListOut,
    InvitationOut,
    to_invitation_out,
)
from app.workspaces.invitation_service import InvitationService

workspace_invitations_router = APIRouter(prefix="/api/workspaces", tags=["invitations"])
invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])


def get_invitation_service(
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> InvitationService:
    return InvitationService(db, email_provider=email)


@workspace_invitations_router.post(
    "/{workspace_id}/invitations",
    response_model=InvitationOut,
    status_code=201,
)
def create_invitation(
    workspace_id: uuid.UUID,
    body: InvitationCreateRequest,
    user: User = Depends(get_current_user),
    svc: InvitationService = Depends(get_invitation_service),
) -> InvitationOut:
    row = svc.create_invitation(
        workspace_id=workspace_id,
        actor_id=user.id,
        email=body.email,
        role_id=body.role_id,
    )
    return to_invitation_out(row)


@workspace_invitations_router.get(
    "/{workspace_id}/invitations",
    response_model=InvitationListOut,
)
def list_invitations(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: InvitationService = Depends(get_invitation_service),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> InvitationListOut:
    items, total = svc.list_pending(
        workspace_id=workspace_id,
        actor_id=user.id,
        limit=limit,
        offset=offset,
    )
    return InvitationListOut(
        items=[to_invitation_out(row) for row in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@workspace_invitations_router.post(
    "/{workspace_id}/invitations/{invitation_id}/resend",
    response_model=InvitationOut,
)
def resend_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: InvitationService = Depends(get_invitation_service),
) -> InvitationOut:
    row = svc.resend(
        workspace_id=workspace_id,
        actor_id=user.id,
        invitation_id=invitation_id,
    )
    return to_invitation_out(row)


@workspace_invitations_router.delete(
    "/{workspace_id}/invitations/{invitation_id}",
    status_code=204,
)
def revoke_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    svc: InvitationService = Depends(get_invitation_service),
) -> None:
    svc.revoke(
        workspace_id=workspace_id,
        actor_id=user.id,
        invitation_id=invitation_id,
    )


@invitations_router.post("/accept", response_model=InvitationAcceptOut)
def accept_invitation(
    body: InvitationAcceptRequest,
    user: User = Depends(get_current_user),
    svc: InvitationService = Depends(get_invitation_service),
) -> InvitationAcceptOut:
    from app.workspaces.schemas import to_role_summary

    invitation, membership, workspace, already_member = svc.accept(
        user=user,
        raw_token=body.token,
    )
    summary = to_role_summary(membership.workspace_role)
    assert summary is not None
    return InvitationAcceptOut(
        invitation_id=invitation.id,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_slug=workspace.slug,
        role=summary,
        membership_id=membership.id,
        already_member=already_member,
    )
