"""Phase 6B — catalog DTO fields, purchase list isolation, SPA return handoff."""

from __future__ import annotations

import json
import uuid
from urllib.parse import parse_qs, urlparse

from app.billing.models import PurchaseStatus
from app.core.errors import ErrorCategory
from tests.integration.test_billing_phase6a import (
    _as_test_path,
    _create_pack,
    _create_paid_plan,
    _create_workspace,
    _ws_headers,
)


def test_plans_list_exposes_entitlements_not_internal_fields(client, register_user, db) -> None:
    user = register_user(email="6b-plans@example.com")
    ws = _create_workspace(client, user["access_token"], "Plans", "p6b-plans")
    headers = _ws_headers(user["access_token"], ws)
    _create_paid_plan(db, code="p6b_pro", price="99.00", tokens=1234)
    db.commit()
    res = client.get("/api/billing/plans", headers=headers)
    assert res.status_code == 200, res.text
    row = next(item for item in res.json() if item["code"] == "p6b_pro")
    assert row["price_amount"] == "99.00"
    assert row["currency"] == "SAR"
    keys = {item["key"] for item in row["entitlements"]}
    assert "ai_tokens_daily" in keys
    ordered = [item["key"] for item in row["entitlements"]]
    assert ordered.index("ai_tokens_daily") < ordered.index("ai_tokens_weekly")
    assert ordered.index("ai_tokens_weekly") < ordered.index("ai_tokens_monthly")
    daily = next(item for item in row["entitlements"] if item["key"] == "ai_tokens_daily")
    assert daily["value"] == 1234
    dumped = json.dumps(row)
    assert "server_key" not in dumped
    assert "credentials" not in dumped
    assert "extra" not in row
    assert "metadata" not in row


def test_credit_packs_list_only_active(client, register_user, db) -> None:
    user = register_user(email="6b-packs@example.com")
    ws = _create_workspace(client, user["access_token"], "Packs", "p6b-packs")
    headers = _ws_headers(user["access_token"], ws)
    active = _create_pack(db, code="p6b_live", credits=500, price="12.00")
    inactive = _create_pack(db, code="p6b_hidden", credits=9000, price="1.00")
    inactive.active = False
    db.commit()
    res = client.get("/api/billing/credit-packs", headers=headers)
    assert res.status_code == 200, res.text
    ids = {row["id"] for row in res.json()}
    assert str(active.id) in ids
    assert str(inactive.id) not in ids
    assert all(row["active"] is True for row in res.json())


def test_purchase_list_and_detail_are_workspace_scoped(client, register_user, db) -> None:
    user_a = register_user(email="6b-list-a@example.com")
    user_b = register_user(email="6b-list-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p6b-list-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p6b-list-b")
    pack = _create_pack(db, code="p6b_list_pack", credits=800, price="20.00")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"credit_pack_id": str(pack.id)},
    )
    assert checkout.status_code == 200, checkout.text
    purchase_id = checkout.json()["purchase_id"]
    listed_a = client.get(
        "/api/billing/purchases",
        headers=_ws_headers(user_a["access_token"], ws_a),
    )
    assert listed_a.status_code == 200, listed_a.text
    body_a = listed_a.json()
    assert body_a["total"] == 1
    assert body_a["items"][0]["id"] == purchase_id
    assert body_a["items"][0]["kind"] == "credit_pack"
    assert body_a["items"][0]["item_name"]
    assert body_a["items"][0]["credits"] == 800
    dumped = json.dumps(body_a)
    assert "redirect_url" not in dumped
    assert "server_key" not in dumped
    assert "return_token" not in dumped
    assert "credentials" not in dumped
    assert "payload" not in body_a["items"][0]

    listed_b = client.get(
        "/api/billing/purchases",
        headers=_ws_headers(user_b["access_token"], ws_b),
    )
    assert listed_b.status_code == 200
    assert listed_b.json()["total"] == 0
    assert listed_b.json()["items"] == []

    missing = client.get(
        f"/api/billing/purchases/{purchase_id}",
        headers=_ws_headers(user_b["access_token"], ws_b),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == ErrorCategory.PURCHASE_NOT_FOUND.value

    own = client.get(
        f"/api/billing/purchases/{purchase_id}",
        headers=_ws_headers(user_a["access_token"], ws_a),
    )
    assert own.status_code == 200
    assert own.json()["id"] == purchase_id
    assert "redirect_url" not in own.json()


def test_purchase_list_filters_and_pagination(client, register_user, db) -> None:
    user = register_user(email="6b-page@example.com")
    ws = _create_workspace(client, user["access_token"], "Page", "p6b-page")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p6b_page_pack")
    plan = _create_paid_plan(db, code="p6b_page_plan")
    db.commit()
    client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    client.post(
        "/api/billing/checkout/subscription",
        headers=headers,
        json={"plan_id": str(plan.id)},
    )
    page = client.get("/api/billing/purchases?limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1
    packs = client.get("/api/billing/purchases?kind=credit_pack", headers=headers)
    assert packs.json()["total"] == 1
    assert packs.json()["items"][0]["kind"] == "credit_pack"
    bad = client.get("/api/billing/purchases?kind=not-a-kind", headers=headers)
    assert bad.status_code == 422
    pending = client.get("/api/billing/purchases?status=pending", headers=headers)
    assert pending.status_code == 200
    assert pending.json()["total"] == 2
    assert {row["status"] for row in pending.json()["items"]} <= {"pending", "redirected"}


def test_html_return_redirects_to_spa_without_trusted_status(client, register_user, db) -> None:
    user = register_user(email="6b-redir@example.com")
    ws = _create_workspace(client, user["access_token"], "Redir", "p6b-redir")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p6b_redir_pack")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    purchase_id = checkout.json()["purchase_id"]
    res = client.get(
        _as_test_path(checkout.json()["redirect_url"]),
        headers={"Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    location = res.headers["location"]
    parsed = urlparse(location)
    assert parsed.path == "/billing/payment/success"
    query = parse_qs(parsed.query)
    assert query["purchase"] == [purchase_id]
    assert "rt" not in query
    assert "respStatus" not in query
    assert "tranRef" not in query
    assert "status" not in query
    assert "server_key" not in location
    assert "authorization" not in location.lower()
    got = client.get(f"/api/billing/purchases/{purchase_id}", headers=headers)
    assert got.json()["status"] == PurchaseStatus.PAID.value


def test_json_return_still_available_for_api_clients(client, register_user, db) -> None:
    user = register_user(email="6b-json@example.com")
    ws = _create_workspace(client, user["access_token"], "Json", "p6b-json")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p6b_json_pack")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    res = client.get(
        _as_test_path(checkout.json()["redirect_url"]),
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "paid"
    assert res.json()["id"] == checkout.json()["purchase_id"]
    assert uuid.UUID(res.json()["id"])
