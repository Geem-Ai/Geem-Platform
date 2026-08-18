"""Workspace invitation persistence. All queries are workspace-scoped except token lookup."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.identity.models import User
from app.workspaces.models import (
    InvitationStatus,
    WorkspaceInvitation,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceRolePermission,
)


_INVITE_LOAD = (
    selectinload(WorkspaceInvitation.inviter),
    selectinload(WorkspaceInvitation.workspace_role)
    .selectinload(WorkspaceRoleDef.permission_links)
    .selectinload(WorkspaceRolePermission.permission),
)


class InvitationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, invitation: WorkspaceInvitation) -> WorkspaceInvitation:
        self.db.add(invitation)
        self.db.flush()
        return invitation

    def get_by_id_for_workspace(
        self,
        workspace_id: uuid.UUID,
        invitation_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> WorkspaceInvitation | None:
        stmt = (
            select(WorkspaceInvitation)
            .options(*_INVITE_LOAD)
            .where(
                WorkspaceInvitation.id == invitation_id,
                WorkspaceInvitation.workspace_id == workspace_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def get_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> WorkspaceInvitation | None:
        stmt = (
            select(WorkspaceInvitation)
            .options(
                selectinload(WorkspaceInvitation.workspace),
                *_INVITE_LOAD,
            )
            .where(WorkspaceInvitation.token_hash == token_hash)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def get_open_for_email(
        self,
        workspace_id: uuid.UUID,
        email: str,
        *,
        for_update: bool = False,
    ) -> WorkspaceInvitation | None:
        """Non-finalized invitation (accepted_at and revoked_at are null), including expired."""
        stmt = select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.email == email,
            WorkspaceInvitation.accepted_at.is_(None),
            WorkspaceInvitation.revoked_at.is_(None),
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def list_pending(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        now: datetime | None = None,
    ) -> tuple[list[WorkspaceInvitation], int]:
        when = now or datetime.now(timezone.utc)
        pending = (
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.accepted_at.is_(None),
            WorkspaceInvitation.revoked_at.is_(None),
            WorkspaceInvitation.expires_at > when,
            ~_membership_exists_for_invite_email(),
        )
        total = int(
            self.db.scalar(select(func.count()).select_from(WorkspaceInvitation).where(*pending))
            or 0
        )
        items = list(
            self.db.scalars(
                select(WorkspaceInvitation)
                .options(*_INVITE_LOAD)
                .where(*pending)
                .order_by(WorkspaceInvitation.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return items, total


def membership_for_email(
    db: Session, workspace_id: uuid.UUID, email: str
) -> WorkspaceMembership | None:
    return db.scalar(
        select(WorkspaceMembership)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            User.email == email,
            User.deleted_at.is_(None),
        )
    )


def _membership_exists_for_invite_email():
    """Correlated EXISTS: invite email already has an active workspace membership."""
    return (
        select(WorkspaceMembership.id)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(
            WorkspaceMembership.workspace_id == WorkspaceInvitation.workspace_id,
            User.email == WorkspaceInvitation.email,
            User.deleted_at.is_(None),
        )
        .exists()
    )


# Keep InvitationStatus re-exported for callers.
__all__ = [
    "InvitationRepository",
    "InvitationStatus",
    "membership_for_email",
]
