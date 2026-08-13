"""Unit tests for document repository search helpers."""

from __future__ import annotations

from app.documents.repository import ilike_contains_pattern


def test_ilike_contains_pattern_escapes_metacharacters() -> None:
    assert ilike_contains_pattern("100%") == r"%100\%%"
    assert ilike_contains_pattern("a_b") == r"%a\_b%"
    assert ilike_contains_pattern(r"path\to") == r"%path\\to%"
    assert ilike_contains_pattern("plain") == "%plain%"
