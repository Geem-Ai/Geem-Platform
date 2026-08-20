"""Workspace-scoped usage / credit data access.

Every tenant query takes ``workspace_id``. Ledger and storage events are
append-only — this repository has no update/delete for those tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.usage.metrics import CreditLedgerEntryType
from app.usage.models import (
    AiUsageReservation,
    CreditAccount,
    CreditLedgerEntry,
    StorageReservation,
    StorageUsageEvent,
    UsagePeriodCounter,
    WorkspaceResourceUsage,
)



class CreditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_account(self, workspace_id: uuid.UUID) -> CreditAccount | None:
        return self.db.scalar(
            select(CreditAccount).where(CreditAccount.workspace_id == workspace_id)
        )

    def get_account_for_update(self, workspace_id: uuid.UUID) -> CreditAccount | None:
        return self.db.scalar(
            select(CreditAccount)
            .where(CreditAccount.workspace_id == workspace_id)
            .with_for_update()
        )

    def create_account(self, account: CreditAccount) -> CreditAccount:
        self.db.add(account)
        self.db.flush()
        return account

    def get_ledger_by_request_id(
        self, workspace_id: uuid.UUID, request_id: str
    ) -> CreditLedgerEntry | None:
        return self.db.scalar(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.workspace_id == workspace_id,
                CreditLedgerEntry.request_id == request_id,
            )
        )

    def list_ledger(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        entry_types: list[str] | None = None,
    ) -> list[CreditLedgerEntry]:
        stmt = select(CreditLedgerEntry).where(
            CreditLedgerEntry.workspace_id == workspace_id
        )
        if entry_types:
            stmt = stmt.where(CreditLedgerEntry.entry_type.in_(entry_types))
        return list(
            self.db.scalars(
                stmt.order_by(CreditLedgerEntry.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def count_ledger(
        self,
        workspace_id: uuid.UUID,
        *,
        entry_types: list[str] | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(CreditLedgerEntry)
            .where(CreditLedgerEntry.workspace_id == workspace_id)
        )
        if entry_types:
            stmt = stmt.where(CreditLedgerEntry.entry_type.in_(entry_types))
        return int(self.db.scalar(stmt) or 0)

    def append_ledger(self, entry: CreditLedgerEntry) -> CreditLedgerEntry:
        self.db.add(entry)
        self.db.flush()
        return entry

    def lock_grants_for_fifo(
        self,
        workspace_id: uuid.UUID,
        *,
        extra_ids: list[uuid.UUID] | None = None,
    ) -> list[CreditLedgerEntry]:
        """Lock GRANT rows in created_at, id order (open remaining and/or extra ids)."""
        open_grants = and_(
            CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
            CreditLedgerEntry.remaining_amount > 0,
        )
        if extra_ids:
            stmt = (
                select(CreditLedgerEntry)
                .where(
                    CreditLedgerEntry.workspace_id == workspace_id,
                    or_(open_grants, CreditLedgerEntry.id.in_(extra_ids)),
                )
                .order_by(CreditLedgerEntry.created_at.asc(), CreditLedgerEntry.id.asc())
                .with_for_update()
            )
        else:
            stmt = (
                select(CreditLedgerEntry)
                .where(CreditLedgerEntry.workspace_id == workspace_id, open_grants)
                .order_by(CreditLedgerEntry.created_at.asc(), CreditLedgerEntry.id.asc())
                .with_for_update()
            )
        return list(self.db.scalars(stmt))


class AiUsageReservationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_request_id(
        self, workspace_id: uuid.UUID, request_id: str
    ) -> AiUsageReservation | None:
        return self.db.scalar(
            select(AiUsageReservation).where(
                AiUsageReservation.workspace_id == workspace_id,
                AiUsageReservation.request_id == request_id,
            )
        )

    def get_by_request_id_for_update(
        self, workspace_id: uuid.UUID, request_id: str
    ) -> AiUsageReservation | None:
        return self.db.scalar(
            select(AiUsageReservation)
            .where(
                AiUsageReservation.workspace_id == workspace_id,
                AiUsageReservation.request_id == request_id,
            )
            .with_for_update()
        )

    def create(self, row: AiUsageReservation) -> AiUsageReservation:
        self.db.add(row)
        self.db.flush()
        return row


class UsageCounterRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: str,
        period_type: str,
        period_start: datetime,
    ) -> UsagePeriodCounter | None:
        return self.db.scalar(
            select(UsagePeriodCounter).where(
                UsagePeriodCounter.workspace_id == workspace_id,
                UsagePeriodCounter.metric == metric,
                UsagePeriodCounter.period_type == period_type,
                UsagePeriodCounter.period_start == period_start,
            )
        )

    def get_for_update(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: str,
        period_type: str,
        period_start: datetime,
    ) -> UsagePeriodCounter | None:
        return self.db.scalar(
            select(UsagePeriodCounter)
            .where(
                UsagePeriodCounter.workspace_id == workspace_id,
                UsagePeriodCounter.metric == metric,
                UsagePeriodCounter.period_type == period_type,
                UsagePeriodCounter.period_start == period_start,
            )
            .with_for_update()
        )

    def create(self, counter: UsagePeriodCounter) -> UsagePeriodCounter:
        self.db.add(counter)
        self.db.flush()
        return counter

    def get_by_id_for_update(self, counter_id: uuid.UUID) -> UsagePeriodCounter | None:
        return self.db.scalar(
            select(UsagePeriodCounter)
            .where(UsagePeriodCounter.id == counter_id)
            .with_for_update()
        )

    def list_for_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        metric: str | None = None,
    ) -> list[UsagePeriodCounter]:
        stmt = select(UsagePeriodCounter).where(
            UsagePeriodCounter.workspace_id == workspace_id
        )
        if metric is not None:
            stmt = stmt.where(UsagePeriodCounter.metric == metric)
        return list(
            self.db.scalars(stmt.order_by(UsagePeriodCounter.period_start.desc()))
        )


class StorageUsageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(self, event: StorageUsageEvent) -> StorageUsageEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def list_for_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StorageUsageEvent]:
        return list(
            self.db.scalars(
                select(StorageUsageEvent)
                .where(StorageUsageEvent.workspace_id == workspace_id)
                .order_by(StorageUsageEvent.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def sum_delta(self, workspace_id: uuid.UUID) -> int:
        value = self.db.scalar(
            select(func.coalesce(func.sum(StorageUsageEvent.delta_bytes), 0)).where(
                StorageUsageEvent.workspace_id == workspace_id
            )
        )
        return int(value or 0)


class WorkspaceResourceUsageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, workspace_id: uuid.UUID, metric: str) -> WorkspaceResourceUsage | None:
        return self.db.scalar(
            select(WorkspaceResourceUsage).where(
                WorkspaceResourceUsage.workspace_id == workspace_id,
                WorkspaceResourceUsage.metric == metric,
            )
        )

    def get_for_update(
        self, workspace_id: uuid.UUID, metric: str
    ) -> WorkspaceResourceUsage | None:
        return self.db.scalar(
            select(WorkspaceResourceUsage)
            .where(
                WorkspaceResourceUsage.workspace_id == workspace_id,
                WorkspaceResourceUsage.metric == metric,
            )
            .with_for_update()
        )

    def create(self, row: WorkspaceResourceUsage) -> WorkspaceResourceUsage:
        self.db.add(row)
        self.db.flush()
        return row


class StorageReservationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_request_id(
        self, workspace_id: uuid.UUID, request_id: str
    ) -> StorageReservation | None:
        return self.db.scalar(
            select(StorageReservation).where(
                StorageReservation.workspace_id == workspace_id,
                StorageReservation.request_id == request_id,
            )
        )

    def get_by_request_id_for_update(
        self, workspace_id: uuid.UUID, request_id: str
    ) -> StorageReservation | None:
        return self.db.scalar(
            select(StorageReservation)
            .where(
                StorageReservation.workspace_id == workspace_id,
                StorageReservation.request_id == request_id,
            )
            .with_for_update()
        )

    def create(self, row: StorageReservation) -> StorageReservation:
        self.db.add(row)
        self.db.flush()
        return row

    def list_stale_reserved(
        self, workspace_id: uuid.UUID, *, older_than: datetime
    ) -> list[StorageReservation]:
        return list(
            self.db.scalars(
                select(StorageReservation)
                .where(
                    StorageReservation.workspace_id == workspace_id,
                    StorageReservation.status == "reserved",
                    StorageReservation.created_at < older_than,
                )
                .order_by(StorageReservation.created_at.asc())
                .with_for_update()
            )
        )
