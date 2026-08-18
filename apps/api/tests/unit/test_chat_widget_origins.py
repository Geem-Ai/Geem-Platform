"""Unit tests for Chat Widget origin allowlist helpers."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.widgets.origins import (
    normalize_origin,
    normalize_origins_list,
    origin_allowed,
    request_origin,
)


def test_normalize_origin_strips_path() -> None:
    with pytest.raises(AppError):
        normalize_origin("https://example.com/path")


def test_normalize_origin_ok() -> None:
    assert normalize_origin("https://Example.com") == "https://example.com"
    assert normalize_origin("http://localhost:3000") == "http://localhost:3000"


def test_normalize_origins_list_empty_becomes_none() -> None:
    assert normalize_origins_list([]) is None
    assert normalize_origins_list(["  ", ""]) is None


def test_origin_allowed_empty_allowlist() -> None:
    assert origin_allowed(None, None) is True
    assert origin_allowed([], "https://evil.test") is True
    assert origin_allowed(None, "https://ok.test") is True


def test_origin_allowed_exact_match() -> None:
    allowed = ["https://www.example.com"]
    assert origin_allowed(allowed, "https://www.example.com") is True
    assert origin_allowed(allowed, "https://shop.example.com") is False
    assert origin_allowed(allowed, None) is False


def test_request_origin_prefers_origin_header() -> None:
    assert (
        request_origin("https://a.example", "https://b.example/page")
        == "https://a.example"
    )
    assert request_origin(None, "https://b.example/page") == "https://b.example"
