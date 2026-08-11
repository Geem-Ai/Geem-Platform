from __future__ import annotations

import uuid

from app.workspaces.models import WorkspaceMembership, WorkspaceRole
from app.workspaces.service import WorkspaceService


def _auth(headers_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {headers_token}"}


def test_create_workspace_normalized_slug_and_owner(client, register_user) -> None:
    user = register_user(email="owner@example.com")
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": "Acme Co", "slug": "Acme-Co"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["slug"] == "acme-co"
    assert body["role"] == "owner"


def test_duplicate_and_reserved_slug(client, register_user) -> None:
    user = register_user(email="slug@example.com")
    headers = _auth(user["access_token"])
    assert (
        client.post("/api/workspaces", headers=headers, json={"name": "A", "slug": "alpha"})
        .status_code
        == 201
    )
    dup = client.post("/api/workspaces", headers=headers, json={"name": "B", "slug": "ALPHA"})
    assert dup.status_code == 409
    assert dup.json()["code"] == "workspace_slug_taken"

    reserved = client.post(
        "/api/workspaces", headers=headers, json={"name": "Admin", "slug": "admin"}
    )
    assert reserved.status_code == 422
    assert reserved.json()["code"] == "workspace_slug_invalid"


def test_create_workspace_owner_membership_atomic(db, register_user) -> None:
    user = register_user(email="tx@example.com")
    svc = WorkspaceService(db)
    workspace, membership = svc.create_workspace(
        name="TX",
        slug="tx-ok",
        created_by=uuid.UUID(user["user"]["id"]),
    )
    assert membership.role == WorkspaceRole.OWNER.value
    assert membership.workspace_id == workspace.id
    before = len(svc.list_for_user(uuid.UUID(user["user"]["id"])))
    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=uuid.UUID(user["user"]["id"]),
            role=WorkspaceRole.MEMBER.value,
        )
    )
    try:
        db.commit()
        assert False, "expected unique violation"
    except Exception:
        db.rollback()
    after = len(WorkspaceService(db).list_for_user(uuid.UUID(user["user"]["id"])))
    assert before == after == 1


def test_user_multi_workspace_membership(client, register_user) -> None:
    user = register_user(email="multi@example.com")
    headers = _auth(user["access_token"])
    a = client.post("/api/workspaces", headers=headers, json={"name": "A", "slug": "ws-a"})
    b = client.post("/api/workspaces", headers=headers, json={"name": "B", "slug": "ws-b"})
    assert a.status_code == 201 and b.status_code == 201
    listed = client.get("/api/workspaces", headers=headers)
    assert listed.status_code == 200
    slugs = {w["slug"] for w in listed.json()}
    assert {"ws-a", "ws-b"} <= slugs


def test_member_cannot_update_workspace(client, register_user, db) -> None:
    owner = register_user(email="own@example.com")
    member = register_user(email="mem@example.com")
    create = client.post(
        "/api/workspaces",
        headers=_auth(owner["access_token"]),
        json={"name": "Roles", "slug": "roles-ws"},
    )
    ws_id = create.json()["id"]

    from app.workspaces.repository import MembershipRepository

    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws_id),
            user_id=uuid.UUID(member["user"]["id"]),
            role=WorkspaceRole.MEMBER.value,
        )
    )
    db.commit()

    denied = client.patch(
        f"/api/workspaces/{ws_id}",
        headers=_auth(member["access_token"]),
        json={"name": "Hacked"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "insufficient_workspace_role"

    allowed = client.patch(
        f"/api/workspaces/{ws_id}",
        headers=_auth(owner["access_token"]),
        json={"name": "Roles Updated"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["name"] == "Roles Updated"


def test_last_owner_cannot_demote_or_remove_self(client, register_user) -> None:
    owner = register_user(email="solo-owner@example.com")
    create = client.post(
        "/api/workspaces",
        headers=_auth(owner["access_token"]),
        json={"name": "Solo", "slug": "solo-ws"},
    )
    ws_id = create.json()["id"]
    uid = owner["user"]["id"]

    demote = client.patch(
        f"/api/workspaces/{ws_id}/members/{uid}",
        headers=_auth(owner["access_token"]),
        json={"role": "admin"},
    )
    assert demote.status_code == 409
    assert demote.json()["code"] == "last_workspace_owner"

    remove = client.delete(
        f"/api/workspaces/{ws_id}/members/{uid}",
        headers=_auth(owner["access_token"]),
    )
    assert remove.status_code == 409
    assert remove.json()["code"] == "last_workspace_owner"


def test_admin_cannot_promote_to_owner(client, register_user, db) -> None:
    owner = register_user(email="o2@example.com")
    admin = register_user(email="a2@example.com")
    create = client.post(
        "/api/workspaces",
        headers=_auth(owner["access_token"]),
        json={"name": "Promote", "slug": "promote-ws"},
    )
    ws_id = create.json()["id"]
    from app.workspaces.repository import MembershipRepository

    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws_id),
            user_id=uuid.UUID(admin["user"]["id"]),
            role=WorkspaceRole.ADMIN.value,
        )
    )
    db.commit()

    res = client.patch(
        f"/api/workspaces/{ws_id}/members/{admin['user']['id']}",
        headers=_auth(admin["access_token"]),
        json={"role": "owner"},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "insufficient_workspace_role"
