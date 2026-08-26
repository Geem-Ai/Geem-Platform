from __future__ import annotations

import pytest

from app.core.config import Settings, assert_mcp_settings, assert_secure_settings


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
    with caplog.at_level("WARNING", logger="app.core.config"):
        assert_secure_settings(settings)
    assert "SMTP_TLS_VERIFY is false" in caplog.text


def _mcp_ready_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_env": "test",
        "mcp_connector_enabled": True,
        "mcp_egress_gateway_url": "https://mcp-egress-gateway:8443",
        "mcp_egress_client_cert_file": "/run/secrets/mcp-egress/client.crt",
        "mcp_egress_client_key_file": "/run/secrets/mcp-egress/client.key",
        "mcp_egress_ca_cert_file": "/run/secrets/mcp-egress/ca.crt",
        "openrouter_api_key": "test-provider-key",
    }
    values.update(overrides)
    return Settings(**values)


def test_mcp_settings_are_default_closed_and_ready_shape_passes() -> None:
    disabled = Settings(_env_file=None)
    assert disabled.mcp_connector_enabled is False
    assert_mcp_settings(disabled)

    ready = _mcp_ready_settings()
    assert ready.mcp_supported_protocol_version_list == (
        "2026-07-28",
        "2025-11-25",
        "2024-11-05",
    )
    assert_mcp_settings(ready)


def test_mcp_private_egress_is_never_allowed_outside_local() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        mcp_connector_enabled=False,
        mcp_allow_private_egress=True,
    )
    with pytest.raises(RuntimeError, match="MCP_ALLOW_PRIVATE_EGRESS"):
        assert_mcp_settings(settings)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"mcp_egress_gateway_url": "http://gateway:8443"}, "MCP_EGRESS_GATEWAY_URL"),
        ({"mcp_egress_client_key_file": ""}, "MCP_EGRESS_CLIENT_KEY_FILE"),
        (
            {"mcp_supported_protocol_versions": "2025-11-25,2026-07-28"},
            "MCP_SUPPORTED_PROTOCOL_VERSIONS",
        ),
        (
            {"mcp_tool_provider_capability_matrix": "{}"},
            "not readiness-approved",
        ),
    ],
)
def test_enabled_mcp_settings_fail_closed(overrides, match: str) -> None:
    with pytest.raises(RuntimeError, match=match):
        assert_mcp_settings(_mcp_ready_settings(**overrides))


def test_nonlocal_enabled_mcp_requires_dedicated_forward_proxy() -> None:
    settings = _mcp_ready_settings(
        app_env="production",
        mcp_egress_proxy_url="",
    )
    with pytest.raises(RuntimeError, match="MCP_EGRESS_PROXY_URL"):
        assert_mcp_settings(settings)


def test_nonlocal_enabled_mcp_rejects_public_gateway_host() -> None:
    settings = _mcp_ready_settings(
        app_env="production",
        mcp_egress_gateway_url="https://public.example.com:8443",
        mcp_egress_proxy_url="http://mcp-egress-proxy:3128",
    )
    with pytest.raises(RuntimeError, match="internal gateway service"):
        assert_mcp_settings(settings)


def test_nonlocal_enabled_mcp_requires_readable_mtls_mounts(tmp_path) -> None:
    settings = _mcp_ready_settings(
        app_env="production",
        mcp_egress_proxy_url="http://mcp-egress-proxy:3128",
        mcp_egress_client_cert_file=str(tmp_path / "missing-client.crt"),
        mcp_egress_client_key_file=str(tmp_path / "missing-client.key"),
        mcp_egress_ca_cert_file=str(tmp_path / "missing-ca.crt"),
    )
    with pytest.raises(RuntimeError, match="readable mounted"):
        assert_mcp_settings(settings)
