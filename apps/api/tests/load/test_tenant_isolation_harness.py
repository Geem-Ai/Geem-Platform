"""Phase 11D — concurrent tenant isolation harness.

Run explicitly: pytest -m isolation
These tests stay in the default suite because they are HTTP-sized, not million-row.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from tests.support.rbac import add_workspace_member


def _auth(token: str, workspace: dict | None = None, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace is not None:
        headers["X-Workspace-Id"] = workspace["id"]
    headers.update(extra)
    return headers


def _workspace(client, user, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


@pytest.mark.isolation
def test_cross_tenant_identifiers_fail_closed(client, register_user, db) -> None:
    user_a = register_user(email="iso-a@example.com")
    user_b = register_user(email="iso-b@example.com")
    ws_a = _workspace(client, user_a, "iso-harness-a")
    ws_b = _workspace(client, user_b, "iso-harness-b")
    ha = _auth(user_a["access_token"], ws_a)
    hb = _auth(user_b["access_token"], ws_b)

    expert_b = client.post("/api/experts", headers=hb, json={"name": "B Expert"})
    assert expert_b.status_code == 201, expert_b.text
    conv_b = client.post(
        "/api/conversations",
        headers=hb,
        json={"expert_id": expert_b.json()["id"]},
    )
    assert conv_b.status_code == 201, conv_b.text
    key_b = client.post("/api/api-keys", headers=hb, json={"name": "b-bot"})
    assert key_b.status_code in {200, 201}, key_b.text

    denied = [
        client.get(f"/api/experts/{expert_b.json()['id']}", headers=ha),
        client.get(f"/api/conversations/{conv_b.json()['id']}", headers=ha),
        client.get(f"/api/conversations/{conv_b.json()['id']}/messages", headers=ha),
        client.get("/api/api-keys", headers=_auth(user_a["access_token"], ws_b)),
        client.post(
            f"/api/api-keys/{key_b.json()['id']}/revoke",
            headers=ha,
        ),
        client.get("/api/apps", headers=_auth(user_a["access_token"], ws_b)),
        client.get("/api/workspaces/current", headers=_auth(user_a["access_token"], ws_b)),
    ]
    for res in denied:
        assert res.status_code in {401, 403, 404}, res.text

    ok_history = client.get("/api/usage/history", headers=ha)
    assert ok_history.status_code == 200, ok_history.text

    def _hit() -> int:
        return client.get(f"/api/experts/{expert_b.json()['id']}", headers=ha).status_code

    codes: list[int] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_hit) for _ in range(16)]
        for fut in as_completed(futs):
            codes.append(fut.result())
    assert codes
    assert all(code in {401, 403, 404} for code in codes)


@pytest.mark.isolation
def test_same_user_two_workspaces_rbac_does_not_leak(client, register_user, db) -> None:
    owner_a = register_user(email="iso-rbac-a@example.com")
    owner_b = register_user(email="iso-rbac-b@example.com")
    member = register_user(email="iso-rbac-m@example.com")
    ws_a = _workspace(client, owner_a, "iso-rbac-a")
    ws_b = _workspace(client, owner_b, "iso-rbac-b")

    role_a = client.post(
        f"/api/workspaces/{ws_a['id']}/roles",
        headers=_auth(owner_a["access_token"], ws_a),
        json={
            "name": "Chat only A",
            "description": "a",
            "permissions": ["workspace.view", "chat.use", "experts.view", "experts.use"],
        },
    )
    assert role_a.status_code == 201, role_a.text
    role_b = client.post(
        f"/api/workspaces/{ws_b['id']}/roles",
        headers=_auth(owner_b["access_token"], ws_b),
        json={
            "name": "Members only B",
            "description": "b",
            "permissions": ["workspace.view", "members.view"],
        },
    )
    assert role_b.status_code == 201, role_b.text

    add_workspace_member(db, ws_a["id"], member["user"]["id"], "member")
    add_workspace_member(db, ws_b["id"], member["user"]["id"], "member")
    # Re-assign custom roles
    mem_a = client.patch(
        f"/api/workspaces/{ws_a['id']}/members/{member['user']['id']}",
        headers=_auth(owner_a["access_token"], ws_a),
        json={"role_id": role_a.json()["id"]},
    )
    mem_b = client.patch(
        f"/api/workspaces/{ws_b['id']}/members/{member['user']['id']}",
        headers=_auth(owner_b["access_token"], ws_b),
        json={"role_id": role_b.json()["id"]},
    )
    assert mem_a.status_code in {200, 204}, mem_a.text
    assert mem_b.status_code in {200, 204}, mem_b.text

    experts_a = client.post(
        "/api/experts",
        headers=_auth(member["access_token"], ws_a),
        json={"name": "Should fail create"},
    )
    experts_b = client.get("/api/experts", headers=_auth(member["access_token"], ws_b))
    members_a = client.get(
        f"/api/workspaces/{ws_a['id']}/members",
        headers=_auth(member["access_token"], ws_a),
    )
    members_b = client.get(
        f"/api/workspaces/{ws_b['id']}/members",
        headers=_auth(member["access_token"], ws_b),
    )
    assert experts_a.status_code in {401, 403}
    assert experts_b.status_code in {401, 403}
    assert members_a.status_code in {401, 403}
    assert members_b.status_code == 200, members_b.text

    barrier = threading.Barrier(2, timeout=10)
    results: dict[str, int] = {}

    def _chat_ws() -> None:
        barrier.wait()
        results["a"] = client.get(
            "/api/experts", headers=_auth(member["access_token"], ws_a)
        ).status_code

    def _members_ws() -> None:
        barrier.wait()
        results["b"] = client.get(
            f"/api/workspaces/{ws_b['id']}/members",
            headers=_auth(member["access_token"], ws_b),
        ).status_code

    t1 = threading.Thread(target=_chat_ws)
    t2 = threading.Thread(target=_members_ws)
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)
    assert results.get("a") == 200
    assert results.get("b") == 200


@pytest.mark.isolation
def test_api_key_cannot_target_foreign_expert(client, register_user, db) -> None:
    user_a = register_user(email="iso-key-a@example.com")
    user_b = register_user(email="iso-key-b@example.com")
    ws_a = _workspace(client, user_a, "iso-key-a")
    ws_b = _workspace(client, user_b, "iso-key-b")
    expert_b = client.post(
        "/api/experts",
        headers=_auth(user_b["access_token"], ws_b),
        json={"name": "B only"},
    )
    assert expert_b.status_code == 201
    key_a = client.post(
        "/api/api-keys",
        headers=_auth(user_a["access_token"], ws_a),
        json={"name": "a-bot"},
    )
    assert key_a.status_code in {200, 201}, key_a.text
    secret = key_a.json()["key"]
    res = client.post(
        "/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {secret}",
            "X-Geem-Expert-Id": expert_b.json()["id"],
        },
        json={
            "model": "geem",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code in {401, 403, 404}, res.text
    assert secret not in res.text
    revoked = client.post(
        f"/api/api-keys/{key_a.json()['id']}/revoke",
        headers=_auth(user_a["access_token"], ws_a),
    )
    assert revoked.status_code in {200, 204}, revoked.text
    again = client.post(
        "/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {secret}",
            "X-Geem-Expert-Id": expert_b.json()["id"],
        },
        json={"model": "geem", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert again.status_code in {401, 403}
