"""Unit tests for Workspace lifecycle guard (Phase 12B)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import AppError, ErrorCategory
from app.workspaces.lifecycle import require_active_workspace
from app.workspaces.models import WorkspaceStatus


def test_require_active_workspace_passes_for_active() -> None:
    require_active_workspace(SimpleNamespace(status=WorkspaceStatus.ACTIVE.value))


@pytest.mark.parametrize(
    "status",
    [WorkspaceStatus.SUSPENDED.value, WorkspaceStatus.ARCHIVED.value, "unknown"],
)
def test_require_active_workspace_rejects_non_active(status: str) -> None:
    with pytest.raises(AppError) as exc:
        require_active_workspace(SimpleNamespace(status=status))
    assert exc.value.category == ErrorCategory.WORKSPACE_ACCESS_DENIED
    assert exc.value.details["status"] == status
