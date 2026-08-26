"""Product-specific catalog publication gates."""

from __future__ import annotations

from decimal import Decimal

from app.apps_catalog.agent_product import (
    AGENTS_AI_APP_SLUG,
    AGENTS_AI_PLAN_CODES,
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
)
from app.apps_catalog.models import (
    AppBillingType,
    AppPlanBillingInterval,
    CatalogApp,
)
from app.apps_catalog.mcp_product import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTOR_KEY,
    MCP_CONNECTOR_KIND,
    MCP_CONNECTORS_APP_SLUG,
    MCP_PLAN_CODES,
    MCP_PLAN_CONNECTION_LIMITS,
    MCP_PLAN_TOOL_CALL_LIMITS,
    MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
)
from app.billing.money import parse_decimal_money
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.connectors.registry import connector_registry


def validate_product_publish_ready(app: CatalogApp, settings: Settings) -> None:
    """Apply locked product gates in addition to the generic App validator."""
    if app.slug == AGENTS_AI_APP_SLUG:
        validate_agents_ai_publish_ready(app, settings)
    elif app.slug == MCP_CONNECTORS_APP_SLUG:
        validate_mcp_connectors_publish_ready(app, settings)


def validate_mcp_connectors_publish_ready(
    app: CatalogApp,
    settings: Settings,
) -> None:
    """Block publication until the exact paid MCP launch product is signed."""

    if not settings.mcp_connector_enabled:
        _invalid("MCP_CONNECTOR_ENABLED must be true before MCP Connectors publication.")
    if app.billing_type != AppBillingType.SUBSCRIPTION.value:
        _invalid("MCP Connectors must use subscription billing.")
    if app.connector_key != MCP_CONNECTOR_KEY or app.connector_kind != MCP_CONNECTOR_KIND:
        _invalid("MCP Connectors must use the mcp_remote tool_source adapter.")
    if not connector_registry.has(MCP_CONNECTOR_KEY):
        _invalid("The mcp_remote connector adapter must be registered before publication.")
    if not connector_registry.is_available(MCP_CONNECTOR_KEY):
        _invalid("The mcp_remote connector adapter must be configured before publication.")

    plans = list(app.plans or [])
    by_code = {plan.code: plan for plan in plans}
    if len(by_code) != len(plans) or set(by_code) != set(MCP_PLAN_CODES):
        _invalid("MCP Connectors requires exactly mcp-starter, mcp-team, and mcp-scale.")
    if sum(1 for plan in plans if plan.is_default) != 1:
        _invalid("MCP Connectors requires exactly one default plan.")
    if len({int(plan.sort_order) for plan in plans}) != len(plans):
        _invalid("MCP Connectors plan sort_order values must be unique.")
    ordered = tuple(
        plan.code for plan in sorted(plans, key=lambda row: (row.sort_order, row.code))
    )
    if ordered != MCP_PLAN_CODES:
        _invalid("MCP Connectors plans must use the locked deterministic sort order.")

    required = {MCP_CONNECTIONS_ENTITLEMENT, MCP_TOOL_CALLS_DAILY_ENTITLEMENT}
    for index, code in enumerate(MCP_PLAN_CODES):
        plan = by_code[code]
        if not plan.is_active:
            _invalid(f"MCP Connectors launch plan '{code}' must be active.")
        if plan.billing_interval != AppPlanBillingInterval.MONTHLY.value:
            _invalid(f"MCP Connectors plan '{code}' must be monthly.")
        if plan.currency != "SAR" or parse_decimal_money(plan.price_amount) <= Decimal("0.00"):
            _invalid(f"MCP Connectors plan '{code}' requires a positive signed SAR price.")
        values = {row.key: row.value for row in (plan.entitlements or [])}
        if set(values) != required:
            _invalid(
                f"MCP Connectors plan '{code}' requires exactly connections and "
                "tool_calls_daily entitlements."
            )
        for key in sorted(required):
            value = values[key]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                _invalid(
                    f"MCP Connectors plan '{code}' requires a positive integer {key}."
                )
        if values[MCP_CONNECTIONS_ENTITLEMENT] != MCP_PLAN_CONNECTION_LIMITS[index]:
            _invalid(f"MCP Connectors plan '{code}' has an unsigned connections limit.")
        if (
            values[MCP_TOOL_CALLS_DAILY_ENTITLEMENT]
            != MCP_PLAN_TOOL_CALL_LIMITS[index]
        ):
            _invalid(
                f"MCP Connectors plan '{code}' has an unsigned tool_calls_daily limit."
            )


def validate_agents_ai_publish_ready(app: CatalogApp, settings: Settings) -> None:
    if not settings.client_agent_api_enabled:
        _invalid("CLIENT_AGENT_API_ENABLED must be true before Agents AI publication.")
    if app.billing_type != AppBillingType.SUBSCRIPTION.value:
        _invalid("Agents AI must use subscription billing.")
    if app.connector_key is not None or app.connector_kind is not None:
        _invalid("Agents AI must remain a non-connector App.")

    # Validate the complete persisted product set, not only plans currently
    # available for new selection. ``is_active`` may be turned off without
    # revoking existing subscribers, but it must not hide an unreviewed fourth
    # plan or a malformed inactive launch tier from the publication gate.
    plans = list(app.plans or [])
    by_code = {plan.code: plan for plan in plans}
    if len(by_code) != len(plans) or set(by_code) != set(AGENTS_AI_PLAN_CODES):
        _invalid(
            "Agents AI requires exactly the plans agents-starter, "
            "agents-team, and agents-scale."
        )
    if sum(1 for plan in plans if plan.is_default) != 1:
        _invalid("Agents AI requires exactly one default plan.")
    if len({int(plan.sort_order) for plan in plans}) != len(plans):
        _invalid("Agents AI plan sort_order values must be unique.")

    ordered_codes = tuple(
        plan.code for plan in sorted(plans, key=lambda row: (row.sort_order, row.code))
    )
    if ordered_codes != AGENTS_AI_PLAN_CODES:
        _invalid("Agents AI plans must use the locked deterministic sort order.")

    for code in AGENTS_AI_PLAN_CODES:
        plan = by_code[code]
        if plan.billing_interval != AppPlanBillingInterval.MONTHLY.value:
            _invalid(f"Agents AI plan '{code}' must be monthly.")
        if plan.currency != "SAR" or parse_decimal_money(plan.price_amount) <= Decimal("0.00"):
            _invalid(f"Agents AI plan '{code}' requires a positive signed SAR price.")
        entitlement = next(
            (
                row
                for row in (plan.entitlements or [])
                if row.key == AGENT_REQUESTS_DAILY_ENTITLEMENT
            ),
            None,
        )
        value = entitlement.value if entitlement is not None else None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            _invalid(
                f"Agents AI plan '{code}' requires a positive integer "
                f"{AGENT_REQUESTS_DAILY_ENTITLEMENT}."
            )


def _invalid(message: str) -> None:
    raise AppError(ErrorCategory.VALIDATION, message)
