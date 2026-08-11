from __future__ import annotations


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_cross_workspace_isolation(client, register_user) -> None:
    """User A / Workspace A must not access User B / Workspace B resources."""
    user_a = register_user(email="user-a@example.com")
    user_b = register_user(email="user-b@example.com")

    ws_a = client.post(
        "/api/workspaces",
        headers=_auth(user_a["access_token"]),
        json={"name": "Workspace A", "slug": "workspace-a"},
    ).json()
    ws_b = client.post(
        "/api/workspaces",
        headers=_auth(user_b["access_token"]),
        json={"name": "Workspace B", "slug": "workspace-b"},
    ).json()

    assert (
        client.get(f"/api/workspaces/{ws_a['id']}", headers=_auth(user_a["access_token"])).status_code
        == 200
    )
    denied_detail = client.get(
        f"/api/workspaces/{ws_b['id']}", headers=_auth(user_a["access_token"])
    )
    assert denied_detail.status_code == 403
    assert denied_detail.json()["code"] == "workspace_access_denied"

    denied_b = client.get(
        f"/api/workspaces/{ws_a['id']}", headers=_auth(user_b["access_token"])
    )
    assert denied_b.status_code == 403

    assert (
        client.get(
            f"/api/workspaces/{ws_a['id']}/members",
            headers=_auth(user_a["access_token"]),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/workspaces/{ws_b['id']}/members",
            headers=_auth(user_a["access_token"]),
        ).status_code
        == 403
    )

    assert (
        client.patch(
            f"/api/workspaces/{ws_b['id']}",
            headers=_auth(user_a["access_token"]),
            json={"name": "Hijacked"},
        ).status_code
        == 403
    )

    me = client.get(
        "/api/auth/me",
        headers={
            **_auth(user_a["access_token"]),
            "X-Workspace-Slug": "workspace-b",
        },
    )
    assert me.status_code == 200
    assert me.json()["current_workspace"] is None

    current = client.get(
        "/api/workspaces/current",
        headers={
            **_auth(user_a["access_token"]),
            "X-Workspace-Slug": "workspace-b",
        },
    )
    assert current.status_code == 403

    ok_current = client.get(
        "/api/workspaces/current",
        headers={
            **_auth(user_a["access_token"]),
            "X-Workspace-Slug": "workspace-a",
        },
    )
    assert ok_current.status_code == 200
    assert ok_current.json()["slug"] == "workspace-a"
