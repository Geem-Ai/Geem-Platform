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
    local = Settings(
        _env_file=None,
        app_env="test",
        app_root_domain="localhost",
        workspace_web_url="",
    )
    assert local.effective_workspace_web_url == "http://localhost:5174"
    geem_local = Settings(
        _env_file=None,
        app_env="local",
        app_root_domain="geem.dm",
        workspace_web_url="",
    )
    assert geem_local.effective_workspace_web_url == "http://app.geem.dm:5174"
    assert geem_local.is_allowed_spa_origin("http://app.geem.dm:5174")
    assert geem_local.is_allowed_spa_origin("http://acme.geem.dm:5174")
    assert not geem_local.is_allowed_spa_origin("http://evil-geem.dm:5174")
    production = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
        workspace_web_url="",
        app_root_domain="geem.ai",
    )
    assert production.effective_workspace_web_url == ""
    assert production.is_allowed_spa_origin("https://acme.geem.ai")
    assert production.is_allowed_spa_origin("https://app.geem.ai")
    assert not production.is_allowed_spa_origin("http://acme.geem.ai")
    assert not production.is_allowed_spa_origin("https://evil-geem.ai")
    explicit = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
        workspace_web_url="https://app.geem.ai",
    )
    assert explicit.effective_workspace_web_url == "https://app.geem.ai"


def test_assert_secure_settings_rejects_insecure_api_key_pepper() -> None:
    with pytest.raises(RuntimeError, match="API_KEY_HASH_PEPPER"):
        assert_secure_settings(
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="a" * 40,
                cors_origins="https://app.geem.ai",
                api_key_hash_pepper="",
            )
        )
    with pytest.raises(RuntimeError, match="API_KEY_HASH_PEPPER"):
        assert_secure_settings(
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="a" * 40,
                cors_origins="https://app.geem.ai",
                api_key_hash_pepper="a" * 40,
            )
        )
    ok = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
        api_key_hash_pepper="b" * 40,
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@geem.ai",
        smtp_password="super-secret-smtp",
    )
    assert_secure_settings(ok)
    dumped = ok.model_dump()
    assert "api_key_hash_pepper" not in dumped
    assert "api_key_hash_pepper" not in repr(ok)
    assert "smtp_password" not in dumped
    assert "super-secret-smtp" not in repr(ok)
    assert "invitation_token_hash_pepper" not in dumped


def test_assert_secure_settings_rejects_star_cors_in_production() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="*",
    )
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        assert_secure_settings(settings)


def test_assert_secure_settings_rejects_console_email_in_production() -> None:
    with pytest.raises(RuntimeError, match="EMAIL_PROVIDER"):
        assert_secure_settings(
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="a" * 40,
                cors_origins="https://app.geem.ai",
                api_key_hash_pepper="b" * 40,
                email_provider="console",
            )
        )
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        assert_secure_settings(
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="a" * 40,
                cors_origins="https://app.geem.ai",
                api_key_hash_pepper="b" * 40,
                email_provider="smtp",
                smtp_host="",
                smtp_from_email="",
            )
        )


def test_assert_secure_settings_rejects_smtp_without_tls() -> None:
    with pytest.raises(RuntimeError, match="SMTP_USE_TLS"):
        assert_secure_settings(
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="a" * 40,
                cors_origins="https://app.geem.ai",
                api_key_hash_pepper="b" * 40,
                email_provider="smtp",
                smtp_host="smtp.example.com",
                smtp_from_email="noreply@geem.ai",
                smtp_password="super-secret-smtp",
                smtp_use_tls=False,
            )
        )


def test_assert_secure_settings_allows_smtp_without_cert_verify(caplog) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
        api_key_hash_pepper="b" * 40,
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@geem.ai",
        smtp_password="super-secret-smtp",
        smtp_use_tls=True,
        smtp_tls_verify=False,
    )
    with caplog.at_level("WARNING"):
        assert_secure_settings(settings)
    assert "SMTP_TLS_VERIFY is false" in caplog.text
