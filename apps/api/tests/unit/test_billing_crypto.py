from __future__ import annotations

import pytest

from app.common.crypto import decrypt_json, decrypt_secret, encrypt_json, encrypt_secret
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret="unit-test-jwt-secret-not-for-production",
    )


def test_round_trip_secret() -> None:
    token = encrypt_secret("server-key-value", settings=_settings())
    assert "server-key-value" not in token
    assert decrypt_secret(token, settings=_settings()) == "server-key-value"


def test_round_trip_json_hides_server_key() -> None:
    token = encrypt_json(
        {"profile_id": "1", "server_key": "sk_live_secret"},
        settings=_settings(),
    )
    assert "sk_live_secret" not in token
    assert decrypt_json(token, settings=_settings())["server_key"] == "sk_live_secret"


def test_tampered_token_fails() -> None:
    token = encrypt_secret("x", settings=_settings())
    with pytest.raises(ValueError):
        decrypt_secret(token[:-4] + "abcd", settings=_settings())
