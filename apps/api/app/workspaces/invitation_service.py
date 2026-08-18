"""Workspace invitation lifecycle. Controllers stay thin; authz uses WorkspacePolicy."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.identity.security import normalize_email
from app.notifications.factory import build_email_provider
from app.notifications.protocol import EmailMessage, EmailProvider
from app.workspaces.invitation_email import render_invitation_email
from app.workspaces.invitation_locks import workspace_invitation_email_lock
from app.workspaces.invitation_repository import InvitationRepository, membership_for_email
from app.workspaces.invitation_tokens import (
    MAX_INVITATION_TOKEN_LENGTH,
    generate_invitation_token,
    hash_invitation_token,
    hashes_equal,
)
from app.workspaces.invitation_urls import invitation_accept_url
from app.workspaces.models import (
    InvitationStatus,
    Workspace,
    WorkspaceInvitation,
    WorkspaceKind,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceStatus,
)
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import require_permission
from app.workspaces.repository import MembershipRepository, WorkspaceRepository
from app.workspaces.service import WorkspaceService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_constraint(exc: IntegrityError, name: str) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint = (getattr(diag, "constraint_name", None) or "") if diag is not None else ""
    if name in constraint.lower():
        return True
    blob = str(orig or exc).lower()
    return name in blob


def _reject_invalid_invitation() -> None:
    raise AppError(ErrorCategory.INVALID_INVITATION, "Invitation is not valid.")


class InvitationService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        email_provider: EmailProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.email = email_provider or build_email_provider(self.settings)
        self.invitations = InvitationRepository(db)
        self.memberships = MembershipRepository(db)
        self.workspaces = WorkspaceRepository(db)
        self._workspace_svc = WorkspaceService(db, settings=self.settings)

    def create_invitation(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        email: str,
        role_id: uuid.UUID,
    ) -> WorkspaceInvitation:
        workspace, membership = self._require_invite(workspace_id, actor_id)
        self._require_active_workspace(workspace)
        invite_role = self._require_assignable_role(workspace.id, role_id)
        normalized = self._normalize_invite_email(email)
        self._reject_existing_member(workspace.id, normalized)

        workspace_invitation_email_lock(self.db, workspace.id, normalized)
        self._reject_existing_member(workspace.id, normalized)
        existing = self.invitations.get_open_for_email(workspace.id, normalized, for_update=True)
        if existing is not None:
            status = existing.derived_status()
            if status == InvitationStatus.PENDING:
                raise AppError(
                    ErrorCategory.INVITATION_ALREADY_EXISTS,
                    "A pending invitation already exists for this email.",
                    details={"invitation_id": str(existing.id)},
                )
            # Expired open row occupies the partial unique slot; rotate it.
            return self._rotate_and_send(
                invitation=existing,
                workspace=workspace,
                actor_id=actor_id,
                role_id=invite_role.id,
                log_event="workspace_invitation_created",
            )

        raw_token = generate_invitation_token()
        invitation = WorkspaceInvitation(
            workspace_id=workspace.id,
            email=normalized,
            role_id=invite_role.id,
            token_hash=hash_invitation_token(raw_token, settings=self.settings),
            invited_by=actor_id,
            expires_at=_now() + timedelta(hours=self.settings.effective_workspace_invite_ttl_hours),
        )
        try:
            self.invitations.create(invitation)
            self._deliver(invitation, workspace, raw_token, actor_id=actor_id)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _is_constraint(exc, "uq_workspace_invitations_pending_email"):
                raise AppError(
                    ErrorCategory.INVITATION_ALREADY_EXISTS,
                    "A pending invitation already exists for this email.",
                ) from exc
            if _is_constraint(exc, "uq_workspace_invitations_token_hash"):
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "Unable to create invitation. Please retry.",
                ) from exc
            raise
        except Exception:
            self.db.rollback()
            raise

        security_log(
            "workspace_invitation_created",
            workspace_id=str(workspace.id),
            invitation_id=str(invitation.id),
            actor_id=str(actor_id),
            role=invitation.role,
        )
        _ = membership
        loaded = self.invitations.get_by_id_for_workspace(workspace.id, invitation.id)
        return loaded or invitation

    def list_pending(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkspaceInvitation], int]:
        self._require_invite(workspace_id, actor_id)
        return self.invitations.list_pending(workspace_id, limit=limit, offset=offset)

    def resend(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ) -> WorkspaceInvitation:
        workspace, _membership = self._require_invite(workspace_id, actor_id)
        self._require_active_workspace(workspace)
        invitation = self.invitations.get_by_id_for_workspace(
            workspace.id, invitation_id, for_update=True
        )
        if invitation is None:
            raise AppError(ErrorCategory.INVITATION_NOT_FOUND, "Invitation not found.")

        status = invitation.derived_status()
        if status == InvitationStatus.ACCEPTED:
            raise AppError(
                ErrorCategory.INVITATION_ALREADY_ACCEPTED,
                "Invitation has already been accepted.",
            )
        if status == InvitationStatus.REVOKED:
            raise AppError(ErrorCategory.INVITATION_REVOKED, "Invitation has been revoked.")

        self._reject_existing_member(workspace.id, invitation.email)
        return self._rotate_and_send(
            invitation=invitation,
            workspace=workspace,
            actor_id=actor_id,
            log_event="workspace_invitation_resent",
        )

    def revoke(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ) -> None:
        workspace, _membership = self._require_invite(workspace_id, actor_id)
        invitation = self.invitations.get_by_id_for_workspace(
            workspace.id, invitation_id, for_update=True
        )
        if invitation is None:
            raise AppError(ErrorCategory.INVITATION_NOT_FOUND, "Invitation not found.")

        status = invitation.derived_status()
        if status == InvitationStatus.ACCEPTED:
            raise AppError(
                ErrorCategory.INVITATION_ALREADY_ACCEPTED,
                "Invitation has already been accepted.",
            )
        if invitation.revoked_at is None:
            invitation.revoked_at = _now()
            self.db.commit()
            security_log(
                "workspace_invitation_revoked",
                workspace_id=str(workspace.id),
                invitation_id=str(invitation.id),
                actor_id=str(actor_id),
            )
        else:
            self.db.commit()

    def accept(
        self,
        *,
        user: User,
        raw_token: str,
    ) -> tuple[WorkspaceInvitation, WorkspaceMembership, Workspace, bool]:
        token = (raw_token or "").strip()
        if not token or len(token) > MAX_INVITATION_TOKEN_LENGTH:
            _reject_invalid_invitation()

        digest = hash_invitation_token(token, settings=self.settings)
        invitation = self.invitations.get_by_token_hash(digest, for_update=True)
        if invitation is None or not hashes_equal(invitation.token_hash, digest):
            _reject_invalid_invitation()

        actor_email = normalize_email(user.email)
        if actor_email != invitation.email:
            raise AppError(
                ErrorCategory.INVITATION_EMAIL_MISMATCH,
                "This invitation was sent to a different email address.",
            )

        status = invitation.derived_status()
        workspace = self.workspaces.get_by_id(invitation.workspace_id)
        if workspace is None or workspace.kind != WorkspaceKind.TENANT.value:
            _reject_invalid_invitation()
        if workspace.status != WorkspaceStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.WORKSPACE_ACCESS_DENIED,
                "Workspace is not active.",
                details={"status": workspace.status},
            )

        existing = self.memberships.get_for_update(invitation.workspace_id, user.id)

        if status == InvitationStatus.ACCEPTED:
            if existing is None:
                _reject_invalid_invitation()
            self.db.commit()
            return invitation, existing, workspace, True

        if status == InvitationStatus.REVOKED:
            raise AppError(ErrorCategory.INVITATION_REVOKED, "Invitation has been revoked.")
        if status == InvitationStatus.EXPIRED:
            raise AppError(ErrorCategory.INVITATION_EXPIRED, "Invitation has expired.")

        already_member = existing is not None
        if existing is None:
            invite_role = self._require_assignable_role(
                invitation.workspace_id, invitation.role_id
            )
            existing = WorkspaceMembership(
                workspace_id=invitation.workspace_id,
                user_id=user.id,
                role_id=invite_role.id,
            )
            try:
                self.memberships.create(existing)
            except IntegrityError as exc:
                self.db.rollback()
                if not _is_constraint(exc, "uq_workspace_membership"):
                    raise
                # Concurrent accept: reload locked invitation + membership.
                invitation = self.invitations.get_by_token_hash(digest, for_update=True)
                if invitation is None:
                    _reject_invalid_invitation()
                existing = self.memberships.get(invitation.workspace_id, user.id)
                if existing is None:
                    raise AppError(
                        ErrorCategory.CONFLICT,
                        "Unable to accept invitation. Please retry.",
                    ) from exc
                already_member = True
                workspace = self.workspaces.get_by_id(invitation.workspace_id) or workspace

        if invitation.accepted_at is None:
            invitation.accepted_at = _now()
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _is_constraint(exc, "uq_workspace_membership"):
                invitation = self.invitations.get_by_token_hash(digest, for_update=True)
                if invitation is None:
                    _reject_invalid_invitation()
                if invitation.accepted_at is None:
                    invitation.accepted_at = _now()
                    self.db.commit()
                existing = self.memberships.get(invitation.workspace_id, user.id)
                if existing is None:
                    raise AppError(
                        ErrorCategory.CONFLICT,
                        "Unable to accept invitation. Please retry.",
                    ) from exc
                already_member = True
            else:
                raise

        security_log(
            "workspace_invitation_accepted",
            workspace_id=str(invitation.workspace_id),
            invitation_id=str(invitation.id),
            actor_id=str(user.id),
            role=invitation.role,
        )
        return invitation, existing, workspace, already_member

    def _rotate_and_send(
        self,
        *,
        invitation: WorkspaceInvitation,
        workspace: Workspace,
        actor_id: uuid.UUID,
        log_event: str,
        role_id: uuid.UUID | None = None,
    ) -> WorkspaceInvitation:
        raw_token = generate_invitation_token()
        invitation.token_hash = hash_invitation_token(raw_token, settings=self.settings)
        invitation.expires_at = _now() + timedelta(
            hours=self.settings.effective_workspace_invite_ttl_hours
        )
        invitation.invited_by = actor_id
        if role_id is not None:
            invitation.role_id = role_id
        try:
            self._deliver(invitation, workspace, raw_token, actor_id=actor_id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        security_log(
            log_event,
            workspace_id=str(workspace.id),
            invitation_id=str(invitation.id),
            actor_id=str(actor_id),
            role=invitation.role,
        )
        loaded = self.invitations.get_by_id_for_workspace(workspace.id, invitation.id)
        return loaded or invitation

    def _deliver(
        self,
        invitation: WorkspaceInvitation,
        workspace: Workspace,
        raw_token: str,
        *,
        actor_id: uuid.UUID,
    ) -> None:
        """Send email before commit. Failure rolls back so no usable invitation remains.

        Transaction decision (Phase 10A): persist+flush, send, then commit. If the
        provider raises, the caller rolls back. No outbox/job queue.
        """
        accept_url = invitation_accept_url(raw_token, settings=self.settings)
        content = render_invitation_email(
            workspace_name=workspace.name,
            role=invitation.role,
            accept_url=accept_url,
            expires_at=invitation.expires_at,
            invitee_email=invitation.email,
            inviter_email=self._inviter_email(actor_id),
        )
        try:
            self.email.send(
                EmailMessage(
                    to=invitation.email,
                    subject=content.subject,
                    text_body=content.text_body,
                    html_body=content.html_body,
                )
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCategory.EMAIL_DELIVERY_FAILED,
                "Unable to send invitation email.",
                retryable=True,
            ) from exc

    def _inviter_email(self, actor_id: uuid.UUID) -> str | None:
        from app.identity.repository import UserRepository

        user = UserRepository(self.db).get_by_id(actor_id)
        return user.email if user is not None else None

    def _require_invite(
        self, workspace_id: uuid.UUID, actor_id: uuid.UUID
    ) -> tuple[Workspace, WorkspaceMembership]:
        workspace, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.MEMBERS_INVITE)
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        return workspace, membership

    def _require_assignable_role(
        self, workspace_id: uuid.UUID, role_id: uuid.UUID
    ) -> WorkspaceRoleDef:
        role = self.db.get(WorkspaceRoleDef, role_id)
        if role is None or role.workspace_id != workspace_id:
            raise AppError(ErrorCategory.ROLE_NOT_FOUND, "Role not found.")
        if role.is_owner_role:
            raise AppError(
                ErrorCategory.ROLE_PROTECTED,
                "The Owner role cannot be assigned by invitation.",
            )
        return role

    @staticmethod
    def _require_active_workspace(workspace: Workspace) -> None:
        if workspace.status != WorkspaceStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.WORKSPACE_ACCESS_DENIED,
                "Workspace is not active.",
                details={"status": workspace.status},
            )

    def _reject_existing_member(self, workspace_id: uuid.UUID, email: str) -> None:
        if membership_for_email(self.db, workspace_id, email) is not None:
            raise AppError(
                ErrorCategory.ALREADY_WORKSPACE_MEMBER,
                "This email already belongs to a workspace member.",
            )

    @staticmethod
    def _normalize_invite_email(email: str) -> str:
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise AppError(ErrorCategory.VALIDATION, "Invalid email address.")
        return normalized
