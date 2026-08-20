"""Phase 12A — Platform Admin authorization, host boundary, bootstrap /me."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.identity.models import PlatformRole, User, UserStatus
from app.workspaces.models import WorkspaceRole
from tests.support.rbac import add_workspace_member


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _promote_platform_admin(db, user_id: str) -> User:
    user = db.get(User, uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _create_workspace(client: TestClient, user: dict, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_unauthenticated_platform_me_401(client: TestClient) -> None:
    res = client.get("/api/platform/me")
    assert res.status_code == 401
    assert res.json()["code"] == "unauthorized"


def test_normal_user_platform_me_403(client: TestClient, register_user) -> None:
    user = register_user(email="normal-12a@example.com")
    res = client.get("/api/platform/me", headers=_auth(user["access_token"]))
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "platform_admin_required"


def test_workspace_member_cannot_access_platform(
    client: TestClient, register_user, db
) -> None:
    owner = register_user(email="owner-12a-member@example.com")
    member = register_user(email="member-12a@example.com")
    ws = _create_workspace(client, owner, "ws-12a-member")
    add_workspace_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER.value)

    res = client.get("/api/platform/me", headers=_auth(member["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_workspace_administrator_cannot_access_platform(
    client: TestClient, register_user, db
) -> None:
    owner = register_user(email="owner-12a-admin@example.com")
    admin = register_user(email="ws-admin-12a@example.com")
    ws = _create_workspace(client, owner, "ws-12a-admin")
    add_workspace_member(db, ws["id"], admin["user"]["id"], WorkspaceRole.ADMIN.value)

    res = client.get("/api/platform/me", headers=_auth(admin["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_workspace_owner_without_platform_role_cannot_access_platform(
    client: TestClient, register_user
) -> None:
    owner = register_user(email="owner-12a-no-pr@example.com")
    _create_workspace(client, owner, "ws-12a-owner")
    res = client.get("/api/platform/me", headers=_auth(owner["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_platform_admin_me_success(client: TestClient, register_user, db) -> None:
    body = register_user(email="padmin-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    res = client.get("/api/platform/me", headers=_auth(body["access_token"]))
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["authorized"] is True
    assert payload["platform_role"] == "admin"
    assert payload["user"]["id"] == body["user"]["id"]
    assert payload["user"]["email"] == "padmin-12a@example.com"
    assert "workspaces" not in payload
    assert "current_workspace" not in payload


def test_platform_admin_with_zero_workspaces_succeeds(
    client: TestClient, register_user, db
) -> None:
    body = register_user(email="padmin-lonely-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    res = client.get("/api/platform/me", headers=_auth(body["access_token"]))
    assert res.status_code == 200, res.text
    assert res.json()["authorized"] is True


def test_disabled_platform_admin_rejected(client: TestClient, register_user, db) -> None:
    body = register_user(email="padmin-disabled-12a@example.com")
    user = _promote_platform_admin(db, body["user"]["id"])
    user.status = UserStatus.DISABLED.value
    db.commit()

    res = client.get("/api/platform/me", headers=_auth(body["access_token"]))
    assert res.status_code == 401
    assert res.json()["code"] == "unauthorized"


def test_soft_deleted_platform_admin_rejected(
    client: TestClient, register_user, db
) -> None:
    body = register_user(email="padmin-deleted-12a@example.com")
    user = _promote_platform_admin(db, body["user"]["id"])
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()

    res = client.get("/api/platform/me", headers=_auth(body["access_token"]))
    assert res.status_code == 401
    assert res.json()["code"] == "unauthorized"


def test_workspace_api_key_rejected_from_platform(
    client: TestClient, register_user
) -> None:
    owner = register_user(email="keys-12a@example.com")
    ws = _create_workspace(client, owner, "ws-12a-keys")
    created = client.post(
        "/api/api-keys",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
        json={"name": "12A key"},
    )
    assert created.status_code == 201, created.text
    secret = created.json()["key"]
    assert secret.startswith("geem_sk_")

    res = client.get("/api/platform/me", headers=_auth(secret))
    assert res.status_code == 401
    assert res.json()["code"] == "unauthorized"


def test_incorrect_host_rejected_in_production_like_config(
    client: TestClient, register_user, db, monkeypatch
) -> None:
    body = register_user(email="padmin-host-bad-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: False,
    )
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "app_admin_host", "admin.geem.ai")
    monkeypatch.setattr(settings, "trust_proxy_headers", False)

    res = client.get(
        "/api/platform/me",
        headers={**_auth(body["access_token"]), "Host": "acme.geem.ai"},
    )
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "platform_admin_host_required"


def test_correct_admin_host_accepted_in_production_like_config(
    client: TestClient, register_user, db, monkeypatch
) -> None:
    body = register_user(email="padmin-host-ok-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: False,
    )
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "app_admin_host", "admin.geem.ai")
    monkeypatch.setattr(settings, "trust_proxy_headers", False)

    res = client.get(
        "/api/platform/me",
        headers={**_auth(body["access_token"]), "Host": "admin.geem.ai"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["authorized"] is True


def test_forwarded_host_ignored_when_proxy_untrusted(
    client: TestClient, register_user, db, monkeypatch
) -> None:
    body = register_user(email="padmin-xff-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: False,
    )
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "app_admin_host", "admin.geem.ai")
    monkeypatch.setattr(settings, "trust_proxy_headers", False)

    res = client.get(
        "/api/platform/me",
        headers={
            **_auth(body["access_token"]),
            "Host": "acme.geem.ai",
            "X-Forwarded-Host": "admin.geem.ai",
        },
    )
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_host_required"


def test_forwarded_host_cannot_spoof_admin_host_when_proxy_trusted(
    client: TestClient, register_user, db, monkeypatch
) -> None:
    """Host is authoritative; X-Forwarded-Host must not bypass a non-admin Host."""
    body = register_user(email="padmin-xff-spoof-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    monkeypatch.setattr(
        "app.platform_admin.host.host_enforcement_relaxed",
        lambda _s: False,
    )
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "app_admin_host", "admin.geem.ai")
    monkeypatch.setattr(settings, "trust_proxy_headers", True)

    res = client.get(
        "/api/platform/me",
        headers={
            **_auth(body["access_token"]),
            "Host": "api-uat.geem.ai",
            "X-Forwarded-Host": "admin.geem.ai",
        },
    )
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_host_required"


def test_platform_me_does_not_require_workspace_resolution(
    client: TestClient, register_user, db
) -> None:
    body = register_user(email="padmin-no-ws-hdr-12a@example.com")
    _promote_platform_admin(db, body["user"]["id"])
    res = client.get("/api/platform/me", headers=_auth(body["access_token"]))
    assert res.status_code == 200, res.text
    assert "X-Workspace-Slug" not in res.request.headers
    assert "X-Workspace-Id" not in res.request.headers


def test_tenant_headers_cannot_promote_normal_user(
    client: TestClient, register_user
) -> None:
    owner = register_user(email="owner-hdr-12a@example.com")
    ws = _create_workspace(client, owner, "ws-12a-hdr")
    res = client.get(
        "/api/platform/me",
        headers=_auth(
            owner["access_token"],
            **{
                "X-Workspace-Id": ws["id"],
                "X-Workspace-Slug": ws["slug"],
            },
        ),
    )
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"
