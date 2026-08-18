"""Phase 10C — dynamic workspace RBAC, isolation, and least privilege."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.notifications.factory import get_email_provider
from tests.support.fake_email import RecordingEmailProvider

from app.workspaces.models import WorkspaceMembership
from app.workspaces.permissions import (
    ADMIN_PERMISSION_KEYS,
    ALL_PERMISSION_KEYS,
    MEMBER_PERMISSION_KEYS,
    WorkspacePermission,
)
from app.workspaces.rbac_service import get_effective_permissions
from tests.support.rbac import add_workspace_member, get_membership, role_id, system_role


@pytest.fixture()
def inbox() -> RecordingEmailProvider:
    provider = RecordingEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: provider
    return provider


def _auth(token: str, workspace: dict | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace is not None:
        headers["X-Workspace-Id"] = workspace["id"]
    return headers


def _create_workspace(client: TestClient, user: dict, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_custom_role(
    client: TestClient,
    owner: dict,
    workspace: dict,
    name: str,
    permissions: list[str],
) -> dict:
    res = client.post(
        f"/api/workspaces/{workspace['id']}/roles",
        headers=_auth(owner["access_token"], workspace),
        json={"name": name, "description": "custom", "permissions": permissions},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_default_roles_match_phase10_permission_sets(client, register_user, db) -> None:
    owner = register_user(email="rbac-owner-eq@example.com")
    admin = register_user(email="rbac-admin-eq@example.com")
    member = register_user(email="rbac-member-eq@example.com")
    ws = _create_workspace(client, owner, "rbac-eq")
    add_workspace_member(db, ws["id"], admin["user"]["id"], "admin")
    add_workspace_member(db, ws["id"], member["user"]["id"], "member")

    owner_m = get_membership(db, ws["id"], owner["user"]["id"])
    admin_m = get_membership(db, ws["id"], admin["user"]["id"])
    member_m = get_membership(db, ws["id"], member["user"]["id"])
    db.refresh(owner_m)
    db.refresh(admin_m)
    db.refresh(member_m)

    assert get_effective_permissions(owner_m) == ALL_PERMISSION_KEYS
    assert get_effective_permissions(admin_m) == ADMIN_PERMISSION_KEYS
    assert get_effective_permissions(member_m) == MEMBER_PERMISSION_KEYS

    me = client.get("/api/auth/me", headers=_auth(owner["access_token"], ws))
    assert me.status_code == 200
    current = me.json()["current_workspace"]
    assert current["role"]["is_owner_role"] is True
    assert set(current["permissions"]) == set(ALL_PERMISSION_KEYS)


def test_role_crud_and_unknown_permission(client, register_user) -> None:
    owner = register_user(email="rbac-crud@example.com")
    ws = _create_workspace(client, owner, "rbac-crud")
    created = _create_custom_role(
        client,
        owner,
        ws,
        "Support Agent",
        [WorkspacePermission.CHAT_USE.value, WorkspacePermission.EXPERTS_VIEW.value],
    )
    assert created["is_system"] is False
    assert created["is_owner_role"] is False
    assert set(created["permissions"]) == {
        WorkspacePermission.CHAT_USE.value,
        WorkspacePermission.EXPERTS_VIEW.value,
    }

    listed = client.get(
        f"/api/workspaces/{ws['id']}/roles",
        headers=_auth(owner["access_token"], ws),
    )
    assert listed.status_code == 200
    names = {r["name"] for r in listed.json()["items"]}
    assert {"Owner", "Administrator", "Member", "Support Agent"} <= names

    unknown = client.post(
        f"/api/workspaces/{ws['id']}/roles",
        headers=_auth(owner["access_token"], ws),
        json={"name": "Hacker", "permissions": ["not.a.real.permission"]},
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "unknown_permission"

    owner_only = client.post(
        f"/api/workspaces/{ws['id']}/roles",
        headers=_auth(owner["access_token"], ws),
        json={"name": "Pretend Owner", "permissions": [WorkspacePermission.WORKSPACE_DELETE.value]},
    )
    assert owner_only.status_code == 403
    assert owner_only.json()["code"] == "role_protected"


def test_owner_role_immutable_and_non_deletable(client, register_user, db) -> None:
    owner = register_user(email="rbac-own-imm@example.com")
    ws = _create_workspace(client, owner, "rbac-own-imm")
    owner_role = system_role(db, ws["id"], "owner")
    patched = client.patch(
        f"/api/workspaces/{ws['id']}/roles/{owner_role.id}",
        headers=_auth(owner["access_token"], ws),
        json={"name": "Not Owner"},
    )
    assert patched.status_code == 403
    assert patched.json()["code"] == "role_protected"
    deleted = client.delete(
        f"/api/workspaces/{ws['id']}/roles/{owner_role.id}",
        headers=_auth(owner["access_token"], ws),
    )
    assert deleted.status_code == 403

    admin_role = system_role(db, ws["id"], "admin")
    renamed = client.patch(
        f"/api/workspaces/{ws['id']}/roles/{admin_role.id}",
        headers=_auth(owner["access_token"], ws),
        json={"name": "Not Admin"},
    )
    assert renamed.status_code == 403
    deleted_admin = client.delete(
        f"/api/workspaces/{ws['id']}/roles/{admin_role.id}",
        headers=_auth(owner["access_token"], ws),
    )
    assert deleted_admin.status_code == 403


def test_delete_role_in_use_blocked(client, register_user, db) -> None:
    owner = register_user(email="rbac-inuse@example.com")
    other = register_user(email="rbac-inuse-m@example.com")
    ws = _create_workspace(client, owner, "rbac-inuse")
    role = _create_custom_role(
        client, owner, ws, "Temp Role", [WorkspacePermission.WORKSPACE_VIEW.value]
    )
    membership = WorkspaceMembership(
        workspace_id=uuid.UUID(ws["id"]),
        user_id=uuid.UUID(other["user"]["id"]),
        role_id=uuid.UUID(role["id"]),
    )
    db.add(membership)
    db.commit()
    res = client.delete(
        f"/api/workspaces/{ws['id']}/roles/{role['id']}",
        headers=_auth(owner["access_token"], ws),
    )
    assert res.status_code == 409
    assert res.json()["code"] == "role_in_use"


def test_cross_workspace_role_ids_fail_closed(client, register_user) -> None:
    owner_a = register_user(email="rbac-iso-a@example.com")
    owner_b = register_user(email="rbac-iso-b@example.com")
    invitee = register_user(email="rbac-iso-inv@example.com")
    ws_a = _create_workspace(client, owner_a, "rbac-iso-a")
    ws_b = _create_workspace(client, owner_b, "rbac-iso-b")
    role_a = _create_custom_role(
        client, owner_a, ws_a, "Agent A", [WorkspacePermission.CHAT_USE.value]
    )

    invite = client.post(
        f"/api/workspaces/{ws_b['id']}/invitations",
        headers=_auth(owner_b["access_token"], ws_b),
        json={"email": "rbac-iso-inv@example.com", "role_id": role_a["id"]},
    )
    assert invite.status_code == 404
    assert invite.json()["code"] == "role_not_found"

    assign = client.patch(
        f"/api/workspaces/{ws_b['id']}/members/{owner_b['user']['id']}",
        headers=_auth(owner_b["access_token"], ws_b),
        json={"role_id": role_a["id"]},
    )
    assert assign.status_code in {403, 404}

    get_foreign = client.get(
        f"/api/workspaces/{ws_b['id']}/roles/{role_a['id']}",
        headers=_auth(owner_b["access_token"], ws_b),
    )
    assert get_foreign.status_code == 404
    _ = invitee


def test_custom_role_least_privilege_experts_only(client, register_user, db) -> None:
    owner = register_user(email="rbac-lp-own@example.com")
    agent = register_user(email="rbac-lp-ag@example.com")
    ws = _create_workspace(client, owner, "rbac-lp")
    role = _create_custom_role(
        client,
        owner,
        ws,
        "Expert Viewer",
        [
            WorkspacePermission.WORKSPACE_VIEW.value,
            WorkspacePermission.EXPERTS_VIEW.value,
        ],
    )
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws["id"]),
            user_id=uuid.UUID(agent["user"]["id"]),
            role_id=uuid.UUID(role["id"]),
        )
    )
    db.commit()

    headers = _auth(agent["access_token"], ws)
    listed = client.get("/api/experts", headers=headers)
    assert listed.status_code == 200, listed.text

    created = client.post("/api/experts", headers=headers, json={"name": "Nope"})
    assert created.status_code == 403

    billing = client.get("/api/subscription", headers=headers)
    assert billing.status_code == 403

    members = client.get(f"/api/workspaces/{ws['id']}/members", headers=headers)
    assert members.status_code == 403

    apps = client.get("/api/apps", headers=headers)
    assert apps.status_code == 403


def test_role_permission_update_affects_authorization_immediately(
    client, register_user, db
) -> None:
    owner = register_user(email="rbac-live-own@example.com")
    agent = register_user(email="rbac-live-ag@example.com")
    ws = _create_workspace(client, owner, "rbac-live")
    role = _create_custom_role(
        client,
        owner,
        ws,
        "Live Role",
        [WorkspacePermission.WORKSPACE_VIEW.value],
    )
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws["id"]),
            user_id=uuid.UUID(agent["user"]["id"]),
            role_id=uuid.UUID(role["id"]),
        )
    )
    db.commit()
    headers = _auth(agent["access_token"], ws)
    denied = client.get("/api/subscription", headers=headers)
    assert denied.status_code == 403

    patched = client.patch(
        f"/api/workspaces/{ws['id']}/roles/{role['id']}",
        headers=_auth(owner["access_token"], ws),
        json={
            "permissions": [
                WorkspacePermission.WORKSPACE_VIEW.value,
                WorkspacePermission.BILLING_VIEW.value,
            ]
        },
    )
    assert patched.status_code == 200, patched.text
    allowed = client.get("/api/subscription", headers=headers)
    assert allowed.status_code == 200, allowed.text


def test_role_description_can_be_cleared(client, register_user) -> None:
    owner = register_user(email="rbac-desc-own@example.com")
    ws = _create_workspace(client, owner, "rbac-desc")
    role = _create_custom_role(
        client,
        owner,
        ws,
        "Described",
        [WorkspacePermission.WORKSPACE_VIEW.value],
    )
    assert role["description"] == "custom"
    cleared = client.patch(
        f"/api/workspaces/{ws['id']}/roles/{role['id']}",
        headers=_auth(owner["access_token"], ws),
        json={"description": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["description"] is None
    kept = client.patch(
        f"/api/workspaces/{ws['id']}/roles/{role['id']}",
        headers=_auth(owner["access_token"], ws),
        json={"name": "Described still"},
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["description"] is None
    assert kept.json()["name"] == "Described still"


def test_invite_custom_role_and_reject_owner_role(client, register_user, inbox, db) -> None:
    from tests.support.fake_email import token_from_invite_email

    owner = register_user(email="rbac-inv-own@example.com")
    invitee = register_user(email="rbac-inv-ag@example.com")
    ws = _create_workspace(client, owner, "rbac-inv")
    role = _create_custom_role(
        client,
        owner,
        ws,
        "Support Agent",
        [WorkspacePermission.CHAT_USE.value, WorkspacePermission.WORKSPACE_VIEW.value],
    )
    created = client.post(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"], ws),
        json={"email": "rbac-inv-ag@example.com", "role_id": role["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"]["id"] == role["id"]
    assert created.json()["role"]["is_owner_role"] is False
    assert "Support Agent" in inbox.messages[0].text_body

    token = token_from_invite_email(inbox.messages[0])
    accepted = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": token},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"]["id"] == role["id"]
    membership = get_membership(db, ws["id"], invitee["user"]["id"])
    assert str(membership.role_id) == role["id"]

    owner_invite = client.post(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"], ws),
        json={
            "email": "never-owner@example.com",
            "role_id": str(role_id(db, ws["id"], "owner")),
        },
    )
    assert owner_invite.status_code == 403
    assert owner_invite.json()["code"] == "role_protected"


def test_assignable_roles_exclude_owner(client, register_user) -> None:
    owner = register_user(email="rbac-asg@example.com")
    ws = _create_workspace(client, owner, "rbac-asg")
    res = client.get(
        f"/api/workspaces/{ws['id']}/roles/assignable",
        headers=_auth(owner["access_token"], ws),
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert all(not r["is_owner_role"] for r in items)
    keys = {r["system_key"] for r in items}
    assert "owner" not in keys
    assert "admin" in keys
    assert "member" in keys


def test_last_owner_protections_unchanged(client, register_user, db) -> None:
    owner = register_user(email="rbac-last@example.com")
    ws = _create_workspace(client, owner, "rbac-last")
    uid = owner["user"]["id"]
    demote = client.patch(
        f"/api/workspaces/{ws['id']}/members/{uid}",
        headers=_auth(owner["access_token"], ws),
        json={"role_id": str(role_id(db, ws["id"], "admin"))},
    )
    assert demote.status_code == 409
    assert demote.json()["code"] == "last_workspace_owner"


def test_member_cannot_manage_roles(client, register_user, db) -> None:
    owner = register_user(email="rbac-mem-own@example.com")
    member = register_user(email="rbac-mem@example.com")
    ws = _create_workspace(client, owner, "rbac-mem-roles")
    add_workspace_member(db, ws["id"], member["user"]["id"], "member")
    listed = client.get(
        f"/api/workspaces/{ws['id']}/roles",
        headers=_auth(member["access_token"], ws),
    )
    assert listed.status_code == 403
    created = client.post(
        f"/api/workspaces/{ws['id']}/roles",
        headers=_auth(member["access_token"], ws),
        json={"name": "Nope", "permissions": [WorkspacePermission.CHAT_USE.value]},
    )
    assert created.status_code == 403
