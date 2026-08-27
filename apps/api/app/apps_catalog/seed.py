"""Idempotent App Store catalog seed (Phase 9A).

Safe to re-run. Updates mutable catalog metadata by stable slug/code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENTS_AI_APP_SLUG,
    AGENTS_AI_PLAN_CODES,
)
from app.apps_catalog.models import (
    AppBillingType,
    AppCategory,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.mcp_product import (
    MCP_CONNECTOR_KEY,
    MCP_CONNECTOR_KIND,
    MCP_CONNECTORS_APP_SLUG,
)
from app.apps_catalog.publication import validate_product_publish_ready
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.runtime_locks import acquire_app_runtime_mutation_fence
from app.billing.money import parse_decimal_money
from app.core.config import Settings, get_settings

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
    # Product launch lifecycle is controlled by a validated promotion, not by
    # a routine metadata seed. Such rows are created with ``status`` once and
    # later seed runs preserve the database lifecycle state.
    preserve_status: bool = False


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

CHAT_WIDGET_PLANS: tuple[PlanSpec, ...] = (
    PlanSpec(
        code="standard",
        name="Chat Widget Standard",
        description="One embeddable chat widget grounded on a Geem Expert.",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount="199.00",
        is_default=True,
        sort_order=10,
        entitlements={"widgets": 1},
    ),
)

_AGENTS_AI_PLAN_PRICES: tuple[str, ...] = ("99.00", "249.00", "599.00")
_AGENTS_AI_PLAN_DAILY_LIMITS: tuple[int, ...] = (100, 500, 2000)
_AGENTS_AI_PLAN_NAMES: tuple[str, ...] = (
    "Agents Starter",
    "Agents Team",
    "Agents Scale",
)
_AGENTS_AI_PLAN_DESCRIPTIONS: tuple[str, ...] = (
    "Entry plan for applications running client-owned agent loops.",
    "Expanded daily agent capacity for teams and production integrations.",
    "Highest launch capacity for larger client-owned agent workloads.",
)

AGENTS_AI_PLANS: tuple[PlanSpec, ...] = tuple(
    PlanSpec(
        code=code,
        name=_AGENTS_AI_PLAN_NAMES[index],
        description=_AGENTS_AI_PLAN_DESCRIPTIONS[index],
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=_AGENTS_AI_PLAN_PRICES[index],
        is_default=index == 0,
        sort_order=(index + 1) * 10,
        entitlements={AGENT_REQUESTS_DAILY_ENTITLEMENT: _AGENTS_AI_PLAN_DAILY_LIMITS[index]},
    )
    for index, code in enumerate(AGENTS_AI_PLAN_CODES)
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
    AppSpec(
        slug="chat-widget",
        name="Chat Widget",
        short_description="Embed a Geem Expert chat widget on your website.",
        description=(
            "Subscribe monthly, install Chat Widget, bind one Expert for private RAG grounding, "
            "customize appearance, and paste a script tag on your site. "
            "Optional allowed origins restrict which domains can load the widget. "
            "Visitor chats use your workspace AI quota — no API key in the embed script."
        ),
        category_slug="communication",
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=False,
        sort_order=40,
        icon_url="/brand/apps/chat-widget.svg",
        connector_key=None,
        connector_kind=None,
        plans=CHAT_WIDGET_PLANS,
    ),
    AppSpec(
        slug="agents-ai",
        name="Agents AI",
        short_description="Build client-owned agents with Geem knowledge and models.",
        description=(
            "Use an OpenAI-compatible Agent API with a Workspace-owned Expert while "
            "your application owns and executes its tools. Agents AI is a separate "
            "paid App subscription and is not an MCP connector."
        ),
        category_slug="automation",
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.COMING_SOON.value,
        is_featured=False,
        sort_order=50,
        connector_key=None,
        connector_kind=None,
        plans=AGENTS_AI_PLANS,
        preserve_status=True,
    ),
    # Phase 13 intentionally seeds only the stable product identity. Commercial
    # prices must be signed and installed as exact Plan rows before publication;
    # never manufacture zero or placeholder plans in a production seed.
    AppSpec(
        slug=MCP_CONNECTORS_APP_SLUG,
        name="MCP Connectors",
        short_description="Connect reviewed remote MCP tools to Geem Experts.",
        description=(
            "Attach compatible public-HTTPS MCP servers, review individual tools, "
            "and let Geem invoke approved tools from explicitly enabled surfaces. "
            "Remote tools use a Workspace-shared external service account."
        ),
        category_slug="automation",
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.COMING_SOON.value,
        is_featured=False,
        sort_order=60,
        connector_key=MCP_CONNECTOR_KEY,
        connector_kind=MCP_CONNECTOR_KIND,
        plans=(),
        preserve_status=True,
    ),
)

MCP_CATEGORY_SPEC = next(spec for spec in CATEGORY_SPECS if spec.slug == "automation")
MCP_APP_SPEC = next(spec for spec in APP_SPECS if spec.slug == MCP_CONNECTORS_APP_SLUG)

# One-time slug renames so re-seed migrates existing rows instead of duplicating.
_SLUG_ALIASES: dict[str, str] = {
    "whatsapp": "openwa",
}


def seed_app_catalog(
    db: Session,
    *,
    settings: Settings | None = None,
) -> tuple[list[AppCategory], list[CatalogApp]]:
    """Insert/update starter categories and apps. Idempotent by slug/code."""
    repo = AppCatalogRepository(db)
    categories: list[AppCategory] = []
    for spec in CATEGORY_SPECS:
        categories.append(_ensure_category(repo, spec))

    apps: list[CatalogApp] = []
    for spec in APP_SPECS:
        guarded_product_mutation = _seeds_guarded_product_authority(spec)
        if guarded_product_mutation:
            # A signed Agents AI seed mutates the same global plan/quota
            # authority read by paid admission. Hold the App-wide exclusive
            # fence before any metadata, plan, or entitlement upsert so a
            # concurrent shared-fence waiter can only observe the complete
            # pre-seed or post-seed product state.
            acquire_app_runtime_mutation_fence(db, spec.slug)
        app = _ensure_app(repo, spec)
        if guarded_product_mutation:
            _validate_seeded_product_after_mutation(
                repo,
                app,
                settings=settings,
            )
        apps.append(app)

    db.flush()
    logger.info(
        "app_catalog_seeded categories=%s apps=%s",
        len(categories),
        len(apps),
    )
    return categories, apps


def ensure_app_catalog(
    db: Session,
    *,
    settings: Settings | None = None,
) -> tuple[list[AppCategory], list[CatalogApp]]:
    """Always-safe entrypoint for bootstrap / API startup."""
    return seed_app_catalog(db, settings=settings)


def reconcile_mcp_app_catalog(
    db: Session,
    *,
    settings: Settings | None = None,
) -> tuple[AppCategory, CatalogApp]:
    """Reconcile only the MCP catalog identity for a production upgrade.

    Unlike :func:`seed_app_catalog`, this path never iterates over or mutates
    any other App. It creates the shared ``automation`` category only when the
    category is absent; an existing shared category is deliberately left
    untouched. MCP lifecycle status and commercial plans are also preserved.
    """

    acquire_app_runtime_mutation_fence(db, MCP_CONNECTORS_APP_SLUG)
    repo = AppCatalogRepository(db)
    category = repo.get_category_by_slug(MCP_CATEGORY_SPEC.slug)
    if category is None:
        category = AppCategory(
            slug=MCP_CATEGORY_SPEC.slug,
            name_key=MCP_CATEGORY_SPEC.name_key,
            description_key=MCP_CATEGORY_SPEC.description_key,
            icon=MCP_CATEGORY_SPEC.icon,
            sort_order=MCP_CATEGORY_SPEC.sort_order,
            is_active=True,
        )
        repo.upsert_category(category)

    app = _ensure_app(repo, MCP_APP_SPEC)
    _validate_seeded_product_after_mutation(repo, app, settings=settings)
    db.flush()
    logger.info("mcp_app_catalog_reconciled app=%s", MCP_CONNECTORS_APP_SLUG)
    return category, app


def _seeds_guarded_product_authority(spec: AppSpec) -> bool:
    """Return true for product rows with signed plans guarded by publication validators."""

    if spec.slug in {AGENTS_AI_APP_SLUG, MCP_CONNECTORS_APP_SLUG}:
        return bool(spec.plans)
    return False


def _validate_seeded_product_after_mutation(
    repo: AppCatalogRepository,
    app: CatalogApp,
    *,
    settings: Settings | None,
) -> None:
    """Revalidate a published signed product from freshly loaded relationships."""

    if app.status != AppStatus.PUBLISHED.value:
        return
    db = repo.db
    db.flush()
    for plan in list(app.plans or []):
        db.expire(plan, ["entitlements"])
    db.expire(app, ["plans"])
    refreshed = repo.get_app_by_slug(app.slug)
    if refreshed is None:
        raise RuntimeError(f"Seeded app '{app.slug}' disappeared before validation")
    validate_product_publish_ready(refreshed, settings or get_settings())


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
        if not spec.preserve_status:
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
