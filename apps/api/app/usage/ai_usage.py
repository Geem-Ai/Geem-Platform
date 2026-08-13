"""Atomic AI usage reservation, settlement, and purchased-credit FIFO (Phase 5B).

Commercial source of truth is ``usage_period_counters`` + credit ledger.
``usage_events`` remain model/provider telemetry.

Reservation algorithm
---------------------
``reserve_ai_usage`` runs in the caller's DB transaction (caller commits).
No LLM call may start until this returns successfully.

Inside the transaction:

1. Take a workspace advisory lock (``pg_advisory_xact_lock``) so concurrent
   reserve/settle/release for the same Workspace serialize at the metering
   layer. Row locks still apply.
2. Reload an existing reservation for ``request_id`` and return it (idempotent;
   does not create a second hold).
3. Resolve current AI entitlement limits (fail-closed missing keys → 0).
4. Ensure today's / this week's / this month's ``ai_tokens`` counter rows exist.
5. Lock in deterministic order:
     credit_account
     GRANT ledger rows (remaining_amount > 0) ORDER BY created_at, id
     daily counter, weekly counter, monthly counter
6. ``included_available = min(daily_remaining, weekly_remaining, monthly_remaining)``
   where remaining = max(0, limit - used - reserved).
7. ``credit_available = min(account.balance, sum(grant.remaining_amount))``.
8. Use included first: ``included = min(estimated, included_available)``.
   Remainder ``credit_needed = estimated - included`` is taken FIFO from grants.
9. If ``included + credit_available < estimated``: raise a typed error
   (no counter/ledger writes persist — savepoint rollback).
10. Increment ``reserved`` on all three counters by ``included``.
    Decrement grant ``remaining_amount`` FIFO; append a RESERVE ledger row
    (``{request_id}:cr``) which decreases cached balance.
11. Persist ``ai_usage_reservations`` keyed by ``(workspace_id, request_id)``.

Included / purchased-credit allocation
--------------------------------------
Included allowance is the binding min of the three period remainings.
Purchased credits never make a period counter go negative; they only cover
the amount above ``included_available``. Grants are consumed oldest-first
(``created_at``, then ``id``). ``remaining_amount`` is the FIFO cursor on
GRANT rows; type/amount of those rows are never rewritten.

Settle
------
Convert the hold to actual usage:

* ``included_used = min(actual, included_reserved)``
* ``credit_used = min(max(actual - included_used, 0), credit_reserved)``
* Counters: ``reserved -= included_reserved``, ``used += included_used``.
* Unused credit hold is restored onto grant remaining (tail of allocations)
  and RELEASE'd (``{request_id}:cl``).
* If ``actual > estimated``, take extra from remaining included then FIFO
  credits. If still short, charge everything available and record
  ``undercharged_tokens`` — never a negative balance. The user-facing
  generation is not failed after the model already ran.
Idempotent: a second settle returns the first result.

Release
-------
On failure before chargeable usage: restore included ``reserved`` and all
credit allocations, RELEASE ledger (``{request_id}:cl``). Idempotent.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.quota import QuotaService
from app.usage.credits import CreditService
from app.usage.dtos import AiUsageReservationDTO, CreditAllocation
from app.usage.meters import UsageMeterService
from app.usage.metrics import AiUsageReservationStatus, CreditLedgerEntryType, UsageMetric
from app.usage.models import AiUsageReservation, CreditLedgerEntry, UsagePeriodCounter
from app.usage.periods import PeriodType, utcnow
from app.usage.repository import AiUsageReservationRepository, UsageCounterRepository


class AiUsageService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.quota = QuotaService(db, self.settings)
        self.credits = CreditService(db, self.settings)
        self.meters = UsageMeterService(db, self.settings)
        self.reservations = AiUsageReservationRepository(db)
        self.counters = UsageCounterRepository(db)

    def reserve_ai_usage(
        self,
        workspace_id: uuid.UUID,
        request_id: str,
        estimated_tokens: int,
        *,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        expert_id: uuid.UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AiUsageReservationDTO:
        rid = (request_id or "").strip()
        if not rid:
            raise AppError(ErrorCategory.VALIDATION, "request_id is required.")
        if estimated_tokens < 0:
            raise AppError(ErrorCategory.VALIDATION, "estimated_tokens must be non-negative.")

        self._advisory_lock(workspace_id)
        existing = self.reservations.get_by_request_id(workspace_id, rid)
        if existing is not None:
            return self._to_dto(existing)

        try:
            with self.db.begin_nested():
                return self._reserve_locked(
                    workspace_id,
                    rid,
                    estimated_tokens,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    user_id=user_id,
                    expert_id=expert_id,
                    extra=extra,
                )
        except IntegrityError:
            replay = self.reservations.get_by_request_id(workspace_id, rid)
            if replay is not None:
                return self._to_dto(replay)
            raise

    def settle_ai_usage(
        self,
        workspace_id: uuid.UUID,
        request_id: str,
        actual_usage: int,
    ) -> AiUsageReservationDTO:
        rid = (request_id or "").strip()
        if not rid:
            raise AppError(ErrorCategory.VALIDATION, "request_id is required.")
        if actual_usage < 0:
            raise AppError(ErrorCategory.VALIDATION, "actual_usage must be non-negative.")

        self._advisory_lock(workspace_id)
        row = self.reservations.get_by_request_id_for_update(workspace_id, rid)
        if row is None:
            raise AppError(
                ErrorCategory.NOT_FOUND,
                "AI usage reservation not found.",
                details={"request_id": rid},
            )
        if row.status == AiUsageReservationStatus.SETTLED.value:
            return self._to_dto(row)
        if row.status == AiUsageReservationStatus.RELEASED.value:
            return self._to_dto(row)
        return self._settle_locked(row, actual_usage)

    def release_ai_usage(
        self,
        workspace_id: uuid.UUID,
        request_id: str,
    ) -> AiUsageReservationDTO:
        rid = (request_id or "").strip()
        if not rid:
            raise AppError(ErrorCategory.VALIDATION, "request_id is required.")

        self._advisory_lock(workspace_id)
        row = self.reservations.get_by_request_id_for_update(workspace_id, rid)
        if row is None:
            raise AppError(
                ErrorCategory.NOT_FOUND,
                "AI usage reservation not found.",
                details={"request_id": rid},
            )
        if row.status != AiUsageReservationStatus.RESERVED.value:
            return self._to_dto(row)
        return self._release_locked(row)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _advisory_lock(self, workspace_id: uuid.UUID) -> None:
        key = int.from_bytes(workspace_id.bytes[0:8], "big", signed=True)
        self.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})

    def _reserve_locked(
        self,
        workspace_id: uuid.UUID,
        request_id: str,
        estimated_tokens: int,
        *,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        expert_id: uuid.UUID | None,
        extra: dict[str, Any] | None,
    ) -> AiUsageReservationDTO:
        existing = self.reservations.get_by_request_id_for_update(workspace_id, request_id)
        if existing is not None:
            return self._to_dto(existing)

        self.credits.ensure_account(workspace_id)
        now = utcnow()
        daily = self.meters.get_or_create_window(
            workspace_id, metric=UsageMetric.AI_TOKENS, period_type=PeriodType.DAILY, now=now
        )
        weekly = self.meters.get_or_create_window(
            workspace_id, metric=UsageMetric.AI_TOKENS, period_type=PeriodType.WEEKLY, now=now
        )
        monthly = self.meters.get_or_create_window(
            workspace_id, metric=UsageMetric.AI_TOKENS, period_type=PeriodType.MONTHLY, now=now
        )

        account = self.credits.repo.get_account_for_update(workspace_id)
        if account is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Credit account could not be created.")
        grants = self.credits.repo.lock_grants_for_fifo(workspace_id)
        daily = self.counters.get_for_update(
            workspace_id,
            metric=UsageMetric.AI_TOKENS.value,
            period_type=PeriodType.DAILY.value,
            period_start=daily.period_start,
        )
        weekly = self.counters.get_for_update(
            workspace_id,
            metric=UsageMetric.AI_TOKENS.value,
            period_type=PeriodType.WEEKLY.value,
            period_start=weekly.period_start,
        )
        monthly = self.counters.get_for_update(
            workspace_id,
            metric=UsageMetric.AI_TOKENS.value,
            period_type=PeriodType.MONTHLY.value,
            period_start=monthly.period_start,
        )
        if daily is None or weekly is None or monthly is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Usage period counters could not be locked.")

        limits = self.quota.get_ai_limits(workspace_id)
        daily_rem = _remaining(limits.daily, daily)
        weekly_rem = _remaining(limits.weekly, weekly)
        monthly_rem = _remaining(limits.monthly, monthly)
        included_available = min(daily_rem, weekly_rem, monthly_rem)
        credit_available = _credit_available(account.balance, grants)

        included = min(estimated_tokens, included_available)
        credit_needed = estimated_tokens - included
        if credit_needed > credit_available:
            _raise_insufficient(
                requested=estimated_tokens,
                included_available=included_available,
                credit_available=credit_available,
                daily_remaining=daily_rem,
                weekly_remaining=weekly_rem,
                monthly_remaining=monthly_rem,
                included_cap=min(limits.daily, limits.weekly, limits.monthly),
            )

        allocations = _take_fifo(grants, credit_needed)
        daily.reserved = int(daily.reserved) + included
        weekly.reserved = int(weekly.reserved) + included
        monthly.reserved = int(monthly.reserved) + included

        if credit_needed:
            self.credits.append(
                workspace_id,
                entry_type=CreditLedgerEntryType.RESERVE,
                amount=credit_needed,
                request_id=_ledger_request_id(request_id, "cr"),
                source_type="ai_usage",
                source_id=request_id,
                extra={"kind": "reserve"},
            )

        row = AiUsageReservation(
            workspace_id=workspace_id,
            request_id=request_id,
            status=AiUsageReservationStatus.RESERVED.value,
            estimated_tokens=estimated_tokens,
            included_reserved=included,
            credit_reserved=credit_needed,
            credit_allocations=[a.as_dict() for a in allocations],
            daily_counter_id=daily.id,
            weekly_counter_id=weekly.id,
            monthly_counter_id=monthly.id,
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
            expert_id=expert_id,
            extra=extra or {},
        )
        self.reservations.create(row)
        return self._to_dto(row)

    def _settle_locked(self, row: AiUsageReservation, actual: int) -> AiUsageReservationDTO:
        daily, weekly, monthly, account, grants = self._lock_settlement_rows(row)
        included_reserved = int(row.included_reserved)
        credit_reserved = int(row.credit_reserved)
        estimated = int(row.estimated_tokens)

        included_used = min(actual, included_reserved)
        credit_used = min(max(actual - included_used, 0), credit_reserved)

        daily.reserved = _nonneg(int(daily.reserved) - included_reserved)
        weekly.reserved = _nonneg(int(weekly.reserved) - included_reserved)
        monthly.reserved = _nonneg(int(monthly.reserved) - included_reserved)
        daily.used = int(daily.used) + included_used
        weekly.used = int(weekly.used) + included_used
        monthly.used = int(monthly.used) + included_used

        unused_credit = credit_reserved - credit_used
        allocations = list(row.credit_allocations or [])
        if unused_credit:
            _restore_tail(grants, allocations, unused_credit)
            self.credits.append(
                row.workspace_id,
                entry_type=CreditLedgerEntryType.RELEASE,
                amount=unused_credit,
                request_id=_ledger_request_id(row.request_id, "cl"),
                source_type="ai_usage",
                source_id=row.request_id,
                extra={"kind": "release_unused"},
            )

        extra = max(0, actual - estimated)
        extra_included = 0
        extra_credit = 0
        undercharged = 0
        extra_allocations: list[CreditAllocation] = []
        if extra:
            self.db.flush()
            limits = self.quota.get_ai_limits(row.workspace_id)
            extra_included, extra_credit, undercharged, extra_allocations = self._consume_extra(
                extra,
                daily=daily,
                weekly=weekly,
                monthly=monthly,
                limits=limits,
                grants=grants,
                account_balance=int(account.balance),
            )
            if extra_credit:
                self.credits.append(
                    row.workspace_id,
                    entry_type=CreditLedgerEntryType.CONSUME,
                    amount=extra_credit,
                    request_id=_ledger_request_id(row.request_id, "cx"),
                    source_type="ai_usage",
                    source_id=row.request_id,
                    extra={"kind": "settle_extra"},
                )

        included_settled = included_used + extra_included
        credit_settled = credit_used + extra_credit
        merged_allocs = [a for a in allocations if int(a.get("amount") or 0) > 0]
        merged_allocs.extend(a.as_dict() for a in extra_allocations)

        row.status = AiUsageReservationStatus.SETTLED.value
        row.actual_tokens = actual
        row.included_settled = included_settled
        row.credit_settled = credit_settled
        row.credit_allocations = merged_allocs
        meta = dict(row.extra or {})
        if undercharged:
            meta["undercharged_tokens"] = undercharged
        row.extra = meta
        self.db.flush()
        return self._to_dto(row)

    def _release_locked(self, row: AiUsageReservation) -> AiUsageReservationDTO:
        daily, weekly, monthly, _account, grants = self._lock_settlement_rows(row)
        included_reserved = int(row.included_reserved)
        credit_reserved = int(row.credit_reserved)

        daily.reserved = _nonneg(int(daily.reserved) - included_reserved)
        weekly.reserved = _nonneg(int(weekly.reserved) - included_reserved)
        monthly.reserved = _nonneg(int(monthly.reserved) - included_reserved)

        allocations = list(row.credit_allocations or [])
        if credit_reserved:
            _restore_tail(grants, allocations, credit_reserved)
            self.credits.append(
                row.workspace_id,
                entry_type=CreditLedgerEntryType.RELEASE,
                amount=credit_reserved,
                request_id=_ledger_request_id(row.request_id, "cl"),
                source_type="ai_usage",
                source_id=row.request_id,
                extra={"kind": "release"},
            )

        row.status = AiUsageReservationStatus.RELEASED.value
        row.included_settled = 0
        row.credit_settled = 0
        row.actual_tokens = 0
        row.credit_allocations = allocations
        self.db.flush()
        return self._to_dto(row)

    def _lock_settlement_rows(
        self, row: AiUsageReservation
    ) -> tuple[
        UsagePeriodCounter,
        UsagePeriodCounter,
        UsagePeriodCounter,
        Any,
        list[CreditLedgerEntry],
    ]:
        account = self.credits.repo.get_account_for_update(row.workspace_id)
        if account is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Credit account not found.")
        extra_ids = [
            uuid.UUID(str(item["grant_id"]))
            for item in (row.credit_allocations or [])
            if item.get("grant_id")
        ]
        grants = self.credits.repo.lock_grants_for_fifo(row.workspace_id, extra_ids=extra_ids or None)
        daily = self.counters.get_by_id_for_update(row.daily_counter_id)
        weekly = self.counters.get_by_id_for_update(row.weekly_counter_id)
        monthly = self.counters.get_by_id_for_update(row.monthly_counter_id)
        if daily is None or weekly is None or monthly is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Usage period counters not found.")
        return daily, weekly, monthly, account, grants

    def _consume_extra(
        self,
        extra: int,
        *,
        daily: UsagePeriodCounter,
        weekly: UsagePeriodCounter,
        monthly: UsagePeriodCounter,
        limits: Any,
        grants: list[CreditLedgerEntry],
        account_balance: int,
    ) -> tuple[int, int, int, list[CreditAllocation]]:
        daily_rem = _remaining(limits.daily, daily)
        weekly_rem = _remaining(limits.weekly, weekly)
        monthly_rem = _remaining(limits.monthly, monthly)
        included_available = min(daily_rem, weekly_rem, monthly_rem)
        credit_available = _credit_available(account_balance, grants)

        extra_included = min(extra, included_available)
        extra_credit_needed = extra - extra_included
        extra_credit = min(extra_credit_needed, credit_available)
        undercharged = extra - extra_included - extra_credit

        daily.used = int(daily.used) + extra_included
        weekly.used = int(weekly.used) + extra_included
        monthly.used = int(monthly.used) + extra_included
        allocations = _take_fifo(grants, extra_credit)
        return extra_included, extra_credit, undercharged, allocations

    def _to_dto(self, row: AiUsageReservation) -> AiUsageReservationDTO:
        allocations = [
            CreditAllocation(
                grant_id=uuid.UUID(str(item["grant_id"])),
                amount=int(item.get("amount") or 0),
            )
            for item in (row.credit_allocations or [])
            if item.get("grant_id")
        ]
        return AiUsageReservationDTO(
            id=row.id,
            workspace_id=row.workspace_id,
            request_id=row.request_id,
            status=row.status,
            estimated_tokens=int(row.estimated_tokens),
            included_reserved=int(row.included_reserved),
            credit_reserved=int(row.credit_reserved),
            actual_tokens=int(row.actual_tokens) if row.actual_tokens is not None else None,
            included_settled=int(row.included_settled),
            credit_settled=int(row.credit_settled),
            credit_allocations=allocations,
            undercharged_tokens=int((row.extra or {}).get("undercharged_tokens") or 0),
        )


def _remaining(limit: int, counter: UsagePeriodCounter) -> int:
    return max(0, int(limit) - int(counter.used) - int(counter.reserved))


def _credit_available(balance: int, grants: list[CreditLedgerEntry]) -> int:
    grant_sum = sum(max(0, int(g.remaining_amount or 0)) for g in grants)
    return min(max(0, int(balance)), grant_sum)


def _take_fifo(grants: list[CreditLedgerEntry], amount: int) -> list[CreditAllocation]:
    need = int(amount)
    allocations: list[CreditAllocation] = []
    if need <= 0:
        return allocations
    for grant in grants:
        if need <= 0:
            break
        available = max(0, int(grant.remaining_amount or 0))
        if available <= 0:
            continue
        take = min(available, need)
        grant.remaining_amount = available - take
        allocations.append(CreditAllocation(grant_id=grant.id, amount=take))
        need -= take
    if need > 0:
        raise AppError(
            ErrorCategory.INSUFFICIENT_CREDITS,
            "Purchased credits could not cover the requested AI usage.",
            details={"shortfall": need},
        )
    return allocations


def _restore_tail(
    grants: list[CreditLedgerEntry],
    allocations: list[dict[str, Any]],
    unused: int,
) -> None:
    by_id = {g.id: g for g in grants}
    remaining = int(unused)
    for item in reversed(allocations):
        if remaining <= 0:
            break
        grant_id = uuid.UUID(str(item["grant_id"]))
        held = int(item.get("amount") or 0)
        if held <= 0:
            continue
        give = min(held, remaining)
        grant = by_id.get(grant_id)
        if grant is None:
            continue
        grant.remaining_amount = int(grant.remaining_amount or 0) + give
        item["amount"] = held - give
        remaining -= give


def _nonneg(value: int) -> int:
    return value if value >= 0 else 0


def _ledger_request_id(request_id: str, suffix: str) -> str:
    return f"{request_id}:{suffix}"


def _raise_insufficient(
    *,
    requested: int,
    included_available: int,
    credit_available: int,
    daily_remaining: int,
    weekly_remaining: int,
    monthly_remaining: int,
    included_cap: int,
) -> None:
    details = {
        "requested": requested,
        "included_available": included_available,
        "credit_available": credit_available,
        "daily_remaining": daily_remaining,
        "weekly_remaining": weekly_remaining,
        "monthly_remaining": monthly_remaining,
    }
    credits_are_the_binding_limit = included_cap <= 0 or (
        included_available == 0 and credit_available > 0
    )
    if credits_are_the_binding_limit:
        raise AppError(
            ErrorCategory.INSUFFICIENT_CREDITS,
            "Not enough purchased credits to complete this AI request.",
            details=details,
        )
    raise AppError(
        ErrorCategory.QUOTA_EXCEEDED,
        "AI usage quota exceeded for this workspace.",
        details=details,
    )
