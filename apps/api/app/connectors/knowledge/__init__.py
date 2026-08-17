"""Shared knowledge-source connector helpers (Phase 9E)."""

from app.connectors.knowledge.ingest import KnowledgeIngestBridge
from app.connectors.knowledge.resolve import (
    ResolvedExternalItem,
    resolve_selections_via_adapter,
)

__all__ = [
    "KnowledgeIngestBridge",
    "ResolvedExternalItem",
    "resolve_selections_via_adapter",
]
