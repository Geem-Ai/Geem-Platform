"""Document / query / jobs route dependencies — authenticated Workspace only (Phase 2C).

Production HTTP Document and RAG operations require:
  valid Bearer + Workspace membership resolved via RequestContext.

Invalid / expired / malformed / revoked Bearer → 401 (never a legacy population).
Missing workspace hint / membership → workspace resolution error (never global docs).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.identity.dependencies import get_current_user, get_workspace_hint, require_workspace
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.policy import WorkspaceAction, WorkspacePolicy

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class DocumentAccess:
    """Authenticated Workspace context for Document / Query / Jobs routes."""

    user: User
    workspace: Workspace
    membership: WorkspaceMembership

    @property
    def is_workspace(self) -> bool:
        return True

    def require_action(self, action: WorkspaceAction) -> None:
        WorkspacePolicy.require(self.membership, action)


def _authorization_header_present(request: Request) -> bool:
    value = request.headers.get("Authorization")
    return bool(value and value.strip())


def get_document_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> DocumentAccess:
    """Require authenticated Workspace context for all Document/RAG HTTP routes."""
    if credentials is None:
        if _authorization_header_present(request):
            raise AppError(ErrorCategory.UNAUTHORIZED, "Authentication required.")
        raise AppError(ErrorCategory.UNAUTHORIZED, "Authentication required.")

    if credentials.scheme.lower() != "bearer":
        raise AppError(ErrorCategory.UNAUTHORIZED, "Authentication required.")

    user = get_current_user(request, credentials, db)
    hint = get_workspace_hint(request)
    workspace, membership = require_workspace(request, user, hint, db)
    return DocumentAccess(user=user, workspace=workspace, membership=membership)


# Alias used by query/jobs routes
get_population_access = get_document_access
PopulationAccess = DocumentAccess
