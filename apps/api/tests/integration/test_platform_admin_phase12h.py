"""Phase 12H — Platform Admin release gate (security, isolation, E2E smoke).

Consolidates cross-cutting acceptance checks not owned by a single 12A–12G slice.
Does not add product features.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.audit import AuditAction
from app.identity.models import PlatformRole, User
from app.usage.credits import CreditService
from app.workspaces.models import WorkspaceKind
from app.workspaces.service import WorkspaceService

# Representative Platform Admin routes (one per major Phase 12 domain).
PLATFORM_ROUTE_SAMPLES: list[tuple[str, str]] = [
    ("GET", "/api/platform/me"),
    ("GET", "/api/platform/dashboard/summary"),
    ("GET", "/api/platform/workspaces"),
    ("GET", "/api/platform/users"),
    ("GET", "/api/platform/plans"),
    ("GET", "/api/platform/experts"),
    ("GET", "/api/platform/apps"),
    ("GET", "/api/platform/payment-gateways"),
    ("GET", "/api/platform/purchases"),
    ("GET", "/api/platform/usage/summary"),
    ("GET", "/api/platform/audit-logs"),
]


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


def _workspace_api_key(client: TestClient, owner: dict, ws: dict) -> str:
    created = client.post(
        "/api/api-keys",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
        json={"name": "12h-probe"},
    )
    assert created.status_code == 201, created.text
    secret = created.json()["key"]
    assert secret.startswith("geem_sk_")
    return secret


@pytest.mark.parametrize("method,path", PLATFORM_ROUTE_SAMPLES)
def test_workspace_api_key_rejected_on_platform_routes(
    client: TestClient,
    register_user,
    method: str,
    path: str,
) -> None:
  """Every Platform category must reject Workspace API keys (401, not session JWT)."""
  owner = register_user(email=f"owner-12h-key-{uuid.uuid4().hex[:8]}@example.com")
  ws = _create_workspace(client, owner, f"ws-12h-{uuid.uuid4().hex[:6]}")
  secret = _workspace_api_key(client, owner, ws)

  res = client.request(method, path, headers=_auth(secret))
  assert res.status_code == 401, f"{method} {path}: {res.text}"
  assert res.json()["code"] == "unauthorized"


def test_zero_membership_platform_admin_surface_smoke(
    client: TestClient, register_user, db
) -> None:
    """Platform Admin with no Workspace memberships can operate globally."""
    admin_body, _ = _admin_client(
        client, register_user, db, "padmin-12h-lonely@example.com"
    )
    headers = _auth(admin_body["access_token"])

    for method, path in PLATFORM_ROUTE_SAMPLES:
        if path == "/api/platform/usage/summary":
            res = client.request(method, path, headers=headers)
        else:
            res = client.request(method, path, headers=headers)
        assert res.status_code == 200, f"{method} {path}: {res.text}"


def test_audit_logs_are_read_only(client: TestClient, register_user, db) -> None:
    """Platform Admin cannot mutate audit history."""
    admin_body, _ = _admin_client(
        client, register_user, db, "padmin-12h-audit@example.com"
    )
    headers = _auth(admin_body["access_token"])

    listed = client.get("/api/platform/audit-logs", headers=headers)
    assert listed.status_code == 200, listed.text
    audit_id = (
        listed.json()["items"][0]["id"]
        if listed.json().get("items")
        else str(uuid.uuid4())
    )

    for method in ("POST", "PATCH", "PUT", "DELETE"):
        res = client.request(
            method,
            f"/api/platform/audit-logs/{audit_id}",
            headers=headers,
            json={"action": "tamper"},
        )
        assert res.status_code in (404, 405), f"{method} should not mutate audits: {res.text}"


def test_cross_workspace_credit_grant_isolation(
    client: TestClient, register_user, db
) -> None:
    """Granting credits to Workspace A must not change Workspace B balance."""
    admin_body, _ = _admin_client(
        client, register_user, db, "padmin-12h-xws@example.com"
    )
    owner_a = register_user(email="owner-a-12h@example.com")
    owner_b = register_user(email="owner-b-12h@example.com")
    ws_a = _create_workspace(client, owner_a, f"ws-a-12h-{uuid.uuid4().hex[:6]}")
    ws_b = _create_workspace(client, owner_b, f"ws-b-12h-{uuid.uuid4().hex[:6]}")

    credits = CreditService(db)
    balance_b_before = credits.get_balance(uuid.UUID(ws_b["id"]))

    grant = client.post(
        f"/api/platform/workspaces/{ws_a['id']}/credits/grant",
        headers=_auth(admin_body["access_token"]),
        json={
            "amount": 500,
            "reason": "12H isolation probe",
            "request_id": f"platform-credit-grant:12h-{uuid.uuid4()}",
        },
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["workspace_id"] == ws_a["id"]
    assert grant.json()["balance"] >= 500

    balance_b_after = credits.get_balance(uuid.UUID(ws_b["id"]))
    assert balance_b_after == balance_b_before


def test_credit_grant_idempotency_integration(
    client: TestClient, register_user, db
) -> None:
    """Same manual grant request_id must not double-apply."""
    admin_body, _ = _admin_client(
        client, register_user, db, "padmin-12h-idem@example.com"
    )
    owner = register_user(email="owner-idem-12h@example.com")
    ws = _create_workspace(client, owner, f"ws-idem-12h-{uuid.uuid4().hex[:6]}")
    request_id = f"platform-credit-grant:12h-idem-{uuid.uuid4()}"
    body = {
        "amount": 250,
        "reason": "Idempotency probe",
        "request_id": request_id,
    }
    headers = _auth(admin_body["access_token"])

    first = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json=body,
    )
    assert first.status_code == 200, first.text
    balance_after_first = first.json()["balance"]
    assert first.json()["idempotent_replay"] is False

    second = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json=body,
    )
    assert second.status_code == 200, second.text
    assert second.json()["balance"] == balance_after_first
    assert second.json()["idempotent_replay"] is True

    history = client.get(
        f"/api/platform/workspaces/{ws['id']}/credits/history",
        headers=headers,
    )
    assert history.status_code == 200
    grant_entries = [
        item
        for item in history.json()["items"]
        if item.get("request_id") == request_id
    ]
    assert len(grant_entries) == 1


def test_system_workspace_protection_matrix(
    client: TestClient, register_user, db
) -> None:
    """Platform Knowledge system Workspace rejects tenant-commercial operations."""
    admin_body, _ = _admin_client(
        client, register_user, db, "padmin-12h-sys@example.com"
    )
    headers = _auth(admin_body["access_token"])
    pk = WorkspaceService(db).get_platform_knowledge_workspace()
    assert pk.kind == WorkspaceKind.SYSTEM.value
    ws_id = str(pk.id)

    disable = client.post(
        f"/api/platform/workspaces/{ws_id}/disable",
        headers=headers,
        json={"reason": "Should fail"},
    )
    assert disable.status_code == 409
    assert disable.json()["code"] == "system_workspace_protected"

    assign = client.post(
        f"/api/platform/workspaces/{ws_id}/subscription/assign",
        headers=headers,
        json={"plan_id": str(uuid.uuid4()), "reason": "Should fail"},
    )
    assert assign.status_code == 409
    assert assign.json()["code"] == "system_workspace_not_billable"

    grant = client.post(
        f"/api/platform/workspaces/{ws_id}/credits/grant",
        headers=headers,
        json={
            "amount": 100,
            "reason": "Should fail",
            "request_id": f"platform-credit-grant:12h-sys-{uuid.uuid4()}",
        },
    )
    assert grant.status_code == 409
    assert grant.json()["code"] == "system_workspace_not_billable"


def test_platform_happy_path_orchestration(
    client: TestClient, register_user, db
) -> None:
    """Deterministic smoke across Workspaces → Plans → Credits → Audit."""
    admin_body, _ = _admin_client(
        client, register_user, db, "padmin-12h-happy@example.com"
    )
    owner = register_user(email="owner-happy-12h@example.com")
    ws = _create_workspace(client, owner, f"happy-12h-{uuid.uuid4().hex[:6]}")
    headers = _auth(admin_body["access_token"])

    ws_detail = client.get(f"/api/platform/workspaces/{ws['id']}", headers=headers)
    assert ws_detail.status_code == 200

    plan = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"happy12h_{uuid.uuid4().hex[:8]}",
            "name": "12H Happy Plan",
            "price_amount": "25.00",
            "entitlements": [
                {"key": "ai_tokens_daily", "value": 1000, "value_type": "integer"},
                {"key": "ai_tokens_weekly", "value": 5000, "value_type": "integer"},
                {"key": "ai_tokens_monthly", "value": 20000, "value_type": "integer"},
                {"key": "experts_limit", "value": 5, "value_type": "integer"},
                {"key": "storage_bytes", "value": 1073741824, "value_type": "integer"},
                {"key": "api_requests_per_minute", "value": 60, "value_type": "integer"},
            ],
        },
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    assign = client.post(
        f"/api/platform/workspaces/{ws['id']}/subscription/assign",
        headers=headers,
        json={"plan_id": plan_id, "reason": "12H happy path"},
    )
    assert assign.status_code == 200, assign.text

    grant = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json={
            "amount": 100,
            "reason": "12H happy path grant",
            "request_id": f"platform-credit-grant:12h-happy-{uuid.uuid4()}",
        },
    )
    assert grant.status_code == 200, grant.text

    usage = client.get(f"/api/platform/workspaces/{ws['id']}/usage", headers=headers)
    assert usage.status_code == 200

    audit = client.get(
        "/api/platform/audit-logs",
        headers=headers,
        params={"workspace_id": ws["id"], "limit": 10},
    )
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert AuditAction.WORKSPACE_CREDIT_GRANTED.value in actions
