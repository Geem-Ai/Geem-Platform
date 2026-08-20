"""Workspace lifecycle guards (Phase 12B).

Disable maps to ``WorkspaceStatus.SUSPENDED`` — distinct from soft-delete /
``archived`` / Phase 11 purge. Tenant access must fail closed when the
Workspace is not ``active``.
"""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace, WorkspaceStatus


def require_active_workspace(workspace: Workspace) -> None:
    """Reject non-active Workspaces at the tenant access boundary.

    Soft-deleted rows should already be filtered by repositories; this guard
    covers ``suspended`` and ``archived`` statuses that remain visible in some
    admin contexts but must not serve tenant traffic.
    """
    if workspace.status == WorkspaceStatus.ACTIVE.value:
        return
    raise AppError(
        ErrorCategory.WORKSPACE_ACCESS_DENIED,
        "Workspace is not active.",
        details={"status": workspace.status},
    )
