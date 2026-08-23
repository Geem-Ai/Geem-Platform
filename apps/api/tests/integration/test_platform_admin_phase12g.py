"""Phase 12G — Platform Admin dashboard, usage analytics, and audit logs."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.audit import AuditAction, AuditEntityType, AuditLog, record_audit
from app.audit.sanitize import redact_audit_metadata_for_read
from app.db.models import UsageEvent
from app.identity.models import PlatformRole, User
from app.usage.models import UsageDailyWorkspace
from app.usage.rollup import UsageDailyRollupService
from app.workspaces.models import WorkspaceKind

pytestmark = pytest.mark.usefixtures("db")


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


def _admin_client(client: TestClient, register_user, db, email: str) -> tuple[dict, User]:
    body = register_user(email=email)
    admin = _promote_platform_admin(db, body["user"]["id"])
    return body, admin


def _create_workspace(client: TestClient, user: dict, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _insert_usage_event(
    db,
    *,
    workspace_id: uuid.UUID,
    billed_tokens: int,
    created_at: datetime,
    api_key_id: uuid.UUID | None = None,
    operation_type: str = "chat",
) -> None:
    db.add(
        UsageEvent(
            operation_type=operation_type,
            model="test",
            input_tokens=4,
            output_tokens=6,
            cost_metadata={
                "family": "chat",
                "billed_tokens": billed_tokens,
                "raw_prompt_tokens": 4,
                "raw_completion_tokens": 6,
            },
            workspace_id=workspace_id,
            api_key_id=api_key_id,
            created_at=created_at,
        )
    )
    db.flush()


def test_unauthenticated_dashboard_401(client: TestClient) -> None:
    res = client.get("/api/platform/dashboard/summary")
    assert res.status_code == 401


def test_tenant_user_dashboard_403(client: TestClient, register_user) -> None:
    user = register_user(email="tenant-12g-dash@example.com")
    res = client.get("/api/platform/dashboard/summary", headers=_auth(user["access_token"]))
    assert res.status_code == 403


def test_dashboard_summary_counts(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-dash@example.com")
    owner = register_user(email="owner-12g-dash@example.com")
    ws = _create_workspace(client, owner, "dash-acme")
    res = client.get(
        "/api/platform/dashboard/summary",
        headers=_auth(admin_body["access_token"]),
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["workspaces"]["total"] >= 1
    assert payload["users"]["total"] >= 2
    assert "billed_tokens_30d" in payload["usage"]
    assert "recent_activity" in payload


def _create_api_key(db, workspace_id: uuid.UUID, actor_id: uuid.UUID, name: str):
    from app.api_keys.service import ApiKeyService
    from app.workspaces.models import Workspace

    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None
    return ApiKeyService(db).create_key(workspace=workspace, actor_id=actor_id, name=name).row


def test_usage_summary_uses_rollups_and_events(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-usage@example.com")
    owner = register_user(email="owner-12g-usage@example.com")
    ws = _create_workspace(client, owner, "usage-acme")
    workspace_id = uuid.UUID(ws["id"])
    api_key = _create_api_key(
        db, workspace_id, uuid.UUID(owner["user"]["id"]), "usage-key"
    )
    day = date.today() - timedelta(days=2)
    event_at = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=workspace_id,
        billed_tokens=100,
        created_at=event_at,
        api_key_id=api_key.id,
    )
    _insert_usage_event(
        db,
        workspace_id=workspace_id,
        billed_tokens=50,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    UsageDailyRollupService(db).rollup_day(day)
    db.commit()
    res = client.get(
        "/api/platform/usage/summary",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["total_billed_tokens"] == 150
    assert payload["active_workspaces"] == 1


def test_usage_summary_rejects_oversized_range(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-range@example.com")
    today = date.today()
    from_day = today - timedelta(days=120)
    res = client.get(
        "/api/platform/usage/summary",
        headers=_auth(admin_body["access_token"]),
        params={"from": from_day.isoformat(), "to": today.isoformat()},
    )
    assert res.status_code == 422 or res.status_code == 400


def test_usage_trend_daily_buckets(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-trend@example.com")
    owner = register_user(email="owner-12g-trend@example.com")
    ws = _create_workspace(client, owner, "trend-acme")
    workspace_id = uuid.UUID(ws["id"])
    day = date.today() - timedelta(days=1)
    event_at = datetime(day.year, day.month, day.day, 10, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=workspace_id,
        billed_tokens=42,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    res = client.get(
        "/api/platform/usage/trend",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert res.status_code == 200, res.text
    points = res.json()["points"]
    assert len(points) == 1
    assert points[0]["billed_tokens"] == 42


def test_top_workspaces_ranking(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-top@example.com")
    owner = register_user(email="owner-12g-top@example.com")
    ws_a = _create_workspace(client, owner, "top-a")
    ws_b = _create_workspace(client, owner, "top-b")
    day = date.today() - timedelta(days=1)
    event_at = datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=uuid.UUID(ws_a["id"]),
        billed_tokens=200,
        created_at=event_at,
        api_key_id=None,
    )
    _insert_usage_event(
        db,
        workspace_id=uuid.UUID(ws_b["id"]),
        billed_tokens=50,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    res = client.get(
        "/api/platform/usage/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat(), "limit": 10},
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items[0]["workspace_slug"] == "top-a"
    assert items[0]["billed_tokens"] == 200


def test_workspace_usage_drill_down(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-ws@example.com")
    owner = register_user(email="owner-12g-ws@example.com")
    ws = _create_workspace(client, owner, "ws-usage")
    workspace_id = ws["id"]
    day = date.today() - timedelta(days=1)
    event_at = datetime(day.year, day.month, day.day, 8, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=uuid.UUID(workspace_id),
        billed_tokens=77,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    res = client.get(
        f"/api/platform/workspaces/{workspace_id}/usage/summary",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert res.status_code == 200, res.text
    assert res.json()["total_billed_tokens"] == 77


def test_usage_events_require_date_range(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-events@example.com")
    res = client.get(
        "/api/platform/usage/events",
        headers=_auth(admin_body["access_token"]),
    )
    assert res.status_code == 422


def test_usage_events_safe_payload(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-event-safe@example.com")
    owner = register_user(email="owner-12g-event-safe@example.com")
    ws = _create_workspace(client, owner, "event-safe")
    day = date.today()
    event_at = datetime(day.year, day.month, day.day, 7, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        billed_tokens=10,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    res = client.get(
        "/api/platform/usage/events",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert res.status_code == 200, res.text
    blob = res.text
    assert "password" not in blob.lower()


def test_audit_logs_list_and_detail(
    client: TestClient, register_user, db
) -> None:
    admin_body, admin = _admin_client(client, register_user, db, "admin-12g-audit@example.com")
    owner = register_user(email="owner-12g-audit@example.com")
    ws = _create_workspace(client, owner, "audit-acme")
    record_audit(
        db,
        action=AuditAction.WORKSPACE_CREDIT_GRANTED,
        entity_type=AuditEntityType.CREDIT_LEDGER_ENTRY,
        entity_id=uuid.uuid4(),
        workspace_id=uuid.UUID(ws["id"]),
        actor_user_id=admin.id,
        metadata={"reason": "fixture grant", "amount": 1000, "server_key": "secret"},
        allowlist=frozenset({"reason", "amount", "server_key"}),
        required=False,
    )
    db.commit()
    res = client.get(
        "/api/platform/audit-logs",
        headers=_auth(admin_body["access_token"]),
        params={"action": AuditAction.WORKSPACE_CREDIT_GRANTED.value},
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) >= 1
    audit_id = items[0]["id"]
    detail = client.get(
        f"/api/platform/audit-logs/{audit_id}",
        headers=_auth(admin_body["access_token"]),
    )
    assert detail.status_code == 200, detail.text
    assert "secret" not in detail.text.lower()


def test_audit_redaction_recursive() -> None:
    raw = {
        "reason": "rotate",
        "credentials": {"secret": "nested", "profile_id": "123"},
        "access_token": "jwt",
    }
    cleaned = redact_audit_metadata_for_read(raw)
    assert cleaned["reason"] == "rotate"
    assert "access_token" not in cleaned
    assert "credentials" not in cleaned
    assert "unexpected_field" not in redact_audit_metadata_for_read(
        {"reason": "ok", "unexpected_field": "value"}
    )


def test_system_workspaces_excluded_from_tenant_usage_ranking(
    client: TestClient, register_user, db
) -> None:
    from app.workspaces.service import WorkspaceService

    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-system@example.com")
    pk = WorkspaceService(db).get_platform_knowledge_workspace()
    day = date.today() - timedelta(days=1)
    event_at = datetime(day.year, day.month, day.day, 6, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=pk.id,
        billed_tokens=9999,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    res = client.get(
        "/api/platform/usage/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert res.status_code == 200, res.text
    slugs = [item["workspace_slug"] for item in res.json()["items"]]
    assert pk.slug not in slugs


def test_api_only_workspace_counts_as_active_without_rollup(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-api-only@example.com")
    owner = register_user(email="owner-12g-api-only@example.com")
    ws = _create_workspace(client, owner, "api-only-acme")
    workspace_id = uuid.UUID(ws["id"])
    api_key = _create_api_key(
        db, workspace_id, uuid.UUID(owner["user"]["id"]), "api-only-key"
    )
    now = datetime.now(UTC)
    _insert_usage_event(
        db,
        workspace_id=workspace_id,
        billed_tokens=80,
        created_at=now - timedelta(minutes=5),
        api_key_id=api_key.id,
    )
    db.commit()
    res = client.get(
        "/api/platform/usage/summary",
        headers=_auth(admin_body["access_token"]),
        params={"from": now.date().isoformat(), "to": now.date().isoformat()},
    )
    assert res.status_code == 200, res.text
    assert res.json()["active_workspaces"] == 1


def test_top_workspaces_active_days_union_not_sum(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(
        client, register_user, db, "admin-12g-active-days@example.com"
    )
    owner = register_user(email="owner-12g-active-days@example.com")
    ws = _create_workspace(client, owner, "active-days-acme")
    workspace_id = uuid.UUID(ws["id"])
    api_key = _create_api_key(
        db, workspace_id, uuid.UUID(owner["user"]["id"]), "active-days-key"
    )
    day = date.today() - timedelta(days=2)
    event_at = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    _insert_usage_event(
        db,
        workspace_id=workspace_id,
        billed_tokens=100,
        created_at=event_at,
        api_key_id=api_key.id,
    )
    _insert_usage_event(
        db,
        workspace_id=workspace_id,
        billed_tokens=50,
        created_at=event_at,
        api_key_id=None,
    )
    db.commit()
    UsageDailyRollupService(db).rollup_day(day)
    db.commit()
    res = client.get(
        "/api/platform/usage/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert res.status_code == 200, res.text
    item = next(row for row in res.json()["items"] if row["workspace_slug"] == "active-days-acme")
    assert item["active_days"] == 1


def test_usage_workspaces_rejects_invalid_sort(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "admin-12g-sort@example.com")
    res = client.get(
        "/api/platform/usage/workspaces",
        headers=_auth(admin_body["access_token"]),
        params={"sort": "workspace_name"},
    )
    assert res.status_code == 422 or res.status_code == 400


def test_recent_activity_prefers_platform_scope(
    client: TestClient, register_user, db
) -> None:
    admin_body, admin = _admin_client(client, register_user, db, "admin-12g-recent@example.com")
    owner = register_user(email="owner-12g-recent@example.com")
    ws = _create_workspace(client, owner, "recent-acme")
    record_audit(
        db,
        action=AuditAction.MEMBER_ROLE_CHANGED,
        entity_type=AuditEntityType.MEMBERSHIP,
        entity_id=uuid.uuid4(),
        workspace_id=uuid.UUID(ws["id"]),
        actor_user_id=uuid.UUID(owner["user"]["id"]),
        metadata={"target_user_id": owner["user"]["id"]},
        allowlist=frozenset({"target_user_id"}),
        required=False,
    )
    record_audit(
        db,
        action=AuditAction.PAYMENT_GATEWAY_UPDATED,
        entity_type=AuditEntityType.PAYMENT_GATEWAY,
        entity_id=uuid.uuid4(),
        workspace_id=None,
        actor_user_id=admin.id,
        metadata={"code": "clickpay"},
        allowlist=frozenset({"code"}),
        required=False,
    )
    db.commit()
    res = client.get(
        "/api/platform/dashboard/summary",
        headers=_auth(admin_body["access_token"]),
    )
    assert res.status_code == 200, res.text
    actions = [row["action"] for row in res.json()["recent_activity"]]
    assert AuditAction.PAYMENT_GATEWAY_UPDATED.value in actions
    assert AuditAction.MEMBER_ROLE_CHANGED.value not in actions
