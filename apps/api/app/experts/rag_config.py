"""Typed effective RAG config for Expert-scoped retrieval (Phase 3B).

Storage side of the Expert stores a raw ``rag_config`` JSONB with an open shape
whose keys are validated at write time by
``app.experts.service.normalize_rag_config``. At query time we resolve the raw
dict into a strictly-typed ``EffectiveRagConfig`` layered on Settings defaults
and clamped to safe bounds — this is the single source of truth consumed by
``RagService`` / ``ExpertQueryService``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings

# Bounds must match ``normalize_rag_config`` in ``app.experts.service``; kept
# in sync deliberately so a stored rag_config that predates a tighter clamp
# still resolves to a safe value here.
_TOP_K_MIN = 1
_TOP_K_MAX = 100
_RERANK_MIN = 1
_RERANK_MAX = 50
_SIM_MIN = 0.0
_SIM_MAX = 1.0

SUPPORTED_KEYS: frozenset[str] = frozenset(
    {"top_k", "rerank_top_n", "similarity_threshold"}
)


@dataclass(frozen=True, slots=True)
class EffectiveRagConfig:
    """Fully-resolved RAG knobs after Settings defaults + Expert overrides."""

    top_k: int
    rerank_top_n: int
    similarity_threshold: float | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "top_k": self.top_k,
            "rerank_top_n": self.rerank_top_n,
        }
        if self.similarity_threshold is not None:
            out["similarity_threshold"] = self.similarity_threshold
        return out


def _clamp_int(value: Any, *, lo: int, hi: int, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _clamp_float(value: Any, *, lo: float, hi: float) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    val = float(value)
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def resolve_effective_rag_config(
    expert_rag_config: dict[str, Any] | None,
    settings: Settings | None = None,
) -> EffectiveRagConfig:
    """Merge Settings defaults with a persisted Expert ``rag_config``.

    Unknown keys are silently ignored (they were rejected at Expert create /
    update time; encountering them here means the stored blob predates a
    tightening of the schema).
    """
    cfg = settings or get_settings()
    raw = expert_rag_config if isinstance(expert_rag_config, dict) else {}

    default_top_k = _clamp_int(
        cfg.retrieval_top_k, lo=_TOP_K_MIN, hi=_TOP_K_MAX, fallback=_TOP_K_MIN
    )
    default_rerank = _clamp_int(
        cfg.rerank_top_n, lo=_RERANK_MIN, hi=_RERANK_MAX, fallback=_RERANK_MIN
    )

    top_k = _clamp_int(
        raw.get("top_k", default_top_k),
        lo=_TOP_K_MIN,
        hi=_TOP_K_MAX,
        fallback=default_top_k,
    )
    rerank_top_n = _clamp_int(
        raw.get("rerank_top_n", default_rerank),
        lo=_RERANK_MIN,
        hi=_RERANK_MAX,
        fallback=default_rerank,
    )
    similarity_threshold: float | None = None
    if "similarity_threshold" in raw:
        similarity_threshold = _clamp_float(
            raw.get("similarity_threshold"), lo=_SIM_MIN, hi=_SIM_MAX
        )

    return EffectiveRagConfig(
        top_k=top_k,
        rerank_top_n=rerank_top_n,
        similarity_threshold=similarity_threshold,
    )
