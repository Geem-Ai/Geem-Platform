"""Workspace usage summary and history (Phase 5A/5D). No checkout APIs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.schemas import (
    AiTokensUsageOut,
    CreditsUsageOut,
    MeterOut,
    StorageUsageOut,
    UsageHistoryCountsOut,
    UsageHistoryItemOut,
    UsageHistoryOut,
    UsageHistoryTokensOut,
    UsageSummaryOut,
)
from app.common.public_model import public_model_or_none
from app.db.session import get_db
from app.usage.history import UsageHistoryService
from app.usage.summary import MeterSnapshot, UsageSummaryService
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _meter(snap: MeterSnapshot) -> MeterOut:
    return MeterOut(
        limit=snap.limit,
        used=snap.used,
        reserved=snap.reserved,
        remaining=snap.remaining,
        period_start=snap.period_start,
        period_end=snap.period_end,
    )


@router.get("/summary", response_model=UsageSummaryOut)
def get_usage_summary(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> UsageSummaryOut:
    workspace, _membership = pair
    svc = UsageSummaryService(db)
    try:
        summary = svc.summarize(workspace.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        summary = svc.summarize(workspace.id)
        db.commit()
    ai = AiTokensUsageOut(
        daily=_meter(summary.ai_daily),
        weekly=_meter(summary.ai_weekly),
        monthly=_meter(summary.ai_monthly),
    )
    storage = summary.storage_detail
    return UsageSummaryOut(
        ai_tokens=ai,
        ai=ai,
        experts=_meter(summary.experts),
        storage_bytes=_meter(summary.storage),
        storage=StorageUsageOut(
            limit_bytes=storage.limit_bytes,
            used_bytes=storage.used_bytes,
            remaining_bytes=storage.remaining_bytes,
            reserved_bytes=storage.reserved_bytes,
            percentage=storage.percentage,
        ),
        credits=CreditsUsageOut(balance=summary.credit_balance),
    )


@router.get("/history", response_model=UsageHistoryOut)
def get_usage_history(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kind: str | None = Query(default=None, max_length=32),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
) -> UsageHistoryOut:
    workspace, _membership = pair
    page = UsageHistoryService(db).list_page(
        workspace.id,
        limit=limit,
        offset=offset,
        kind=kind,
        from_at=from_at,
        to_at=to_at,
    )
    return UsageHistoryOut(
        items=[
            UsageHistoryItemOut(
                id=item.id,
                kind=item.kind,
                tokens=item.tokens,
                credits=item.credits,
                created_at=item.created_at,
                operation_type=item.operation_type,
                model=public_model_or_none(item.model),
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
                request_id=item.request_id,
                source_type=item.source_type,
            )
            for item in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        counts=UsageHistoryCountsOut(
            all=page.counts.all,
            ai=page.counts.ai,
            credits=page.counts.credits,
        ),
        tokens=UsageHistoryTokensOut(
            input=page.tokens.input,
            output=page.tokens.output,
            total=page.tokens.total,
        ),
    )
