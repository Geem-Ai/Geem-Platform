from __future__ import annotations

import re

from app.core.config import Settings


def _pattern_for(root: str) -> str:
    return rf"^https?://([a-z0-9-]+\.)?{re.escape(root)}(:\d+)?$"


def test_geem_dm_cors_regex_matches_tenant_and_app_hosts() -> None:
    pattern = _pattern_for("geem.dm")
    assert re.match(pattern, "http://app.geem.dm:5174")
    assert re.match(pattern, "http://acme.geem.dm:5174")
    assert re.match(pattern, "http://geem.dm:5174")
    assert re.match(pattern, "https://research.geem.dm")
    assert not re.match(pattern, "http://evil-geem.dm:5174")
    assert not re.match(pattern, "http://geem.dm.attacker.com")
    assert not re.match(pattern, "http://api.geem.dm.attacker.com")


def test_local_cors_helper_uses_root_domain(monkeypatch) -> None:
    # Import after ensuring settings can be constructed for local geem.dm
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_ROOT_DOMAIN", "geem.dm")
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.is_local
    assert settings.app_root_domain == "geem.dm"
    get_settings.cache_clear()


def test_production_spa_origin_regex_matches_one_label_https() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://hub.geem.ai",
        app_root_domain="geem.ai",
    )
    pattern = settings.spa_origin_regex()
    assert pattern is not None
    assert re.match(pattern, "https://acme.geem.ai")
    assert re.match(pattern, "https://hub.geem.ai")
    assert not re.match(pattern, "http://acme.geem.ai")
    assert not re.match(pattern, "https://acme.geem.ai:5174")
    assert not re.match(pattern, "https://foo.bar.geem.ai")
    assert not re.match(pattern, "https://evil-geem.ai")
    assert not re.match(pattern, "https://geem.ai.attacker.com")
    assert not re.match(pattern, "https://geem.ai")
    assert settings.is_allowed_spa_origin("https://acme.geem.ai")
    assert settings.is_allowed_spa_origin("https://hub.geem.ai")
    assert not settings.is_allowed_spa_origin("https://geem.ai")


def test_production_settings_still_reject_star_cors() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="*",
        app_root_domain="geem.dm",
    )
    from app.core.config import assert_secure_settings
    import pytest

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        assert_secure_settings(settings)
