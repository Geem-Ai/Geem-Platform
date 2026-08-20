"""Plan / subscription / billing data access. Tenant queries always take workspace_id."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.billing.models import (
    CreditPack,
    PaymentGatewayConfig,
    Plan,
    PlanEntitlement,
    PlanStatus,
    Purchase,
    PurchaseStatus,
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
                .order_by(Plan.price_amount.asc(), Plan.name.asc())
            )
        )

    def _admin_filters(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        currency: str | None = None,
    ):
        clauses: list = []
        if search:
            term = f"%{search.strip()}%"
            clauses.append(
                (Plan.code.ilike(term)) | (Plan.name.ilike(term)) | (Plan.description.ilike(term))
            )
        if status:
            clauses.append(Plan.status == status.strip().lower())
        if currency:
            clauses.append(Plan.currency == currency.strip().upper())
        return clauses

    def count_admin(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        currency: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Plan)
        for clause in self._admin_filters(search=search, status=status, currency=currency):
            stmt = stmt.where(clause)
        return int(self.db.scalar(stmt) or 0)

    def list_admin(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        currency: str | None = None,
    ) -> list[Plan]:
        stmt = select(Plan).options(selectinload(Plan.entitlements))
        for clause in self._admin_filters(search=search, status=status, currency=currency):
            stmt = stmt.where(clause)
        return list(
            self.db.scalars(
                stmt.order_by(Plan.created_at.desc(), Plan.code.asc())
                .offset(offset)
                .limit(limit)
            )
        )

    def count_active_subscribers(self, plan_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.plan_id == plan_id,
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                )
            )
            or 0
        )

    def count_active_subscribers_batch(self, plan_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not plan_ids:
            return {}
        rows = self.db.execute(
            select(Subscription.plan_id, func.count())
            .where(
                Subscription.plan_id.in_(plan_ids),
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .group_by(Subscription.plan_id)
        ).all()
        return {plan_id: int(count) for plan_id, count in rows}

    def list_active_subscriber_workspace_ids(self, plan_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            self.db.scalars(
                select(Subscription.workspace_id).where(
                    Subscription.plan_id == plan_id,
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                )
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
                .options(selectinload(Subscription.plan))
                .where(Subscription.workspace_id == workspace_id)
                .order_by(Subscription.created_at.desc())
            )
        )

    def list_for_workspace_paginated(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Subscription]:
        return list(
            self.db.scalars(
                select(Subscription)
                .options(selectinload(Subscription.plan))
                .where(Subscription.workspace_id == workspace_id)
                .order_by(Subscription.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def count_for_workspace(self, workspace_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.workspace_id == workspace_id)
            )
            or 0
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

    def list_for_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        statuses: list[str] | None = None,
        kind: str | None = None,
    ) -> tuple[list[Purchase], int]:
        filters = [Purchase.workspace_id == workspace_id]
        if statuses:
            if len(statuses) == 1:
                filters.append(Purchase.status == statuses[0])
            else:
                filters.append(Purchase.status.in_(statuses))
        if kind:
            filters.append(Purchase.kind == kind)
        total = int(
            self.db.scalar(select(func.count()).select_from(Purchase).where(*filters)) or 0
        )
        rows = list(
            self.db.scalars(
                select(Purchase)
                .where(*filters)
                .order_by(Purchase.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total

    def find_open_app_checkout(
        self,
        workspace_id: uuid.UUID,
        *,
        app_id: uuid.UUID,
        kinds: list[str],
    ) -> Purchase | None:
        """Return a pending/redirected App Store checkout for (workspace, app)."""
        if not kinds:
            return None
        return self.db.scalar(
            select(Purchase)
            .where(
                Purchase.workspace_id == workspace_id,
                Purchase.kind.in_(kinds),
                Purchase.status.in_(
                    [
                        PurchaseStatus.PENDING.value,
                        PurchaseStatus.REDIRECTED.value,
                    ]
                ),
                Purchase.payload["app_id"].astext == str(app_id),
            )
            .order_by(Purchase.created_at.desc())
            .limit(1)
        )
