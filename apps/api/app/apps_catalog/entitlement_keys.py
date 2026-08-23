"""Known App plan entitlement keys for Platform Admin validation (Phase 12E)."""

from __future__ import annotations

from dataclasses import dataclass

from app.apps_catalog.models import CatalogApp


@dataclass(frozen=True, slots=True)
class AppEntitlementKeySpec:
    key: str
    value_type: str  # integer
    unit: str


# Slug-specific entitlement catalogs. Unknown apps may still use keys from seed patterns.
_SLUG_ENTITLEMENTS: dict[str, tuple[AppEntitlementKeySpec, ...]] = {
    "whatsapp": (AppEntitlementKeySpec("connections", "integer", "connections"),),
    "openwa": (AppEntitlementKeySpec("connections", "integer", "connections"),),
    "chat-widget": (AppEntitlementKeySpec("widgets", "integer", "widgets"),),
    "google-drive": (AppEntitlementKeySpec("connections", "integer", "connections"),),
    "microsoft-onedrive": (AppEntitlementKeySpec("connections", "integer", "connections"),),
}

_CONNECTOR_ENTITLEMENTS: dict[str, tuple[AppEntitlementKeySpec, ...]] = {
    "openwa": (AppEntitlementKeySpec("connections", "integer", "connections"),),
    "google_drive": (AppEntitlementKeySpec("connections", "integer", "connections"),),
    "microsoft_onedrive": (AppEntitlementKeySpec("connections", "integer", "connections"),),
}


def entitlement_catalog_for_app(app: CatalogApp) -> list[AppEntitlementKeySpec]:
    by_slug = _SLUG_ENTITLEMENTS.get(app.slug)
    if by_slug:
        return list(by_slug)
    if app.connector_key:
        by_connector = _CONNECTOR_ENTITLEMENTS.get(app.connector_key)
        if by_connector:
            return list(by_connector)
    return []


def validate_entitlement_key(app: CatalogApp, key: str) -> None:
    catalog = entitlement_catalog_for_app(app)
    if not catalog:
        return
    known = {spec.key for spec in catalog}
    if key not in known:
        from app.core.errors import AppError, ErrorCategory

        raise AppError(
            ErrorCategory.VALIDATION,
            f"Unknown entitlement key '{key}' for this app.",
            details={"allowed_keys": sorted(known)},
        )
