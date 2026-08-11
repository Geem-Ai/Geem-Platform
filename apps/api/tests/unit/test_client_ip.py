from __future__ import annotations

from app.identity.dependencies import client_ip
from app.core.config import get_settings
from starlette.requests import Request


def _req(headers: dict[str, str], client_host: str = "203.0.113.10") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_client_ip_ignores_xff_by_default(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    get_settings.cache_clear()
    ip = client_ip(_req({"X-Forwarded-For": "1.2.3.4"}))
    assert ip == "203.0.113.10"
    get_settings.cache_clear()


def test_client_ip_uses_xff_when_trusted(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()
    ip = client_ip(_req({"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}))
    assert ip == "1.2.3.4"
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    get_settings.cache_clear()
