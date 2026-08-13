"""Current Workspace subscription (Phase 5A). Checkout lives at /api/billing."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.schemas import PlanSummaryOut, SubscriptionOut
from app.billing.service import SubscriptionService
from app.db.session import get_db
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


@router.get("", response_model=SubscriptionOut)
def get_subscription(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> SubscriptionOut:
    workspace, _membership = pair
    svc = SubscriptionService(db)
    try:
        subscription = svc.ensure_bootstrap_subscription(workspace.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        subscription = svc.ensure_bootstrap_subscription(workspace.id)
        db.commit()
    plan = subscription.plan
    return SubscriptionOut(
        id=subscription.id,
        status=subscription.status,
        plan=PlanSummaryOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            status=plan.status,
        ),
        starts_at=subscription.starts_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        ends_at=subscription.ends_at,
    )
