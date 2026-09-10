"""Idempotent billing catalogs (plans + credit packs).

* Local/dev: demo catalog — not Geem commercial pricing.
* Production: commercial Workspace subscription + credit packs.

Never seeded in test. Existing rows are not overwritten so operators can tune
them. ``ensure_local_demo_catalog`` also enables a checkout gateway (ClickPay
from env, otherwise Noop). ``python -m app.billing.seed`` branches on APP_ENV.
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

# Querying any mapped class configures every mapper on the shared registry, so a
# standalone entrypoint must register them all first. Workspace refers to User by
# name, which stays unresolvable while only the billing package is imported.
import app.db.models  # noqa: E402,F401

DEMO_CATALOG_ENVS = frozenset({"local", "dev", "development"})
PRODUCTION_CATALOG_ENVS = frozenset({"production"})

DEMO_CATALOG_METADATA = {
    "kind": "demo",
    "commercial": False,
    "note": "Local/dev demo catalog — not Geem product pricing.",
}

PRODUCTION_CATALOG_METADATA = {
    "kind": "workspace",
    "commercial": True,
    "note": "Geem Workspace subscription catalog.",
}

_GIB = 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PlanSpec:
    code: str
    name: str
    description: str
    price_amount: str
    entitlements: dict[EntitlementKey, int]


@dataclass(frozen=True, slots=True)
class PackSpec:
    code: str
    name: str
    description: str
    credits: int
    price_amount: str


# Back-compat aliases for tests / callers that imported the old names.
DemoPlanSpec = PlanSpec
DemoPackSpec = PackSpec

# Legacy codes → current codes (rename in place so re-seed does not duplicate rows).
DEMO_PLAN_CODE_ALIASES: dict[str, str] = {
    "demo_starter": "starter",
    "demo_pro": "pro",
    "demo_business": "business",
}

_STARTER_ENTITLEMENTS: dict[EntitlementKey, int] = {
    EntitlementKey.AI_TOKENS_DAILY: 50_000,
    EntitlementKey.AI_TOKENS_WEEKLY: 250_000,
    EntitlementKey.AI_TOKENS_MONTHLY: 1_000_000,
    EntitlementKey.EXPERTS_LIMIT: 3,
    EntitlementKey.STORAGE_BYTES: 1 * _GIB,
    EntitlementKey.API_REQUESTS_PER_MINUTE: 60,
}

_PRO_ENTITLEMENTS: dict[EntitlementKey, int] = {
    EntitlementKey.AI_TOKENS_DAILY: 200_000,
    EntitlementKey.AI_TOKENS_WEEKLY: 1_000_000,
    EntitlementKey.AI_TOKENS_MONTHLY: 4_000_000,
    EntitlementKey.EXPERTS_LIMIT: 15,
    EntitlementKey.STORAGE_BYTES: 10 * _GIB,
    EntitlementKey.API_REQUESTS_PER_MINUTE: 120,
}

_BUSINESS_ENTITLEMENTS: dict[EntitlementKey, int] = {
    EntitlementKey.AI_TOKENS_DAILY: 1_000_000,
    EntitlementKey.AI_TOKENS_WEEKLY: 5_000_000,
    EntitlementKey.AI_TOKENS_MONTHLY: 20_000_000,
    EntitlementKey.EXPERTS_LIMIT: 50,
    EntitlementKey.STORAGE_BYTES: 50 * _GIB,
    EntitlementKey.API_REQUESTS_PER_MINUTE: 300,
}

DEMO_PLANS: tuple[PlanSpec, ...] = (
    PlanSpec(
        code="starter",
        name="Starter (demo)",
        description="Small demo workspace: a few Experts and modest AI token limits.",
        price_amount="49.00",
        entitlements=_STARTER_ENTITLEMENTS,
    ),
    PlanSpec(
        code="pro",
        name="Pro (demo)",
        description="Larger demo workspace for everyday billing and quota testing.",
        price_amount="149.00",
        entitlements=_PRO_ENTITLEMENTS,
    ),
    PlanSpec(
        code="business",
        name="Business (demo)",
        description="Highest demo limits so you can compare plan switches after checkout.",
        price_amount="399.00",
        entitlements=_BUSINESS_ENTITLEMENTS,
    ),
)

DEMO_CREDIT_PACKS: tuple[PackSpec, ...] = (
    PackSpec(
        code="demo_credits_1k",
        name="1,000 credits (demo)",
        description="Small AI credit pack for checkout testing.",
        credits=1_000,
        price_amount="25.00",
    ),
    PackSpec(
        code="demo_credits_5k",
        name="5,000 credits (demo)",
        description="Medium AI credit pack for checkout testing.",
        credits=5_000,
        price_amount="99.00",
    ),
    PackSpec(
        code="demo_credits_20k",
        name="20,000 credits (demo)",
        description="Large AI credit pack for checkout testing.",
        credits=20_000,
        price_amount="349.00",
    ),
)

PRODUCTION_PLANS: tuple[PlanSpec, ...] = (
    PlanSpec(
        code="starter",
        name="Starter",
        description="Small workspace: a few Experts and modest AI token limits.",
        price_amount="49.00",
        entitlements=_STARTER_ENTITLEMENTS,
    ),
    PlanSpec(
        code="pro",
        name="Pro",
        description="Larger workspace for everyday teams and higher AI usage.",
        price_amount="149.00",
        entitlements=_PRO_ENTITLEMENTS,
    ),
    PlanSpec(
        code="business",
        name="Business",
        description="Highest limits for larger teams and heavy AI workloads.",
        price_amount="399.00",
        entitlements=_BUSINESS_ENTITLEMENTS,
    ),
)

PRODUCTION_CREDIT_PACKS: tuple[PackSpec, ...] = (
    PackSpec(
        code="credits_1m",
        name="1 million credits",
        description="1,000,000 AI credits top-up pack.",
        credits=1_000_000,
        price_amount="69.00",
    ),
    PackSpec(
        code="credits_5m",
        name="5 million credits",
        description="5,000,000 AI credits top-up pack.",
        credits=5_000_000,
        price_amount="229.00",
    ),
    PackSpec(
        code="credits_10m",
        name="10 million credits",
        description="10,000,000 AI credits top-up pack.",
        credits=10_000_000,
        price_amount="399.00",
    ),
)


def demo_catalog_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return cfg.app_env.lower() in DEMO_CATALOG_ENVS


def production_catalog_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return cfg.app_env.lower() in PRODUCTION_CATALOG_ENVS


def seed_demo_catalog(
    db: Session, settings: Settings | None = None
) -> tuple[list[Plan], list[CreditPack]]:
    """Insert missing demo plans and credit packs. Always runs (callers gate env)."""
    cfg = settings or get_settings()
    plans = [
        _ensure_plan(
            db,
            cfg,
            spec,
            metadata=DEMO_CATALOG_METADATA,
            plan_code_aliases=DEMO_PLAN_CODE_ALIASES,
        )
        for spec in DEMO_PLANS
    ]
    packs = [
        _ensure_pack(db, cfg, spec, metadata=DEMO_CATALOG_METADATA)
        for spec in DEMO_CREDIT_PACKS
    ]
    db.flush()
    return plans, packs


def seed_production_catalog(
    db: Session, settings: Settings | None = None
) -> tuple[list[Plan], list[CreditPack]]:
    """Insert missing production plans and credit packs. Always runs (callers gate env)."""
    cfg = settings or get_settings()
    plans = [
        _ensure_plan(db, cfg, spec, metadata=PRODUCTION_CATALOG_METADATA)
        for spec in PRODUCTION_PLANS
    ]
    packs = [
        _ensure_pack(db, cfg, spec, metadata=PRODUCTION_CATALOG_METADATA)
        for spec in PRODUCTION_CREDIT_PACKS
    ]
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


def ensure_production_catalog(
    db: Session, settings: Settings | None = None
) -> tuple[list[Plan], list[CreditPack]] | None:
    """No-op outside production. Safe to call from bootstrap and workspace provision."""
    cfg = settings or get_settings()
    if not production_catalog_enabled(cfg):
        return None
    return seed_production_catalog(db, cfg)


def _ensure_plan(
    db: Session,
    settings: Settings,
    spec: PlanSpec,
    *,
    metadata: dict,
    plan_code_aliases: dict[str, str] | None = None,
) -> Plan:
    svc = PlanService(db, settings)
    plan = svc.plans.get_by_code(spec.code)
    if plan is None and plan_code_aliases:
        for legacy_code, current_code in plan_code_aliases.items():
            if current_code != spec.code:
                continue
            legacy = svc.plans.get_by_code(legacy_code)
            if legacy is None:
                continue
            legacy.code = spec.code
            db.flush()
            plan = legacy
            break
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
                    extra=dict(metadata),
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


def _ensure_pack(
    db: Session, settings: Settings, spec: PackSpec, *, metadata: dict
) -> CreditPack:
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
                extra=dict(metadata),
            )
            return svc.packs.create(pack)
    except IntegrityError:
        winner = svc.packs.get_by_code(spec.code)
        if winner is None:
            raise
        return winner


def _print_catalog(label: str, plans: list[Plan], packs: list[CreditPack]) -> None:
    print(f"{label} ready:")
    for plan in plans:
        print(f"  plan {plan.code}  {plan.name}  {plan.price_amount} {plan.currency}")
    for pack in packs:
        print(
            f"  pack {pack.code}  {pack.name}  "
            f"{pack.credits} credits / {pack.price_amount} {pack.currency}"
        )


def main() -> None:
    """Seed billing catalog. From apps/api: python -m app.billing.seed"""
    settings = get_settings()
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        if demo_catalog_enabled(settings):
            from app.billing.provisioning import ensure_local_checkout_gateway

            plans, packs = seed_demo_catalog(db, settings)
            gateway = ensure_local_checkout_gateway(db, settings=settings)
            db.commit()
            _print_catalog("Demo billing catalog", plans, packs)
            if gateway is not None:
                print(
                    f"  gateway {gateway.code}  enabled={gateway.enabled}  "
                    f"test_mode={gateway.test_mode}"
                )
            return

        if production_catalog_enabled(settings):
            plans, packs = seed_production_catalog(db, settings)
            db.commit()
            _print_catalog("Production billing catalog", plans, packs)
            return

        raise SystemExit(
            "Billing catalog seed requires APP_ENV local/dev (demo) or "
            f"production (commercial); current={settings.app_env!r}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
