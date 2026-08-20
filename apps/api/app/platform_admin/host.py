"""APP_ADMIN_HOST guard for Platform Admin HTTP surfaces.

Production: Host must match ``Settings.app_admin_host`` (never a tenant slug).

Host is authoritative. Reverse proxies (including Cloudflare Tunnel) must
rewrite the origin Host (e.g. ``originRequest.httpHostHeader``). Client
``X-Forwarded-Host`` is never preferred over Host — when
``TRUST_PROXY_HEADERS`` is true a caller can still forge that header on a
non-admin ingress. It is only used as a last resort when Host is absent.

Local/test: enforcement is relaxed so the SPA can call the API as
localhost / testserver without a reverse-proxy Host rewrite. Production-like
tests monkeypatch ``host_enforcement_relaxed``.
"""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory


def host_enforcement_relaxed(settings: Settings) -> bool:
    """Local/test DX: dashboard_web talks to the API as localhost, not APP_ADMIN_HOST."""
    return settings.is_local


def normalize_hostname(value: str | None) -> str:
    """Return a lowercase hostname without port. Empty if unusable."""
    raw = (value or "").split(",")[0].strip().lower()
    if not raw:
        return ""
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    return raw.split("/")[0].split(":")[0]


def request_hostname(request: Request, settings: Settings) -> str:
    """Resolve the request host for Platform Admin host matching.

    Prefer Host. Only fall back to X-Forwarded-Host when Host is empty and
    trusted-proxy mode is enabled.
    """
    hostname = normalize_hostname(request.headers.get("host"))
    if hostname:
        return hostname
    if settings.trust_proxy_headers:
        return normalize_hostname(request.headers.get("X-Forwarded-Host"))
    return ""


def expected_admin_hostname(settings: Settings) -> str:
    return normalize_hostname(settings.app_admin_host)


def enforce_platform_admin_host(
    request: Request, settings: Settings | None = None
) -> str:
    """Fail closed when the Host is not the Platform Admin host.

    Returns the resolved hostname (empty when local enforcement is relaxed).
    """
    cfg = settings or get_settings()
    hostname = request_hostname(request, cfg)
    if host_enforcement_relaxed(cfg):
        return hostname

    expected = expected_admin_hostname(cfg)
    if not expected or hostname != expected:
        raise AppError(
            ErrorCategory.PLATFORM_ADMIN_HOST_REQUIRED,
            "Platform Admin APIs are only available on the admin host.",
        )
    return hostname
