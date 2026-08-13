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


def test_workspace_web_url_falls_back_to_localhost_only_when_local() -> None:
    local = Settings(_env_file=None, app_env="test", workspace_web_url="")
    assert local.effective_workspace_web_url == "http://localhost:5174"
    production = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
        workspace_web_url="",
    )
    assert production.effective_workspace_web_url == ""
    explicit = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
        workspace_web_url="https://app.geem.ai",
    )
    assert explicit.effective_workspace_web_url == "https://app.geem.ai"


def test_assert_secure_settings_rejects_star_cors_in_production() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="*",
    )
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        assert_secure_settings(settings)
