"""Effective Workspace entitlements (Phase 5A)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.schemas import EntitlementItemOut, EntitlementsOut, PlanSummaryOut
from app.db.session import get_db
from app.entitlements.keys import entitlement_display_sort_key
from app.entitlements.service import EntitlementService
from app.workspaces.dependencies import require_workspace_action
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.policy import WorkspaceAction

router = APIRouter(prefix="/api/entitlements", tags=["entitlements"])


@router.get("", response_model=EntitlementsOut)
def get_entitlements(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace_action(WorkspaceAction.READ_WORKSPACE)),
    db: Session = Depends(get_db),
) -> EntitlementsOut:
    workspace, _membership = pair
    svc = EntitlementService(db)
    try:
        resolved = svc.get_effective_entitlements(workspace.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        resolved = svc.get_effective_entitlements(workspace.id)
        db.commit()
    items = [
        EntitlementItemOut(
            key=item.key,
            value=item.as_python(),
            value_type=item.value_type.value,
        )
        for item in sorted(
            resolved.items.values(),
            key=lambda row: entitlement_display_sort_key(row.key),
        )
    ]
    return EntitlementsOut(
        subscription_id=resolved.subscription_id,
        plan=PlanSummaryOut(
            id=resolved.plan_id,
            code=resolved.plan_code,
            name=resolved.plan_name,
            status=resolved.plan_status,
        ),
        items=items,
    )
