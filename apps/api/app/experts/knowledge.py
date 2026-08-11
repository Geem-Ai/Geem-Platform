"""Resolve an authorized Expert to a fully-typed retrieval context (Phase 3B).

``ExpertKnowledgeResolver`` is the single place where an ``AuthorizedExpert``
(already vetted by ``ExpertAccessService``) is turned into everything RAG needs
to serve a query:

* the ``ExpertRagScope`` that Qdrant will filter by,
* the system-instruction string that gets fused into the base RAG prompt,
* the effective (clamped, Settings-defaulted) RAG config, and
* the list of ready Documents currently linked to the Expert.

Isolation rules enforced here:

* Never mutate ``RequestContext`` — the consumer Workspace stays the tenant's
  chosen Workspace. Retrieval reads the internal Platform Knowledge Workspace
  through a separate ``knowledge_workspace_id`` on the scope.
* Never construct an ``ExpertRagScope`` outside this resolver.
* Workspace Expert knowledge Workspace MUST equal the consumer Workspace.
* Platform Expert knowledge Workspace MUST equal the Platform Knowledge
  Workspace resolved via ``WorkspaceService.get_platform_knowledge_workspace``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.experts.access import AuthorizedExpert
from app.experts.models import ExpertDocument, ExpertType
from app.experts.rag_config import EffectiveRagConfig, resolve_effective_rag_config
from app.storage.scopes import ExpertRagScope
from app.workspaces.models import Workspace
from app.workspaces.service import WorkspaceService


@dataclass(frozen=True, slots=True)
class ResolvedExpertKnowledge:
    """Everything the RAG layer needs to serve a query for one Expert."""

    authorized: AuthorizedExpert
    scope: ExpertRagScope
    system_instructions: str
    rag_config: EffectiveRagConfig
    knowledge_workspace: Workspace
    ready_document_ids: tuple[uuid.UUID, ...]
    all_linked_document_ids: tuple[uuid.UUID, ...]

    @property
    def knowledge_workspace_id(self) -> uuid.UUID:
        return self.knowledge_workspace.id

    @property
    def consumer_workspace_id(self) -> uuid.UUID:
        return self.authorized.workspace.id

    @property
    def expert_id(self) -> uuid.UUID:
        return self.authorized.expert_id

    @property
    def has_ready_knowledge(self) -> bool:
        return bool(self.ready_document_ids)


class ExpertKnowledgeResolver:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self._workspaces = WorkspaceService(db, self.settings)

    def resolve(self, authorized: AuthorizedExpert) -> ResolvedExpertKnowledge:
        """Build a ``ResolvedExpertKnowledge`` from an already-authorized Expert.

        Callers must obtain ``AuthorizedExpert`` through ``ExpertAccessService``
        first; this method never rechecks role/grants but does re-verify the
        ownership/knowledge-Workspace invariants as defense in depth.
        """
        expert = authorized.expert
        consumer = authorized.workspace

        knowledge_workspace = self._resolve_knowledge_workspace(authorized)

        # Defense-in-depth: ownership vs. knowledge Workspace invariants that
        # ExpertAccessService already enforces, re-checked here so a broken
        # caller cannot accidentally cross populations.
        if expert.type == ExpertType.WORKSPACE.value:
            if knowledge_workspace.id != consumer.id:
                self._deny(authorized, reason="workspace_knowledge_mismatch")
                raise AppError(
                    ErrorCategory.EXPERT_ACCESS_DENIED,
                    "Workspace Expert knowledge Workspace mismatch.",
                )
        elif expert.type == ExpertType.PLATFORM.value:
            pk = self._workspaces.get_platform_knowledge_workspace()
            if knowledge_workspace.id != pk.id:
                self._deny(authorized, reason="platform_knowledge_mismatch")
                raise AppError(
                    ErrorCategory.EXPERT_ACCESS_DENIED,
                    "Platform Expert knowledge Workspace mismatch.",
                )
        else:
            self._deny(authorized, reason="unknown_expert_type")
            raise AppError(ErrorCategory.VALIDATION, "Unknown Expert type.")

        linked_docs = self._list_active_linked_documents(expert.id, knowledge_workspace.id)
        ready_doc_ids: list[uuid.UUID] = []
        all_doc_ids: list[uuid.UUID] = []
        for doc in linked_docs:
            all_doc_ids.append(doc.id)
            if doc.status == "ready" and doc.deleted_at is None:
                ready_doc_ids.append(doc.id)

        scope = ExpertRagScope(
            consumer_workspace_id=consumer.id,
            knowledge_workspace_id=knowledge_workspace.id,
            expert_id=expert.id,
            expert_type=expert.type,
        )
        rag_config = resolve_effective_rag_config(expert.rag_config, self.settings)

        return ResolvedExpertKnowledge(
            authorized=authorized,
            scope=scope,
            system_instructions=expert.system_instructions or "",
            rag_config=rag_config,
            knowledge_workspace=knowledge_workspace,
            ready_document_ids=tuple(ready_doc_ids),
            all_linked_document_ids=tuple(all_doc_ids),
        )

    def assert_candidate_membership(
        self,
        *,
        expert_id: uuid.UUID,
        document_id: uuid.UUID,
        knowledge_workspace_id: uuid.UUID,
    ) -> bool:
        """Return True iff PG records the Document as linked to the Expert in-scope.

        Used by the pipeline / reconciliation to double-check payload writes
        against DB reality before / after set_payload calls. Never leaks
        cross-Workspace membership.
        """
        stmt = (
            select(ExpertDocument.id)
            .join(Document, Document.id == ExpertDocument.document_id)
            .where(
                ExpertDocument.expert_id == expert_id,
                ExpertDocument.document_id == document_id,
                Document.workspace_id == knowledge_workspace_id,
                Document.deleted_at.is_(None),
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def _resolve_knowledge_workspace(
        self, authorized: AuthorizedExpert
    ) -> Workspace:
        expert = authorized.expert
        if expert.type == ExpertType.WORKSPACE.value:
            return authorized.workspace
        if expert.type == ExpertType.PLATFORM.value:
            return self._workspaces.get_platform_knowledge_workspace()
        raise AppError(ErrorCategory.VALIDATION, "Unknown Expert type.")

    def _list_active_linked_documents(
        self, expert_id: uuid.UUID, knowledge_workspace_id: uuid.UUID
    ) -> list[Document]:
        stmt = (
            select(Document)
            .join(ExpertDocument, ExpertDocument.document_id == Document.id)
            .where(
                ExpertDocument.expert_id == expert_id,
                Document.workspace_id == knowledge_workspace_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    @staticmethod
    def _deny(authorized: AuthorizedExpert, *, reason: str, **extra: Any) -> None:
        security_log(
            "expert.knowledge_resolve_denied",
            expert_id=str(authorized.expert_id),
            workspace_id=str(authorized.workspace.id),
            reason=reason,
            **extra,
        )
