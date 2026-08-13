"""Idempotent local/dev demo catalog (plans + credit packs).

Not Geem commercial pricing. Never seeded in test or production.
Existing rows are not overwritten so operators can tune them.
`ensure_local_demo_catalog` / `python -m app.billing.seed` also enable a
checkout gateway (ClickPay from env, otherwise Noop).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.models import CreditPack, Plan, PlanStatus
from app.billing.money import normalize_currency, quantize_money
from app.billing.service import CreditPackService, PlanService
from app.core.config import Settings, get_settings
from app.entitlements.keys import EntitlementKey

DEMO_CATALOG_ENVS = frozenset({"local", "dev", "development"})

DEMO_CATALOG_METADATA = {
    "kind": "demo",
    "commercial": False,
    "note": "Local/dev demo catalog — not Geem product pricing.",
}

_GIB = 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DemoPlanSpec:
    code: str
    name: str
    description: str
    price_amount: str
    entitlements: dict[EntitlementKey, int]


@dataclass(frozen=True, slots=True)
class DemoPackSpec:
    code: str
    name: str
    description: str
    credits: int
    price_amount: str


DEMO_PLANS: tuple[DemoPlanSpec, ...] = (
    DemoPlanSpec(
        code="demo_starter",
        name="Starter (demo)",
        description="Small demo workspace: a few Experts and modest AI token limits.",
        price_amount="49.00",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY: 50_000,
            EntitlementKey.AI_TOKENS_WEEKLY: 250_000,
            EntitlementKey.AI_TOKENS_MONTHLY: 1_000_000,
            EntitlementKey.EXPERTS_LIMIT: 3,
            EntitlementKey.STORAGE_BYTES: 1 * _GIB,
        },
    ),
    DemoPlanSpec(
        code="demo_pro",
        name="Pro (demo)",
        description="Larger demo workspace for everyday billing and quota testing.",
        price_amount="149.00",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY: 200_000,
            EntitlementKey.AI_TOKENS_WEEKLY: 1_000_000,
            EntitlementKey.AI_TOKENS_MONTHLY: 4_000_000,
            EntitlementKey.EXPERTS_LIMIT: 15,
            EntitlementKey.STORAGE_BYTES: 10 * _GIB,
        },
    ),
    DemoPlanSpec(
        code="demo_business",
        name="Business (demo)",
        description="Highest demo limits so you can compare plan switches after checkout.",
        price_amount="399.00",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY: 1_000_000,
            EntitlementKey.AI_TOKENS_WEEKLY: 5_000_000,
            EntitlementKey.AI_TOKENS_MONTHLY: 20_000_000,
            EntitlementKey.EXPERTS_LIMIT: 50,
            EntitlementKey.STORAGE_BYTES: 50 * _GIB,
        },
    ),
)

DEMO_CREDIT_PACKS: tuple[DemoPackSpec, ...] = (
    DemoPackSpec(
        code="demo_credits_1k",
        name="1,000 credits (demo)",
        description="Small AI credit pack for checkout testing.",
        credits=1_000,
        price_amount="25.00",
    ),
    DemoPackSpec(
        code="demo_credits_5k",
        name="5,000 credits (demo)",
        description="Medium AI credit pack for checkout testing.",
        credits=5_000,
        price_amount="99.00",
    ),
    DemoPackSpec(
        code="demo_credits_20k",
        name="20,000 credits (demo)",
        description="Large AI credit pack for checkout testing.",
        credits=20_000,
        price_amount="349.00",
    ),
)


def demo_catalog_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return cfg.app_env.lower() in DEMO_CATALOG_ENVS


def seed_demo_catalog(
    db: Session, settings: Settings | None = None
) -> tuple[list[Plan], list[CreditPack]]:
    """Insert missing demo plans and credit packs. Always runs (callers gate env)."""
    cfg = settings or get_settings()
    plans = [_ensure_demo_plan(db, cfg, spec) for spec in DEMO_PLANS]
    packs = [_ensure_demo_pack(db, cfg, spec) for spec in DEMO_CREDIT_PACKS]
    db.flush()
    return plans, packs


def ensure_local_demo_catalog(
    db: Session, settings: Settings | None = None
) -> tuple[list[Plan], list[CreditPack]] | None:
    """No-op outside local/dev. Safe to call from bootstrap and workspace provision."""
    cfg = settings or get_settings()
    if not demo_catalog_enabled(cfg):
        return None
    plans, packs = seed_demo_catalog(db, cfg)
    from app.billing.provisioning import ensure_local_checkout_gateway

    ensure_local_checkout_gateway(db, settings=cfg)
    return plans, packs


def _ensure_demo_plan(db: Session, settings: Settings, spec: DemoPlanSpec) -> Plan:
    svc = PlanService(db, settings)
    plan = svc.plans.get_by_code(spec.code)
    if plan is None:
        try:
            with db.begin_nested():
                plan = Plan(
                    code=spec.code,
                    name=spec.name,
                    description=spec.description,
                    status=PlanStatus.ACTIVE.value,
                    price_amount=quantize_money(spec.price_amount),
                    currency=normalize_currency("SAR"),
                    extra=dict(DEMO_CATALOG_METADATA),
                )
                svc.plans.create(plan)
        except IntegrityError:
            plan = svc.plans.get_by_code(spec.code)
            if plan is None:
                raise

    if plan.price_amount is None:
        plan.price_amount = quantize_money(spec.price_amount)
        plan.currency = normalize_currency(plan.currency or "SAR")
        db.flush()

    for key, value in spec.entitlements.items():
        if svc.plans.get_entitlement(plan.id, key.value) is not None:
            continue
        try:
            with db.begin_nested():
                svc.set_entitlement(plan.id, key.value, value)
        except IntegrityError:
            continue

    return svc.plans.get_by_id(plan.id) or plan


def _ensure_demo_pack(db: Session, settings: Settings, spec: DemoPackSpec) -> CreditPack:
    svc = CreditPackService(db, settings)
    existing = svc.packs.get_by_code(spec.code)
    if existing is not None:
        return existing
    try:
        with db.begin_nested():
            pack = CreditPack(
                code=spec.code,
                name=spec.name,
                description=spec.description,
                credits=spec.credits,
                price_amount=quantize_money(spec.price_amount),
                currency=normalize_currency("SAR"),
                active=True,
                extra=dict(DEMO_CATALOG_METADATA),
            )
            return svc.packs.create(pack)
    except IntegrityError:
        winner = svc.packs.get_by_code(spec.code)
        if winner is None:
            raise
        return winner


def main() -> None:
    """Seed demo plans/packs. From apps/api: python -m app.billing.seed"""
    settings = get_settings()
    if not demo_catalog_enabled(settings):
        raise SystemExit(
            f"Demo catalog is only seeded when APP_ENV is local/dev "
            f"(current={settings.app_env!r})."
        )
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        from app.billing.provisioning import ensure_local_checkout_gateway

        plans, packs = seed_demo_catalog(db, settings)
        gateway = ensure_local_checkout_gateway(db, settings=settings)
        db.commit()
        print("Demo billing catalog ready:")
        for plan in plans:
            print(f"  plan {plan.code}  {plan.name}  {plan.price_amount} {plan.currency}")
        for pack in packs:
            print(
                f"  pack {pack.code}  {pack.name}  "
                f"{pack.credits} credits / {pack.price_amount} {pack.currency}"
            )
        if gateway is not None:
            print(f"  gateway {gateway.code}  enabled={gateway.enabled}  test_mode={gateway.test_mode}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
