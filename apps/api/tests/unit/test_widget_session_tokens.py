"""Unit tests for HMAC widget session tokens."""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.widgets.session_tokens import (
    mint_session_token,
    parse_bare_session_uuid,
    parse_session_token,
    require_session_uuid,
)


def test_mint_and_parse_roundtrip() -> None:
    secret = "unit-test-secret-not-for-production-use"
    sid = str(uuid.uuid4())
    token = mint_session_token(sid, secret=secret)
    assert parse_session_token(token, secret=secret) == sid
    assert parse_session_token(token, secret="other-secret") is None


def test_tampered_token_rejected() -> None:
    secret = "unit-test-secret-not-for-production-use"
    sid = str(uuid.uuid4())
    token = mint_session_token(sid, secret=secret)
    bad = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert parse_session_token(bad, secret=secret) is None


def test_bare_uuid_helper() -> None:
    sid = str(uuid.uuid4())
    assert parse_bare_session_uuid(sid) == sid
    assert parse_bare_session_uuid(f"{sid}.abc") is None
    assert parse_bare_session_uuid("not-a-uuid") is None


def test_require_mints_when_empty() -> None:
    secret = "unit-test-secret-not-for-production-use"
    sid, token = require_session_uuid(None, secret=secret)
    assert parse_session_token(token, secret=secret) == sid


def test_require_rejects_bare_uuid() -> None:
    secret = "unit-test-secret-not-for-production-use"
    with pytest.raises(AppError):
        require_session_uuid(str(uuid.uuid4()), secret=secret)
