"""App Store API DTOs. Never include config_encrypted or credentials."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.apps_catalog.access import AppAccessSnapshot, AppAccessStatus
from app.apps_catalog.models import (
    AppBillingType,
    AppInstallation,
    AppInstallationStatus,
    AppPlan,
    AppStatus,
    CatalogApp,
)
from app.billing.money import parse_decimal_money
from app.connectors.registry import connector_registry
from app.connectors.schemas import ConnectorCapabilityOut


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money_str(value: Decimal | int | float | str) -> str:
    return f"{parse_decimal_money(value):.2f}"


AccessRequirement = Literal["free", "one_time", "subscription", "unavailable"]


class AppCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name_key: str
    description_key: str | None = None
    icon: str | None = None
    sort_order: int = 0


class AppPlanOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    billing_interval: str
    price_amount: str
    currency: str
    is_default: bool = False
    entitlements: dict[str, Any] = Field(default_factory=dict)


class AppInstallationSummaryOut(BaseModel):
    id: uuid.UUID | None = None
    status: str | None = None
    installed_at: datetime | None = None


class AppAccessOut(BaseModel):
    status: str
    plan_id: uuid.UUID | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    commercially_entitled: bool = False
    can_purchase: bool = False
    can_renew: bool = False
    can_install: bool = False
    can_uninstall: bool = False


class ConnectionUsageOut(BaseModel):
    """Safe connection entitlement usage for Apps management UX."""

    used: int = 0
    limit: int | None = None


class ConnectionSummaryOut(BaseModel):
    """Safe per-connection summary — never includes credentials or sync state."""

    id: uuid.UUID
    display_name: str | None = None
    status: str
    health: str
    external_account_name: str | None = None
    connector_key: str


class CatalogAppOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    short_description: str
    description: str | None = None
    category: AppCategoryOut
    icon_url: str | None = None
    billing_type: str
    status: str
    is_featured: bool = False
    sort_order: int = 0
    plans: list[AppPlanOut] = Field(default_factory=list)
    installation: AppInstallationSummaryOut | None = None
    installation_status: str | None = None
    can_install: bool = False
    can_uninstall: bool = False
    access_requirement: AccessRequirement = "unavailable"
    access: AppAccessOut | None = None
    connector: ConnectorCapabilityOut | None = None
    has_active_connection: bool = False
    connection_status: str | None = None
    connection_usage: ConnectionUsageOut | None = None
    connections: list[ConnectionSummaryOut] = Field(default_factory=list)


class CatalogAppListOut(BaseModel):
    items: list[CatalogAppOut]
    total: int
    limit: int
    offset: int


class AppInstallationOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    app_id: uuid.UUID
    status: str
    installed_at: datetime
    uninstalled_at: datetime | None = None
    installed_by_user_id: uuid.UUID | None = None
    app: CatalogAppOut


class AppInstallationListOut(BaseModel):
    items: list[AppInstallationOut]
    total: int
    limit: int
    offset: int


class AppCheckoutRequest(BaseModel):
    plan_id: uuid.UUID


class AppRenewRequest(BaseModel):
    plan_id: uuid.UUID | None = None


def to_category_out(category: object) -> AppCategoryOut:
    return AppCategoryOut(
        slug=getattr(category, "slug"),
        name_key=getattr(category, "name_key"),
        description_key=getattr(category, "description_key", None),
        icon=getattr(category, "icon", None),
        sort_order=int(getattr(category, "sort_order", 0) or 0),
    )


def to_plan_out(plan: AppPlan) -> AppPlanOut:
    ents: dict[str, Any] = {}
    for row in plan.entitlements or []:
        ents[str(row.key)] = row.value
    return AppPlanOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        billing_interval=plan.billing_interval,
        price_amount=_money_str(plan.price_amount),
        currency=plan.currency,
        is_default=bool(plan.is_default),
        entitlements=ents,
    )


def to_access_out(snapshot: AppAccessSnapshot) -> AppAccessOut:
    return AppAccessOut(
        status=snapshot.status.value,
        plan_id=snapshot.plan_id,
        plan_code=snapshot.plan_code,
        plan_name=snapshot.plan_name,
        current_period_start=_utc(snapshot.current_period_start),
        current_period_end=_utc(snapshot.current_period_end),
        commercially_entitled=snapshot.commercially_entitled,
        can_purchase=snapshot.can_purchase,
        can_renew=snapshot.can_renew,
        can_install=snapshot.can_install,
        can_uninstall=snapshot.can_uninstall,
    )


def access_requirement_from_snapshot(
    app: CatalogApp, snapshot: AppAccessSnapshot
) -> AccessRequirement:
    if snapshot.status == AppAccessStatus.UNAVAILABLE:
        return "unavailable"
    if app.billing_type == AppBillingType.FREE.value:
        return "free"
    if app.billing_type == AppBillingType.ONE_TIME.value:
        return "one_time"
    if app.billing_type == AppBillingType.SUBSCRIPTION.value:
        return "subscription"
    return "unavailable"


def to_catalog_app_out(
    app: CatalogApp,
    *,
    installation: AppInstallation | None = None,
    can_manage: bool = False,
    include_description: bool = True,
    access: AppAccessSnapshot | None = None,
    has_active_connection: bool = False,
    connection_status: str | None = None,
    connection_usage: ConnectionUsageOut | None = None,
    connections: list[ConnectionSummaryOut] | None = None,
) -> CatalogAppOut:
    active = (
        installation is not None
        and installation.status == AppInstallationStatus.ACTIVE.value
    )
    inst_status = installation.status if installation and active else None

    if access is not None:
        can_install = access.can_install
        can_uninstall = access.can_uninstall
        access_req = access_requirement_from_snapshot(app, access)
        access_out = to_access_out(access)
    else:
        # Fallback for callers that have not resolved commercial access yet.
        if app.status == AppStatus.COMING_SOON.value:
            can_install, can_uninstall, access_req = False, False, "unavailable"
        elif app.status != AppStatus.PUBLISHED.value:
            can_install = False
            can_uninstall = bool(active and can_manage)
            access_req = "unavailable"
        elif app.billing_type == AppBillingType.FREE.value:
            access_req = "free"
            can_install = can_manage and not active
            can_uninstall = can_manage and active
        elif app.billing_type == AppBillingType.ONE_TIME.value:
            can_install, can_uninstall, access_req = (
                False,
                bool(active and can_manage),
                "one_time",
            )
        elif app.billing_type == AppBillingType.SUBSCRIPTION.value:
            can_install, can_uninstall, access_req = (
                False,
                bool(active and can_manage),
                "subscription",
            )
        else:
            can_install, can_uninstall, access_req = False, False, "unavailable"
        access_out = None

    plans = [
        to_plan_out(p)
        for p in sorted(
            (app.plans or []),
            key=lambda p: (not p.is_default, p.sort_order, p.code),
        )
        if p.is_active
    ]
    summary: AppInstallationSummaryOut | None = None
    if installation is not None and installation.status == AppInstallationStatus.ACTIVE.value:
        summary = AppInstallationSummaryOut(
            id=installation.id,
            status=installation.status,
            installed_at=_utc(installation.installed_at),
        )

    connector_out: ConnectorCapabilityOut | None = None
    if app.connector_key:
        desc = connector_registry.describe(app.connector_key) or {}
        connector_out = ConnectorCapabilityOut(
            key=app.connector_key,
            kind=app.connector_kind or desc.get("kind"),
            available=bool(desc.get("available")),
            auth_mode=desc.get("auth_mode"),
            can_connect=bool(desc.get("can_connect") and desc.get("available")),
            supports_sync=bool(desc.get("supports_sync")),
            supports_webhooks=bool(desc.get("supports_webhooks")),
            supports_health_check=bool(desc.get("supports_health_check")),
            unavailable_reason=desc.get("unavailable_reason"),
        )

    return CatalogAppOut(
        id=app.id,
        slug=app.slug,
        name=app.name,
        short_description=app.short_description,
        description=app.description if include_description else None,
        category=to_category_out(app.category),
        icon_url=app.icon_url,
        billing_type=app.billing_type,
        status=app.status,
        is_featured=bool(app.is_featured),
        sort_order=int(app.sort_order or 0),
        plans=plans,
        installation=summary,
        installation_status=inst_status,
        can_install=can_install,
        can_uninstall=can_uninstall,
        access_requirement=access_req,
        access=access_out,
        connector=connector_out,
        has_active_connection=bool(has_active_connection),
        connection_status=connection_status,
        connection_usage=connection_usage,
        connections=list(connections or []),
    )


def to_installation_out(
    row: AppInstallation,
    *,
    can_manage: bool,
    access: AppAccessSnapshot | None = None,
    has_active_connection: bool = False,
    connection_status: str | None = None,
    connection_usage: ConnectionUsageOut | None = None,
    connections: list[ConnectionSummaryOut] | None = None,
) -> AppInstallationOut:
    app_out = to_catalog_app_out(
        row.app,
        installation=row,
        can_manage=can_manage,
        access=access,
        has_active_connection=has_active_connection,
        connection_status=connection_status,
        connection_usage=connection_usage,
        connections=connections,
    )
    return AppInstallationOut(
        id=row.id,
        workspace_id=row.workspace_id,
        app_id=row.app_id,
        status=row.status,
        installed_at=_utc(row.installed_at) or row.installed_at,
        uninstalled_at=_utc(row.uninstalled_at),
        installed_by_user_id=row.installed_by_user_id,
        app=app_out,
    )
