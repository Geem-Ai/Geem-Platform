"""RBAC test helpers (Phase 10C)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.workspaces.models import WorkspaceMembership, WorkspaceRoleDef
from app.workspaces.permissions import SystemRoleKey
from app.workspaces.rbac_seed import ensure_default_workspace_roles, seed_permission_catalog


def system_role(
    db: Session,
    workspace_id: str | uuid.UUID,
    key: str | SystemRoleKey = SystemRoleKey.MEMBER,
) -> WorkspaceRoleDef:
    seed_permission_catalog(db)
    wid = uuid.UUID(str(workspace_id))
    roles = ensure_default_workspace_roles(db, wid)
    system_key = key.value if isinstance(key, SystemRoleKey) else key
    role = roles.get(system_key) or db.scalar(
        select(WorkspaceRoleDef).where(
            WorkspaceRoleDef.workspace_id == wid,
            WorkspaceRoleDef.system_key == system_key,
        )
    )
    assert role is not None
    return role


def get_membership(
    db: Session,
    workspace_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
) -> WorkspaceMembership:
    row = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == uuid.UUID(str(workspace_id)),
            WorkspaceMembership.user_id == uuid.UUID(str(user_id)),
        )
    )
    assert row is not None
    return row


def role_id(
    db: Session,
    workspace_id: str | uuid.UUID,
    key: str | SystemRoleKey = SystemRoleKey.MEMBER,
) -> uuid.UUID:
    return system_role(db, workspace_id, key).id


def fake_membership(
    *,
    is_owner: bool = False,
    keys: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> WorkspaceMembership:
    """Duck-typed membership for policy unit tests (no DB)."""
    from types import SimpleNamespace

    links = [SimpleNamespace(permission=SimpleNamespace(key=k)) for k in keys]
    role = SimpleNamespace(is_owner_role=is_owner, permission_links=links, system_key=None)
    return SimpleNamespace(workspace_role=role, role_id=uuid.uuid4())  # type: ignore[return-value]


def add_workspace_member(
    db: Session,
    workspace_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    role: str | SystemRoleKey = SystemRoleKey.MEMBER,
) -> WorkspaceMembership:
    """Attach a user to a workspace using a seeded system role."""
    row = system_role(db, workspace_id, role)
    membership = WorkspaceMembership(
        workspace_id=uuid.UUID(str(workspace_id)),
        user_id=uuid.UUID(str(user_id)),
        role_id=row.id,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership
