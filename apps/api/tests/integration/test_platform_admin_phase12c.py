"""Phase 12C — Platform Admin plans, subscriptions, credits."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit import AuditAction, AuditLog
from app.billing.models import PlanStatus, Subscription, SubscriptionStatus
from app.billing.service import PlanService
from app.entitlements.keys import EntitlementKey
from app.entitlements.service import EntitlementService
from app.identity.models import PlatformRole, User
from app.usage.meters import UsageMeterService
from app.usage.metrics import CreditLedgerEntryType, UsageMetric
from app.usage.models import CreditLedgerEntry
from app.usage.periods import PeriodType
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


def _canonical_entitlements(**overrides: int) -> list[dict]:
    base = {
        EntitlementKey.AI_TOKENS_DAILY.value: 1000,
        EntitlementKey.AI_TOKENS_WEEKLY.value: 5000,
        EntitlementKey.AI_TOKENS_MONTHLY.value: 20000,
        EntitlementKey.EXPERTS_LIMIT.value: 5,
        EntitlementKey.STORAGE_BYTES.value: 1_073_741_824,
        EntitlementKey.API_REQUESTS_PER_MINUTE.value: 60,
    }
    base.update(overrides)
    return [{"key": k, "value": v} for k, v in base.items()]


def test_plans_list_unauthenticated_401(client: TestClient) -> None:
    assert client.get("/api/platform/plans").status_code == 401


def test_plans_list_owner_without_platform_role_403(client: TestClient, register_user) -> None:
    owner = register_user(email="owner-12c-plans@example.com")
    _create_workspace(client, owner, "ws-12c-owner-plans")
    res = client.get("/api/platform/plans", headers=_auth(owner["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_api_key_cannot_call_platform_plans(client: TestClient, register_user, db) -> None:
    owner = register_user(email="owner-12c-key@example.com")
    ws = _create_workspace(client, owner, "ws-12c-key")
    key_res = client.post(
        "/api/api-keys",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
        json={"name": "probe"},
    )
    assert key_res.status_code == 201, key_res.text
    res = client.get("/api/platform/plans", headers=_auth(key_res.json()["key"]))
    assert res.status_code == 401


def test_platform_admin_plan_crud_and_lifecycle(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-plans@example.com")
    headers = _auth(admin_body["access_token"])
    code = f"admin_plan_{uuid.uuid4().hex[:8]}"

    create = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": code,
            "name": "Admin Plan",
            "description": "12C plan",
            "price_amount": "99.00",
            "currency": "SAR",
            "entitlements": _canonical_entitlements(experts_limit=10),
        },
    )
    assert create.status_code == 201, create.text
    plan = create.json()
    assert plan["code"] == code
    assert plan["status"] == PlanStatus.ACTIVE.value
    assert plan["price_amount"] == "99.00"
    assert plan["is_commercial"] is True

    listed = client.get("/api/platform/plans", headers=headers, params={"search": code})
    assert listed.status_code == 200
    assert any(i["id"] == plan["id"] for i in listed.json()["items"])

    detail = client.get(f"/api/platform/plans/{plan['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["name"] == "Admin Plan"

    dup = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": code,
            "name": "Dup",
            "entitlements": _canonical_entitlements(),
        },
    )
    assert dup.status_code == 409

    bad_ent = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"{code}_bad",
            "name": "Bad",
            "entitlements": [{"key": "not_a_real_key", "value": 1}],
        },
    )
    assert bad_ent.status_code in (400, 422)

    patch = client.patch(
        f"/api/platform/plans/{plan['id']}",
        headers=headers,
        json={
            "name": "Admin Plan Updated",
            "entitlements": _canonical_entitlements(experts_limit=12),
            "reason": "Raise expert limit",
        },
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["name"] == "Admin Plan Updated"
    experts = next(
        e for e in patch.json()["entitlements"] if e["key"] == EntitlementKey.EXPERTS_LIMIT.value
    )
    assert experts["value"] == 12

    deactivate = client.post(
        f"/api/platform/plans/{plan['id']}/deactivate",
        headers=headers,
        json={"reason": "Retire SKU"},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == PlanStatus.ARCHIVED.value

    owner = register_user(email="tenant-12c-plist@example.com")
    ws = _create_workspace(client, owner, "ws-12c-plist")
    purchasable = client.get(
        "/api/billing/plans",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert purchasable.status_code == 200
    assert all(p["id"] != plan["id"] for p in purchasable.json())

    activate = client.post(
        f"/api/platform/plans/{plan['id']}/activate",
        headers=headers,
        json={"reason": "Bring back"},
    )
    assert activate.status_code == 200
    assert activate.json()["status"] == PlanStatus.ACTIVE.value

    audits = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == uuid.UUID(plan["id"]))
    ).all()
    actions = {a.action for a in audits}
    assert AuditAction.PLAN_CREATED.value in actions
    assert AuditAction.PLAN_DEACTIVATED.value in actions
    assert AuditAction.PLAN_ACTIVATED.value in actions


def test_plan_entitlement_change_affects_subscribers(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-ent@example.com")
    owner = register_user(email="tenant-12c-ent@example.com")
    ws = _create_workspace(client, owner, "ws-12c-ent")
    headers = _auth(admin_body["access_token"])

    create = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"ent_{uuid.uuid4().hex[:8]}",
            "name": "Ent Plan",
            "price_amount": "50.00",
            "entitlements": _canonical_entitlements(experts_limit=3),
        },
    )
    assert create.status_code == 201, create.text
    plan_id = create.json()["id"]

    assign = client.post(
        f"/api/platform/workspaces/{ws['id']}/subscription/assign",
        headers=headers,
        json={"plan_id": plan_id, "reason": "Assign for entitlement test"},
    )
    assert assign.status_code == 200, assign.text

    before = EntitlementService(db).get_int(
        uuid.UUID(ws["id"]), EntitlementKey.EXPERTS_LIMIT
    )
    assert before == 3

    patch = client.patch(
        f"/api/platform/plans/{plan_id}",
        headers=headers,
        json={
            "entitlements": _canonical_entitlements(experts_limit=7),
            "reason": "Raise for all subscribers",
        },
    )
    assert patch.status_code == 200, patch.text
    after = EntitlementService(db).get_int(
        uuid.UUID(ws["id"]), EntitlementKey.EXPERTS_LIMIT
    )
    assert after == 7


def test_subscription_assign_change_and_system_protected(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-sub@example.com")
    owner = register_user(email="tenant-12c-sub@example.com")
    ws = _create_workspace(client, owner, "ws-12c-sub")
    headers = _auth(admin_body["access_token"])

    plan_a = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"suba_{uuid.uuid4().hex[:8]}",
            "name": "Sub A",
            "price_amount": "10.00",
            "entitlements": _canonical_entitlements(ai_tokens_monthly=1000),
        },
    ).json()
    plan_b = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"subb_{uuid.uuid4().hex[:8]}",
            "name": "Sub B",
            "price_amount": "20.00",
            "entitlements": _canonical_entitlements(ai_tokens_monthly=5000),
        },
    ).json()

    inspect = client.get(
        f"/api/platform/workspaces/{ws['id']}/subscription", headers=headers
    )
    assert inspect.status_code == 200

    assign = client.post(
        f"/api/platform/workspaces/{ws['id']}/subscription/assign",
        headers=headers,
        json={"plan_id": plan_a["id"], "reason": "Enterprise agreement"},
    )
    assert assign.status_code == 200, assign.text
    assert assign.json()["plan_id"] == plan_a["id"]

    counter = UsageMeterService(db).get_or_create_window(
        uuid.UUID(ws["id"]),
        metric=UsageMetric.AI_TOKENS,
        period_type=PeriodType.MONTHLY,
    )
    counter.used = 500_000
    db.commit()

    change = client.post(
        f"/api/platform/workspaces/{ws['id']}/subscription/assign",
        headers=headers,
        json={"plan_id": plan_b["id"], "reason": "Upgrade"},
    )
    assert change.status_code == 200, change.text
    assert change.json()["plan_id"] == plan_b["id"]

    ents = client.get(
        f"/api/platform/workspaces/{ws['id']}/entitlements", headers=headers
    )
    assert ents.status_code == 200
    monthly = next(
        i
        for i in ents.json()["items"]
        if i["key"] == EntitlementKey.AI_TOKENS_MONTHLY.value
    )
    assert monthly["value"] == 5000

    usage = client.get(f"/api/platform/workspaces/{ws['id']}/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["ai_tokens_monthly"]["used"] == 500_000
    assert usage.json()["ai_tokens_monthly"]["limit"] == 5000

    active = db.scalars(
        select(Subscription).where(
            Subscription.workspace_id == uuid.UUID(ws["id"]),
            Subscription.status == SubscriptionStatus.ACTIVE.value,
        )
    ).all()
    assert len(active) == 1

    history = client.get(
        f"/api/platform/workspaces/{ws['id']}/subscriptions", headers=headers
    )
    assert history.status_code == 200
    assert history.json()["total"] >= 2

    system = WorkspaceService(db).ensure_platform_knowledge_workspace()
    sys_res = client.post(
        f"/api/platform/workspaces/{system.id}/subscription/assign",
        headers=headers,
        json={"plan_id": plan_a["id"], "reason": "Should fail"},
    )
    assert sys_res.status_code == 409
    assert sys_res.json()["code"] == "system_workspace_not_billable"

    owner_res = client.post(
        f"/api/platform/workspaces/{ws['id']}/subscription/assign",
        headers=_auth(owner["access_token"]),
        json={"plan_id": plan_b["id"], "reason": "Nope"},
    )
    assert owner_res.status_code == 403

    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.action.in_(
                [
                    AuditAction.WORKSPACE_SUBSCRIPTION_ASSIGNED.value,
                    AuditAction.WORKSPACE_SUBSCRIPTION_CHANGED.value,
                ]
            ),
            AuditLog.workspace_id == uuid.UUID(ws["id"]),
        )
    ).all()
    assert len(audits) >= 1


def test_credit_grant_idempotent_ledger_and_protections(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-cred@example.com")
    owner = register_user(email="tenant-12c-cred@example.com")
    ws = _create_workspace(client, owner, "ws-12c-cred")
    headers = _auth(admin_body["access_token"])
    request_id = f"platform-credit-grant:{uuid.uuid4()}"

    zero = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json={"amount": 0, "reason": "bad"},
    )
    assert zero.status_code == 422

    neg = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json={"amount": -5, "reason": "bad"},
    )
    assert neg.status_code == 422

    grant = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json={
            "amount": 1_000_000,
            "reason": "Customer service goodwill credit",
            "request_id": request_id,
        },
    )
    assert grant.status_code == 200, grant.text
    payload = grant.json()
    assert payload["balance"] == 1_000_000
    assert payload["idempotent_replay"] is False
    assert payload["entry"]["entry_type"] == CreditLedgerEntryType.GRANT.value
    assert payload["entry"]["amount"] == 1_000_000
    assert payload["entry"]["remaining_amount"] == 1_000_000

    replay = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=headers,
        json={
            "amount": 1_000_000,
            "reason": "Customer service goodwill credit",
            "request_id": request_id,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["balance"] == 1_000_000

    credits = client.get(f"/api/platform/workspaces/{ws['id']}/credits", headers=headers)
    assert credits.status_code == 200
    assert credits.json()["balance"] == 1_000_000

    history = client.get(
        f"/api/platform/workspaces/{ws['id']}/credits/history", headers=headers
    )
    assert history.status_code == 200
    assert history.json()["total"] >= 1

    grants = db.scalars(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.workspace_id == uuid.UUID(ws["id"]),
            CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
        )
    ).all()
    assert len(grants) == 1

    system = WorkspaceService(db).ensure_platform_knowledge_workspace()
    sys_grant = client.post(
        f"/api/platform/workspaces/{system.id}/credits/grant",
        headers=headers,
        json={"amount": 100, "reason": "nope"},
    )
    assert sys_grant.status_code == 409
    assert sys_grant.json()["code"] == "system_workspace_not_billable"

    tenant_forbidden = client.post(
        f"/api/platform/workspaces/{ws['id']}/credits/grant",
        headers=_auth(owner["access_token"]),
        json={"amount": 100, "reason": "nope"},
    )
    assert tenant_forbidden.status_code == 403

    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_CREDIT_GRANTED.value,
            AuditLog.workspace_id == uuid.UUID(ws["id"]),
        )
    ).all()
    assert len(audits) == 1
    assert audits[0].extra.get("amount") == 1_000_000


def test_bootstrap_plan_protected_from_deactivate(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-boot@example.com")
    bootstrap = PlanService(db).ensure_bootstrap_plan()
    db.commit()
    res = client.post(
        f"/api/platform/plans/{bootstrap.id}/deactivate",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Should fail"},
    )
    assert res.status_code == 422


def test_bootstrap_plan_cannot_be_assigned(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-boot-assign@example.com")
    owner = register_user(email="tenant-12c-boot-assign@example.com")
    ws = _create_workspace(client, owner, "ws-12c-boot-assign")
    bootstrap = PlanService(db).ensure_bootstrap_plan()
    db.commit()
    res = client.post(
        f"/api/platform/workspaces/{ws['id']}/subscription/assign",
        headers=_auth(admin_body["access_token"]),
        json={"plan_id": str(bootstrap.id), "reason": "Should fail"},
    )
    assert res.status_code == 422


def test_plan_create_rejects_non_sar_currency(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-currency@example.com")
    res = client.post(
        "/api/platform/plans",
        headers=_auth(admin_body["access_token"]),
        json={
            "code": f"usd_{uuid.uuid4().hex[:8]}",
            "name": "USD Plan",
            "price_amount": "10.00",
            "currency": "USD",
            "entitlements": _canonical_entitlements(),
        },
    )
    assert res.status_code == 422


def test_plan_create_commercial_flag_follows_price(
    client: TestClient, register_user, db
) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12c-commercial@example.com")
    headers = _auth(admin_body["access_token"])
    unpriced = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"free_{uuid.uuid4().hex[:8]}",
            "name": "Manual Only",
            "entitlements": _canonical_entitlements(),
        },
    )
    assert unpriced.status_code == 201, unpriced.text
    assert unpriced.json()["is_commercial"] is False
    assert unpriced.json()["price_amount"] is None

    priced = client.post(
        "/api/platform/plans",
        headers=headers,
        json={
            "code": f"paid_{uuid.uuid4().hex[:8]}",
            "name": "Priced",
            "price_amount": "49.00",
            "currency": "SAR",
            "entitlements": _canonical_entitlements(),
        },
    )
    assert priced.status_code == 201, priced.text
    assert priced.json()["is_commercial"] is True
