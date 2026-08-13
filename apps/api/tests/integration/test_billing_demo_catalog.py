"""Local/dev demo plan + credit pack seed."""

from __future__ import annotations

from decimal import Decimal

from app.billing.checkout import BillingService
from app.billing.gateways.registry import GatewayRegistry
from app.billing.provisioning import ensure_local_checkout_gateway
from app.billing.repository import PaymentGatewayConfigRepository
from app.billing.seed import (
    DEMO_CREDIT_PACKS,
    DEMO_PLANS,
    ensure_local_demo_catalog,
    seed_demo_catalog,
)
from app.billing.service import PlanService
from app.common.crypto import decrypt_json
from app.core.config import Settings
from app.entitlements.keys import EntitlementKey


def _local_settings() -> Settings:
    return Settings(_env_file=None, app_env="local", jwt_secret="x" * 40)


def _prod_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        cors_origins="https://app.geem.ai",
    )


def test_seed_demo_catalog_is_idempotent(db) -> None:
    first_plans, first_packs = seed_demo_catalog(db)
    assert {plan.code for plan in first_plans} == {spec.code for spec in DEMO_PLANS}
    assert {pack.code for pack in first_packs} == {spec.code for spec in DEMO_CREDIT_PACKS}
    starter = next(plan for plan in first_plans if plan.code == "demo_starter")
    assert starter.price_amount == Decimal("49.00")
    assert starter.currency == "SAR"
    keys = {row.key for row in starter.entitlements}
    assert EntitlementKey.AI_TOKENS_DAILY.value in keys
    assert EntitlementKey.EXPERTS_LIMIT.value in keys

    second_plans, second_packs = seed_demo_catalog(db)
    assert [plan.id for plan in first_plans] == [plan.id for plan in second_plans]
    assert [pack.id for pack in first_packs] == [pack.id for pack in second_packs]


def test_seed_demo_catalog_does_not_overwrite_tuned_values(db) -> None:
    plans, packs = seed_demo_catalog(db)
    starter = next(plan for plan in plans if plan.code == "demo_starter")
    starter.price_amount = Decimal("12.00")
    starter.name = "Tuned starter"
    packs[0].credits = 42
    db.flush()

    again, packs_again = seed_demo_catalog(db)
    reloaded = next(plan for plan in again if plan.code == "demo_starter")
    assert reloaded.price_amount == Decimal("12.00")
    assert reloaded.name == "Tuned starter"
    assert packs_again[0].credits == 42


def test_demo_plans_are_purchasable_and_bootstrap_is_not(db) -> None:
    PlanService(db).ensure_bootstrap_plan()
    seed_demo_catalog(db)
    listed = BillingService(db).list_purchasable_plans()
    codes = [plan.code for plan in listed]
    assert codes == ["demo_starter", "demo_pro", "demo_business"]
    packs = BillingService(db).list_active_credit_packs()
    assert [pack.code for pack in packs] == [
        "demo_credits_1k",
        "demo_credits_5k",
        "demo_credits_20k",
    ]


def test_seed_without_clickpay_env_enables_noop(db) -> None:
    settings = _local_settings()
    seed_demo_catalog(db, settings)
    gateway = ensure_local_checkout_gateway(db, settings=settings)
    assert gateway is not None
    assert gateway.code == "noop"
    assert GatewayRegistry(db, settings).get_enabled().code == "noop"


def test_seed_with_clickpay_env_enables_clickpay_and_disables_noop(db) -> None:
    ensure_local_checkout_gateway(db, settings=_local_settings())
    assert PaymentGatewayConfigRepository(db).get_by_code("noop") is not None
    clickpay_settings = Settings(
        _env_file=None,
        app_env="local",
        jwt_secret="x" * 40,
        clickpay_profile_id="43334",
        clickpay_server_key="sk_clickpay_test",
        clickpay_test_mode=True,
        clickpay_base_url="https://secure.clickpay.com.sa",
    )
    seed_demo_catalog(db, clickpay_settings)
    gateway = ensure_local_checkout_gateway(db, settings=clickpay_settings)
    assert gateway is not None
    assert gateway.code == "clickpay"
    assert gateway.enabled is True
    assert gateway.test_mode is True
    noop = PaymentGatewayConfigRepository(db).get_by_code("noop")
    assert noop is not None
    assert noop.enabled is False
    stored = decrypt_json(gateway.credentials_encrypted, settings=clickpay_settings)
    assert stored["profile_id"] == "43334"
    assert stored["server_key"] == "sk_clickpay_test"
    assert GatewayRegistry(db, clickpay_settings).get_enabled().code == "clickpay"


def test_ensure_local_demo_catalog_skips_non_local_env(db) -> None:
    assert ensure_local_demo_catalog(db, settings=_prod_settings()) is None
    assert BillingService(db).list_purchasable_plans() == []
    assert BillingService(db).list_active_credit_packs() == []

    seeded = ensure_local_demo_catalog(db, settings=_local_settings())
    assert seeded is not None
    assert len(seeded[0]) == len(DEMO_PLANS)


def test_demo_catalog_http_list(client, register_user, db) -> None:
    user = register_user(email="demo-cat@example.com")
    ws = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={"name": "Demo", "slug": "demo-cat"},
    )
    assert ws.status_code in {200, 201}, ws.text
    seed_demo_catalog(db)
    db.commit()
    headers = {
        "Authorization": f"Bearer {user['access_token']}",
        "X-Workspace-Id": ws.json()["id"],
    }
    plans = client.get("/api/billing/plans", headers=headers)
    assert plans.status_code == 200, plans.text
    codes = [row["code"] for row in plans.json()]
    assert codes == ["demo_starter", "demo_pro", "demo_business"]
    assert "bootstrap_dev" not in codes
    packs = client.get("/api/billing/credit-packs", headers=headers)
    assert packs.status_code == 200, packs.text
    assert [row["code"] for row in packs.json()] == [
        "demo_credits_1k",
        "demo_credits_5k",
        "demo_credits_20k",
    ]
