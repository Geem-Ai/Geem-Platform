"""Idempotent permission catalog + default workspace role seeding (Phase 10C)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.workspaces.models import (
    Permission,
    WorkspaceRoleDef,
    WorkspaceRolePermission,
)
from app.workspaces.permissions import (
    ADMIN_PERMISSION_KEYS,
    MEMBER_PERMISSION_KEYS,
    PERMISSION_CATALOG,
    SYSTEM_ROLE_DISPLAY_NAMES,
    SystemRoleKey,
)


def normalize_role_name(name: str) -> str:
    return " ".join((name or "").strip().split()).casefold()


def seed_permission_catalog(db: Session) -> dict[str, Permission]:
    """Upsert Geem permission definitions. Does not delete unknown rows."""
    existing = {
        row.key: row
        for row in db.scalars(select(Permission)).all()
    }
    by_key: dict[str, Permission] = {}
    for spec in PERMISSION_CATALOG:
        row = existing.get(spec.key.value)
        if row is None:
            row = Permission(
                key=spec.key.value,
                name_key=spec.name_key,
                description_key=spec.description_key,
                group_key=spec.group_key,
                owner_only=spec.owner_only,
            )
            db.add(row)
        else:
            row.name_key = spec.name_key
            row.description_key = spec.description_key
            row.group_key = spec.group_key
            row.owner_only = spec.owner_only
        by_key[spec.key.value] = row
    db.flush()
    return by_key


def _permission_map(db: Session) -> dict[str, Permission]:
    rows = list(db.scalars(select(Permission)).all())
    if len(rows) < len(PERMISSION_CATALOG):
        return seed_permission_catalog(db)
    return {row.key: row for row in rows}


def _set_role_permissions(
    db: Session,
    role: WorkspaceRoleDef,
    keys: frozenset[str],
    permission_by_key: dict[str, Permission],
) -> None:
    desired = {permission_by_key[k].id for k in keys if k in permission_by_key}
    current = {link.permission_id: link for link in list(role.permission_links)}
    for permission_id, link in list(current.items()):
        if permission_id not in desired:
            role.permission_links.remove(link)
    for permission_id in desired:
        if permission_id not in current:
            perm = next(p for p in permission_by_key.values() if p.id == permission_id)
            role.permission_links.append(
                WorkspaceRolePermission(permission_id=permission_id, permission=perm)
            )


def get_system_role(
    db: Session,
    workspace_id: uuid.UUID,
    system_key: str | SystemRoleKey,
) -> WorkspaceRoleDef | None:
    key = system_key.value if isinstance(system_key, SystemRoleKey) else system_key
    return db.scalar(
        select(WorkspaceRoleDef)
        .options(
            selectinload(WorkspaceRoleDef.permission_links).selectinload(
                WorkspaceRolePermission.permission
            )
        )
        .where(
            WorkspaceRoleDef.workspace_id == workspace_id,
            WorkspaceRoleDef.system_key == key,
        )
    )


def ensure_default_workspace_roles(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    reset_system_permissions: bool = False,
) -> dict[str, WorkspaceRoleDef]:
    """Create Owner / Administrator / Member for a workspace if missing.

    Owner has no stored permission rows (implicit full access).
    Administrator / Member get seeded permission sets matching Phase 10 behavior.

    When ``reset_system_permissions`` is True, Administrator/Member permission
    assignments are reset to the default sets (used by Alembic backfill only).
    """
    permission_by_key = _permission_map(db)
    existing = {
        row.system_key: row
        for row in db.scalars(
            select(WorkspaceRoleDef)
            .options(
                selectinload(WorkspaceRoleDef.permission_links).selectinload(
                    WorkspaceRolePermission.permission
                )
            )
            .where(
                WorkspaceRoleDef.workspace_id == workspace_id,
                WorkspaceRoleDef.system_key.is_not(None),
            )
        ).all()
        if row.system_key
    }

    result: dict[str, WorkspaceRoleDef] = {}

    owner = existing.get(SystemRoleKey.OWNER.value)
    if owner is None:
        owner = WorkspaceRoleDef(
            workspace_id=workspace_id,
            name=SYSTEM_ROLE_DISPLAY_NAMES[SystemRoleKey.OWNER.value],
            name_normalized=normalize_role_name(
                SYSTEM_ROLE_DISPLAY_NAMES[SystemRoleKey.OWNER.value]
            ),
            description="Workspace Owner — full access (protected).",
            system_key=SystemRoleKey.OWNER.value,
            is_system=True,
            is_owner_role=True,
        )
        db.add(owner)
        db.flush()
    result[SystemRoleKey.OWNER.value] = owner

    admin = existing.get(SystemRoleKey.ADMIN.value)
    if admin is None:
        admin = WorkspaceRoleDef(
            workspace_id=workspace_id,
            name=SYSTEM_ROLE_DISPLAY_NAMES[SystemRoleKey.ADMIN.value],
            name_normalized=normalize_role_name(
                SYSTEM_ROLE_DISPLAY_NAMES[SystemRoleKey.ADMIN.value]
            ),
            description="Administrator — manage most workspace resources.",
            system_key=SystemRoleKey.ADMIN.value,
            is_system=True,
            is_owner_role=False,
        )
        db.add(admin)
        db.flush()
        _set_role_permissions(db, admin, ADMIN_PERMISSION_KEYS, permission_by_key)
    elif reset_system_permissions:
        _set_role_permissions(db, admin, ADMIN_PERMISSION_KEYS, permission_by_key)
    result[SystemRoleKey.ADMIN.value] = admin

    member = existing.get(SystemRoleKey.MEMBER.value)
    if member is None:
        member = WorkspaceRoleDef(
            workspace_id=workspace_id,
            name=SYSTEM_ROLE_DISPLAY_NAMES[SystemRoleKey.MEMBER.value],
            name_normalized=normalize_role_name(
                SYSTEM_ROLE_DISPLAY_NAMES[SystemRoleKey.MEMBER.value]
            ),
            description="Member — use workspace resources without admin controls.",
            system_key=SystemRoleKey.MEMBER.value,
            is_system=True,
            is_owner_role=False,
        )
        db.add(member)
        db.flush()
        _set_role_permissions(db, member, MEMBER_PERMISSION_KEYS, permission_by_key)
    elif reset_system_permissions:
        _set_role_permissions(db, member, MEMBER_PERMISSION_KEYS, permission_by_key)
    result[SystemRoleKey.MEMBER.value] = member

    db.flush()
    return result
