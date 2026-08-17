"""Unit tests for AppConfigEncryptionService."""

from __future__ import annotations

from app.apps_catalog.encryption import AppConfigEncryptionService
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret="unit-test-jwt-secret-not-for-production",
    )


def test_encrypt_decrypt_roundtrip() -> None:
    svc = AppConfigEncryptionService(_settings())
    token = svc.encrypt({"oauth": {"access": "tok_abc"}})
    assert "tok_abc" not in token
    assert svc.decrypt(token)["oauth"]["access"] == "tok_abc"
