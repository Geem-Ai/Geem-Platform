"""Phase 6A — gateway registry, Noop checkout, mocked ClickPay, isolation."""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.billing.checkout import BillingService, purchase_grant_request_id
from app.billing.gateways.registry import GatewayRegistry
from app.billing.models import PaymentGatewayConfig, Purchase, PurchaseStatus
from app.billing.repository import PaymentGatewayConfigRepository
from app.billing.service import CreditPackService, PlanService, SubscriptionService
from app.common.crypto import encrypt_json
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey
from app.entitlements.service import EntitlementService
from app.usage.credits import CreditService
from app.usage.metrics import CreditLedgerEntryType
from app.usage.models import CreditLedgerEntry
from app.workspaces.models import WorkspaceKind
from app.workspaces.service import WorkspaceService
from tests.conftest import TestingSessionLocal

CLICKPAY_BASE = "https://secure.clickpay.com.sa"


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client, token: str, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _ws_headers(token: str, workspace: dict) -> dict[str, str]:
    return _auth(token, **{"X-Workspace-Id": workspace["id"]})


def _return_token(redirect_url: str) -> str:
    return parse_qs(urlparse(redirect_url).query)["rt"][0]


def _as_test_path(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _create_paid_plan(db, *, code: str, price: str = "99.00", tokens: int = 5000):
    return PlanService(db).create_plan(
        code=code,
        name=f"Paid {code}",
        description="Test commercial plan",
        price_amount=Decimal(price),
        currency="SAR",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: tokens,
            EntitlementKey.AI_TOKENS_WEEKLY.value: tokens * 7,
            EntitlementKey.AI_TOKENS_MONTHLY.value: tokens * 30,
            EntitlementKey.EXPERTS_LIMIT.value: 5,
            EntitlementKey.STORAGE_BYTES.value: 1_000_000,
        },
        extra={"kind": "test", "commercial": True},
    )


def _create_pack(db, *, code: str, credits: int = 1000, price: str = "25.00"):
    return CreditPackService(db).create_pack(
        code=code,
        name=f"Pack {code}",
        credits=credits,
        price_amount=Decimal(price),
        currency="SAR",
    )


def _disable_all_gateways(db) -> None:
    for row in PaymentGatewayConfigRepository(db).list_all():
        row.enabled = False
    db.flush()


def _enable_gateway(db, code: str, *, credentials: dict | None = None) -> PaymentGatewayConfig:
    repo = PaymentGatewayConfigRepository(db)
    _disable_all_gateways(db)
    existing = repo.get_by_code(code)
    blob = encrypt_json(credentials or {}, settings=get_settings())
    if existing is None:
        existing = repo.create(
            PaymentGatewayConfig(
                code=code,
                enabled=True,
                test_mode=True,
                credentials_encrypted=blob,
                extra={},
            )
        )
    else:
        existing.enabled = True
        existing.credentials_encrypted = blob
    db.flush()
    db.commit()
    db.refresh(existing)
    return existing


def _grant_count(db, workspace_id: uuid.UUID, request_id: str) -> int:
    rows = list(
        db.scalars(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.workspace_id == workspace_id,
                CreditLedgerEntry.request_id == request_id,
                CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
            )
        )
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_resolves_single_enabled_noop(client, register_user, db) -> None:
    user = register_user(email="6a-reg@example.com")
    _create_workspace(client, user["access_token"], "Reg", "p6a-reg")
    enabled = GatewayRegistry(db).get_enabled()
    assert enabled.code == "noop"
    assert enabled.config.enabled is True


def test_registry_no_enabled_gateway(client, register_user, db) -> None:
    user = register_user(email="6a-none@example.com")
    ws = _create_workspace(client, user["access_token"], "None", "p6a-none")
    _disable_all_gateways(db)
    db.commit()
    with pytest.raises(AppError) as exc:
        GatewayRegistry(db).get_enabled()
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_UNAVAILABLE
    plan = _create_paid_plan(db, code="p6a_none_plan")
    db.commit()
    res = client.post(
        "/api/billing/checkout/subscription",
        headers=_ws_headers(user["access_token"], ws),
        json={"plan_id": str(plan.id)},
    )
    assert res.status_code == 503
    assert res.json()["code"] == "billing_gateway_unavailable"


def test_registry_disabled_gateway_ignored(client, register_user, db) -> None:
    user = register_user(email="6a-dis@example.com")
    _create_workspace(client, user["access_token"], "Dis", "p6a-dis")
    _enable_gateway(
        db,
        "clickpay",
        credentials={"profile_id": "1", "server_key": "sk"},
    )
    clickpay = PaymentGatewayConfigRepository(db).get_by_code("clickpay")
    assert clickpay is not None
    clickpay.enabled = False
    db.flush()
    noop = PaymentGatewayConfigRepository(db).get_by_code("noop")
    assert noop is not None
    noop.enabled = False
    db.commit()
    with pytest.raises(AppError) as exc:
        GatewayRegistry(db).get_enabled()
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_UNAVAILABLE


def test_database_prevents_two_enabled_configs(client, register_user, db) -> None:
    user = register_user(email="6a-uniq@example.com")
    _create_workspace(client, user["access_token"], "Uniq", "p6a-uniq")
    repo = PaymentGatewayConfigRepository(db)
    noop = repo.get_by_code("noop")
    assert noop is not None
    assert noop.enabled is True
    blob = encrypt_json({}, settings=get_settings())
    with pytest.raises(IntegrityError):
        repo.create(
            PaymentGatewayConfig(
                code="clickpay",
                enabled=True,
                test_mode=True,
                credentials_encrypted=blob,
            )
        )
    db.rollback()


def test_unsupported_adapter_fails_safely(client, register_user, db) -> None:
    user = register_user(email="6a-bad@example.com")
    ws = _create_workspace(client, user["access_token"], "Bad", "p6a-bad")
    _enable_gateway(db, "stripe", credentials={})
    plan = _create_paid_plan(db, code="p6a_bad_plan")
    db.commit()
    res = client.post(
        "/api/billing/checkout/subscription",
        headers=_ws_headers(user["access_token"], ws),
        json={"plan_id": str(plan.id)},
    )
    assert res.status_code == 503
    assert res.json()["code"] == "billing_gateway_unavailable"


# ---------------------------------------------------------------------------
# Catalog + Noop happy paths
# ---------------------------------------------------------------------------


def test_catalog_lists_priced_plans_and_active_packs(client, register_user, db) -> None:
    user = register_user(email="6a-cat@example.com")
    ws = _create_workspace(client, user["access_token"], "Cat", "p6a-cat")
    headers = _ws_headers(user["access_token"], ws)
    _create_paid_plan(db, code="p6a_cat_pro", price="120.00")
    _create_pack(db, code="p6a_cat_pack", credits=2500, price="40.00")
    db.commit()
    plans = client.get("/api/billing/plans", headers=headers)
    assert plans.status_code == 200, plans.text
    codes = {row["code"] for row in plans.json()}
    assert "p6a_cat_pro" in codes
    assert "bootstrap_dev" not in codes
    assert all(row["currency"] == "SAR" for row in plans.json())
    packs = client.get("/api/billing/credit-packs", headers=headers)
    assert packs.status_code == 200, packs.text
    assert packs.json()[0]["credits"] == 2500
    assert packs.json()[0]["price_amount"] == "40.00"


def test_noop_subscription_purchase_happy_path(client, register_user, db) -> None:
    user = register_user(email="6a-sub@example.com")
    ws = _create_workspace(client, user["access_token"], "Sub", "p6a-sub")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_paid_plan(db, code="p6a_sub_plan", tokens=777)
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/subscription",
        headers=headers,
        json={
            "plan_id": str(plan.id),
            "amount": "0.01",
            "gateway": "clickpay",
        },
    )
    assert checkout.status_code == 200, checkout.text
    body = checkout.json()
    assert body["status"] == "redirected"
    assert body["amount"] == "99.00"
    assert body["currency"] == "SAR"
    assert "server_key" not in checkout.text
    assert "credentials" not in checkout.text
    token = _return_token(body["redirect_url"])
    done = client.get(_as_test_path(body["redirect_url"]))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "paid"
    replay = client.get(
        f"/api/billing/return/noop/{body['purchase_id']}",
        params={"rt": token},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "paid"
    sub = client.get("/api/subscription", headers=headers)
    assert sub.json()["plan"]["code"] == "p6a_sub_plan"
    assert EntitlementService(db).get_int(
        uuid.UUID(ws["id"]), EntitlementKey.AI_TOKENS_DAILY
    ) == 777


def test_noop_credit_pack_purchase_happy_path(client, register_user, db) -> None:
    user = register_user(email="6a-cr@example.com")
    ws = _create_workspace(client, user["access_token"], "Cr", "p6a-cr")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p6a_cr_pack", credits=4000, price="15.50")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id), "credits": 999999, "amount": "1"},
    )
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["amount"] == "15.50"
    purchase_id = uuid.UUID(checkout.json()["purchase_id"])
    done = client.get(_as_test_path(checkout.json()["redirect_url"]))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "paid"
    replay = client.get(_as_test_path(checkout.json()["redirect_url"]))
    assert replay.json()["status"] == "paid"
    assert CreditService(db).get_balance(uuid.UUID(ws["id"])) == 4000
    request_id = purchase_grant_request_id(purchase_id)
    assert _grant_count(db, uuid.UUID(ws["id"]), request_id) == 1


def test_client_cannot_select_gateway_or_price(client, register_user, db) -> None:
    user = register_user(email="6a-price@example.com")
    ws = _create_workspace(client, user["access_token"], "Price", "p6a-price")
    plan = _create_paid_plan(db, code="p6a_price_plan", price="80.00")
    db.commit()
    res = client.post(
        "/api/billing/checkout/subscription",
        headers=_ws_headers(user["access_token"], ws),
        json={"plan_id": str(plan.id), "amount": "1.00", "gateway": "clickpay"},
    )
    assert res.json()["amount"] == "80.00"
    assert res.json()["redirect_url"]
    got = client.get(
        f"/api/billing/purchases/{res.json()['purchase_id']}",
        headers=_ws_headers(user["access_token"], ws),
    )
    assert got.status_code == 200
    assert "server_key" not in got.text
    assert got.json()["amount"] == "80.00"


def test_inactive_pack_and_unpriced_plan_rejected(client, register_user, db) -> None:
    user = register_user(email="6a-na@example.com")
    ws = _create_workspace(client, user["access_token"], "NA", "p6a-na")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p6a_na_pack")
    pack.active = False
    db.commit()
    res = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    assert res.status_code == 404
    assert res.json()["code"] == "credit_pack_unavailable"
    sub = client.get("/api/subscription", headers=headers)
    bootstrap_id = sub.json()["plan"]["id"]
    res = client.post(
        "/api/billing/checkout/subscription",
        headers=headers,
        json={"plan_id": bootstrap_id},
    )
    assert res.status_code == 404
    assert res.json()["code"] == "plan_unavailable"


# ---------------------------------------------------------------------------
# ClickPay mocked checkout + verification
# ---------------------------------------------------------------------------


def _clickpay_checkout_ok(tran_ref: str = "TST-REF-1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "tran_ref": tran_ref,
            "redirect_url": "https://secure.clickpay.com.sa/payment/page/hosted",
        },
    )


def _clickpay_query(status: str, amount: str = "99.00", currency: str = "SAR") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "tran_ref": "TST-REF-1",
            "cart_amount": amount,
            "cart_currency": currency,
            "payment_result": {"response_status": status, "response_message": status},
        },
    )


def _start_clickpay_subscription(client, register_user, db, *, email: str, slug: str):
    import json

    user = register_user(email=email)
    ws = _create_workspace(client, user["access_token"], slug, slug)
    plan = _create_paid_plan(db, code=f"{slug}_plan")
    _enable_gateway(
        db,
        "clickpay",
        credentials={"profile_id": "59020", "server_key": "sk_clickpay_secret"},
    )
    headers = _ws_headers(user["access_token"], ws)
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        route = router.post("/payment/request").mock(
            return_value=_clickpay_checkout_ok()
        )
        checkout = client.post(
            "/api/billing/checkout/subscription",
            headers=headers,
            json={"plan_id": str(plan.id)},
        )
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["redirect_url"].startswith("https://secure.clickpay.com.sa/")
    assert "sk_clickpay_secret" not in checkout.text
    payload = json.loads(route.calls.last.request.content)
    assert payload["cart_currency"] == "SAR"
    assert payload["tran_type"] == "sale"
    assert route.calls.last.request.headers["authorization"] == "sk_clickpay_secret"
    return_url = payload["return"]
    assert payload["callback"] is None
    assert "/api/billing/return/clickpay/" in return_url
    return user, ws, headers, checkout.json(), return_url


def test_clickpay_authorized_fulfills(client, register_user, db) -> None:
    user, ws, headers, checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-ok@example.com", slug="p6a-cp-ok"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(return_value=_clickpay_query("A"))
        done = client.get(_as_test_path(return_url) + "&respStatus=A")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "paid"
    assert (
        client.get("/api/subscription", headers=headers).json()["plan"]["code"]
        == "p6a-cp-ok_plan"
    )


def test_clickpay_callback_post_fulfills_via_query_not_body(client, register_user, db) -> None:
    _user, ws, headers, checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-cb@example.com", slug="p6a-cp-cb"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        query = router.post("/payment/query").mock(return_value=_clickpay_query("A"))
        done = client.post(
            _as_test_path(return_url),
            json={"respStatus": "D", "tranRef": "forged"},
            headers={"Accept": "application/json"},
        )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "paid"
    assert query.called
    assert (
        client.get("/api/subscription", headers=headers).json()["plan"]["code"]
        == "p6a-cp-cb_plan"
    )


def test_clickpay_declined_does_not_fulfill(client, register_user, db) -> None:
    _user, ws, headers, checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-d@example.com", slug="p6a-cp-d"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(return_value=_clickpay_query("D"))
        done = client.get(_as_test_path(return_url) + "&respStatus=A")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "failed"
    assert client.get("/api/subscription", headers=headers).json()["plan"]["code"] == "bootstrap_dev"
    assert CreditService(db).get_balance(uuid.UUID(ws["id"])) == 0


def test_clickpay_cancelled_does_not_fulfill(client, register_user, db) -> None:
    _user, _ws, headers, _checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-c@example.com", slug="p6a-cp-c"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(return_value=_clickpay_query("C"))
        done = client.get(_as_test_path(return_url))
    assert done.json()["status"] == "cancelled"
    assert client.get("/api/subscription", headers=headers).json()["plan"]["code"] == "bootstrap_dev"


def test_clickpay_failed_status_does_not_fulfill(client, register_user, db) -> None:
    _user, _ws, headers, _checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-e@example.com", slug="p6a-cp-e"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(return_value=_clickpay_query("E"))
        done = client.get(_as_test_path(return_url))
    assert done.json()["status"] == "failed"
    assert client.get("/api/subscription", headers=headers).json()["plan"]["code"] == "bootstrap_dev"


def test_clickpay_amount_mismatch_does_not_fulfill(client, register_user, db) -> None:
    _user, ws, headers, checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-amt@example.com", slug="p6a-cp-amt"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(
            return_value=_clickpay_query("A", amount="1.00")
        )
        done = client.get(_as_test_path(return_url))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "failed"
    assert client.get("/api/subscription", headers=headers).json()["plan"]["code"] == "bootstrap_dev"
    db.expire_all()
    fresh = TestingSessionLocal()
    try:
        row = fresh.get(Purchase, uuid.UUID(checkout["purchase_id"]))
        assert row is not None
        assert row.status == PurchaseStatus.FAILED.value
        assert (row.extra or {}).get("failure") == "amount_mismatch"
    finally:
        fresh.close()


def test_clickpay_currency_mismatch_does_not_fulfill(client, register_user, db) -> None:
    _user, _ws, headers, _checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-cur@example.com", slug="p6a-cp-cur"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(
            return_value=_clickpay_query("A", currency="USD")
        )
        done = client.get(_as_test_path(return_url))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "failed"
    assert client.get("/api/subscription", headers=headers).json()["plan"]["code"] == "bootstrap_dev"
    db.expire_all()
    fresh = TestingSessionLocal()
    try:
        row = fresh.get(Purchase, uuid.UUID(_checkout["purchase_id"]))
        assert row is not None
        assert row.status == PurchaseStatus.FAILED.value
        assert (row.extra or {}).get("failure") == "currency_mismatch"
    finally:
        fresh.close()


def test_return_browser_params_alone_cannot_mark_paid(client, register_user, db) -> None:
    _user, ws, headers, checkout, return_url = _start_clickpay_subscription(
        client, register_user, db, email="6a-cp-forge@example.com", slug="p6a-cp-forge"
    )
    with respx.mock(base_url=CLICKPAY_BASE) as router:
        router.post("/payment/query").mock(return_value=_clickpay_query("D"))
        done = client.get(
            _as_test_path(return_url) + "&respStatus=A&respMessage=Authorised"
        )
    assert done.json()["status"] == "failed"
    missing = client.get(
        f"/api/billing/return/clickpay/{checkout['purchase_id']}",
        params={"respStatus": "A"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "purchase_not_found"


# ---------------------------------------------------------------------------
# Concurrency / isolation / SYSTEM
# ---------------------------------------------------------------------------


def test_concurrent_return_does_not_double_grant(client, register_user, db) -> None:
    user = register_user(email="6a-race@example.com")
    ws = _create_workspace(client, user["access_token"], "Race", "p6a-race")
    pack = _create_pack(db, code="p6a_race_pack", credits=3000)
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user["access_token"], ws),
        json={"credit_pack_id": str(pack.id)},
    )
    assert checkout.status_code == 200, checkout.text
    token = _return_token(checkout.json()["redirect_url"])
    purchase_id = uuid.UUID(checkout.json()["purchase_id"])
    workspace_id = uuid.UUID(ws["id"])
    barrier = threading.Barrier(2, timeout=10)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            BillingService(session).complete_on_return(purchase_id, return_token=token)
            session.commit()
            with lock:
                results.append("ok")
        except AppError as exc:
            session.rollback()
            with lock:
                results.append(exc.category.value)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    assert results.count("ok") == 2
    db.expire_all()
    assert CreditService(db).get_balance(workspace_id) == 3000
    assert _grant_count(db, workspace_id, purchase_grant_request_id(purchase_id)) == 1


def test_cross_workspace_purchase_is_404(client, register_user, db) -> None:
    user_a = register_user(email="6a-iso-a@example.com")
    user_b = register_user(email="6a-iso-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p6a-iso-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p6a-iso-b")
    pack = _create_pack(db, code="p6a_iso_pack")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"credit_pack_id": str(pack.id)},
    )
    purchase_id = checkout.json()["purchase_id"]
    token = _return_token(checkout.json()["redirect_url"])
    missing = client.get(
        f"/api/billing/purchases/{purchase_id}",
        headers=_ws_headers(user_b["access_token"], ws_b),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "purchase_not_found"
    # Tenant B cannot complete A's purchase even with the raw token: purchase is
    # correlated by token, but GET purchase is workspace-scoped. Completing via
    # return token is the payer's browser; cross-tenant listing stays 404.
    assert (
        client.get(
            f"/api/billing/return/noop/{purchase_id}",
            headers=_ws_headers(user_b["access_token"], ws_b),
            params={"rt": "not-the-token"},
        ).status_code
        == 404
    )
    done = client.get(
        f"/api/billing/return/noop/{purchase_id}",
        params={"rt": token},
    )
    assert done.status_code == 200
    assert CreditService(db).get_balance(uuid.UUID(ws_b["id"])) == 0
    assert CreditService(db).get_balance(uuid.UUID(ws_a["id"])) == 1000


def test_system_workspace_cannot_checkout(client, register_user, db) -> None:
    from app.identity.repository import UserRepository

    register_user(email="6a-sys@example.com")
    plan = _create_paid_plan(db, code="p6a_sys_plan")
    db.commit()
    system = WorkspaceService(db).ensure_platform_knowledge_workspace()
    actor = UserRepository(db).get_by_email("6a-sys@example.com")
    assert actor is not None
    assert system.kind == WorkspaceKind.SYSTEM.value
    with pytest.raises(AppError) as exc:
        BillingService(db).create_subscription_checkout(system, actor, plan.id)
    assert exc.value.category == ErrorCategory.SYSTEM_WORKSPACE_CHECKOUT_FORBIDDEN


def test_wrong_return_token_is_not_found(client, register_user, db) -> None:
    user = register_user(email="6a-tok@example.com")
    ws = _create_workspace(client, user["access_token"], "Tok", "p6a-tok")
    pack = _create_pack(db, code="p6a_tok_pack")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user["access_token"], ws),
        json={"credit_pack_id": str(pack.id)},
    )
    pid = checkout.json()["purchase_id"]
    res = client.get(f"/api/billing/return/noop/{pid}", params={"rt": "forged-token"})
    assert res.status_code == 404
    assert res.json()["code"] == "purchase_not_found"
    row = db.scalar(select(Purchase).where(Purchase.id == uuid.UUID(pid)))
    assert row is not None
    assert row.status == PurchaseStatus.REDIRECTED.value


def test_unauthenticated_catalog_rejected(client) -> None:
    assert client.get("/api/billing/plans").status_code == 401
    assert client.get("/api/billing/credit-packs").status_code == 401
