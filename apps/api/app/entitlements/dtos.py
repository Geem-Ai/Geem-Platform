"""Effective entitlement DTOs — resolved from subscription → plan → keys."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.entitlements.keys import EntitlementKey
from app.entitlements.values import EntitlementValue


@dataclass(frozen=True, slots=True)
class EffectiveEntitlements:
    workspace_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    plan_status: str
    items: dict[str, EntitlementValue]

    def get(self, key: str | EntitlementKey) -> EntitlementValue | None:
        name = key.value if isinstance(key, EntitlementKey) else key
        return self.items.get(name)

    def to_cache_payload(self) -> dict:
        return {
            "workspace_id": str(self.workspace_id),
            "subscription_id": str(self.subscription_id),
            "plan_id": str(self.plan_id),
            "plan_code": self.plan_code,
            "plan_name": self.plan_name,
            "plan_status": self.plan_status,
            "items": {
                key: {"raw": item.raw, "value_type": item.value_type.value}
                for key, item in self.items.items()
            },
        }

    @classmethod
    def from_cache_payload(cls, payload: dict) -> EffectiveEntitlements:
        from app.entitlements.values import entitlement_value_from_row

        items = {
            key: entitlement_value_from_row(
                key=key,
                raw=row["raw"],
                value_type=row["value_type"],
            )
            for key, row in (payload.get("items") or {}).items()
        }
        return cls(
            workspace_id=uuid.UUID(payload["workspace_id"]),
            subscription_id=uuid.UUID(payload["subscription_id"]),
            plan_id=uuid.UUID(payload["plan_id"]),
            plan_code=payload["plan_code"],
            plan_name=payload["plan_name"],
            plan_status=str(payload.get("plan_status") or "active"),
            items=items,
        )
