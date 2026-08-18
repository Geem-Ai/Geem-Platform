"""Workspace API-key management (session auth). Owner/admin only."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey
from app.api_keys.schemas import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyOut, to_api_key_out
from app.api_keys.service import ApiKeyService
from app.db.session import get_db
from app.workspaces.dependencies import require_workspace_action
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.policy import WorkspaceAction

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


def _created_response(row: ApiKey, plaintext: str) -> ApiKeyCreateResponse:
    base = to_api_key_out(row)
    return ApiKeyCreateResponse(**base.model_dump(), key=plaintext)


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.VIEW_API_KEYS)
    ),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    workspace, _membership = pair
    return [to_api_key_out(row) for row in ApiKeyService(db).list_keys(workspace.id)]


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
def create_api_key(
    body: ApiKeyCreateRequest,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.CREATE_API_KEYS)
    ),
    db: Session = Depends(get_db),
) -> ApiKeyCreateResponse:
    workspace, membership = pair
    created = ApiKeyService(db).create_key(
        workspace=workspace,
        actor_id=membership.user_id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    return _created_response(created.row, created.plaintext)


@router.post("/{api_key_id}/revoke", response_model=ApiKeyOut)
def revoke_api_key(
    api_key_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.REVOKE_API_KEYS)
    ),
    db: Session = Depends(get_db),
) -> ApiKeyOut:
    workspace, membership = pair
    row = ApiKeyService(db).revoke_key(
        workspace_id=workspace.id,
        api_key_id=api_key_id,
        actor_id=membership.user_id,
    )
    return to_api_key_out(row)
