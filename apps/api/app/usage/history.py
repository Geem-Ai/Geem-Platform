"""Read-only Workspace usage history for the Usage UI (Phase 5D).

Combines AI token events and purchased-credit ledger rows. Internal
reservation/release bookkeeping is omitted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import BigInteger, String, case, cast, func, literal, null, or_, select, union_all
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.usage.metrics import CreditLedgerEntryType
from app.usage.models import CreditLedgerEntry
from app.usage.weights import AI_HISTORY_KINDS

VISIBLE_CREDIT_KINDS: dict[str, str] = {
    CreditLedgerEntryType.GRANT.value: "credit_grant",
    CreditLedgerEntryType.CONSUME.value: "credit_consume",
    CreditLedgerEntryType.ADJUST.value: "credit_adjust",
    CreditLedgerEntryType.EXPIRE.value: "credit_expire",
}

AI_HISTORY_KIND = "ai_tokens"
AI_OPERATION_KIND = case(
    (UsageEvent.operation_type == "embedding", literal("embed_tokens")),
    (UsageEvent.operation_type == "embed_query", literal("embed_tokens")),
    (UsageEvent.operation_type == "rerank", literal("rerank_tokens")),
    (UsageEvent.operation_type == "pdf_parse", literal("ocr_tokens")),
    (UsageEvent.operation_type == "title", literal("title_tokens")),
    (UsageEvent.operation_type == "speech_to_text", literal("stt_tokens")),
    else_=literal("chat_tokens"),
)

HistoryKindFilter = Literal["all", "ai", "credits"]


@dataclass(frozen=True, slots=True)
class UsageHistoryItem:
    id: uuid.UUID
    kind: str
    tokens: int | None
    credits: int | None
    created_at: datetime
    operation_type: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None
    source_type: str | None = None


@dataclass(frozen=True, slots=True)
class UsageHistoryCounts:
    all: int
    ai: int
    credits: int


@dataclass(frozen=True, slots=True)
class UsageHistoryTokens:
    input: int
    output: int
    total: int


@dataclass(frozen=True, slots=True)
class UsageHistoryPage:
    items: list[UsageHistoryItem]
    total: int
    limit: int
    offset: int
    counts: UsageHistoryCounts
    tokens: UsageHistoryTokens


def normalize_history_kind(kind: str | None) -> HistoryKindFilter:
    raw = (kind or "all").strip().lower()
    if raw in {"ai", "ai_tokens"}:
        return "ai"
    if raw == "credits":
        return "credits"
    return "all"


class UsageHistoryService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def list_items(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> list[UsageHistoryItem]:
        return self.list_page(
            workspace_id,
            limit=limit,
            offset=offset,
            kind=kind,
            from_at=from_at,
            to_at=to_at,
        ).items

    def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> UsageHistoryPage:
        cap = max(1, min(int(limit), 100))
        skip = max(0, int(offset))
        filter_kind = normalize_history_kind(kind)
        start, end = resolve_history_window(
            from_at,
            to_at,
            max_days=self.settings.usage_history_max_days,
            default_days=self.settings.usage_history_default_days,
        )
        combined = self._combined(workspace_id, start=start, end=end)
        counts = self._counts(combined)
        filtered = self._apply_kind(combined, filter_kind)
        total = int(self.db.scalar(select(func.count()).select_from(filtered)) or 0)
        tokens = self._token_totals(filtered)
        rows = self.db.execute(
            select(filtered)
            .order_by(filtered.c.created_at.desc(), filtered.c.id.desc())
            .offset(skip)
            .limit(cap)
        ).all()
        items = [
            UsageHistoryItem(
                id=row.id,
                kind=str(row.kind),
                tokens=int(row.tokens) if row.tokens is not None else None,
                credits=int(row.credits) if row.credits is not None else None,
                created_at=row.created_at,
                operation_type=row.operation_type,
                model=row.model,
                input_tokens=int(row.input_tokens) if row.input_tokens is not None else None,
                output_tokens=int(row.output_tokens)
                if row.output_tokens is not None
                else None,
                request_id=row.request_id,
                source_type=row.source_type,
            )
            for row in rows
        ]
        return UsageHistoryPage(
            items=items,
            total=total,
            limit=cap,
            offset=skip,
            counts=counts,
            tokens=tokens,
        )

    def _token_totals(self, filtered) -> UsageHistoryTokens:
        row = self.db.execute(
            select(
                func.coalesce(func.sum(filtered.c.input_tokens), 0),
                func.coalesce(func.sum(filtered.c.output_tokens), 0),
            )
        ).one()
        inp = int(row[0] or 0)
        out = int(row[1] or 0)
        return UsageHistoryTokens(input=inp, output=out, total=inp + out)

    def _counts(self, combined) -> UsageHistoryCounts:
        rows = self.db.execute(
            select(combined.c.kind, func.count()).group_by(combined.c.kind)
        ).all()
        ai = 0
        credits = 0
        for kind, n in rows:
            if str(kind) in AI_HISTORY_KINDS:
                ai += int(n)
            else:
                credits += int(n)
        return UsageHistoryCounts(all=ai + credits, ai=ai, credits=credits)

    def _apply_kind(self, combined, kind: HistoryKindFilter):
        if kind == "ai":
            return (
                select(combined)
                .where(combined.c.kind.in_(list(AI_HISTORY_KINDS)))
                .subquery("usage_history_filtered")
            )
        if kind == "credits":
            return (
                select(combined)
                .where(combined.c.kind.in_(list(VISIBLE_CREDIT_KINDS.values())))
                .subquery("usage_history_filtered")
            )
        return combined

    def _combined(
        self,
        workspace_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
    ):
        token_sum = func.coalesce(UsageEvent.input_tokens, 0) + func.coalesce(
            UsageEvent.output_tokens, 0
        )
        ai = select(
            UsageEvent.id.label("id"),
            cast(AI_OPERATION_KIND, String(32)).label("kind"),
            cast(token_sum, BigInteger).label("tokens"),
            cast(null(), BigInteger).label("credits"),
            UsageEvent.created_at.label("created_at"),
            cast(UsageEvent.operation_type, String(64)).label("operation_type"),
            cast(UsageEvent.model, String(256)).label("model"),
            cast(UsageEvent.input_tokens, BigInteger).label("input_tokens"),
            cast(UsageEvent.output_tokens, BigInteger).label("output_tokens"),
            cast(UsageEvent.request_id, String(128)).label("request_id"),
            cast(null(), String(64)).label("source_type"),
        ).where(
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.created_at >= start,
            UsageEvent.created_at < end,
            or_(
                UsageEvent.input_tokens > 0,
                UsageEvent.output_tokens > 0,
            ),
        )
        kind_expr = case(
            *(
                (CreditLedgerEntry.entry_type == src, dest)
                for src, dest in VISIBLE_CREDIT_KINDS.items()
            ),
            else_=literal("other"),
        )
        credits = select(
            CreditLedgerEntry.id.label("id"),
            cast(kind_expr, String(32)).label("kind"),
            cast(null(), BigInteger).label("tokens"),
            CreditLedgerEntry.amount.label("credits"),
            CreditLedgerEntry.created_at.label("created_at"),
            cast(null(), String(64)).label("operation_type"),
            cast(null(), String(256)).label("model"),
            cast(null(), BigInteger).label("input_tokens"),
            cast(null(), BigInteger).label("output_tokens"),
            cast(CreditLedgerEntry.request_id, String(128)).label("request_id"),
            cast(CreditLedgerEntry.source_type, String(64)).label("source_type"),
        ).where(
            CreditLedgerEntry.workspace_id == workspace_id,
            CreditLedgerEntry.created_at >= start,
            CreditLedgerEntry.created_at < end,
            CreditLedgerEntry.entry_type.in_(list(VISIBLE_CREDIT_KINDS.keys())),
        )
        return union_all(ai, credits).subquery("usage_history")


def resolve_history_window(
    from_at: datetime | None,
    to_at: datetime | None,
    *,
    max_days: int,
    default_days: int,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.tzinfo.utcoffset(current) is None:
        current = current.replace(tzinfo=timezone.utc)
    end = _aware(to_at) or current
    start = _aware(from_at)
    if start is None:
        # No from/to (Workspace "All time"): use the max allowed window so the
        # UI is not silently clipped to 30 days. Only `to` still uses default_days.
        window = max_days if from_at is None and to_at is None else default_days
        start = end - timedelta(days=window)
    if start >= end:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Usage history 'from' must be before 'to'.",
            details={"from": start.isoformat(), "to": end.isoformat()},
        )
    span = end - start
    if span > timedelta(days=max_days):
        raise AppError(
            ErrorCategory.VALIDATION,
            f"Usage history range cannot exceed {max_days} days.",
            details={
                "from": start.isoformat(),
                "to": end.isoformat(),
                "max_days": max_days,
            },
        )
    return start, end


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value
