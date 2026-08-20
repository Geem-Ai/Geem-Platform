"""Phase 12B — Platform Admin Workspace / User inventory + lifecycle."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit import AuditAction, AuditLog
from app.identity.models import PlatformRole, User, UserStatus
from app.workspaces.models import Workspace, WorkspaceKind, WorkspaceStatus
from app.workspaces.service import WorkspaceService


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


def _admin_client(client: TestClient, register_user, db, email: str) -> tuple[dict, User]:
    body = register_user(email=email)
    admin = _promote_platform_admin(db, body["user"]["id"])
    return body, admin


# --- Authz ---


def test_workspaces_list_unauthenticated_401(client: TestClient) -> None:
    res = client.get("/api/platform/workspaces")
    assert res.status_code == 401


def test_workspaces_list_owner_without_platform_role_403(
    client: TestClient, register_user
) -> None:
    owner = register_user(email="owner-12b-list@example.com")
    _create_workspace(client, owner, "ws-12b-owner-list")
    res = client.get("/api/platform/workspaces", headers=_auth(owner["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_api_key_cannot_call_platform_workspaces(
    client: TestClient, register_user, db
) -> None:
    owner = register_user(email="owner-12b-key@example.com")
    ws = _create_workspace(client, owner, "ws-12b-key")
    key_res = client.post(
        "/api/api-keys",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
        json={"name": "probe"},
    )
    assert key_res.status_code == 201, key_res.text
    secret = key_res.json()["key"]
    res = client.get("/api/platform/workspaces", headers=_auth(secret))
    assert res.status_code == 401


# --- Workspace list / detail ---


def test_platform_admin_lists_tenant_workspaces_paginated(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-list@example.com")
    owner = register_user(email="tenant-12b-list@example.com")
    _create_workspace(client, owner, "alpha-12b")
    _create_workspace(client, owner, "beta-12b")
    WorkspaceService(db).ensure_platform_knowledge_workspace()

    res = client.get(
        "/api/platform/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"limit": 1, "offset": 0},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["total"] >= 2
    assert len(payload["items"]) == 1
    assert all(item["kind"] == WorkspaceKind.TENANT.value for item in payload["items"])
    # System Workspace excluded by default
    assert all(item["slug"] != "platform-knowledge" for item in payload["items"])
    for item in payload["items"]:
        assert "password_hash" not in item
        assert "settings" not in item


def test_workspace_list_search_and_status_filter(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-search@example.com")
    owner = register_user(email="tenant-12b-search@example.com")
    ws = _create_workspace(client, owner, "searchable-acme-12b")
    other = _create_workspace(client, owner, "other-corp-12b")

    found = client.get(
        "/api/platform/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"search": "acme"},
    )
    assert found.status_code == 200
    slugs = {i["slug"] for i in found.json()["items"]}
    assert "searchable-acme-12b" in slugs
    assert "other-corp-12b" not in slugs

    # Suspend then filter
    disable = client.post(
        f"/api/platform/workspaces/{ws['id']}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Payment dispute under review"},
    )
    assert disable.status_code == 200, disable.text
    filtered = client.get(
        "/api/platform/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"status": WorkspaceStatus.SUSPENDED.value},
    )
    assert filtered.status_code == 200
    ids = {i["id"] for i in filtered.json()["items"]}
    assert ws["id"] in ids
    assert other["id"] not in ids


def test_workspace_list_kind_system_filter(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-kind@example.com")
    owner = register_user(email="tenant-12b-kind@example.com")
    tenant = _create_workspace(client, owner, "tenant-kind-12b")
    pk = WorkspaceService(db).ensure_platform_knowledge_workspace()

    system_only = client.get(
        "/api/platform/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"kind": WorkspaceKind.SYSTEM.value},
    )
    assert system_only.status_code == 200
    system_ids = {i["id"] for i in system_only.json()["items"]}
    assert str(pk.id) in system_ids
    assert tenant["id"] not in system_ids

    all_kinds = client.get(
        "/api/platform/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"kind": "all"},
    )
    assert all_kinds.status_code == 200
    all_ids = {i["id"] for i in all_kinds.json()["items"]}
    assert str(pk.id) in all_ids
    assert tenant["id"] in all_ids

    default_list = client.get(
        "/api/platform/workspaces",
        headers=_auth(admin_body["access_token"]),
    )
    assert default_list.status_code == 200
    default_ids = {i["id"] for i in default_list.json()["items"]}
    assert tenant["id"] in default_ids
    assert str(pk.id) not in default_ids


def test_workspace_detail_and_members(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-detail@example.com")
    owner = register_user(email="tenant-12b-detail@example.com")
    ws = _create_workspace(client, owner, "detail-ws-12b")

    detail = client.get(
        f"/api/platform/workspaces/{ws['id']}",
        headers=_auth(admin_body["access_token"]),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["id"] == ws["id"]
    assert body["slug"] == "detail-ws-12b"
    assert body["members_count"] >= 1
    assert len(body["owners"]) >= 1
    assert body["owners"][0]["email"] == "tenant-12b-detail@example.com"
    assert "resources" in body
    assert "password_hash" not in body
    assert "settings" not in body

    members = client.get(
        f"/api/platform/workspaces/{ws['id']}/members",
        headers=_auth(admin_body["access_token"]),
    )
    assert members.status_code == 200, members.text
    mbody = members.json()
    assert mbody["total"] >= 1
    row = mbody["items"][0]
    assert row["email"] == "tenant-12b-detail@example.com"
    assert row["role_id"]
    assert row["is_owner_role"] is True
    assert "password_hash" not in row


def test_workspace_detail_404(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-404@example.com")
    res = client.get(
        f"/api/platform/workspaces/{uuid.uuid4()}",
        headers=_auth(admin_body["access_token"]),
    )
    assert res.status_code == 404


# --- Disable / enable ---


def test_disable_requires_reason(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-reason@example.com")
    owner = register_user(email="tenant-12b-reason@example.com")
    ws = _create_workspace(client, owner, "reason-ws-12b")
    res = client.post(
        f"/api/platform/workspaces/{ws['id']}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "   "},
    )
    assert res.status_code in (400, 422)


def test_disable_enable_workspace_audited_and_enforced(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-life@example.com")
    owner = register_user(email="tenant-12b-life@example.com")
    ws = _create_workspace(client, owner, "life-ws-12b")

    # Create API key while active
    key_res = client.post(
        "/api/api-keys",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
        json={"name": "life-key"},
    )
    assert key_res.status_code == 201, key_res.text
    secret = key_res.json()["key"]

    disable = client.post(
        f"/api/platform/workspaces/{ws['id']}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Payment dispute under review"},
    )
    assert disable.status_code == 200, disable.text
    assert disable.json()["status"] == WorkspaceStatus.SUSPENDED.value

    row = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_DISABLED.value,
            AuditLog.entity_id == uuid.UUID(ws["id"]),
        )
    )
    assert row is not None
    assert row.extra.get("reason") == "Payment dispute under review"
    assert row.extra.get("after_status") == WorkspaceStatus.SUSPENDED.value

    # Tenant session API fails closed
    tenant = client.get(
        "/api/workspaces/current",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert tenant.status_code == 403, tenant.text
    assert tenant.json()["code"] == "workspace_access_denied"

    # Path-scoped tenant mutations also fail closed (not only require_workspace)
    patch_denied = client.patch(
        f"/api/workspaces/{ws['id']}",
        headers=_auth(owner["access_token"]),
        json={"name": "Should Not Apply"},
    )
    assert patch_denied.status_code == 403, patch_denied.text
    assert patch_denied.json()["code"] == "workspace_access_denied"

    get_by_id = client.get(
        f"/api/workspaces/{ws['id']}",
        headers=_auth(owner["access_token"]),
    )
    assert get_by_id.status_code == 403, get_by_id.text
    assert get_by_id.json()["code"] == "workspace_access_denied"

    # API key fails closed
    from app.main import app
    from app.api_keys.dependencies import get_api_key_principal
    from fastapi import Depends, Request

    if not getattr(app.state, "_phase12b_probe", False):

        @app.get("/__test__/phase12b/api-key", include_in_schema=False)
        def _probe(principal=Depends(get_api_key_principal)) -> dict:
            return {"ok": True, "workspace_id": str(principal.workspace_id)}

        app.state._phase12b_probe = True

    key_probe = client.get("/__test__/phase12b/api-key", headers=_auth(secret))
    assert key_probe.status_code == 403, key_probe.text
    assert key_probe.json()["code"] == "workspace_access_denied"

    # Owner cannot call platform disable
    denied = client.post(
        f"/api/platform/workspaces/{ws['id']}/disable",
        headers=_auth(owner["access_token"]),
        json={"reason": "Nope"},
    )
    assert denied.status_code == 403

    # Re-enable restores access; does not wipe memberships
    enable = client.post(
        f"/api/platform/workspaces/{ws['id']}/enable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Dispute resolved"},
    )
    assert enable.status_code == 200, enable.text
    assert enable.json()["status"] == WorkspaceStatus.ACTIVE.value
    assert enable.json()["members_count"] >= 1

    enabled_audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_ENABLED.value,
            AuditLog.entity_id == uuid.UUID(ws["id"]),
        )
    )
    assert enabled_audit is not None

    tenant_ok = client.get(
        "/api/workspaces/current",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert tenant_ok.status_code == 200, tenant_ok.text

    key_ok = client.get("/__test__/phase12b/api-key", headers=_auth(secret))
    assert key_ok.status_code == 200, key_ok.text


def test_system_workspace_cannot_be_disabled(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-sys@example.com")
    pk = WorkspaceService(db).ensure_platform_knowledge_workspace()
    res = client.post(
        f"/api/platform/workspaces/{pk.id}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Should not work"},
    )
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "system_workspace_protected"
    db.refresh(pk)
    assert pk.status == WorkspaceStatus.ACTIVE.value


# --- Users ---


def test_users_list_and_filters(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-users@example.com")
    register_user(email="findme-12b@example.com")
    other = register_user(email="other-12b@example.com")

    res = client.get(
        "/api/platform/users",
        headers=_auth(admin_body["access_token"]),
        params={"search": "findme-12b", "limit": 10},
    )
    assert res.status_code == 200, res.text
    emails = {i["email"] for i in res.json()["items"]}
    assert "findme-12b@example.com" in emails
    assert "other-12b@example.com" not in emails
    for item in res.json()["items"]:
        assert "password_hash" not in item
        assert "refresh_token" not in item

    role_filter = client.get(
        "/api/platform/users",
        headers=_auth(admin_body["access_token"]),
        params={"platform_role": PlatformRole.ADMIN.value},
    )
    assert role_filter.status_code == 200
    assert all(i["platform_role"] == "admin" for i in role_filter.json()["items"])

    normal = client.get("/api/platform/users", headers=_auth(other["access_token"]))
    assert normal.status_code == 403


def test_user_detail_memberships(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12b-udetail@example.com")
    owner = register_user(email="member-user-12b@example.com")
    ws = _create_workspace(client, owner, "membership-ws-12b")

    res = client.get(
        f"/api/platform/users/{owner['user']['id']}",
        headers=_auth(admin_body["access_token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == "member-user-12b@example.com"
    assert any(m["workspace_id"] == ws["id"] for m in body["memberships"])
    m = next(m for m in body["memberships"] if m["workspace_id"] == ws["id"])
    assert m["is_owner_role"] is True
    assert m["role_id"]
    assert "password_hash" not in body


def test_disable_enable_user_revokes_sessions_and_blocks_self(
    client: TestClient, register_user, db
) -> None:
    admin_body, admin = _admin_client(
        client, register_user, db, "padmin-12b-udisable@example.com"
    )
    target = register_user(email="disable-target-12b@example.com")
    target_token = target["access_token"]

    # Self-disable blocked
    self_res = client.post(
        f"/api/platform/users/{admin.id}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "oops"},
    )
    assert self_res.status_code == 409
    assert self_res.json()["code"] == "cannot_disable_self"

    disable = client.post(
        f"/api/platform/users/{target['user']['id']}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Abuse report"},
    )
    assert disable.status_code == 200, disable.text
    assert disable.json()["status"] == UserStatus.DISABLED.value

    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.USER_DISABLED.value,
            AuditLog.entity_id == uuid.UUID(target["user"]["id"]),
        )
    )
    assert audit is not None
    assert audit.extra.get("reason") == "Abuse report"

    # Existing session rejected
    me = client.get("/api/auth/me", headers=_auth(target_token))
    assert me.status_code == 401

    # Login rejected
    login = client.post(
        "/api/auth/login",
        json={"email": "disable-target-12b@example.com", "password": "password123"},
    )
    assert login.status_code in (401, 400)

    enable = client.post(
        f"/api/platform/users/{target['user']['id']}/enable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Cleared"},
    )
    assert enable.status_code == 200
    assert enable.json()["status"] == UserStatus.ACTIVE.value

    login_ok = client.post(
        "/api/auth/login",
        json={"email": "disable-target-12b@example.com", "password": "password123"},
    )
    assert login_ok.status_code == 200, login_ok.text
