"""Vector / RAG scope types — make unscoped tenant search hard to write."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True, slots=True)
class LegacyVectorScope:
    """Legacy MVP population: documents with workspace_id IS NULL."""

    kind: Literal["legacy"] = "legacy"


@dataclass(frozen=True, slots=True)
class WorkspaceVectorScope:
    """Workspace SaaS population: mandatory workspace_id filter in Qdrant."""

    workspace_id: uuid.UUID
    kind: Literal["workspace"] = "workspace"


@dataclass(frozen=True, slots=True)
class ExpertRagScope:
    """Expert-scoped retrieval (Phase 3B).

    Retrieval MUST filter Qdrant by both ``workspace_id`` (the knowledge Workspace
    that owns the underlying Documents) and Expert membership (``expert_ids``
    keyword-array contains ``expert_id``).

    * ``consumer_workspace_id`` — the tenant Workspace consuming the answer.
      Used for usage attribution / billing; NEVER used to filter Qdrant.
    * ``knowledge_workspace_id`` — the Workspace that owns the Documents backing
      this Expert (equals ``consumer_workspace_id`` for Workspace Experts; equals
      the internal Platform Knowledge Workspace for Platform Experts). This is
      the value that goes into the Qdrant ``workspace_id`` filter.
    * ``expert_id`` — the Expert whose linked knowledge is being queried.
    * ``expert_type`` — ``workspace`` | ``platform`` (mirrors ``Expert.type``).

    Only ExpertKnowledgeResolver should construct this scope, and only after
    ExpertAccessService has authorized the actor.
    """

    consumer_workspace_id: uuid.UUID
    knowledge_workspace_id: uuid.UUID
    expert_id: uuid.UUID
    expert_type: str  # "workspace" | "platform"
    kind: Literal["expert"] = "expert"


VectorScope = Union[LegacyVectorScope, WorkspaceVectorScope, ExpertRagScope]

# RagService aliases
LegacyRagScope = LegacyVectorScope
WorkspaceRagScope = WorkspaceVectorScope
RagScope = VectorScope
