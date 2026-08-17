"""Unit tests for Expert system-instructions AI assist."""

from __future__ import annotations

from app.experts.generate_instructions import sanitize_generated_instructions
from app.usage.weights import OPERATION_FAMILY, OpenRouterFamily, history_kind_for_operation


def test_expert_instructions_maps_to_chat_family() -> None:
    assert OPERATION_FAMILY["expert_instructions"] == OpenRouterFamily.CHAT
    assert history_kind_for_operation("expert_instructions") == "chat_tokens"


def test_sanitize_strips_fence_and_label() -> None:
    raw = '```markdown\nSystem instructions:\nBe a careful legal assistant.\n```'
    assert sanitize_generated_instructions(raw) == "Be a careful legal assistant."


def test_sanitize_clamps_length() -> None:
    huge = "a" * 40_000
    out = sanitize_generated_instructions(huge)
    assert len(out) == 32_000
