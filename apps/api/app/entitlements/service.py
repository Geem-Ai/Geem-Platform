"""EntitlementService — resolve Workspace limits from subscription → plan → keys.

Controllers must not read plan_entitlements or branch on plan names.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.billing.provisioning import provision_tenant_workspace
from app.billing.repository import PlanRepository
from app.billing.service import SubscriptionService
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.cache import (
    get_cached_entitlements,
    set_cached_entitlements,
)
from app.entitlements.dtos import EffectiveEntitlements
from app.entitlements.keys import EntitlementKey
from app.entitlements.values import (
    EntitlementValue,
    entitlement_value_from_row,
    require_known_key,
)


class EntitlementService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.subscriptions = SubscriptionService(db, self.settings)
        self.plans = PlanRepository(db)

    def get_effective_entitlements(self, workspace_id: uuid.UUID) -> EffectiveEntitlements:
        cached = get_cached_entitlements(workspace_id, settings=self.settings)
        if cached is not None:
            try:
                return EffectiveEntitlements.from_cache_payload(cached)
            except (KeyError, ValueError, TypeError, AppError):
                pass

        subscription = self.subscriptions.get_current(workspace_id)
        if subscription is None:
            provision_tenant_workspace(self.db, workspace_id, settings=self.settings)
            subscription = self.subscriptions.get_current(workspace_id)
        if subscription is None or subscription.plan is None:
            raise AppError(
                ErrorCategory.SUBSCRIPTION_NOT_FOUND,
                "No active subscription for this workspace.",
            )

        items: dict[str, EntitlementValue] = {}
        for row in self.plans.list_entitlements(subscription.plan_id):
            items[row.key] = entitlement_value_from_row(
                key=row.key,
                raw=row.value,
                value_type=row.value_type,
            )
        resolved = EffectiveEntitlements(
            workspace_id=workspace_id,
            subscription_id=subscription.id,
            plan_id=subscription.plan_id,
            plan_code=subscription.plan.code,
            plan_name=subscription.plan.name,
            plan_status=subscription.plan.status,
            items=items,
        )
        set_cached_entitlements(
            workspace_id,
            resolved.to_cache_payload(),
            settings=self.settings,
        )
        return resolved

    def get_entitlement(
        self, workspace_id: uuid.UUID, key: str | EntitlementKey
    ) -> EntitlementValue | None:
        name = require_known_key(key)
        return self.get_effective_entitlements(workspace_id).get(name)

    def get_int(self, workspace_id: uuid.UUID, key: str | EntitlementKey) -> int:
        item = self._require(workspace_id, key)
        return item.as_int()

    def get_bool(self, workspace_id: uuid.UUID, key: str | EntitlementKey) -> bool:
        item = self._require(workspace_id, key)
        return item.as_bool()

    def _require(self, workspace_id: uuid.UUID, key: str | EntitlementKey) -> EntitlementValue:
        name = require_known_key(key)
        item = self.get_entitlement(workspace_id, name)
        if item is None:
            raise AppError(
                ErrorCategory.ENTITLEMENT_NOT_FOUND,
                f"Entitlement '{name}' is not defined for this workspace.",
                details={"key": name},
            )
        return item
