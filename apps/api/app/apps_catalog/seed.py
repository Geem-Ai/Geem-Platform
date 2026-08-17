"""Idempotent App Store catalog seed (Phase 9A).

Safe to re-run. Updates mutable catalog metadata by stable slug/code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.apps_catalog.models import (
    AppBillingType,
    AppCategory,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.repository import AppCatalogRepository
from app.billing.money import parse_decimal_money

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CategorySpec:
    slug: str
    name_key: str
    description_key: str | None
    icon: str | None
    sort_order: int


@dataclass(frozen=True, slots=True)
class PlanSpec:
    code: str
    name: str
    description: str | None
    billing_interval: str
    price_amount: str
    currency: str = "SAR"
    is_default: bool = True
    sort_order: int = 0
    entitlements: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AppSpec:
    slug: str
    name: str
    short_description: str
    description: str
    category_slug: str
    billing_type: str
    status: str
    is_featured: bool
    sort_order: int
    icon_url: str | None = None
    connector_key: str | None = None
    connector_kind: str | None = None
    plans: tuple[PlanSpec, ...] = ()


CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec(
        slug="knowledge",
        name_key="apps.categories.knowledge",
        description_key="apps.categories.knowledgeHint",
        icon="book-open",
        sort_order=10,
    ),
    CategorySpec(
        slug="communication",
        name_key="apps.categories.communication",
        description_key="apps.categories.communicationHint",
        icon="message-circle",
        sort_order=20,
    ),
    CategorySpec(
        slug="productivity",
        name_key="apps.categories.productivity",
        description_key="apps.categories.productivityHint",
        icon="briefcase",
        sort_order=30,
    ),
    CategorySpec(
        slug="analytics",
        name_key="apps.categories.analytics",
        description_key="apps.categories.analyticsHint",
        icon="bar-chart-3",
        sort_order=40,
    ),
    CategorySpec(
        slug="automation",
        name_key="apps.categories.automation",
        description_key="apps.categories.automationHint",
        icon="workflow",
        sort_order=50,
    ),
)

FREE_PLAN = PlanSpec(
    code="free",
    name="Free",
    description="Included at no cost. Provider connection setup comes in a later phase.",
    billing_interval=AppPlanBillingInterval.NONE.value,
    price_amount="0.00",
    is_default=True,
    entitlements={"connections": 1},
)

WHATSAPP_PLANS: tuple[PlanSpec, ...] = (
    PlanSpec(
        code="line",
        name="WhatsApp Line",
        description="One WhatsApp business number routed to a Geem Expert.",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount="79.00",
        is_default=True,
        sort_order=10,
        entitlements={"connections": 1},
    ),
    PlanSpec(
        code="desk",
        name="WhatsApp Desk",
        description="Up to three WhatsApp numbers for small teams and multi-brand lines.",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount="199.00",
        is_default=False,
        sort_order=20,
        entitlements={"connections": 3},
    ),
    PlanSpec(
        code="ops",
        name="WhatsApp Ops",
        description="Up to ten WhatsApp numbers for multi-branch and agency workloads.",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount="449.00",
        is_default=False,
        sort_order=30,
        entitlements={"connections": 10},
    ),
)

APP_SPECS: tuple[AppSpec, ...] = (
    AppSpec(
        slug="google-drive",
        name="Google Drive",
        short_description="Connect selected Google Drive content to Geem Experts.",
        description=(
            "Install Google Drive to prepare this workspace for connecting Drive folders "
            "and files to Geem Experts. OAuth and sync arrive in a later phase — "
            "installation alone does not connect your Google account."
        ),
        category_slug="knowledge",
        billing_type=AppBillingType.FREE.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=True,
        sort_order=10,
        icon_url="/brand/apps/google-drive.svg",
        connector_key="google_drive",
        connector_kind="knowledge_source",
        plans=(FREE_PLAN,),
    ),
    AppSpec(
        slug="microsoft-onedrive",
        name="Microsoft OneDrive",
        short_description="Connect selected Microsoft OneDrive content to Geem Experts.",
        description=(
            "Connect Microsoft work/school or personal OneDrive files to Geem Experts. "
            "After installing, connect your Microsoft account, then add files from Expert "
            "knowledge sources. Geem reads selected files only — it does not modify your OneDrive."
        ),
        category_slug="knowledge",
        billing_type=AppBillingType.FREE.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=True,
        sort_order=20,
        icon_url="/brand/apps/microsoft-onedrive.svg",
        connector_key="microsoft_onedrive",
        connector_kind="knowledge_source",
        plans=(FREE_PLAN,),
    ),
    AppSpec(
        slug="whatsapp",
        name="WhatsApp",
        short_description="Route WhatsApp conversations into a Geem Expert channel.",
        description=(
            "Connect a WhatsApp business number to Geem, bind it to an Expert, and reply "
            "to inbound chats with workspace AI quotas and channel controls. "
            "Subscribe to a monthly plan, install the app, then connect via QR or pairing code. "
            "OpenWA is an unofficial WhatsApp gateway — use a dedicated business number."
        ),
        category_slug="communication",
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=True,
        sort_order=30,
        icon_url="/brand/apps/whatsapp.svg",
        connector_key="openwa",
        connector_kind="channel",
        plans=WHATSAPP_PLANS,
    ),
)

# One-time slug renames so re-seed migrates existing rows instead of duplicating.
_SLUG_ALIASES: dict[str, str] = {
    "whatsapp": "openwa",
}


def seed_app_catalog(db: Session) -> tuple[list[AppCategory], list[CatalogApp]]:
    """Insert/update starter categories and apps. Idempotent by slug/code."""
    repo = AppCatalogRepository(db)
    categories: list[AppCategory] = []
    for spec in CATEGORY_SPECS:
        categories.append(_ensure_category(repo, spec))

    apps: list[CatalogApp] = []
    for spec in APP_SPECS:
        apps.append(_ensure_app(repo, spec))

    db.flush()
    logger.info(
        "app_catalog_seeded categories=%s apps=%s",
        len(categories),
        len(apps),
    )
    return categories, apps


def ensure_app_catalog(db: Session) -> tuple[list[AppCategory], list[CatalogApp]]:
    """Always-safe entrypoint for bootstrap / API startup."""
    return seed_app_catalog(db)


def _ensure_category(repo: AppCatalogRepository, spec: CategorySpec) -> AppCategory:
    row = repo.get_category_by_slug(spec.slug)
    if row is None:
        row = AppCategory(
            slug=spec.slug,
            name_key=spec.name_key,
            description_key=spec.description_key,
            icon=spec.icon,
            sort_order=spec.sort_order,
            is_active=True,
        )
        return repo.upsert_category(row)

    row.name_key = spec.name_key
    row.description_key = spec.description_key
    row.icon = spec.icon
    row.sort_order = spec.sort_order
    row.is_active = True
    return row


def _ensure_app(repo: AppCatalogRepository, spec: AppSpec) -> CatalogApp:
    category = repo.get_category_by_slug(spec.category_slug)
    if category is None:
        raise RuntimeError(f"Missing category '{spec.category_slug}' for app '{spec.slug}'")

    row = repo.get_app_by_slug(spec.slug)
    if row is None:
        legacy = _SLUG_ALIASES.get(spec.slug)
        if legacy:
            row = repo.get_app_by_slug(legacy)
            if row is not None:
                row.slug = spec.slug
                logger.info("app_catalog_slug_renamed from=%s to=%s", legacy, spec.slug)

    if row is None:
        row = CatalogApp(
            slug=spec.slug,
            name=spec.name,
            short_description=spec.short_description,
            description=spec.description,
            category_id=category.id,
            icon_url=spec.icon_url,
            billing_type=spec.billing_type,
            status=spec.status,
            is_featured=spec.is_featured,
            sort_order=spec.sort_order,
            connector_key=spec.connector_key,
            connector_kind=spec.connector_kind,
            extra={"seeded": True},
        )
        repo.upsert_app(row)
    else:
        row.name = spec.name
        row.short_description = spec.short_description
        row.description = spec.description
        row.category_id = category.id
        row.icon_url = spec.icon_url
        row.billing_type = spec.billing_type
        row.status = spec.status
        row.is_featured = spec.is_featured
        row.sort_order = spec.sort_order
        row.connector_key = spec.connector_key
        row.connector_kind = spec.connector_kind

    for plan_spec in spec.plans:
        _ensure_plan(repo, row, plan_spec)
    return row


def _ensure_plan(repo: AppCatalogRepository, app: CatalogApp, spec: PlanSpec) -> AppPlan:
    amount = parse_decimal_money(spec.price_amount)
    row = repo.get_plan_by_code(app.id, spec.code)
    if row is None:
        row = AppPlan(
            app_id=app.id,
            code=spec.code,
            name=spec.name,
            description=spec.description,
            billing_interval=spec.billing_interval,
            price_amount=amount,
            currency=spec.currency,
            sort_order=spec.sort_order,
            is_default=spec.is_default,
            is_active=True,
            extra={},
        )
        repo.upsert_plan(row)
    else:
        row.name = spec.name
        row.description = spec.description
        row.billing_interval = spec.billing_interval
        row.price_amount = amount
        row.currency = spec.currency
        row.sort_order = spec.sort_order
        row.is_default = spec.is_default
        row.is_active = True

    for key, value in spec.entitlements.items():
        existing = repo.get_entitlement(row.id, key)
        if existing is None:
            repo.upsert_entitlement(
                AppPlanEntitlement(app_plan_id=row.id, key=key, value=value)
            )
        else:
            existing.value = value
    return row


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        cats, apps = seed_app_catalog(db)
        db.commit()
        print(f"Seeded {len(cats)} categories and {len(apps)} apps.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
