from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from fastapi.testclient import TestClient

from app.api_keys.dependencies import get_api_key_principal, require_api_scope
from app.api_keys.models import ApiKey
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.scopes import SCOPE_CHAT_WRITE
from app.common.request_context import get_request_context
from app.main import app
from app.workspaces.models import WorkspaceMembership, WorkspaceRole, WorkspaceStatus

_PROBE_MOUNTED = False


def _mount_probes() -> None:
    global _PROBE_MOUNTED
    if _PROBE_MOUNTED:
        return

    @app.get("/__test__/api-key/principal", include_in_schema=False)
    def _principal(
        request: Request,
        principal: ApiKeyPrincipal = Depends(get_api_key_principal),
    ) -> dict:
        ctx = getattr(request.state, "request_context", None) or get_request_context()
        return {
            "api_key_id": str(principal.api_key_id),
            "workspace_id": str(principal.workspace_id),
            "scopes": list(principal.scopes),
            "user_id": str(ctx.user_id) if getattr(ctx, "user_id", None) else None,
            "ctx_workspace_id": str(ctx.workspace_id) if getattr(ctx, "workspace_id", None) else None,
            "workspace_resolution": getattr(ctx, "workspace_resolution", None),
            "api_key_id_ctx": str(ctx.api_key_id) if getattr(ctx, "api_key_id", None) else None,
        }

    @app.get("/__test__/api-key/chat", include_in_schema=False)
    def _chat(principal: ApiKeyPrincipal = Depends(require_api_scope("chat:write"))) -> dict:
        return {"ok": True, "workspace_id": str(principal.workspace_id)}

    @app.get("/__test__/api-key/missing-scope", include_in_schema=False)
    def _missing(
        principal: ApiKeyPrincipal = Depends(require_api_scope("admin:write")),
    ) -> dict:
        return {"ok": True, "workspace_id": str(principal.workspace_id)}

    _PROBE_MOUNTED = True


_mount_probes()


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _create_workspace(client: TestClient, user: dict, slug: str, name: str = "Keys") -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_member(db, workspace_id: str, user_id: str, role=WorkspaceRole.MEMBER) -> None:
    from tests.support.rbac import add_workspace_member
    key = role.value if hasattr(role, "value") else role
    add_workspace_member(db, workspace_id, user_id, key)



def test_owner_creates_key_plaintext_once_and_hash_stored(client, register_user, db) -> None:
    owner = register_user(email="keys-owner@example.com")
    ws = _create_workspace(client, owner, "keys-owner-ws")
    headers = _ws_headers(owner, ws)

    created = client.post(
        "/api/api-keys",
        headers=headers,
        json={"name": "Production"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Production"
    assert body["key"].startswith("geem_sk_")
    assert body["prefix"].startswith("geem_sk_")
    assert body["scopes"] == [SCOPE_CHAT_WRITE]
    assert "secret_hash" not in body
    plaintext = body["key"]

    row = db.get(ApiKey, uuid.UUID(body["id"]))
    assert row is not None
    assert row.secret_hash != plaintext
    assert plaintext not in row.secret_hash
    assert len(row.secret_hash) == 64
    assert row.key_prefix == body["prefix"]
    assert row.last_four == plaintext[-4:]

    listed = client.get("/api/api-keys", headers=headers)
    assert listed.status_code == 200, listed.text
    items = listed.json()
    assert len(items) == 1
    assert "key" not in items[0]
    assert "secret_hash" not in items[0]
    assert plaintext not in listed.text
    assert row.secret_hash not in listed.text
    assert items[0]["prefix"] == body["prefix"]


def test_admin_can_create_list_revoke_member_cannot(client, register_user, db) -> None:
    owner = register_user(email="keys-own2@example.com")
    admin = register_user(email="keys-adm@example.com")
    member = register_user(email="keys-mem@example.com")
    ws = _create_workspace(client, owner, "keys-roles-ws")
    _add_member(db, ws["id"], admin["user"]["id"], WorkspaceRole.ADMIN)
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)

    created = client.post(
        "/api/api-keys",
        headers=_ws_headers(admin, ws),
        json={"name": "Admin Key", "scopes": ["chat:write"]},
    )
    assert created.status_code == 201, created.text
    key_id = created.json()["id"]
    plaintext = created.json()["key"]

    listed = client.get("/api/api-keys", headers=_ws_headers(admin, ws))
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    denied_create = client.post(
        "/api/api-keys",
        headers=_ws_headers(member, ws),
        json={"name": "Nope"},
    )
    assert denied_create.status_code == 403
    assert denied_create.json()["code"] == "insufficient_workspace_role"

    denied_list = client.get("/api/api-keys", headers=_ws_headers(member, ws))
    assert denied_list.status_code == 403

    denied_revoke = client.post(
        f"/api/api-keys/{key_id}/revoke",
        headers=_ws_headers(member, ws),
    )
    assert denied_revoke.status_code == 403

    revoked = client.post(
        f"/api/api-keys/{key_id}/revoke",
        headers=_ws_headers(admin, ws),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_at"] is not None
    assert "key" not in revoked.json()
    assert plaintext not in revoked.text


def test_unknown_scope_rejected(client, register_user) -> None:
    owner = register_user(email="keys-scope@example.com")
    ws = _create_workspace(client, owner, "keys-scope-ws")
    res = client.post(
        "/api/api-keys",
        headers=_ws_headers(owner, ws),
        json={"name": "Bad", "scopes": ["chat:write", "admin:destroy"]},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "validation"


def test_duplicate_scopes_normalized(client, register_user) -> None:
    owner = register_user(email="keys-dup@example.com")
    ws = _create_workspace(client, owner, "keys-dup-ws")
    res = client.post(
        "/api/api-keys",
        headers=_ws_headers(owner, ws),
        json={"name": "Dup", "scopes": ["chat:write", "chat:write"]},
    )
    assert res.status_code == 201, res.text
    assert res.json()["scopes"] == [SCOPE_CHAT_WRITE]


def test_past_expires_at_rejected(client, register_user) -> None:
    owner = register_user(email="keys-exp@example.com")
    ws = _create_workspace(client, owner, "keys-exp-ws")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    res = client.post(
        "/api/api-keys",
        headers=_ws_headers(owner, ws),
        json={"name": "Old", "expires_at": past},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "validation"


def test_authenticate_valid_and_header_failures(client, register_user) -> None:
    owner = register_user(email="keys-auth@example.com")
    ws = _create_workspace(client, owner, "keys-auth-ws")
    created = client.post(
        "/api/api-keys",
        headers=_ws_headers(owner, ws),
        json={"name": "Auth"},
    )
    plaintext = created.json()["key"]
    key_id = created.json()["id"]

    ok = client.get("/__test__/api-key/principal", headers=_auth(plaintext))
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["api_key_id"] == key_id
    assert body["workspace_id"] == ws["id"]
    assert body["ctx_workspace_id"] == ws["id"]
    assert body["workspace_resolution"] == "api_key"
    assert body["user_id"] is None
    assert body["scopes"] == [SCOPE_CHAT_WRITE]

    listed = client.get("/api/api-keys", headers=_ws_headers(owner, ws))
    assert listed.status_code == 200, listed.text
    match = next(item for item in listed.json() if item["id"] == key_id)
    assert match["last_used_at"] is not None

    chat = client.get("/__test__/api-key/chat", headers=_auth(plaintext))
    assert chat.status_code == 200

    missing_scope = client.get("/__test__/api-key/missing-scope", headers=_auth(plaintext))
    assert missing_scope.status_code == 403
    assert missing_scope.json()["code"] == "forbidden"

    missing = client.get("/__test__/api-key/principal")
    assert missing.status_code == 401
    assert missing.json()["code"] == "unauthorized"

    malformed = client.get(
        "/__test__/api-key/principal",
        headers={"Authorization": "Basic abc"},
    )
    assert malformed.status_code == 401

    empty_bearer = client.get(
        "/__test__/api-key/principal",
        headers={"Authorization": "Bearer"},
    )
    assert empty_bearer.status_code == 401

    invalid = client.get("/__test__/api-key/principal", headers=_auth("geem_sk_not-a-real-key"))
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "unauthorized"
    assert "geem_sk_not-a-real-key" not in invalid.text


def test_revoked_and_expired_and_inactive_workspace(client, register_user, db) -> None:
    owner = register_user(email="keys-life@example.com")
    ws = _create_workspace(client, owner, "keys-life-ws")
    headers = _ws_headers(owner, ws)
    created = client.post("/api/api-keys", headers=headers, json={"name": "Live"})
    plaintext = created.json()["key"]
    key_id = created.json()["id"]

    assert client.get("/__test__/api-key/chat", headers=_auth(plaintext)).status_code == 200

    revoked = client.post(f"/api/api-keys/{key_id}/revoke", headers=headers)
    assert revoked.status_code == 200
    first_revoked_at = revoked.json()["revoked_at"]
    again = client.post(f"/api/api-keys/{key_id}/revoke", headers=headers)
    assert again.status_code == 200
    assert again.json()["revoked_at"] == first_revoked_at
    assert client.get("/__test__/api-key/chat", headers=_auth(plaintext)).status_code == 401

    created2 = client.post("/api/api-keys", headers=headers, json={"name": "Expiring"})
    plaintext2 = created2.json()["key"]
    row = db.get(ApiKey, uuid.UUID(created2.json()["id"]))
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get("/__test__/api-key/chat", headers=_auth(plaintext2)).status_code == 401

    created3 = client.post("/api/api-keys", headers=headers, json={"name": "Suspended"})
    plaintext3 = created3.json()["key"]
    from app.workspaces.models import Workspace

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    workspace.status = WorkspaceStatus.SUSPENDED.value
    db.commit()
    inactive = client.get("/__test__/api-key/principal", headers=_auth(plaintext3))
    assert inactive.status_code == 403
    assert inactive.json()["code"] == "workspace_access_denied"


def test_tenant_isolation_and_header_cannot_override(client, register_user) -> None:
    user_a = register_user(email="keys-a@example.com")
    user_b = register_user(email="keys-b@example.com")
    ws_a = _create_workspace(client, user_a, "keys-iso-a", name="A")
    ws_b = _create_workspace(client, user_b, "keys-iso-b", name="B")

    key_a = client.post(
        "/api/api-keys",
        headers=_ws_headers(user_a, ws_a),
        json={"name": "A Key"},
    ).json()
    key_b = client.post(
        "/api/api-keys",
        headers=_ws_headers(user_b, ws_b),
        json={"name": "B Key"},
    ).json()

    listed_a = client.get("/api/api-keys", headers=_ws_headers(user_a, ws_a))
    listed_b = client.get("/api/api-keys", headers=_ws_headers(user_b, ws_b))
    ids_a = {item["id"] for item in listed_a.json()}
    ids_b = {item["id"] for item in listed_b.json()}
    assert key_a["id"] in ids_a and key_b["id"] not in ids_a
    assert key_b["id"] in ids_b and key_a["id"] not in ids_b
    assert key_a["key"] not in listed_a.text
    assert key_b["key"] not in listed_b.text

    cross_list = client.get("/api/api-keys", headers=_ws_headers(user_a, ws_b))
    assert cross_list.status_code == 403

    cross_revoke = client.post(
        f"/api/api-keys/{key_b['id']}/revoke",
        headers=_ws_headers(user_a, ws_a),
    )
    assert cross_revoke.status_code == 404
    assert cross_revoke.json()["code"] == "api_key_not_found"

    # API key A with Workspace B headers / host still resolves A.
    forged = client.get(
        "/__test__/api-key/principal",
        headers=_auth(
            key_a["key"],
            **{
                "X-Workspace-Id": ws_b["id"],
                "X-Workspace-Slug": "keys-iso-b",
                "Host": "keys-iso-b.geem.dm",
            },
        ),
    )
    assert forged.status_code == 200, forged.text
    assert forged.json()["workspace_id"] == ws_a["id"]
    assert forged.json()["ctx_workspace_id"] == ws_a["id"]
    assert forged.json()["workspace_resolution"] == "api_key"
    assert forged.json()["user_id"] is None

    forged_b = client.get(
        "/__test__/api-key/principal",
        headers=_auth(key_b["key"], **{"X-Workspace-Id": ws_a["id"]}),
    )
    assert forged_b.json()["workspace_id"] == ws_b["id"]


def test_session_workspace_cannot_change_api_key_workspace(client, register_user) -> None:
    user = register_user(email="keys-session@example.com")
    ws_a = _create_workspace(client, user, "keys-sess-a")
    ws_b = _create_workspace(client, user, "keys-sess-b")
    key_a = client.post(
        "/api/api-keys",
        headers=_ws_headers(user, ws_a),
        json={"name": "A"},
    ).json()["key"]

    # Same TestClient still has the user session cookie from register.
    res = client.get(
        "/__test__/api-key/principal",
        headers=_auth(key_a, **{"X-Workspace-Id": ws_b["id"]}),
    )
    assert res.status_code == 200
    assert res.json()["workspace_id"] == ws_a["id"]
    assert res.json()["user_id"] is None


def test_model_repr_omits_hash_and_secret(client, register_user, db) -> None:
    owner = register_user(email="keys-repr@example.com")
    ws = _create_workspace(client, owner, "keys-repr-ws")
    created = client.post(
        "/api/api-keys",
        headers=_ws_headers(owner, ws),
        json={"name": "Repr"},
    )
    plaintext = created.json()["key"]
    row = db.get(ApiKey, uuid.UUID(created.json()["id"]))
    assert row is not None
    text = repr(row)
    assert plaintext not in text
    assert row.secret_hash not in text
    assert "secret_hash" not in text

    from app.api_keys.service import CreatedApiKey

    created_obj = CreatedApiKey(row=row, plaintext=plaintext)
    assert plaintext not in repr(created_obj)
    assert "plaintext" not in repr(created_obj)
