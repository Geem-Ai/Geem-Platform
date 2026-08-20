"""Unit tests for Platform Admin host matching (Phase 12A)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError, ErrorCategory
from app.platform_admin.authz import require_platform_admin_role, require_platform_admin_user
from app.platform_admin.host import (
    enforce_platform_admin_host,
    expected_admin_hostname,
    normalize_hostname,
    request_hostname,
)
from app.identity.models import PlatformRole, UserStatus


def test_normalize_hostname_strips_port_and_case() -> None:
    assert normalize_hostname("Admin.Geem.AI:443") == "admin.geem.ai"
    assert normalize_hostname("admin.geem.ai") == "admin.geem.ai"
    assert normalize_hostname("") == ""
    assert normalize_hostname(None) == ""


def test_request_hostname_prefers_host_over_forwarded() -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "X-Forwarded-Host": "admin.geem.ai",
        "host": "acme.geem.ai",
    }.get(key, default)
    settings = SimpleNamespace(trust_proxy_headers=True)
    assert request_hostname(request, settings) == "acme.geem.ai"


def test_request_hostname_ignores_forwarded_host_when_untrusted() -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "X-Forwarded-Host": "admin.geem.ai",
        "host": "acme.geem.ai",
    }.get(key, default)
    settings = SimpleNamespace(trust_proxy_headers=False)
    assert request_hostname(request, settings) == "acme.geem.ai"


def test_request_hostname_falls_back_to_forwarded_when_host_absent() -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "X-Forwarded-Host": "admin.geem.ai",
        "host": "",
    }.get(key, default)
    settings = SimpleNamespace(trust_proxy_headers=True)
    assert request_hostname(request, settings) == "admin.geem.ai"


def test_request_hostname_uses_first_forwarded_host_when_trusted_and_host_absent() -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "X-Forwarded-Host": "evil.example, admin.geem.ai",
        "host": None,
    }.get(key, default)
    settings = SimpleNamespace(trust_proxy_headers=True)
    assert request_hostname(request, settings) == "evil.example"


def test_enforce_relaxed_in_local(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "host": "localhost:8000",
    }.get(key, default)
    settings = SimpleNamespace(
        is_local=True,
        app_admin_host="admin.geem.ai",
        trust_proxy_headers=False,
    )
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: True,
    )
    assert enforce_platform_admin_host(request, settings) == "localhost"


def test_enforce_rejects_wrong_host_when_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "host": "acme.geem.ai",
        "X-Forwarded-Host": "admin.geem.ai",
    }.get(key, default)
    settings = SimpleNamespace(
        is_local=False,
        app_admin_host="admin.geem.ai",
        trust_proxy_headers=False,
    )
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: False,
    )
    with pytest.raises(AppError) as exc:
        enforce_platform_admin_host(request, settings)
    assert exc.value.category == ErrorCategory.PLATFORM_ADMIN_HOST_REQUIRED


def test_enforce_accepts_admin_host_when_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: {
        "host": "admin.geem.ai",
    }.get(key, default)
    settings = SimpleNamespace(
        is_local=False,
        app_admin_host="admin.geem.ai",
        trust_proxy_headers=False,
    )
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: False,
    )
    assert enforce_platform_admin_host(request, settings) == "admin.geem.ai"
    assert expected_admin_hostname(settings) == "admin.geem.ai"


def test_require_platform_admin_role_fail_closed() -> None:
    with pytest.raises(AppError) as exc:
        require_platform_admin_role("none")
    assert exc.value.category == ErrorCategory.PLATFORM_ADMIN_REQUIRED
    require_platform_admin_role(PlatformRole.ADMIN.value)


def test_require_platform_admin_user_rejects_inactive() -> None:
    user = SimpleNamespace(
        deleted_at=None,
        status=UserStatus.DISABLED.value,
        platform_role=PlatformRole.ADMIN.value,
    )
    with pytest.raises(AppError) as exc:
        require_platform_admin_user(user)  # type: ignore[arg-type]
    assert exc.value.category == ErrorCategory.UNAUTHORIZED
