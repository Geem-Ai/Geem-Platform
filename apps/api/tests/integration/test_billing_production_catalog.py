"""Production plan + credit pack seed."""

from __future__ import annotations

from decimal import Decimal

from app.billing.checkout import BillingService
from app.billing.seed import (
    PRODUCTION_CREDIT_PACKS,
    PRODUCTION_PLANS,
    ensure_local_demo_catalog,
    ensure_production_catalog,
    seed_production_catalog,
)
from app.billing.service import PlanService
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


def _test_settings() -> Settings:
    return Settings(_env_file=None, app_env="test", jwt_secret="x" * 40)


def test_seed_production_catalog_is_idempotent(db) -> None:
    first_plans, first_packs = seed_production_catalog(db)
    assert {plan.code for plan in first_plans} == {spec.code for spec in PRODUCTION_PLANS}
    assert {pack.code for pack in first_packs} == {
        spec.code for spec in PRODUCTION_CREDIT_PACKS
    }
    starter = next(plan for plan in first_plans if plan.code == "starter")
    assert starter.name == "Starter"
    assert starter.price_amount == Decimal("49.00")
    assert starter.currency == "SAR"
    assert starter.extra.get("commercial") is True
    keys = {row.key for row in starter.entitlements}
    assert EntitlementKey.AI_TOKENS_DAILY.value in keys
    assert EntitlementKey.EXPERTS_LIMIT.value in keys
    assert EntitlementKey.API_REQUESTS_PER_MINUTE.value in keys

    pack_1m = next(pack for pack in first_packs if pack.code == "credits_1m")
    assert pack_1m.credits == 1_000_000
    assert pack_1m.price_amount == Decimal("69.00")
    assert pack_1m.extra.get("commercial") is True

    second_plans, second_packs = seed_production_catalog(db)
    assert [plan.id for plan in first_plans] == [plan.id for plan in second_plans]
    assert [pack.id for pack in first_packs] == [pack.id for pack in second_packs]


def test_seed_production_catalog_does_not_overwrite_tuned_values(db) -> None:
    plans, packs = seed_production_catalog(db)
    starter = next(plan for plan in plans if plan.code == "starter")
    starter.price_amount = Decimal("12.00")
    starter.name = "Tuned starter"
    packs[0].credits = 42
    db.flush()

    again, packs_again = seed_production_catalog(db)
    reloaded = next(plan for plan in again if plan.code == "starter")
    assert reloaded.price_amount == Decimal("12.00")
    assert reloaded.name == "Tuned starter"
    assert packs_again[0].credits == 42


def test_production_plans_and_packs_are_purchasable(db) -> None:
    PlanService(db).ensure_bootstrap_plan()
    seed_production_catalog(db)
    listed = BillingService(db).list_purchasable_plans()
    codes = [plan.code for plan in listed]
    assert codes == ["starter", "pro", "business"]
    packs = BillingService(db).list_active_credit_packs()
    assert [pack.code for pack in packs] == [
        "credits_1m",
        "credits_5m",
        "credits_10m",
    ]
    by_code = {pack.code: pack for pack in packs}
    assert by_code["credits_1m"].credits == 1_000_000
    assert by_code["credits_1m"].price_amount == Decimal("69.00")
    assert by_code["credits_5m"].credits == 5_000_000
    assert by_code["credits_5m"].price_amount == Decimal("229.00")
    assert by_code["credits_10m"].credits == 10_000_000
    assert by_code["credits_10m"].price_amount == Decimal("399.00")


def test_ensure_production_catalog_skips_non_production_env(db) -> None:
    assert ensure_production_catalog(db, settings=_local_settings()) is None
    assert ensure_production_catalog(db, settings=_test_settings()) is None
    assert BillingService(db).list_purchasable_plans() == []
    assert BillingService(db).list_active_credit_packs() == []

    seeded = ensure_production_catalog(db, settings=_prod_settings())
    assert seeded is not None
    assert len(seeded[0]) == len(PRODUCTION_PLANS)
    assert len(seeded[1]) == len(PRODUCTION_CREDIT_PACKS)


def test_demo_and_production_gates_are_mutually_exclusive(db) -> None:
    assert ensure_local_demo_catalog(db, settings=_prod_settings()) is None
    assert ensure_production_catalog(db, settings=_local_settings()) is None

    prod = ensure_production_catalog(db, settings=_prod_settings())
    assert prod is not None
    assert [p.code for p in prod[1]] == ["credits_1m", "credits_5m", "credits_10m"]


def test_production_catalog_http_list(client, register_user, db) -> None:
    user = register_user(email="prod-cat@example.com")
    ws = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={"name": "Prod", "slug": "prod-cat"},
    )
    assert ws.status_code in {200, 201}, ws.text
    seed_production_catalog(db)
    db.commit()
    headers = {
        "Authorization": f"Bearer {user['access_token']}",
        "X-Workspace-Id": ws.json()["id"],
    }
    plans = client.get("/api/billing/plans", headers=headers)
    assert plans.status_code == 200, plans.text
    codes = [row["code"] for row in plans.json()]
    assert codes == ["starter", "pro", "business"]
    assert "bootstrap_dev" not in codes
    packs = client.get("/api/billing/credit-packs", headers=headers)
    assert packs.status_code == 200, packs.text
    assert [row["code"] for row in packs.json()] == [
        "credits_1m",
        "credits_5m",
        "credits_10m",
    ]
    amounts = {
        row["code"]: (int(row["credits"]), str(row["price_amount"]))
        for row in packs.json()
    }
    assert amounts["credits_1m"] == (1_000_000, "69.00")
    assert amounts["credits_5m"] == (5_000_000, "229.00")
    assert amounts["credits_10m"] == (10_000_000, "399.00")
