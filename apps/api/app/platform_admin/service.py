"""Platform Admin orchestration boundary.

Phase 12A: identity bootstrap.
Phase 12B: Workspace / User inventory + lifecycle (disable/enable).

Domain mutations call WorkspaceService / Identity session services rather than
duplicating tenant rules. Membership mutations stay read-only in 12B (invite
flow remains the join path; last-owner rules stay in WorkspaceService).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, record_audit
from app.common.security_log import security_log
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User, UserStatus
from app.identity.repository import SessionRepository
from app.identity.schemas import UserOut
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.repository import PlatformAdminRepository
from app.platform_admin.schemas import (
    PlatformMeResponse,
    PlatformResourceSummaryOut,
    PlatformSubscriptionSummaryOut,
    PlatformUserDetailOut,
    PlatformUserListItem,
    PlatformUserListResponse,
    PlatformUserMembershipOut,
    PlatformWorkspaceDetailOut,
    PlatformWorkspaceListItem,
    PlatformWorkspaceListResponse,
    PlatformWorkspaceMemberOut,
    PlatformWorkspaceMembersResponse,
    PlatformWorkspaceOwnerOut,
)
from app.usage.storage import StorageQuotaService
from app.workspaces.models import Workspace, WorkspaceKind, WorkspaceMembership
from app.workspaces.service import WorkspaceService


class PlatformAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PlatformAdminRepository(db)
        self.workspaces = WorkspaceService(db)
        self.sessions = SessionRepository(db)

    def get_me(self, actor: User) -> PlatformMeResponse:
        user = require_platform_admin_user(actor)
        return PlatformMeResponse(
            user=UserOut.model_validate(user),
            platform_role=user.platform_role,
            authorized=True,
        )

    # --- Workspaces ---

    def list_workspaces(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> PlatformWorkspaceListResponse:
        require_platform_admin_user(actor)
        # Default inventory is tenant Workspaces. Explicit kind=all lists every kind.
        raw_kind = (kind or "").strip().lower()
        if raw_kind in ("", "tenant"):
            effective_kind: str | None = WorkspaceKind.TENANT.value
        elif raw_kind == "all":
            effective_kind = None
        else:
            effective_kind = raw_kind
        total = self.repo.count_workspaces(
            search=search,
            status=status,
            kind=effective_kind,
            created_from=created_from,
            created_to=created_to,
        )
        rows = self.repo.list_workspaces(
            limit=limit,
            offset=offset,
            search=search,
            status=status,
            kind=effective_kind,
            created_from=created_from,
            created_to=created_to,
        )
        ids = [w.id for w in rows]
        member_counts = self.repo.member_counts(ids)
        expert_counts = self.repo.expert_counts(ids)
        subs = self.repo.subscription_summaries(ids)
        items = [
            self._workspace_list_item(
                w,
                members_count=member_counts.get(w.id, 0),
                experts_count=expert_counts.get(w.id, 0),
                subscription=subs.get(w.id),
            )
            for w in rows
        ]
        return PlatformWorkspaceListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def get_workspace(self, actor: User, workspace_id: uuid.UUID) -> PlatformWorkspaceDetailOut:
        require_platform_admin_user(actor)
        workspace = self.repo.get_workspace(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")

        counts = self.repo.resource_counts(workspace.id)
        owners = [
            PlatformWorkspaceOwnerOut(
                user_id=m.user_id,
                email=m.user.email if m.user else "",
                status=m.user.status if m.user else UserStatus.DISABLED.value,
                membership_id=m.id,
                role_id=m.role_id,
                role_name=m.workspace_role.name if m.workspace_role else "",
            )
            for m in self.repo.owner_memberships(workspace.id)
        ]
        sub_pair = self.repo.subscription_summaries([workspace.id]).get(workspace.id)
        subscription = None
        if sub_pair is not None:
            sub, plan = sub_pair
            subscription = PlatformSubscriptionSummaryOut(
                subscription_id=sub.id,
                status=sub.status,
                plan_id=plan.id,
                plan_code=plan.code,
                plan_name=plan.name,
                starts_at=sub.starts_at,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                ends_at=sub.ends_at,
            )

        storage_used: int | None = None
        storage_limit: int | None = None
        if workspace.kind == WorkspaceKind.TENANT.value:
            try:
                snap = StorageQuotaService(self.db).snapshot(workspace.id)
                storage_used = snap.used_bytes
                storage_limit = snap.limit_bytes
            except Exception:
                # Read-only summary must not fail the whole detail view.
                storage_used = None
                storage_limit = None

        return PlatformWorkspaceDetailOut(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            kind=workspace.kind,
            status=workspace.status,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
            created_by=workspace.created_by,
            deleted_at=workspace.deleted_at,
            purged_at=getattr(workspace, "purged_at", None),
            members_count=counts["members_count"],
            owners=owners,
            subscription=subscription,
            resources=PlatformResourceSummaryOut(
                members_count=counts["members_count"],
                experts_count=counts["experts_count"],
                api_keys_count=counts["api_keys_count"],
                app_installations_count=counts["app_installations_count"],
                storage_used_bytes=storage_used,
                storage_limit_bytes=storage_limit,
            ),
        )

    def list_workspace_members(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> PlatformWorkspaceMembersResponse:
        require_platform_admin_user(actor)
        workspace = self.repo.get_workspace(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        rows, total = self.repo.list_members_page(workspace.id, limit=limit, offset=offset)
        items = [self._member_out(m) for m in rows]
        return PlatformWorkspaceMembersResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def disable_workspace(
        self, actor: User, workspace_id: uuid.UUID, *, reason: str
    ) -> PlatformWorkspaceDetailOut:
        require_platform_admin_user(actor)
        self.workspaces.disable_workspace(
            workspace_id=workspace_id, actor_id=actor.id, reason=reason
        )
        return self.get_workspace(actor, workspace_id)

    def enable_workspace(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        *,
        reason: str | None = None,
    ) -> PlatformWorkspaceDetailOut:
        require_platform_admin_user(actor)
        self.workspaces.enable_workspace(
            workspace_id=workspace_id, actor_id=actor.id, reason=reason
        )
        return self.get_workspace(actor, workspace_id)

    # --- Users ---

    def list_users(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        platform_role: str | None = None,
    ) -> PlatformUserListResponse:
        require_platform_admin_user(actor)
        total = self.repo.count_users(
            search=search, status=status, platform_role=platform_role
        )
        rows = self.repo.list_users(
            limit=limit,
            offset=offset,
            search=search,
            status=status,
            platform_role=platform_role,
        )
        ids = [u.id for u in rows]
        membership_counts = self.repo.membership_counts(ids)
        last_used = self.repo.last_session_used_at(ids)
        items = [
            PlatformUserListItem(
                id=u.id,
                email=u.email,
                status=u.status,
                platform_role=u.platform_role,
                created_at=u.created_at,
                email_verified_at=u.email_verified_at,
                last_login_at=last_used.get(u.id),
                workspace_memberships_count=membership_counts.get(u.id, 0),
            )
            for u in rows
        ]
        return PlatformUserListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def get_user(self, actor: User, user_id: uuid.UUID) -> PlatformUserDetailOut:
        require_platform_admin_user(actor)
        user = self.repo.get_user(user_id)
        if user is None:
            raise AppError(ErrorCategory.NOT_FOUND, "User not found.")
        memberships = [
            PlatformUserMembershipOut(
                membership_id=m.id,
                workspace_id=m.workspace_id,
                workspace_name=m.workspace.name if m.workspace else "",
                workspace_slug=m.workspace.slug if m.workspace else "",
                workspace_status=m.workspace.status if m.workspace else "",
                role_id=m.role_id,
                role_name=m.workspace_role.name if m.workspace_role else "",
                is_owner_role=bool(m.workspace_role and m.workspace_role.is_owner_role),
                created_at=m.created_at,
            )
            for m in self.repo.list_user_memberships(user.id)
        ]
        last_used = self.repo.last_session_used_at([user.id]).get(user.id)
        return PlatformUserDetailOut(
            id=user.id,
            email=user.email,
            status=user.status,
            platform_role=user.platform_role,
            created_at=user.created_at,
            updated_at=user.updated_at,
            email_verified_at=user.email_verified_at,
            deleted_at=user.deleted_at,
            last_login_at=last_used,
            active_session_count=self.repo.active_session_count(user.id),
            memberships=memberships,
        )

    def disable_user(
        self, actor: User, user_id: uuid.UUID, *, reason: str
    ) -> PlatformUserDetailOut:
        require_platform_admin_user(actor)
        clean_reason = (reason or "").strip()
        if not clean_reason:
            raise AppError(ErrorCategory.VALIDATION, "A reason is required to disable a user.")
        if len(clean_reason) > 500:
            raise AppError(ErrorCategory.VALIDATION, "Reason must be at most 500 characters.")
        if user_id == actor.id:
            raise AppError(
                ErrorCategory.CANNOT_DISABLE_SELF,
                "You cannot disable your own Platform Admin account.",
            )

        user = self.repo.get_user(user_id)
        if user is None:
            raise AppError(ErrorCategory.NOT_FOUND, "User not found.")
        if user.status == UserStatus.DISABLED.value:
            return self.get_user(actor, user_id)

        before = user.status
        user.status = UserStatus.DISABLED.value
        revoked = self.sessions.revoke_all_for_user(user.id)
        record_audit(
            self.db,
            action=AuditAction.USER_DISABLED,
            entity_type=AuditEntityType.USER,
            entity_id=user.id,
            workspace_id=None,
            actor_user_id=actor.id,
            metadata={
                "before_status": before,
                "after_status": user.status,
                "reason": clean_reason,
                "sessions_revoked": revoked,
            },
            allowlist=frozenset(
                {"before_status", "after_status", "reason", "sessions_revoked"}
            ),
        )
        self.db.commit()
        security_log(
            "user.disabled",
            actor_id=str(actor.id),
            target_user_id=str(user.id),
            sessions_revoked=revoked,
        )
        return self.get_user(actor, user_id)

    def enable_user(
        self,
        actor: User,
        user_id: uuid.UUID,
        *,
        reason: str | None = None,
    ) -> PlatformUserDetailOut:
        require_platform_admin_user(actor)
        clean_reason = (reason or "").strip() or None
        if clean_reason is not None and len(clean_reason) > 500:
            raise AppError(ErrorCategory.VALIDATION, "Reason must be at most 500 characters.")

        user = self.repo.get_user(user_id)
        if user is None:
            raise AppError(ErrorCategory.NOT_FOUND, "User not found.")
        if user.status == UserStatus.ACTIVE.value:
            return self.get_user(actor, user_id)

        before = user.status
        user.status = UserStatus.ACTIVE.value
        meta: dict[str, str] = {
            "before_status": before,
            "after_status": user.status,
        }
        allow = {"before_status", "after_status"}
        if clean_reason:
            meta["reason"] = clean_reason
            allow.add("reason")
        record_audit(
            self.db,
            action=AuditAction.USER_ENABLED,
            entity_type=AuditEntityType.USER,
            entity_id=user.id,
            workspace_id=None,
            actor_user_id=actor.id,
            metadata=meta,
            allowlist=frozenset(allow),
        )
        self.db.commit()
        security_log(
            "user.enabled",
            actor_id=str(actor.id),
            target_user_id=str(user.id),
        )
        return self.get_user(actor, user_id)

    # --- helpers ---

    @staticmethod
    def _workspace_list_item(
        workspace: Workspace,
        *,
        members_count: int,
        experts_count: int,
        subscription: tuple | None,
    ) -> PlatformWorkspaceListItem:
        plan_code = plan_name = sub_status = None
        if subscription is not None:
            sub, plan = subscription
            plan_code = plan.code
            plan_name = plan.name
            sub_status = sub.status
        return PlatformWorkspaceListItem(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            kind=workspace.kind,
            status=workspace.status,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
            created_by=workspace.created_by,
            deleted_at=workspace.deleted_at,
            members_count=members_count,
            experts_count=experts_count,
            current_plan_code=plan_code,
            current_plan_name=plan_name,
            subscription_status=sub_status,
        )

    @staticmethod
    def _member_out(membership: WorkspaceMembership) -> PlatformWorkspaceMemberOut:
        role = membership.workspace_role
        user = membership.user
        return PlatformWorkspaceMemberOut(
            membership_id=membership.id,
            user_id=membership.user_id,
            email=user.email if user else "",
            user_status=user.status if user else UserStatus.DISABLED.value,
            role_id=membership.role_id,
            role_name=role.name if role else "",
            is_owner_role=bool(role and role.is_owner_role),
            created_at=membership.created_at,
        )
