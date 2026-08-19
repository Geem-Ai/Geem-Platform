"""Unit tests for email-verification tokens and email rendering."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import Settings
from app.identity.email_verification_email import render_email_verification_email
from app.identity.email_verification_tokens import (
    generate_email_verification_token,
    hash_email_verification_token,
    hashes_equal,
    email_verification_url,
)
from app.identity.password_reset_tokens import hash_password_reset_token


def test_email_verification_token_hash_is_deterministic() -> None:
    settings = Settings(
        app_env="local",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
        password_reset_token_hash_pepper="unit-pepper-verify",
    )
    raw = generate_email_verification_token()
    a = hash_email_verification_token(raw, settings=settings)
    b = hash_email_verification_token(raw, settings=settings)
    assert a == b
    assert len(a) == 64
    assert hashes_equal(a, b)
    assert not hashes_equal(a, "0" * 64)


def test_email_verification_hash_prefix_differs_from_password_reset() -> None:
    settings = Settings(
        app_env="local",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
        password_reset_token_hash_pepper="unit-pepper-verify",
    )
    raw = generate_email_verification_token()
    verify_hash = hash_email_verification_token(raw, settings=settings)
    reset_hash = hash_password_reset_token(raw, settings=settings)
    assert verify_hash != reset_hash


def test_email_verification_url_uses_workspace_web_url() -> None:
    settings = Settings(
        app_env="local",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
        workspace_web_url="https://app.example.test",
    )
    url = email_verification_url("abc+token", settings=settings)
    assert url == "https://app.example.test/verify-email?token=abc+token"


def test_email_verification_email_escapes_and_includes_link() -> None:
    content = render_email_verification_email(
        verify_url="https://app.example.test/verify-email?token=abc+token",
        expires_at=datetime(2030, 1, 2, 3, 4, tzinfo=timezone.utc),
        email='join<script>@example.com',
    )
    assert "Verify your Geem email" in content.subject
    assert "https://app.example.test/verify-email?token=abc+token" in content.text_body
    assert "<script>" not in content.html_body
    assert "join&lt;script&gt;@example.com" in content.html_body
    assert "02 Jan 2030" in content.text_body


def test_email_verification_required_defaults_off_in_test() -> None:
    test_settings = Settings(
        app_env="test",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
    )
    local_settings = Settings(
        app_env="local",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
    )
    assert test_settings.effective_email_verification_required is False
    assert local_settings.effective_email_verification_required is True
    forced = Settings(
        app_env="test",
        jwt_secret="unit-test-jwt-secret-at-least-32-chars!!",
        email_verification_required=True,
    )
    assert forced.effective_email_verification_required is True
