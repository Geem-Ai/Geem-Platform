"""Central Expert access resolver — controllers must not reimplement these rules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.errors import AppError, ErrorCategory
from app.experts.models import (
    Expert,
    ExpertAvailabilityMode,
    ExpertStatus,
    ExpertType,
    ExpertVisibility,
)
from app.experts.policy import ExpertAction, ExpertPolicy
from app.experts.repository import ExpertRepository
from app.identity.models import PlatformRole
from app.workspaces.models import Workspace, WorkspaceMembership


@dataclass(frozen=True, slots=True)
class AuthorizedExpert:
    """Expert authorized for a specific Workspace actor + action.

    ``membership`` is None for Workspace API-key (machine) consumers.
    """

    expert: Expert
    ownership: str  # "workspace" | "platform"
    workspace: Workspace
    membership: WorkspaceMembership | None
    action: ExpertAction

    @property
    def expert_id(self) -> uuid.UUID:
        return self.expert.id


class ExpertAccessService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ExpertRepository(db)

    def resolve_for_workspace(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        expert_id: uuid.UUID,
        action: ExpertAction,
        actor_id: uuid.UUID | None = None,
    ) -> AuthorizedExpert:
        ExpertPolicy.require(membership, action)
        return self._resolve_expert(
            workspace=workspace,
            expert_id=expert_id,
            action=action,
            actor_id=actor_id,
            membership=membership,
        )

    def resolve_for_workspace_consumer(
        self,
        *,
        workspace: Workspace,
        expert_id: uuid.UUID,
        action: ExpertAction = ExpertAction.USE,
        actor_id: uuid.UUID | None = None,
    ) -> AuthorizedExpert:
        """Authorize an Expert for a Workspace without a User membership.

        Used by Workspace API keys (Phase 7B). HTTP scope checks replace
        membership roles. Visibility, grants, and cross-workspace isolation
        are identical to the session path — no fake User is created.
        """
        if action not in {ExpertAction.VIEW, ExpertAction.USE}:
            self._deny(expert_id, workspace.id, actor_id, reason="api_manage_denied")
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "API keys cannot manage Experts.",
            )
        return self._resolve_expert(
            workspace=workspace,
            expert_id=expert_id,
            action=action,
            actor_id=actor_id,
            membership=None,
        )

    def _resolve_expert(
        self,
        *,
        workspace: Workspace,
        expert_id: uuid.UUID,
        action: ExpertAction,
        actor_id: uuid.UUID | None,
        membership: WorkspaceMembership | None,
    ) -> AuthorizedExpert:
        expert = self.repo.get_by_id(expert_id)
        if expert is None or expert.deleted_at is not None:
            self._deny(expert_id, workspace.id, actor_id, reason="missing")
            raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")

        if expert.type == ExpertType.WORKSPACE.value:
            if expert.workspace_id != workspace.id:
                self._deny(expert_id, workspace.id, actor_id, reason="cross_workspace")
                raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
            return AuthorizedExpert(
                expert=expert,
                ownership="workspace",
                workspace=workspace,
                membership=membership,
                action=action,
            )

        if expert.type == ExpertType.PLATFORM.value:
            # Tenant users may view/use granted published Platform Experts.
            # Mutations always fail through tenant Expert endpoints.
            if ExpertPolicy.is_manage_action(action) or action in {
                ExpertAction.UPDATE,
                ExpertAction.DELETE,
                ExpertAction.MANAGE_KNOWLEDGE,
                ExpertAction.CREATE,
            }:
                self._deny(expert_id, workspace.id, actor_id, reason="platform_immutable")
                raise AppError(
                    ErrorCategory.EXPERT_IMMUTABLE,
                    "Platform Experts cannot be modified through Workspace APIs.",
                )
            if not self._platform_available_to_workspace(expert, workspace.id):
                self._deny(expert_id, workspace.id, actor_id, reason="no_grant")
                raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
            return AuthorizedExpert(
                expert=expert,
                ownership="platform",
                workspace=workspace,
                membership=membership,
                action=action,
            )

        self._deny(expert_id, workspace.id, actor_id, reason="unknown_type")
        raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")

    def _platform_available_to_workspace(self, expert: Expert, workspace_id: uuid.UUID) -> bool:
        if expert.status == ExpertStatus.DISABLED.value:
            return False
        if expert.visibility != ExpertVisibility.PLATFORM_PUBLISHED.value:
            return False
        if expert.availability_mode == ExpertAvailabilityMode.ALL_WORKSPACES.value:
            return True
        return self.repo.has_active_grant(workspace_id, expert.id)

    def require_platform_admin_expert(
        self,
        *,
        expert_id: uuid.UUID,
        platform_role: str | None,
        actor_id: uuid.UUID | None = None,
    ) -> Expert:
        ExpertPolicy.require_platform_admin(platform_role)
        expert = self.repo.get_by_id(expert_id)
        if expert is None or expert.deleted_at is not None:
            raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
        if expert.type != ExpertType.PLATFORM.value:
            raise AppError(ErrorCategory.VALIDATION, "Not a Platform Expert.")
        return expert

    def is_platform_admin(self, platform_role: str | None) -> bool:
        return platform_role == PlatformRole.ADMIN.value

    @staticmethod
    def _deny(
        expert_id: uuid.UUID,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        *,
        reason: str,
    ) -> None:
        security_log(
            "expert.access_denied",
            expert_id=str(expert_id),
            workspace_id=str(workspace_id),
            actor_id=str(actor_id) if actor_id else None,
            reason=reason,
        )
