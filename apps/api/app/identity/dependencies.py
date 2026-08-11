from __future__ import annotations

import uuid
from dataclasses import replace

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext, get_request_context, set_request_context
from app.common.workspace_resolver import WorkspaceResolutionHint, resolve_workspace_hint
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.identity.models import Session as AuthSession
from app.identity.models import User, UserStatus
from app.identity.repository import SessionRepository, UserRepository
from app.identity.security import decode_access_token
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.service import WorkspaceService

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    """Client IP for rate limiting.

    X-Forwarded-For is ignored unless Settings.trust_proxy_headers is true.
    When enabled, the edge proxy must overwrite (not append-trust) the header.
    """
    from app.core.config import get_settings

    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def get_workspace_hint(request: Request) -> WorkspaceResolutionHint:
    return resolve_workspace_hint(request)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(ErrorCategory.UNAUTHORIZED, "Authentication required.")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(payload["sub"]))
        session_id = uuid.UUID(str(payload["sid"]))
    except (KeyError, ValueError) as exc:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid access token.") from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise AppError(ErrorCategory.UNAUTHORIZED, "User is not active.")

    session = SessionRepository(db).get_by_id(session_id)
    if session is None or session.user_id != user.id:
        raise AppError(ErrorCategory.SESSION_REVOKED, "Session is invalid or revoked.")
    if session.revoked_at is not None:
        raise AppError(ErrorCategory.SESSION_REVOKED, "Session is invalid or revoked.")

    _bind_user_context(request, user=user, session=session)
    request.state.user = user
    request.state.auth_session = session
    return user


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        return get_current_user(request, credentials, db)
    except AppError:
        return None


def require_workspace(
    request: Request,
    user: User = Depends(get_current_user),
    hint: WorkspaceResolutionHint = Depends(get_workspace_hint),
    db: Session = Depends(get_db),
) -> tuple[Workspace, WorkspaceMembership]:
    """Resolve workspace from hint and verify membership. Frontend context is not trusted."""
    svc = WorkspaceService(db)
    if hint.workspace_id is not None:
        workspace, membership = svc.get_workspace_for_user(hint.workspace_id, user.id)
    elif hint.slug is not None:
        workspace, membership = svc.get_by_slug_for_user(hint.slug, user.id)
    else:
        raise AppError(
            ErrorCategory.WORKSPACE_NOT_FOUND,
            "No workspace context provided.",
        )

    _bind_workspace_context(
        request,
        workspace=workspace,
        membership=membership,
        resolution_source=hint.source,
    )
    request.state.workspace = workspace
    request.state.membership = membership
    return workspace, membership


def _bind_user_context(request: Request, *, user: User, session: AuthSession) -> None:
    ctx = get_request_context()
    updated = replace(
        ctx,
        user_id=user.id,
        platform_role=user.platform_role,
        session_id=session.id,
    )
    set_request_context(updated)
    request.state.request_context = updated


def _bind_workspace_context(
    request: Request,
    *,
    workspace: Workspace,
    membership: WorkspaceMembership,
    resolution_source: str,
) -> None:
    ctx = get_request_context()
    updated = replace(
        ctx,
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        membership_role=membership.role,
        workspace_resolution=resolution_source,
    )
    set_request_context(updated)
    request.state.request_context = updated
