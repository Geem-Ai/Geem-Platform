"""API-key authentication dependencies for public Workspace APIs (Phase 7B).

Workspace identity is taken exclusively from the API key. Host, slug headers,
body/query workspace_id, and session Workspace context cannot override it.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.service import ApiKeyService
from app.common.request_context import get_request_context, set_request_context
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.workspaces.models import Workspace
from app.workspaces.repository import WorkspaceRepository

api_key_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="ApiKey",
    description=(
        "Workspace API key. Send `Authorization: Bearer` followed by the "
        "`geem_sk_` secret returned once at creation."
    ),
)


def get_api_key_service(db: Session = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(db)


def get_api_key_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(api_key_scheme),
    db: Session = Depends(get_db),
) -> ApiKeyPrincipal:
    if credentials is None:
        header = request.headers.get("Authorization")
        if header and header.strip():
            raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid API key.")
        raise AppError(ErrorCategory.UNAUTHORIZED, "Authentication required.")
    if credentials.scheme.lower() != "bearer":
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid API key.")

    service = ApiKeyService(db)
    principal = service.authenticate(credentials.credentials)
    workspace = WorkspaceRepository(db).get_by_id(principal.workspace_id)
    if workspace is None:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid API key.")
    _bind_api_key_context(request, principal=principal, workspace=workspace)
    request.state.api_key_principal = principal
    request.state.workspace = workspace
    return principal


def require_api_scope(scope: str):
    """Dependency factory: authenticate the API key and require ``scope``."""

    def _dep(
        principal: ApiKeyPrincipal = Depends(get_api_key_principal),
        db: Session = Depends(get_db),
    ) -> ApiKeyPrincipal:
        ApiKeyService(db).require_scope(principal, scope)
        return principal

    return _dep


def _bind_api_key_context(
    request: Request,
    *,
    principal: ApiKeyPrincipal,
    workspace: Workspace,
) -> None:
    """Overwrite any Host/header/session Workspace hint with the key's tenant."""
    ctx = get_request_context()
    updated = replace(
        ctx,
        user_id=None,
        session_id=None,
        membership_role=None,
        platform_role=None,
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        workspace_resolution="api_key",
        api_key_id=principal.api_key_id,
    )
    set_request_context(updated)
    request.state.request_context = updated
    from app.observability.attributes import attach_request_context

    attach_request_context()
