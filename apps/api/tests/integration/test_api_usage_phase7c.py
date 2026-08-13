"""Phase 7C — Workspace API usage summary/history (session auth)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api_keys.models import ApiKey
from app.db.models import UsageEvent
from app.entitlements.keys import EntitlementKey
from app.entitlements.quota import QuotaService
from app.workspaces.models import WorkspaceMembership, WorkspaceRole


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _create_workspace(client, user: dict, slug: str, name: str = "ApiUse") -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_key(client, user: dict, workspace: dict, name: str = "Prod") -> dict:
    res = client.post(
        "/api/api-keys",
        headers=_ws_headers(user, workspace),
        json={"name": name},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_member(db, workspace_id: str, user_id: str, role: WorkspaceRole) -> None:
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id),
            role=role.value,
        )
    )
    db.commit()


def _event(
    db,
    *,
    workspace_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    billed: int,
    operation_type: str = "chat",
    model: str = "test-model",
    created_at: datetime | None = None,
    expert_id: uuid.UUID | None = None,
) -> UsageEvent:
    row = UsageEvent(
        operation_type=operation_type,
        model=model,
        input_tokens=billed // 2,
        output_tokens=billed - billed // 2,
        cost_metadata={"family": "chat", "billed_tokens": billed},
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        expert_id=expert_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(row)
    return row


def test_summary_rate_limit_from_entitlement(client, register_user, db) -> None:
    user = register_user(email="7c-ent@example.com")
    ws = _create_workspace(client, user, "p7c-ent")
    expected = QuotaService(db).get_api_requests_per_minute(uuid.UUID(ws["id"]))
    assert expected == 60
    res = client.get("/api/api-usage/summary", headers=_ws_headers(user, ws))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rate_limit"]["requests_per_minute"] == expected
    assert body["ai_tokens"]["billed"] == 0
    assert "workspace_ai_monthly" in body
    assert body["period"]["key"] == "30d"


def test_api_usage_excludes_workspace_chat(client, register_user, db) -> None:
    user = register_user(email="7c-chat@example.com")
    ws = _create_workspace(client, user, "p7c-chat")
    key = _create_key(client, user, ws)
    ws_id = uuid.UUID(ws["id"])
    _event(db, workspace_id=ws_id, api_key_id=uuid.UUID(key["id"]), billed=40)
    _event(db, workspace_id=ws_id, api_key_id=None, billed=999)
    db.commit()

    summary = client.get("/api/api-usage/summary", headers=_ws_headers(user, ws))
    assert summary.status_code == 200, summary.text
    assert summary.json()["ai_tokens"]["billed"] == 40
    keys = {item["api_key_id"]: item for item in summary.json()["keys"]}
    assert keys[key["id"]]["billed_tokens"] == 40
    assert keys[key["id"]]["prefix"] == key["prefix"]
    assert "key" not in keys[key["id"]]
    assert "secret_hash" not in keys[key["id"]]
    assert key["key"] not in summary.text

    history = client.get("/api/api-usage/history", headers=_ws_headers(user, ws))
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["billed_tokens"] == 40
    assert items[0]["api_key_id"] == key["id"]
    assert key["key"] not in history.text


def test_per_key_grouping_and_revoked_history(client, register_user, db) -> None:
    user = register_user(email="7c-grp@example.com")
    ws = _create_workspace(client, user, "p7c-grp")
    prod = _create_key(client, user, ws, "Production")
    staging = _create_key(client, user, ws, "Staging")
    ws_id = uuid.UUID(ws["id"])
    _event(db, workspace_id=ws_id, api_key_id=uuid.UUID(prod["id"]), billed=10)
    _event(db, workspace_id=ws_id, api_key_id=uuid.UUID(prod["id"]), billed=15)
    _event(db, workspace_id=ws_id, api_key_id=uuid.UUID(staging["id"]), billed=7)
    db.commit()

    revoked = client.post(
        f"/api/api-keys/{prod['id']}/revoke",
        headers=_ws_headers(user, ws),
    )
    assert revoked.status_code == 200, revoked.text

    summary = client.get("/api/api-usage/summary", headers=_ws_headers(user, ws))
    body = summary.json()
    by_id = {item["api_key_id"]: item for item in body["keys"]}
    assert by_id[prod["id"]]["billed_tokens"] == 25
    assert by_id[prod["id"]]["revoked_at"]
    assert by_id[staging["id"]]["billed_tokens"] == 7
    assert body["ai_tokens"]["billed"] == 32

    history = client.get(
        "/api/api-usage/history",
        headers=_ws_headers(user, ws),
        params={"api_key_id": prod["id"]},
    )
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 2
    assert all(item["api_key_id"] == prod["id"] for item in items)


def test_workspace_isolation(client, register_user, db) -> None:
    owner_a = register_user(email="7c-iso-a@example.com")
    owner_b = register_user(email="7c-iso-b@example.com")
    ws_a = _create_workspace(client, owner_a, "p7c-iso-a")
    ws_b = _create_workspace(client, owner_b, "p7c-iso-b")
    key_a = _create_key(client, owner_a, ws_a, "A")
    key_b = _create_key(client, owner_b, ws_b, "B")
    _event(
        db,
        workspace_id=uuid.UUID(ws_a["id"]),
        api_key_id=uuid.UUID(key_a["id"]),
        billed=50,
    )
    _event(
        db,
        workspace_id=uuid.UUID(ws_b["id"]),
        api_key_id=uuid.UUID(key_b["id"]),
        billed=80,
    )
    db.commit()

    a = client.get("/api/api-usage/summary", headers=_ws_headers(owner_a, ws_a))
    b = client.get("/api/api-usage/summary", headers=_ws_headers(owner_b, ws_b))
    assert a.json()["ai_tokens"]["billed"] == 50
    assert b.json()["ai_tokens"]["billed"] == 80
    a_ids = {item["api_key_id"] for item in a.json()["keys"]}
    b_ids = {item["api_key_id"] for item in b.json()["keys"]}
    assert key_a["id"] in a_ids and key_b["id"] not in a_ids
    assert key_b["id"] in b_ids and key_a["id"] not in b_ids

    hijack = client.get(
        "/api/api-usage/history",
        headers=_ws_headers(owner_a, ws_a),
        params={"api_key_id": key_b["id"]},
    )
    assert hijack.status_code == 200
    assert hijack.json()["items"] == []
    assert hijack.json()["total"] == 0


def test_member_can_view_api_usage_not_keys(client, register_user, db) -> None:
    owner = register_user(email="7c-mem-o@example.com")
    member = register_user(email="7c-mem-m@example.com")
    ws = _create_workspace(client, owner, "p7c-mem")
    key = _create_key(client, owner, ws)
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
    _event(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        api_key_id=uuid.UUID(key["id"]),
        billed=12,
    )
    db.commit()

    usage = client.get("/api/api-usage/summary", headers=_ws_headers(member, ws))
    assert usage.status_code == 200, usage.text
    assert usage.json()["ai_tokens"]["billed"] == 12

    keys = client.get("/api/api-keys", headers=_ws_headers(member, ws))
    assert keys.status_code == 403


def test_history_pagination_is_workspace_scoped(client, register_user, db) -> None:
    user = register_user(email="7c-page@example.com")
    ws = _create_workspace(client, user, "p7c-page")
    key = _create_key(client, user, ws)
    ws_id = uuid.UUID(ws["id"])
    for i in range(3):
        _event(
            db,
            workspace_id=ws_id,
            api_key_id=uuid.UUID(key["id"]),
            billed=i + 1,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=i),
        )
    db.commit()

    page = client.get(
        "/api/api-usage/history",
        headers=_ws_headers(user, ws),
        params={"limit": 2, "offset": 0},
    )
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert len(body["items"]) == 2

    rest = client.get(
        "/api/api-usage/history",
        headers=_ws_headers(user, ws),
        params={"limit": 2, "offset": 2},
    )
    assert rest.json()["total"] == 3
    assert len(rest.json()["items"]) == 1


def test_invalid_period_is_422(client, register_user, db) -> None:
    user = register_user(email="7c-period@example.com")
    ws = _create_workspace(client, user, "p7c-period")
    res = client.get(
        "/api/api-usage/summary",
        headers=_ws_headers(user, ws),
        params={"period": "year"},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "validation"


def test_rate_limit_not_derived_from_plan_name(client, register_user, db) -> None:
    user = register_user(email="7c-plan@example.com")
    ws = _create_workspace(client, user, "p7c-plan")
    quota = QuotaService(db)
    limit = quota.get_api_requests_per_minute(uuid.UUID(ws["id"]))
    assert EntitlementKey.API_REQUESTS_PER_MINUTE.value == "api_requests_per_minute"
    res = client.get("/api/api-usage/summary", headers=_ws_headers(user, ws))
    assert res.json()["rate_limit"]["requests_per_minute"] == limit
    assert "bootstrap" not in res.text.lower()


def test_list_keys_never_includes_secret(client, register_user, db) -> None:
    user = register_user(email="7c-secret@example.com")
    ws = _create_workspace(client, user, "p7c-secret")
    created = _create_key(client, user, ws)
    listed = client.get("/api/api-keys", headers=_ws_headers(user, ws))
    assert listed.status_code == 200
    assert "key" not in listed.json()[0]
    assert created["key"] not in listed.text
    row = db.scalar(select(ApiKey).where(ApiKey.id == uuid.UUID(created["id"])))
    assert row is not None
    assert row.secret_hash not in listed.text
