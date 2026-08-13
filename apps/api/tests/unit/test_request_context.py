from __future__ import annotations

from uuid import uuid4

import pytest

from app.common.request_context import (
    RequestContext,
    clear_request_context,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from app.core.config import Settings


def test_request_context_defaults() -> None:
    clear_request_context()
    ctx = get_request_context()
    assert ctx.user_id is None
    assert ctx.workspace_id is None
    assert ctx.is_authenticated is False
    assert ctx.has_workspace is False


def test_request_context_set_reset() -> None:
    clear_request_context()
    user_id = uuid4()
    workspace_id = uuid4()
    token = set_request_context(
        RequestContext(
            request_id="req-1",
            user_id=user_id,
            workspace_id=workspace_id,
            workspace_slug="acme",
            membership_role="owner",
            auth_required=False,
        )
    )
    try:
        ctx = get_request_context()
        assert ctx.request_id == "req-1"
        assert ctx.user_id == user_id
        assert ctx.workspace_id == workspace_id
        assert ctx.workspace_slug == "acme"
        assert ctx.is_authenticated is True
        assert ctx.has_workspace is True
    finally:
        reset_request_context(token)

    assert get_request_context().user_id is None


def test_settings_phase0_class_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert Settings field defaults without process .env / env var coupling."""
    for key in (
        "AUTH_REQUIRED",
        "APP_NAME",
        "CORS_ORIGINS",
        "JWT_SECRET",
        "BOOTSTRAP_ADMIN_EMAIL",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)
    assert settings.auth_required is True
    assert settings.legacy_mvp_writes_enabled is False
    assert settings.app_name == "Geem"
    assert "http://localhost:5174" in settings.cors_origin_list
    assert settings.is_local is True
    assert "admin" in settings.reserved_slugs
    assert "app-uat" in settings.reserved_slugs
    assert "api-uat" in settings.reserved_slugs
    assert settings.access_token_ttl_seconds == 900
