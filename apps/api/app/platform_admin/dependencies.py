"""FastAPI dependencies for Platform Admin HTTP surfaces.

Authorization is session/JWT only. Workspace membership, X-Workspace-Slug,
X-Workspace-Id, and API keys are never used as a grant.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.host import enforce_platform_admin_host


def require_platform_admin_host(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """Router-level host boundary. Does not resolve a tenant Workspace."""
    return enforce_platform_admin_host(request, settings)


def require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Authenticated, active, human session user with ``platform_role=admin``.

    ``get_current_user`` already rejects missing/invalid JWTs (401), inactive
    or soft-deleted users (401), and API-key bearer tokens (401 — they are
    not session JWTs). This dependency then fail-closes on role (403).
    """
    return require_platform_admin_user(user)
