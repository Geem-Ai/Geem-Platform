"""Phase 12F — Platform Admin payment gateways and purchases."""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit import AuditAction, AuditLog
from app.billing.checkout import BillingService, purchase_grant_request_id
from app.billing.models import PaymentGatewayConfig, Purchase, PurchaseStatus
from app.billing.repository import PaymentGatewayConfigRepository
from app.billing.service import CreditPackService, PlanService
from app.common.crypto import decrypt_json, encrypt_json
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey
from app.identity.models import PlatformRole, User
from app.usage.credits import CreditService
from app.usage.metrics import CreditLedgerEntryType
from app.usage.models import CreditLedgerEntry
from tests.conftest import TestingSessionLocal

CLICKPAY_BASE = "https://secure.clickpay.com.sa"


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


def _ws_headers(token: str, workspace: dict) -> dict[str, str]:
    return _auth(token, **{"X-Workspace-Id": workspace["id"]})


def _disable_all_gateways(db) -> None:
    for row in PaymentGatewayConfigRepository(db).list_all():
        row.enabled = False
    db.flush()


def _ensure_gateway(
    db,
    code: str,
    *,
    enabled: bool = False,
    credentials: dict | None = None,
    test_mode: bool = True,
) -> PaymentGatewayConfig:
    repo = PaymentGatewayConfigRepository(db)
    blob = encrypt_json(credentials or {}, settings=get_settings())
    row = repo.get_by_code(code)
    if row is None:
        row = repo.create(
            PaymentGatewayConfig(
                code=code,
                enabled=enabled,
                test_mode=test_mode,
                credentials_encrypted=blob,
                extra={},
            )
        )
    else:
        row.credentials_encrypted = blob
        row.test_mode = test_mode
        row.enabled = enabled
    db.flush()
    return row


def _create_paid_plan(db, *, code: str, price: str = "99.00"):
    return PlanService(db).create_plan(
        code=code,
        name=f"Paid {code}",
        price_amount=Decimal(price),
        currency="SAR",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: 1000,
            EntitlementKey.AI_TOKENS_WEEKLY.value: 5000,
            EntitlementKey.AI_TOKENS_MONTHLY.value: 20000,
            EntitlementKey.EXPERTS_LIMIT.value: 5,
            EntitlementKey.STORAGE_BYTES.value: 1_000_000,
            EntitlementKey.API_REQUESTS_PER_MINUTE.value: 60,
        },
        extra={"kind": "test", "commercial": True},
    )


def _create_pack(db, *, code: str, credits: int = 1000):
    return CreditPackService(db).create_pack(
        code=code,
        name=f"Pack {code}",
        credits=credits,
        price_amount=Decimal("25.00"),
        currency="SAR",
    )


def _return_token(redirect_url: str) -> str:
    return parse_qs(urlparse(redirect_url).query)["rt"][0]


def _grant_count(db, workspace_id: uuid.UUID, request_id: str) -> int:
    return len(
        list(
            db.scalars(
                select(CreditLedgerEntry).where(
                    CreditLedgerEntry.workspace_id == workspace_id,
                    CreditLedgerEntry.request_id == request_id,
                    CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
                )
            )
        )
    )


# --- Auth ---


def test_gateways_unauthenticated_401(client: TestClient) -> None:
    assert client.get("/api/platform/payment-gateways").status_code == 401


def test_gateways_owner_403(client: TestClient, register_user) -> None:
    owner = register_user(email="owner-12f-gw@example.com")
    res = client.get("/api/platform/payment-gateways", headers=_auth(owner["access_token"]))
    assert res.status_code == 403


def test_purchases_api_key_rejected(client: TestClient, register_user, db) -> None:
    owner = register_user(email="owner-12f-key@example.com")
    ws = _create_workspace(client, owner, "ws-12f-key")
    key_res = client.post(
        "/api/api-keys",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
        json={"name": "probe"},
    )
    assert key_res.status_code == 201
    res = client.get("/api/platform/purchases", headers=_auth(key_res.json()["key"]))
    assert res.status_code == 401


# --- Gateway config ---


def test_gateway_list_and_create_clickpay(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-gw@example.com")
    headers = _auth(admin_body["access_token"])

    listed = client.get("/api/platform/payment-gateways", headers=headers)
    assert listed.status_code == 200, listed.text
    codes = {item["code"] for item in listed.json()["items"]}
    assert "clickpay" in codes
    assert "noop" in codes

    create = client.post(
        "/api/platform/payment-gateways",
        headers=headers,
        json={
            "code": "stripe",
            "test_mode": True,
            "credentials": {"profile_id": "1", "server_key": "sk"},
        },
    )
    assert create.status_code == 422 or create.json().get("code") == "validation"

    _disable_all_gateways(db)
    clickpay = _ensure_gateway(db, "clickpay", credentials={"profile_id": "1"})
    db.delete(clickpay)
    db.commit()

    create_ok = client.post(
        "/api/platform/payment-gateways",
        headers=headers,
        json={
            "code": "clickpay",
            "test_mode": True,
            "credentials": {"profile_id": "59020", "server_key": "sk_live_secret_value"},
        },
    )
    assert create_ok.status_code == 201, create_ok.text
    body = create_ok.json()
    assert body["credentials"]["server_key_configured"] is True
    assert body["credentials"]["profile_id"] == "59020"
    assert "sk_live_secret_value" not in create_ok.text
    assert "credentials_encrypted" not in create_ok.text

    row = PaymentGatewayConfigRepository(db).get_by_code("clickpay")
    assert row is not None
    stored = decrypt_json(row.credentials_encrypted, settings=get_settings())
    assert stored["server_key"] == "sk_live_secret_value"
    assert row.credentials_encrypted != "sk_live_secret_value"

    audits = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.PAYMENT_GATEWAY_CREATED.value,
                AuditLog.entity_id == row.id,
            )
        )
    )
    assert audits
    assert "sk_live_secret_value" not in str(audits[0].metadata or {})


def test_gateway_update_preserves_secret_when_omitted(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-rot@example.com")
    headers = _auth(admin_body["access_token"])
    _disable_all_gateways(db)
    row = _ensure_gateway(
        db,
        "clickpay",
        credentials={"profile_id": "1", "server_key": "original_secret"},
    )
    db.commit()

    patch = client.patch(
        f"/api/platform/payment-gateways/{row.id}",
        headers=headers,
        json={"profile_id": "2"},
    )
    assert patch.status_code == 200, patch.text
    stored = decrypt_json(row.credentials_encrypted, settings=get_settings())
    assert stored["server_key"] == "original_secret"
    assert stored["profile_id"] == "2"

    rotate = client.patch(
        f"/api/platform/payment-gateways/{row.id}",
        headers=headers,
        json={"credentials": {"server_key": "rotated_secret"}},
    )
    assert rotate.status_code == 200
    stored2 = decrypt_json(row.credentials_encrypted, settings=get_settings())
    assert stored2["server_key"] == "rotated_secret"


def test_noop_cannot_activate_in_non_local(db, register_user) -> None:
    from app.platform_admin.gateways import PlatformAdminGatewaysService
    from app.platform_admin.schemas import PlatformPaymentGatewayActivateRequest

    body = register_user(email="padmin-12f-prod@example.com")
    user = db.get(User, uuid.UUID(body["user"]["id"]))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    row = _ensure_gateway(db, "noop", enabled=False)
    db.commit()

    staging_settings = get_settings().model_copy(update={"app_env": "staging"})
    svc = PlatformAdminGatewaysService(db, staging_settings)
    with pytest.raises(AppError) as exc:
        svc.activate_gateway(
            user,
            row.id,
            PlatformPaymentGatewayActivateRequest(reason="Attempt noop outside local"),
        )
    assert exc.value.category == ErrorCategory.VALIDATION


def test_activate_exactly_one_enabled(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-act@example.com")
    headers = _auth(admin_body["access_token"])
    _disable_all_gateways(db)
    noop = _ensure_gateway(db, "noop", enabled=False)
    clickpay = _ensure_gateway(
        db,
        "clickpay",
        enabled=False,
        credentials={"profile_id": "1", "server_key": "sk"},
    )
    db.commit()

    act = client.post(
        f"/api/platform/payment-gateways/{clickpay.id}/activate",
        headers=headers,
        json={"reason": "Switch to ClickPay"},
    )
    assert act.status_code == 200, act.text
    assert act.json()["enabled"] is True
    enabled = PaymentGatewayConfigRepository(db).list_enabled()
    assert len(enabled) == 1
    assert enabled[0].id == clickpay.id

    act2 = client.post(
        f"/api/platform/payment-gateways/{noop.id}/activate",
        headers=headers,
        json={"reason": "Switch to Noop"},
    )
    assert act2.status_code == 200
    enabled = PaymentGatewayConfigRepository(db).list_enabled()
    assert len(enabled) == 1
    assert enabled[0].id == noop.id


def test_concurrent_activation_exactly_one(client: TestClient, register_user, db) -> None:
    from app.platform_admin.gateways import PlatformAdminGatewaysService
    from app.platform_admin.schemas import PlatformPaymentGatewayActivateRequest

    body = register_user(email="padmin-12f-race@example.com")
    user = db.get(User, uuid.UUID(body["user"]["id"]))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    _disable_all_gateways(db)
    noop = _ensure_gateway(db, "noop", enabled=False)
    clickpay = _ensure_gateway(
        db,
        "clickpay",
        enabled=False,
        credentials={"profile_id": "1", "server_key": "sk"},
    )
    db.commit()
    barrier = threading.Barrier(2, timeout=10)
    errors: list[Exception] = []

    def worker(target_id: uuid.UUID) -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            actor = session.get(User, user.id)
            assert actor is not None
            PlatformAdminGatewaysService(session).activate_gateway(
                actor,
                target_id,
                PlatformPaymentGatewayActivateRequest(reason="Concurrent activation"),
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=(noop.id,))
    t2 = threading.Thread(target=worker, args=(clickpay.id,))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    fresh = TestingSessionLocal()
    try:
        enabled = PaymentGatewayConfigRepository(fresh).list_enabled()
        assert len(enabled) == 1
    finally:
        fresh.close()


# --- Pinned gateway reconciliation ---


def test_purchase_uses_pinned_gateway_after_switch(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-pin@example.com")
    admin_headers = _auth(admin_body["access_token"])
    user = register_user(email="buyer-12f-pin@example.com")
    ws = _create_workspace(client, user, "p12f-pin")
    headers = _ws_headers(user["access_token"], ws)

    _disable_all_gateways(db)
    noop = _ensure_gateway(db, "noop", enabled=True)
    clickpay = _ensure_gateway(
        db,
        "clickpay",
        enabled=False,
        credentials={"profile_id": "59020", "server_key": "sk_clickpay_secret"},
    )
    pack = _create_pack(db, code="p12f_pin_pack", credits=1500)
    db.commit()

    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    assert checkout.status_code == 200, checkout.text
    purchase_id = checkout.json()["purchase_id"]
    row = db.get(Purchase, uuid.UUID(purchase_id))
    assert row is not None
    assert row.payment_gateway_config_id == noop.id

    client.post(
        f"/api/platform/payment-gateways/{clickpay.id}/activate",
        headers=admin_headers,
        json={"reason": "Switch after checkout"},
    )

    reconcile = client.post(
        f"/api/platform/purchases/{purchase_id}/reconcile",
        headers=admin_headers,
    )
    assert reconcile.status_code == 200, reconcile.text
    assert reconcile.json()["resulting_status"] == "paid"
    assert reconcile.json()["fulfillment_applied"] is True
    assert CreditService(db).get_balance(uuid.UUID(ws["id"])) == 1500
    assert _grant_count(db, uuid.UUID(ws["id"]), purchase_grant_request_id(uuid.UUID(purchase_id))) == 1


def test_reconcile_idempotent_and_return_concurrency(client: TestClient, register_user, db) -> None:
    user = register_user(email="buyer-12f-race@example.com")
    ws = _create_workspace(client, user, "p12f-race")
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-race2@example.com")
    admin_headers = _auth(admin_body["access_token"])
    _disable_all_gateways(db)
    _ensure_gateway(db, "noop", enabled=True)
    pack = _create_pack(db, code="p12f_race_pack", credits=900)
    db.commit()

    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user["access_token"], ws),
        json={"credit_pack_id": str(pack.id)},
    )
    purchase_id = uuid.UUID(checkout.json()["purchase_id"])
    token = _return_token(checkout.json()["redirect_url"])
    workspace_id = uuid.UUID(ws["id"])
    barrier = threading.Barrier(2, timeout=10)
    results: list[str] = []

    def return_worker() -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            BillingService(session).complete_on_return(purchase_id, return_token=token)
            session.commit()
            results.append("return")
        finally:
            session.close()

    def reconcile_worker() -> None:
        barrier.wait()
        res = client.post(
            f"/api/platform/purchases/{purchase_id}/reconcile",
            headers=admin_headers,
        )
        results.append(f"reconcile:{res.status_code}")

    t1 = threading.Thread(target=return_worker)
    t2 = threading.Thread(target=reconcile_worker)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert CreditService(db).get_balance(workspace_id) == 900
    assert _grant_count(db, workspace_id, purchase_grant_request_id(purchase_id)) == 1


def test_clickpay_reconcile_provider_unpaid(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-unpaid@example.com")
    admin_headers = _auth(admin_body["access_token"])
    user = register_user(email="buyer-12f-unpaid@example.com")
    ws = _create_workspace(client, user, "p12f-unpaid")
    headers = _ws_headers(user["access_token"], ws)
    _disable_all_gateways(db)
    _ensure_gateway(
        db,
        "clickpay",
        enabled=True,
        credentials={"profile_id": "59020", "server_key": "sk"},
    )
    plan = _create_paid_plan(db, code="p12f_unpaid_plan")
    db.commit()

    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/request").mock(
            return_value=httpx.Response(
                200,
                json={
                    "tran_ref": "TST-UNPAID",
                    "redirect_url": "https://secure.clickpay.com.sa/pay",
                },
            )
        )
        checkout = client.post(
            "/api/billing/checkout/subscription",
            headers=headers,
            json={"plan_id": str(plan.id)},
        )
    assert checkout.status_code == 200
    purchase_id = checkout.json()["purchase_id"]

    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "tran_ref": "TST-UNPAID",
                    "cart_amount": "99.00",
                    "cart_currency": "SAR",
                    "payment_result": {"response_status": "D"},
                },
            )
        )
        reconcile = client.post(
            f"/api/platform/purchases/{purchase_id}/reconcile",
            headers=admin_headers,
        )
    assert reconcile.status_code == 200
    assert reconcile.json()["resulting_status"] == "failed"
    assert reconcile.json()["fulfillment_applied"] is False


def test_platform_purchase_list_and_detail(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-list@example.com")
    headers = _auth(admin_body["access_token"])
    user = register_user(email="buyer-12f-list@example.com")
    ws = _create_workspace(client, user, "p12f-list")
    _disable_all_gateways(db)
    _ensure_gateway(db, "noop", enabled=True)
    pack = _create_pack(db, code="p12f_list_pack")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user["access_token"], ws),
        json={"credit_pack_id": str(pack.id)},
    )
    purchase_id = checkout.json()["purchase_id"]
    client.get(checkout.json()["redirect_url"].replace("http://testserver", ""))

    listed = client.get(
        "/api/platform/purchases",
        headers=headers,
        params={"workspace_id": ws["id"], "kind": "credit_pack"},
    )
    assert listed.status_code == 200
    assert any(item["id"] == purchase_id for item in listed.json()["items"])
    assert "server_key" not in listed.text

    detail = client.get(f"/api/platform/purchases/{purchase_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["gateway"]["code"] == "noop"


def test_paid_purchase_reconcile_noop(client: TestClient, register_user, db) -> None:
    admin_body, _ = _admin_client(client, register_user, db, "padmin-12f-paid@example.com")
    admin_headers = _auth(admin_body["access_token"])
    user = register_user(email="buyer-12f-paid@example.com")
    ws = _create_workspace(client, user, "p12f-paid")
    _disable_all_gateways(db)
    _ensure_gateway(db, "noop", enabled=True)
    pack = _create_pack(db, code="p12f_paid_pack", credits=500)
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user["access_token"], ws),
        json={"credit_pack_id": str(pack.id)},
    )
    purchase_id = checkout.json()["purchase_id"]
    client.get(checkout.json()["redirect_url"].replace("http://testserver", ""))

    replay = client.post(
        f"/api/platform/purchases/{purchase_id}/reconcile",
        headers=admin_headers,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["fulfillment_applied"] is False
