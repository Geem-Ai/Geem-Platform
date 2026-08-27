"""MCP-only production catalog reconciliation safety."""

from __future__ import annotations

from decimal import Decimal

from app.apps_catalog.mcp_product import MCP_CONNECTORS_APP_SLUG
from app.apps_catalog.models import (
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
)
from app.apps_catalog.reconcile_mcp import (
    inspect_mcp_app_catalog,
    run_mcp_app_catalog_reconciliation,
)
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.seed import ensure_app_catalog


def test_mcp_reconciliation_mutates_only_mcp_and_preserves_commercial_state(db) -> None:
    ensure_app_catalog(db)
    repo = AppCatalogRepository(db)
    drive = repo.get_app_by_slug("google-drive")
    mcp = repo.get_app_by_slug(MCP_CONNECTORS_APP_SLUG)
    automation = repo.get_category_by_slug("automation")
    assert drive is not None
    assert mcp is not None
    assert automation is not None

    drive.name = "Production-owned Drive title"
    mcp.name = "Stale MCP title"
    mcp.status = AppStatus.DISABLED.value
    mcp.extra = {"authority": "operator", "nested": {"preserve": True}}
    automation.name_key = "operator.automation.name"
    automation.description_key = "operator.automation.description"
    automation.icon = "operator-automation-icon"
    automation.sort_order = 987
    automation.is_active = False
    plan = AppPlan(
        app_id=mcp.id,
        code="operator-signed-plan",
        name="Operator signed plan",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=Decimal("123.45"),
        currency="SAR",
        sort_order=10,
        is_default=True,
        is_active=True,
        extra={"authority": "operator"},
    )
    db.add(plan)
    db.flush()
    db.add(
        AppPlanEntitlement(
            app_plan_id=plan.id,
            key="operator.signed.limit",
            value={"limit": 321, "authority": "operator"},
        )
    )
    db.commit()

    dry_run = run_mcp_app_catalog_reconciliation(db, mode="dry-run")
    assert {change.field for change in dry_run.changes} == {"name"}
    assert dry_run.status_preserved == AppStatus.DISABLED.value
    assert dry_run.plan_count_preserved == 1
    db.refresh(mcp)
    assert mcp.name == "Stale MCP title"

    applied = run_mcp_app_catalog_reconciliation(db, mode="apply")
    db.commit()
    assert {change.field for change in applied.changes} == {"name"}

    db.expire_all()
    drive_after = repo.get_app_by_slug("google-drive")
    mcp_after = repo.get_app_by_slug(MCP_CONNECTORS_APP_SLUG)
    assert drive_after is not None
    assert mcp_after is not None
    assert drive_after.name == "Production-owned Drive title"
    assert mcp_after.name == "MCP Connectors"
    assert mcp_after.status == AppStatus.DISABLED.value
    assert mcp_after.extra == {
        "authority": "operator",
        "nested": {"preserve": True},
    }
    assert [(item.code, item.price_amount) for item in mcp_after.plans] == [
        ("operator-signed-plan", Decimal("123.45"))
    ]
    assert mcp_after.plans[0].extra == {"authority": "operator"}
    assert [
        (item.key, item.value) for item in mcp_after.plans[0].entitlements
    ] == [
        (
            "operator.signed.limit",
            {"limit": 321, "authority": "operator"},
        )
    ]
    automation_after = repo.get_category_by_slug("automation")
    assert automation_after is not None
    assert automation_after.name_key == "operator.automation.name"
    assert automation_after.description_key == "operator.automation.description"
    assert automation_after.icon == "operator-automation-icon"
    assert automation_after.sort_order == 987
    assert automation_after.is_active is False
    assert inspect_mcp_app_catalog(db, mode="verify").matches is True


def test_mcp_reconciliation_can_create_only_missing_identity(db) -> None:
    result = run_mcp_app_catalog_reconciliation(db, mode="dry-run")
    assert [(change.resource, change.field) for change in result.changes] == [
        ("category:automation", "exists"),
        ("app:mcp-connectors", "exists"),
    ]

    run_mcp_app_catalog_reconciliation(db, mode="apply")
    db.commit()

    repo = AppCatalogRepository(db)
    mcp = repo.get_app_by_slug(MCP_CONNECTORS_APP_SLUG)
    assert mcp is not None
    assert mcp.status == AppStatus.COMING_SOON.value
    assert mcp.plans == []
    assert repo.get_app_by_slug("google-drive") is None
    assert inspect_mcp_app_catalog(db, mode="verify").matches is True
