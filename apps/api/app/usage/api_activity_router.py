"""Workspace session APIs for public-API usage (Phase 7C).

Not public API-key endpoints. Workspace is taken from the session, never
from a client-supplied workspace_id.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.usage.api_activity import DEFAULT_PERIOD, ApiActivityService
from app.usage.api_activity_schemas import ApiUsageHistoryOut, ApiUsageSummaryOut
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

router = APIRouter(prefix="/api/api-usage", tags=["api-usage"])


@router.get("/summary", response_model=ApiUsageSummaryOut)
def get_api_usage_summary(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
    period: str = Query(default=DEFAULT_PERIOD, max_length=8),
) -> ApiUsageSummaryOut:
    workspace, _membership = pair
    return ApiActivityService(db).summarize(workspace.id, period=period)


@router.get("/history", response_model=ApiUsageHistoryOut)
def get_api_usage_history(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    period: str = Query(default=DEFAULT_PERIOD, max_length=8),
    api_key_id: uuid.UUID | None = Query(default=None),
) -> ApiUsageHistoryOut:
    workspace, _membership = pair
    return ApiActivityService(db).history(
        workspace.id,
        limit=limit,
        offset=offset,
        period=period,
        api_key_id=api_key_id,
    )
