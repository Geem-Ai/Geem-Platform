from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

import app.apps_catalog.publication as publication_module
import app.db.models  # noqa: F401  # register relationship targets for isolated runs
from app.apps_catalog.mcp_product import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTOR_KEY,
    MCP_CONNECTOR_KIND,
    MCP_CONNECTORS_APP_SLUG,
    MCP_PLAN_CODES,
    MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
)
from app.apps_catalog.models import (
    AppBillingType,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.publication import validate_mcp_connectors_publish_ready
from app.apps_catalog.seed import APP_SPECS
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.platform_admin.apps import PlatformAdminAppsService


def _mcp_app() -> CatalogApp:
    app = CatalogApp(
        id=uuid.uuid4(),
        slug=MCP_CONNECTORS_APP_SLUG,
        name="MCP Connectors",
        short_description="Release-candidate fixture",
        description="Non-production signed fixture values.",
        category_id=uuid.uuid4(),
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.COMING_SOON.value,
        connector_key=MCP_CONNECTOR_KEY,
        connector_kind=MCP_CONNECTOR_KIND,
    )
    connection_limits = (1, 3, 10)
    call_limits = (200, 1_000, 5_000)
    plans: list[AppPlan] = []
    for index, code in enumerate(MCP_PLAN_CODES):
        plan = AppPlan(
            id=uuid.uuid4(),
            app_id=app.id,
            code=code,
            name=code,
            billing_interval=AppPlanBillingInterval.MONTHLY.value,
            price_amount=Decimal("10.00") + index,
            currency="SAR",
            sort_order=(index + 1) * 10,
            is_default=index == 0,
            is_active=True,
        )
        plan.entitlements = [
            AppPlanEntitlement(
                app_plan_id=plan.id,
                key=MCP_CONNECTIONS_ENTITLEMENT,
                value=connection_limits[index],
            ),
            AppPlanEntitlement(
                app_plan_id=plan.id,
                key=MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
                value=call_limits[index],
            ),
        ]
        plans.append(plan)
    app.plans = plans
    return app


@pytest.fixture()
def configured_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication_module.connector_registry,
        "has",
        lambda key: key == MCP_CONNECTOR_KEY,
    )
    monkeypatch.setattr(
        publication_module.connector_registry,
        "is_available",
        lambda key: key == MCP_CONNECTOR_KEY,
    )


def test_mcp_seed_is_coming_soon_without_unsigned_plans() -> None:
    spec = next(item for item in APP_SPECS if item.slug == MCP_CONNECTORS_APP_SLUG)
    assert spec.status == AppStatus.COMING_SOON.value
    assert spec.billing_type == AppBillingType.SUBSCRIPTION.value
    assert spec.connector_key == MCP_CONNECTOR_KEY
    assert spec.connector_kind == MCP_CONNECTOR_KIND
    assert spec.plans == ()
    assert spec.preserve_status is True


def test_mcp_billing_identity_is_locked_before_publication() -> None:
    service = object.__new__(PlatformAdminAppsService)

    assert service._billing_type_locked(_mcp_app()) is True


def test_mcp_publication_requires_enabled_adapter_and_exact_signed_shape(
    configured_registry: None,
) -> None:
    app = _mcp_app()
    with pytest.raises(AppError) as disabled:
        validate_mcp_connectors_publish_ready(
            app,
            Settings(_env_file=None, mcp_connector_enabled=False),
        )
    assert disabled.value.category == ErrorCategory.VALIDATION

    validate_mcp_connectors_publish_ready(
        app,
        Settings(_env_file=None, mcp_connector_enabled=True),
    )


@pytest.mark.parametrize(
    "mutation",
    ["price", "limit", "unsigned_limit", "code", "default", "sort", "inactive"],
)
def test_mcp_publication_rejects_every_unsigned_or_ambiguous_shape(
    mutation: str,
    configured_registry: None,
) -> None:
    app = _mcp_app()
    if mutation == "price":
        app.plans[0].price_amount = Decimal("0.00")
    elif mutation == "limit":
        app.plans[0].entitlements[0].value = 0
    elif mutation == "unsigned_limit":
        app.plans[0].entitlements[0].value = 2
    elif mutation == "code":
        app.plans[0].code = "mcp-unreviewed"
    elif mutation == "default":
        app.plans[1].is_default = True
    elif mutation == "inactive":
        app.plans[1].is_active = False
    else:
        app.plans[1].sort_order = app.plans[0].sort_order

    with pytest.raises(AppError) as invalid:
        validate_mcp_connectors_publish_ready(
            app,
            Settings(_env_file=None, mcp_connector_enabled=True),
        )
    assert invalid.value.category == ErrorCategory.VALIDATION
