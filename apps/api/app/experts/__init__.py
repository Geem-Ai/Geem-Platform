"""Experts domain — Phase 3A (ownership) + Phase 3B (Expert-scoped RAG core).

Only leaf modules are re-exported from the package root. Consumers of the
runtime services (``ExpertKnowledgeResolver``, ``ExpertQueryService``,
``ExpertVectorMembershipSynchronizer``, ``ExpertStatusReconciler``) must import
them directly from their submodules — those modules pull in ``app.db.models``
which itself imports the ORM classes from ``app.experts.models``, so eagerly
re-exporting them here would introduce a circular import at package init time.
"""

from app.experts.models import (
    Expert,
    ExpertAvailabilityMode,
    ExpertDocument,
    ExpertKnowledgeMode,
    ExpertSource,
    ExpertSourceStatus,
    ExpertStatus,
    ExpertType,
    ExpertVisibility,
    WorkspaceExpertGrant,
)
from app.experts.prompt import compose_expert_system_prompt, load_prompt_safety
from app.experts.rag_config import EffectiveRagConfig, resolve_effective_rag_config

__all__ = [
    "EffectiveRagConfig",
    "Expert",
    "ExpertAvailabilityMode",
    "ExpertDocument",
    "ExpertKnowledgeMode",
    "ExpertSource",
    "ExpertSourceStatus",
    "ExpertStatus",
    "ExpertType",
    "ExpertVisibility",
    "WorkspaceExpertGrant",
    "compose_expert_system_prompt",
    "load_prompt_safety",
    "resolve_effective_rag_config",
]
