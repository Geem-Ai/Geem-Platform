"""Orchestrate an Expert-scoped RAG query end-to-end (Phase 3B).

Responsibilities:

1. Authorize the actor against the requested Expert (delegates to
   ``ExpertAccessService``). Workspace-Expert / Platform-Expert visibility,
   grants, and role checks live there.
2. Enforce Expert lifecycle preconditions (disabled / processing / no
   knowledge / failed / ready) and translate them into stable error codes.
3. Resolve the Expert into a ``ResolvedExpertKnowledge`` (scope + prompt +
   effective RAG config + ready-Document set).
4. Delegate retrieval and generation to ``RagService.query_expert`` /
   ``query_expert_stream``. Parent work will add those thin wrappers to
   ``RagService``; this module owns the orchestration and the error taxonomy
   above them.

RequestContext (consumer Workspace) is NEVER mutated to reach Platform
Knowledge — the ``ExpertRagScope`` carries a separate
``knowledge_workspace_id`` field, and the consumer Workspace stays whatever
the tenant selected.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.access import AuthorizedExpert, ExpertAccessService
from app.experts.knowledge import ExpertKnowledgeResolver, ResolvedExpertKnowledge
from app.experts.models import ExpertStatus, ExpertType
from app.experts.policy import ExpertAction
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceMembership

if TYPE_CHECKING:  # pragma: no cover
    from app.rag.service import RagService

logger = logging.getLogger(__name__)


class ExpertQueryService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        rag_service: "RagService | None" = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.access = ExpertAccessService(db)
        self.resolver = ExpertKnowledgeResolver(db, self.settings)
        # Import lazily to avoid a circular import (RagService pulls storage,
        # storage exports ExpertRagScope, ExpertRagScope is imported here).
        if rag_service is None:
            from app.rag.service import RagService as _RagService

            rag_service = _RagService(db, self.settings)
        self._rag = rag_service

    # ------------------------------------------------------------------
    # HTTP-facing entry points
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        question: str,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        knowledge = self._prepare(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=expert_id,
        )
        return self._rag.query_expert(
            question=question,
            knowledge=knowledge,
            top_k=top_k,
        )

    def query_stream(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        question: str,
        top_k: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        knowledge = self._prepare(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=expert_id,
        )
        yield from self._rag.query_expert_stream(
            question=question,
            knowledge=knowledge,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Preparation
    # ------------------------------------------------------------------

    def _prepare(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
    ) -> ResolvedExpertKnowledge:
        # 1. Authorize (VIEW is the minimum for reading knowledge; USE is the
        # semantic action for querying — enforce USE so Members without USE
        # would be denied, matching ExpertPolicy).
        authorized = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.USE,
            actor_id=actor.id,
        )

        # 2. Enforce Expert lifecycle preconditions BEFORE resolving knowledge.
        self._require_serviceable(authorized, actor_id=actor.id)

        # 3. Resolve knowledge (scope + system_instructions + rag_config +
        # ready docs) — never before the checks above.
        knowledge = self.resolver.resolve(authorized)

        # 4. An Expert can be status=ready with 0 ready docs if all its docs
        # got soft-deleted after the last reconciliation — treat that as
        # "no knowledge" rather than empty retrieval.
        if not knowledge.has_ready_knowledge:
            security_log(
                "expert.query_denied",
                expert_id=str(expert_id),
                workspace_id=str(workspace.id),
                actor_id=str(actor.id),
                reason="no_ready_knowledge",
            )
            raise AppError(
                ErrorCategory.EXPERT_HAS_NO_KNOWLEDGE,
                "Expert has no ready knowledge to answer with yet.",
            )
        return knowledge

    def _require_serviceable(
        self, authorized: AuthorizedExpert, *, actor_id: uuid.UUID
    ) -> None:
        expert = authorized.expert
        status = expert.status
        expert_id = expert.id
        workspace_id = authorized.workspace.id

        if status == ExpertStatus.DISABLED.value:
            # Workspace-owned Experts advertise "disabled" to their tenant so
            # owners can re-enable. Platform Experts are already filtered out
            # by ExpertAccessService._platform_available; if one reaches here
            # it means an admin flipped status between resolve and query — we
            # still hide behind NOT_FOUND for Platform to preserve platform
            # opacity, and surface DISABLED for owned experts.
            if expert.type == ExpertType.PLATFORM.value:
                security_log(
                    "expert.query_denied",
                    expert_id=str(expert_id),
                    workspace_id=str(workspace_id),
                    actor_id=str(actor_id),
                    reason="platform_disabled_race",
                )
                raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
            security_log(
                "expert.query_denied",
                expert_id=str(expert_id),
                workspace_id=str(workspace_id),
                actor_id=str(actor_id),
                reason="disabled",
            )
            raise AppError(
                ErrorCategory.EXPERT_DISABLED,
                "This Expert is disabled.",
            )

        if status == ExpertStatus.PROCESSING.value:
            security_log(
                "expert.query_denied",
                expert_id=str(expert_id),
                workspace_id=str(workspace_id),
                actor_id=str(actor_id),
                reason="processing",
            )
            raise AppError(
                ErrorCategory.EXPERT_NOT_READY,
                "Expert knowledge is still being processed.",
            )

        if status == ExpertStatus.DRAFT.value:
            security_log(
                "expert.query_denied",
                expert_id=str(expert_id),
                workspace_id=str(workspace_id),
                actor_id=str(actor_id),
                reason="draft_no_knowledge",
            )
            raise AppError(
                ErrorCategory.EXPERT_HAS_NO_KNOWLEDGE,
                "Expert has no knowledge attached yet.",
            )

        if status == ExpertStatus.FAILED.value:
            security_log(
                "expert.query_denied",
                expert_id=str(expert_id),
                workspace_id=str(workspace_id),
                actor_id=str(actor_id),
                reason="failed",
            )
            raise AppError(
                ErrorCategory.EXPERT_KNOWLEDGE_UNAVAILABLE,
                "Expert knowledge is currently unavailable.",
            )

        # ``ready`` (or any unrecognized non-terminal status) falls through —
        # ``_prepare`` will still gate on has_ready_knowledge afterwards.
        if status != ExpertStatus.READY.value:
            logger.info(
                "expert.query_unknown_status",
                extra={
                    "expert_id": str(expert_id),
                    "workspace_id": str(workspace_id),
                    "status": status,
                },
            )


__all__ = ["ExpertQueryService"]
