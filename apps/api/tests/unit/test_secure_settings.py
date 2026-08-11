from __future__ import annotations

import pytest

from app.core.config import Settings, assert_secure_settings


def test_assert_secure_settings_allows_local_default_secret() -> None:
    settings = Settings(
        _env_file=None,
        app_env="local",
        jwt_secret="change-me-in-production-use-long-random-secret",
    )
    assert_secure_settings(settings)


def test_assert_secure_settings_rejects_insecure_production_secret() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="change-me-in-production-use-long-random-secret",
        cors_origins="https://app.geem.ai",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_secure_settings(settings)


def test_assert_secure_settings_rejects_star_cors_in_production() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="*",
    )
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        assert_secure_settings(settings)
