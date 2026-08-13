"""Plan / subscription / billing data access. Tenant queries always take workspace_id."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.billing.models import (
    CreditPack,
    PaymentGatewayConfig,
    Plan,
    PlanEntitlement,
    PlanStatus,
    Purchase,
    Subscription,
    SubscriptionStatus,
)


class PlanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, plan_id: uuid.UUID) -> Plan | None:
        return self.db.scalar(
            select(Plan)
            .options(selectinload(Plan.entitlements))
            .where(Plan.id == plan_id)
        )

    def get_by_code(self, code: str) -> Plan | None:
        return self.db.scalar(
            select(Plan)
            .options(selectinload(Plan.entitlements))
            .where(Plan.code == code)
        )

    def create(self, plan: Plan) -> Plan:
        self.db.add(plan)
        self.db.flush()
        return plan

    def list_entitlements(self, plan_id: uuid.UUID) -> list[PlanEntitlement]:
        return list(
            self.db.scalars(
                select(PlanEntitlement)
                .where(PlanEntitlement.plan_id == plan_id)
                .order_by(PlanEntitlement.key.asc())
            )
        )

    def get_entitlement(self, plan_id: uuid.UUID, key: str) -> PlanEntitlement | None:
        return self.db.scalar(
            select(PlanEntitlement).where(
                PlanEntitlement.plan_id == plan_id,
                PlanEntitlement.key == key,
            )
        )

    def create_entitlement(self, row: PlanEntitlement) -> PlanEntitlement:
        self.db.add(row)
        self.db.flush()
        return row

    def list_purchasable(self) -> list[Plan]:
        return list(
            self.db.scalars(
                select(Plan)
                .options(selectinload(Plan.entitlements))
                .where(
                    Plan.status == PlanStatus.ACTIVE.value,
                    Plan.price_amount.is_not(None),
                    Plan.price_amount > 0,
                )
                .order_by(Plan.name.asc())
            )
        )


class SubscriptionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id_for_workspace(
        self, workspace_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> Subscription | None:
        return self.db.scalar(
            select(Subscription)
            .options(selectinload(Subscription.plan).selectinload(Plan.entitlements))
            .where(
                Subscription.id == subscription_id,
                Subscription.workspace_id == workspace_id,
            )
        )

    def get_current(self, workspace_id: uuid.UUID) -> Subscription | None:
        """Resolve the single effective subscription for a Workspace."""
        now = datetime.now(timezone.utc)
        return self.db.scalar(
            select(Subscription)
            .options(selectinload(Subscription.plan).selectinload(Plan.entitlements))
            .where(
                Subscription.workspace_id == workspace_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
                Subscription.starts_at <= now,
                (Subscription.ends_at.is_(None)) | (Subscription.ends_at > now),
            )
            .order_by(Subscription.starts_at.desc())
            .limit(1)
        )

    def get_active_for_update(self, workspace_id: uuid.UUID) -> Subscription | None:
        return self.db.scalar(
            select(Subscription)
            .where(
                Subscription.workspace_id == workspace_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .with_for_update()
        )

    def list_for_workspace(self, workspace_id: uuid.UUID) -> list[Subscription]:
        return list(
            self.db.scalars(
                select(Subscription)
                .where(Subscription.workspace_id == workspace_id)
                .order_by(Subscription.created_at.desc())
            )
        )

    def create(self, subscription: Subscription) -> Subscription:
        self.db.add(subscription)
        self.db.flush()
        return subscription


class PaymentGatewayConfigRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, config_id: uuid.UUID) -> PaymentGatewayConfig | None:
        return self.db.get(PaymentGatewayConfig, config_id)

    def get_by_code(self, code: str) -> PaymentGatewayConfig | None:
        return self.db.scalar(
            select(PaymentGatewayConfig).where(PaymentGatewayConfig.code == code)
        )

    def list_enabled(self) -> list[PaymentGatewayConfig]:
        return list(
            self.db.scalars(
                select(PaymentGatewayConfig).where(PaymentGatewayConfig.enabled.is_(True))
            )
        )

    def list_all(self) -> list[PaymentGatewayConfig]:
        return list(self.db.scalars(select(PaymentGatewayConfig).order_by(PaymentGatewayConfig.code)))

    def create(self, row: PaymentGatewayConfig) -> PaymentGatewayConfig:
        self.db.add(row)
        self.db.flush()
        return row


class CreditPackRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, pack_id: uuid.UUID) -> CreditPack | None:
        return self.db.get(CreditPack, pack_id)

    def get_by_code(self, code: str) -> CreditPack | None:
        return self.db.scalar(select(CreditPack).where(CreditPack.code == code))

    def list_active(self) -> list[CreditPack]:
        return list(
            self.db.scalars(
                select(CreditPack)
                .where(CreditPack.active.is_(True))
                .order_by(CreditPack.price_amount.asc(), CreditPack.name.asc())
            )
        )

    def create(self, row: CreditPack) -> CreditPack:
        self.db.add(row)
        self.db.flush()
        return row


class PurchaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, purchase: Purchase) -> Purchase:
        self.db.add(purchase)
        self.db.flush()
        return purchase

    def get_by_id(self, purchase_id: uuid.UUID) -> Purchase | None:
        return self.db.get(Purchase, purchase_id)

    def get_for_workspace(
        self, workspace_id: uuid.UUID, purchase_id: uuid.UUID
    ) -> Purchase | None:
        return self.db.scalar(
            select(Purchase).where(
                Purchase.id == purchase_id,
                Purchase.workspace_id == workspace_id,
            )
        )

    def get_by_id_for_update(self, purchase_id: uuid.UUID) -> Purchase | None:
        return self.db.scalar(
            select(Purchase).where(Purchase.id == purchase_id).with_for_update()
        )

    def get_for_workspace_for_update(
        self, workspace_id: uuid.UUID, purchase_id: uuid.UUID
    ) -> Purchase | None:
        return self.db.scalar(
            select(Purchase)
            .where(
                Purchase.id == purchase_id,
                Purchase.workspace_id == workspace_id,
            )
            .with_for_update()
        )
