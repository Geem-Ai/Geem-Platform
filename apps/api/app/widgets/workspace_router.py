"""Workspace-authenticated Chat Widget configuration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.widgets.schemas import WidgetInstanceOut, WidgetUpdateIn
from app.widgets.service import WidgetService
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

router = APIRouter(prefix="/api/apps/chat-widget", tags=["chat-widget"])


@router.get("/widget", response_model=WidgetInstanceOut)
def get_widget(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> WidgetInstanceOut:
    workspace, membership = pair
    return WidgetService(db).get_or_create_for_workspace(
        workspace=workspace,
        membership=membership,
    )


@router.put("/widget", response_model=WidgetInstanceOut)
def update_widget(
    body: WidgetUpdateIn,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> WidgetInstanceOut:
    workspace, membership = pair
    return WidgetService(db).update(
        workspace=workspace,
        membership=membership,
        body=body,
    )


@router.post("/widget/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_widget(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> Response:
    workspace, membership = pair
    WidgetService(db).disconnect(workspace=workspace, membership=membership)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
