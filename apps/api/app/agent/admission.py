"""Short, fail-closed paid admission transactions for the Agent API."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService, RuntimeAppAccessSnapshot
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENTS_AI_APP_SLUG,
)
from app.apps_catalog.agent_usage import (
    AgentRequestQuotaReceipt,
    AgentsAiRequestQuotaService,
)
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    begin_runtime_admission_transaction,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.entitlements.quota import QuotaService
from app.experts.access import AuthorizedExpert
from app.experts.knowledge import ResolvedExpertKnowledge
from app.experts.models import Expert, ExpertKnowledgeMode, ExpertType
from app.experts.policy import ExpertAction
from app.experts.query_service import ExpertQueryService
from app.experts.service import client_agent_enabled
from app.usage.attribution import GenerationUsageContext
from app.usage.metered import MeteredWorkspaceGeneration
from app.usage.weights import settled_tokens_from_payload
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentCompletionAdmission:
    """Committed admission plus the bounded settlement session it owns."""

    db: Session
    access: RuntimeAppAccessSnapshot
    knowledge: ResolvedExpertKnowledge
    execution_mode: str
    quota: AgentRequestQuotaReceipt
    meter: MeteredWorkspaceGeneration
    settings: Settings
    _closed: bool = False

    @property
    def request_id(self) -> str:
        return self.meter.request_id

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def uses_general_knowledge(self) -> bool:
        return self.execution_mode == ExpertKnowledgeMode.GENERAL.value

    def usage_context(self) -> GenerationUsageContext:
        return self.meter.context()

    def settle(self, provider_payload: dict[str, Any] | None) -> int:
        """Settle Workspace AI usage and return the Geem-weighted amount."""

        if self._closed:
            return 0
        billed = settled_tokens_from_payload(
            self.settings,
            provider_payload,
            extra_billed=self.meter.context().extra_billed_tokens,
        )
        try:
            self.meter.settle(provider_payload)
        except Exception:
            # A failed settlement must not leave the pre-provider AI hold
            # orphaned. Meter.release() rolls back the failed transaction
            # first and then performs the bounded release/extra-cost settle.
            self.meter.release()
            raise
        finally:
            self.close()
        return billed

    def release(self) -> None:
        """Release only the AI hold; the committed App request unit remains."""

        if self._closed:
            return
        try:
            self.meter.release()
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.db.close()


def require_agent_models_access(
    workspace_id: uuid.UUID,
) -> RuntimeAppAccessSnapshot:
    """Fresh paid access check for Models without RPM, Expert, or quota use."""

    db = SessionLocal()
    try:
        begin_runtime_admission_transaction(db)
        acquire_runtime_admission_fences(
            db,
            workspace_id=workspace_id,
            app_slugs=(AGENTS_AI_APP_SLUG,),
        )
        access = AppAccessService(db).require_runtime_active(
            workspace_id,
            app_slug=AGENTS_AI_APP_SLUG,
            entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
        )
        db.commit()
        return access
    except SQLAlchemyError as exc:
        _rollback_without_masking(db)
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Agent access is temporarily unavailable.",
            retryable=True,
        ) from exc
    except Exception:
        _rollback_without_masking(db)
        raise
    finally:
        db.close()


def admit_agent_completion(
    *,
    workspace_id: uuid.UUID,
    api_key_id: uuid.UUID,
    expert_id: uuid.UUID,
    request_id: str | None = None,
    settings: Settings | None = None,
) -> AgentCompletionAdmission:
    """Atomically authorize paid access/Expert and reserve both quotas.

    No network, Redis, cache-backed entitlement lookup, or commit-owning helper
    is used while the shared runtime fences are held. The transaction commits
    before this function returns, so retrieval and provider I/O cannot retain
    an authorization lock or database snapshot.
    """

    cfg = settings or get_settings()
    db = SessionLocal()
    rid = (request_id or str(uuid.uuid4())).strip()
    meter = MeteredWorkspaceGeneration(
        db,
        workspace_id=workspace_id,
        expert_id=expert_id,
        api_key_id=api_key_id,
        request_id=rid,
        settings=cfg,
    )
    try:
        begin_runtime_admission_transaction(db)
        acquire_runtime_admission_fences(
            db,
            workspace_id=workspace_id,
            app_slugs=(AGENTS_AI_APP_SLUG,),
        )
        access = AppAccessService(db).require_runtime_active(
            workspace_id,
            app_slug=AGENTS_AI_APP_SLUG,
            entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
        )

        locked = db.execute(
            select(Expert, Workspace)
            .join(Workspace, Workspace.id == Expert.workspace_id)
            .where(
                Expert.id == expert_id,
                Expert.workspace_id == workspace_id,
                Expert.type == ExpertType.WORKSPACE.value,
                Expert.deleted_at.is_(None),
                Workspace.id == workspace_id,
                Workspace.deleted_at.is_(None),
            )
            .with_for_update(of=Expert)
        ).one_or_none()
        if locked is None:
            raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
        expert, workspace = locked
        authorized = AuthorizedExpert(
            expert=expert,
            ownership="workspace",
            workspace=workspace,
            membership=None,
            action=ExpertAction.USE,
        )
        query = ExpertQueryService(db, cfg)
        knowledge = query.resolve_knowledge_for_agent(
            authorized,
            workspace=workspace,
            expert_id=expert.id,
            actor_id=api_key_id,
        )
        if not client_agent_enabled(expert.rag_config):
            raise AppError(
                ErrorCategory.AGENT_EXPERT_NOT_ENABLED,
                "Client agent API is not enabled for this Expert.",
            )
        execution_mode = _agent_execution_mode(knowledge)

        ai_limits = QuotaService(db, cfg).get_ai_limits_db_only(workspace_id)
        meter.reserve_in_transaction(ai_limits)
        receipt = AgentsAiRequestQuotaService(db).consume_in_transaction(
            workspace_id=workspace_id,
            request_id=rid,
            access=access,
        )
        db.commit()
        return AgentCompletionAdmission(
            db=db,
            access=access,
            knowledge=knowledge,
            execution_mode=execution_mode,
            quota=receipt,
            meter=meter,
            settings=cfg,
        )
    except SQLAlchemyError as exc:
        _rollback_without_masking(db)
        db.close()
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Agent admission is temporarily unavailable.",
            retryable=True,
        ) from exc
    except Exception:
        _rollback_without_masking(db)
        db.close()
        raise


def _agent_execution_mode(knowledge: ResolvedExpertKnowledge) -> str:
    """Derive runtime mode without changing the persisted Expert mode."""

    if (
        knowledge.authorized.expert.knowledge_mode
        == ExpertKnowledgeMode.GENERAL.value
    ):
        return ExpertKnowledgeMode.GENERAL.value
    if knowledge.has_ready_knowledge:
        return ExpertKnowledgeMode.RAG.value
    if not knowledge.all_linked_document_ids and not knowledge.has_active_sources:
        return ExpertKnowledgeMode.GENERAL.value

    # ``resolve_knowledge_for_agent`` rejects this state. Keep this defensive
    # boundary fail-closed if a future resolver change violates that contract.
    raise AppError(
        ErrorCategory.EXPERT_HAS_NO_KNOWLEDGE,
        "Expert has no ready knowledge to answer with yet.",
    )


def _rollback_without_masking(db: Session) -> None:
    """Best-effort cleanup while preserving the transaction's root failure."""

    try:
        db.rollback()
    except SQLAlchemyError:
        logger.exception("agent_admission_rollback_failed")


__all__ = [
    "AgentCompletionAdmission",
    "admit_agent_completion",
    "require_agent_models_access",
]
