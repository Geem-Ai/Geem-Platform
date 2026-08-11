from __future__ import annotations

import uuid

from app.workspaces.models import WorkspaceMembership, WorkspaceRole
from app.workspaces.repository import MembershipRepository


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def test_forged_workspace_id_and_host_denied(client, register_user) -> None:
    user_a = register_user(email="iso-a@example.com")
    user_b = register_user(email="iso-b@example.com")
    ws_a = client.post(
        "/api/workspaces",
        headers=_auth(user_a["access_token"]),
        json={"name": "A", "slug": "iso-a"},
    ).json()
    ws_b = client.post(
        "/api/workspaces",
        headers=_auth(user_b["access_token"]),
        json={"name": "B", "slug": "iso-b"},
    ).json()

    # Forged X-Workspace-Id
    forged = client.get(
        "/api/workspaces/current",
        headers=_auth(user_a["access_token"], **{"X-Workspace-Id": ws_b["id"]}),
    )
    assert forged.status_code == 403
    assert forged.json()["code"] == "workspace_access_denied"

    # Host for B while authenticated as A
    host = client.get(
        "/api/workspaces/current",
        headers={
            **_auth(user_a["access_token"]),
            "Host": "iso-b.localhost",
        },
    )
    assert host.status_code == 403

    # Direct member URL
    assert (
        client.get(
            f"/api/workspaces/{ws_b['id']}/members",
            headers=_auth(user_a["access_token"]),
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/workspaces/{ws_b['id']}/members/{user_b['user']['id']}",
            headers=_auth(user_a["access_token"]),
            json={"role": "member"},
        ).status_code
        == 403
    )

    # Sanity: own workspace still works
    assert (
        client.get(
            f"/api/workspaces/{ws_a['id']}",
            headers=_auth(user_a["access_token"]),
        ).status_code
        == 200
    )


def test_multi_workspace_membership_roles(client, register_user, db) -> None:
    owner = register_user(email="multi-owner@example.com")
    member = register_user(email="multi-member@example.com")

    ws_a = client.post(
        "/api/workspaces",
        headers=_auth(owner["access_token"]),
        json={"name": "Owned", "slug": "owned-ws"},
    ).json()
    ws_b = client.post(
        "/api/workspaces",
        headers=_auth(member["access_token"]),
        json={"name": "Other", "slug": "other-ws"},
    ).json()

    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws_b["id"]),
            user_id=uuid.UUID(owner["user"]["id"]),
            role=WorkspaceRole.MEMBER.value,
        )
    )
    db.commit()

    listed = client.get("/api/workspaces", headers=_auth(owner["access_token"]))
    assert listed.status_code == 200
    by_slug = {w["slug"]: w for w in listed.json()}
    assert by_slug["owned-ws"]["role"] == "owner"
    assert by_slug["other-ws"]["role"] == "member"

    # Owner privileges in A
    assert (
        client.patch(
            f"/api/workspaces/{ws_a['id']}",
            headers=_auth(owner["access_token"]),
            json={"name": "Owned Updated"},
        ).status_code
        == 200
    )
    # Member privileges only in B — cannot update
    denied = client.patch(
        f"/api/workspaces/{ws_b['id']}",
        headers=_auth(owner["access_token"]),
        json={"name": "Hijack"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "insufficient_workspace_role"


def test_two_owners_can_demote_one(client, register_user, db) -> None:
    o1 = register_user(email="o1@example.com")
    o2 = register_user(email="o2@example.com")
    ws = client.post(
        "/api/workspaces",
        headers=_auth(o1["access_token"]),
        json={"name": "Duo", "slug": "duo-ws"},
    ).json()
    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws["id"]),
            user_id=uuid.UUID(o2["user"]["id"]),
            role=WorkspaceRole.OWNER.value,
        )
    )
    db.commit()

    demote = client.patch(
        f"/api/workspaces/{ws['id']}/members/{o2['user']['id']}",
        headers=_auth(o1["access_token"]),
        json={"role": "admin"},
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "admin"


def test_admin_cannot_remove_owner(client, register_user, db) -> None:
    owner = register_user(email="own3@example.com")
    admin = register_user(email="adm3@example.com")
    ws = client.post(
        "/api/workspaces",
        headers=_auth(owner["access_token"]),
        json={"name": "Prot", "slug": "prot-ws"},
    ).json()
    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws["id"]),
            user_id=uuid.UUID(admin["user"]["id"]),
            role=WorkspaceRole.ADMIN.value,
        )
    )
    db.commit()

    res = client.delete(
        f"/api/workspaces/{ws['id']}/members/{owner['user']['id']}",
        headers=_auth(admin["access_token"]),
    )
    assert res.status_code == 403


def test_prod_ignores_x_workspace_slug(monkeypatch) -> None:
    from app.common.workspace_resolver import resolve_workspace_hint
    from app.core.config import get_settings
    from starlette.requests import Request

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.geem.ai")
    get_settings.cache_clear()
    try:
        req = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-workspace-slug", b"other-prod-slug")],
            }
        )
        hint = resolve_workspace_hint(req, get_settings())
        assert hint.slug is None
        assert hint.source == "none"
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()


def test_slug_adversarial_rejected(client, register_user) -> None:
    user = register_user(email="slugadv@example.com")
    headers = _auth(user["access_token"])
    cases = [
        ("api", 422),
        ("admin", 422),
        ("www", 422),
        ("-acme", 422),
        ("acme-", 422),
        ("acme_test", 422),
        ("acme.test", 422),
    ]
    for slug, code in cases:
        res = client.post(
            "/api/workspaces",
            headers=headers,
            json={"name": "N", "slug": slug},
        )
        assert res.status_code == code, slug
