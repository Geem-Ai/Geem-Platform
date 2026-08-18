"""Unit tests for password-reset tokens and email rendering."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import Settings
from app.identity.password_reset_email import render_password_reset_email
from app.identity.password_reset_tokens import (
    generate_password_reset_token,
    hash_password_reset_token,
    hashes_equal,
    password_reset_url,
)


def test_password_reset_token_hash_is_deterministic() -> None:
    settings = Settings(
        app_env="local",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
        password_reset_token_hash_pepper="unit-pepper-reset",
    )
    raw = generate_password_reset_token()
    a = hash_password_reset_token(raw, settings=settings)
    b = hash_password_reset_token(raw, settings=settings)
    assert a == b
    assert len(a) == 64
    assert hashes_equal(a, b)
    assert not hashes_equal(a, "0" * 64)


def test_password_reset_url_uses_workspace_web_url() -> None:
    settings = Settings(
        app_env="local",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
        workspace_web_url="https://app.example.test",
    )
    url = password_reset_url("abc+token", settings=settings)
    assert url == "https://app.example.test/reset-password?token=abc+token"


def test_password_reset_email_escapes_and_includes_link() -> None:
    content = render_password_reset_email(
        reset_url="https://app.example.test/reset-password?token=abc+token",
        expires_at=datetime(2030, 1, 2, 3, 4, tzinfo=timezone.utc),
        email='join<script>@example.com',
    )
    assert "Reset your Geem password" in content.subject
    assert "https://app.example.test/reset-password?token=abc+token" in content.text_body
    assert "<script>" not in content.html_body
    assert "join&lt;script&gt;@example.com" in content.html_body
    assert "02 Jan 2030" in content.text_body
