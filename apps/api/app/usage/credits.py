"""Purchased-credit accounts and append-only ledger.

FIFO consumption of GRANT ``remaining_amount`` is owned by ``AiUsageService``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.usage.metrics import CreditLedgerEntryType
from app.usage.models import CreditAccount, CreditLedgerEntry
from app.usage.repository import CreditRepository


class CreditService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = CreditRepository(db)

    def ensure_account(self, workspace_id: uuid.UUID) -> CreditAccount:
        existing = self.repo.get_account(workspace_id)
        if existing is not None:
            return existing
        try:
            with self.db.begin_nested():
                account = self.repo.create_account(
                    CreditAccount(workspace_id=workspace_id, balance=0)
                )
                self.db.flush()
                return account
        except IntegrityError:
            account = self.repo.get_account(workspace_id)
            if account is None:
                raise
            return account

    def get_balance(self, workspace_id: uuid.UUID) -> int:
        account = self.repo.get_account(workspace_id)
        if account is None:
            return 0
        return int(account.balance)

    def append(
        self,
        workspace_id: uuid.UUID,
        *,
        entry_type: CreditLedgerEntryType | str,
        amount: int,
        request_id: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CreditLedgerEntry:
        """Append a ledger row. ``request_id`` is idempotent per Workspace."""
        if amount < 0:
            raise AppError(ErrorCategory.VALIDATION, "Credit amount must be non-negative.")
        parsed = (
            entry_type
            if isinstance(entry_type, CreditLedgerEntryType)
            else CreditLedgerEntryType(entry_type)
        )
        if request_id:
            existing = self.repo.get_ledger_by_request_id(workspace_id, request_id)
            if existing is not None:
                return existing

        account = self.repo.get_account_for_update(workspace_id)
        if account is None:
            self.ensure_account(workspace_id)
            account = self.repo.get_account_for_update(workspace_id)
        if account is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Credit account could not be created.")

        remaining: int | None = amount if parsed == CreditLedgerEntryType.GRANT else None
        delta = _signed_delta(parsed, amount)
        new_balance = int(account.balance) + delta
        if new_balance < 0:
            raise AppError(
                ErrorCategory.INSUFFICIENT_CREDITS,
                "Credit balance cannot go negative.",
                details={"balance": int(account.balance), "amount": amount},
            )
        entry = CreditLedgerEntry(
            workspace_id=workspace_id,
            credit_account_id=account.id,
            request_id=request_id,
            entry_type=parsed.value,
            amount=amount,
            remaining_amount=remaining,
            source_type=source_type,
            source_id=source_id,
            extra=extra or {},
        )
        try:
            with self.db.begin_nested():
                self.repo.append_ledger(entry)
                account.balance = new_balance
                self.db.flush()
        except IntegrityError:
            if request_id:
                replay = self.repo.get_ledger_by_request_id(workspace_id, request_id)
                if replay is not None:
                    return replay
            raise

        return entry

    def list_ledger(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        entry_types: list[str] | None = None,
    ) -> list[CreditLedgerEntry]:
        return self.repo.list_ledger(
            workspace_id, limit=limit, offset=offset, entry_types=entry_types
        )

    def count_ledger(
        self,
        workspace_id: uuid.UUID,
        *,
        entry_types: list[str] | None = None,
    ) -> int:
        return self.repo.count_ledger(workspace_id, entry_types=entry_types)


def _signed_delta(entry_type: CreditLedgerEntryType, amount: int) -> int:
    if entry_type in {CreditLedgerEntryType.GRANT, CreditLedgerEntryType.RELEASE}:
        return amount
    if entry_type in {
        CreditLedgerEntryType.CONSUME,
        CreditLedgerEntryType.RESERVE,
        CreditLedgerEntryType.EXPIRE,
    }:
        return -amount
    if entry_type == CreditLedgerEntryType.ADJUST:
        return amount
    return 0
