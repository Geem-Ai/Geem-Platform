"""ZATCA simplified tax invoice download on paid purchases."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.billing.models import Purchase, PurchaseStatus
from app.core.errors import ErrorCategory
from tests.integration.test_billing_phase6a import (
    _as_test_path,
    _create_pack,
    _create_workspace,
    _ws_headers,
)


def test_invoice_pdf_for_paid_purchase_only(client, register_user, db) -> None:
    user = register_user(email="inv-paid@example.com")
    ws = _create_workspace(client, user["access_token"], "Invoice Co", "p-inv-paid")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p_inv_pack", credits=4000, price="25.00")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    assert checkout.status_code == 200, checkout.text
    purchase_id = checkout.json()["purchase_id"]
    pending = client.get(f"/api/billing/purchases/{purchase_id}/invoice", headers=headers)
    assert pending.status_code == 409, pending.text
    assert pending.json()["code"] == ErrorCategory.INVOICE_NOT_AVAILABLE.value

    done = client.get(_as_test_path(checkout.json()["redirect_url"]))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "paid"

    invoice = client.get(f"/api/billing/purchases/{purchase_id}/invoice", headers=headers)
    assert invoice.status_code == 200, invoice.text
    assert invoice.headers["content-type"].startswith("application/pdf")
    assert invoice.content.startswith(b"%PDF")
    disposition = invoice.headers.get("content-disposition") or ""
    assert "GEEM-" in disposition
    assert ".pdf" in disposition

    row = db.get(Purchase, uuid.UUID(purchase_id))
    assert row is not None
    assert row.status == PurchaseStatus.PAID.value
    assert row.invoice_number
    number = row.invoice_number
    assert number.startswith("GEEM-")
    snapshot = row.invoice_snapshot or {}
    assert snapshot.get("invoice_type") == "simplified_tax_invoice"
    assert snapshot.get("total_amount") == "25.00"
    assert snapshot.get("vat_amount")
    assert snapshot.get("zatca_qr")
    assert snapshot.get("seller", {}).get("vat_number")

    replay = client.get(f"/api/billing/purchases/{purchase_id}/invoice", headers=headers)
    assert replay.status_code == 200
    db.expire_all()
    again = db.get(Purchase, uuid.UUID(purchase_id))
    assert again is not None
    assert again.invoice_number == number


def test_invoice_download_is_workspace_scoped(client, register_user, db) -> None:
    user_a = register_user(email="inv-a@example.com")
    user_b = register_user(email="inv-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p-inv-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p-inv-b")
    pack = _create_pack(db, code="p_inv_iso", credits=100, price="10.00")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"credit_pack_id": str(pack.id)},
    )
    assert checkout.status_code == 200, checkout.text
    client.get(_as_test_path(checkout.json()["redirect_url"]))
    purchase_id = checkout.json()["purchase_id"]

    missing = client.get(
        f"/api/billing/purchases/{purchase_id}/invoice",
        headers=_ws_headers(user_b["access_token"], ws_b),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == ErrorCategory.PURCHASE_NOT_FOUND.value


def test_invoice_sequence_failure_does_not_roll_back_payment(
    client, register_user, db
) -> None:
    user = register_user(email="inv-savepoint@example.com")
    ws = _create_workspace(client, user["access_token"], "Savepoint", "p-inv-sp")
    headers = _ws_headers(user["access_token"], ws)
    pack = _create_pack(db, code="p_inv_sp", credits=200, price="8.00")
    db.commit()
    checkout = client.post(
        "/api/billing/checkout/credit-packs",
        headers=headers,
        json={"credit_pack_id": str(pack.id)},
    )
    assert checkout.status_code == 200, checkout.text
    purchase_id = checkout.json()["purchase_id"]
    db.execute(
        text(
            "ALTER SEQUENCE purchase_invoice_number_seq "
            "RENAME TO purchase_invoice_number_seq_hidden"
        )
    )
    db.commit()
    try:
        done = client.get(_as_test_path(checkout.json()["redirect_url"]))
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "paid"
        db.expire_all()
        row = db.get(Purchase, uuid.UUID(purchase_id))
        assert row is not None
        assert row.status == PurchaseStatus.PAID.value
        assert row.invoice_number is None
    finally:
        db.execute(
            text(
                "ALTER SEQUENCE IF EXISTS purchase_invoice_number_seq_hidden "
                "RENAME TO purchase_invoice_number_seq"
            )
        )
        db.commit()

    invoice = client.get(f"/api/billing/purchases/{purchase_id}/invoice", headers=headers)
    assert invoice.status_code == 200, invoice.text
    db.expire_all()
    issued = db.get(Purchase, uuid.UUID(purchase_id))
    assert issued is not None
    assert issued.invoice_number
