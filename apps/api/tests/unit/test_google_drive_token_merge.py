"""Unit tests — Google Drive token merge / refresh helpers (Phase 9D)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.connectors.providers.google_drive.token import (
    apply_token_response,
    credentials_need_refresh,
    merge_token_response,
)


def test_merge_preserves_refresh_token() -> None:
    old = {"access_token": "a1", "refresh_token": "keep-me", "token_type": "Bearer"}
    new = {"access_token": "a2", "expires_in": 3600}
    merged = merge_token_response(old, new)
    assert merged["access_token"] == "a2"
    assert merged["refresh_token"] == "keep-me"


def test_merge_does_not_overwrite_with_null() -> None:
    old = {"refresh_token": "keep-me", "access_token": "a1"}
    new = {"access_token": "a2", "refresh_token": None}
    merged = merge_token_response(old, new)
    assert merged["refresh_token"] == "keep-me"


def test_merge_accepts_new_refresh_token() -> None:
    old = {"refresh_token": "old", "access_token": "a1"}
    new = {"access_token": "a2", "refresh_token": "new"}
    merged = merge_token_response(old, new)
    assert merged["refresh_token"] == "new"


def test_apply_token_response_sets_expires_at() -> None:
    creds = apply_token_response(
        {"refresh_token": "r1"},
        {"access_token": "a1", "expires_in": 120, "scope": "openid drive.file"},
    )
    assert creds["access_token"] == "a1"
    assert creds["refresh_token"] == "r1"
    assert "expires_at" in creds
    assert "openid" in creds["granted_scopes"]


def test_credentials_need_refresh() -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert not credentials_need_refresh(
        {"access_token": "a", "expires_at": future}
    )
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert credentials_need_refresh({"access_token": "a", "expires_at": past})
    assert credentials_need_refresh({})
