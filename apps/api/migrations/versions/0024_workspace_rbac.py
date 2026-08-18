"""Phase 10C — dynamic workspace roles and Geem permission catalog.

Revision ID: 0024_workspace_rbac
Revises: 0023_workspace_invitations
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_workspace_rbac"
down_revision: Union[str, None] = "0023_workspace_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("description_key", sa.String(length=200), nullable=False),
        sa.Column("group_key", sa.String(length=64), nullable=False),
        sa.Column("owner_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("key", name="uq_permissions_key"),
    )
    op.create_index("ix_permissions_group_key", "permissions", ["group_key"])

    op.create_table(
        "workspace_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_normalized", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_key", sa.String(length=32), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_owner_role", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_roles_workspace_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "name_normalized",
            name="uq_workspace_roles_workspace_name",
        ),
    )
    op.create_index("ix_workspace_roles_workspace_id", "workspace_roles", ["workspace_id"])
    op.create_index(
        "uq_workspace_roles_workspace_system_key",
        "workspace_roles",
        ["workspace_id", "system_key"],
        unique=True,
        postgresql_where=sa.text("system_key IS NOT NULL"),
    )

    op.create_table(
        "workspace_role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["workspace_roles.id"],
            name="fk_workspace_role_permissions_role_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_workspace_role_permissions_permission_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "role_id", "permission_id", name="pk_workspace_role_permissions"
        ),
        sa.UniqueConstraint(
            "role_id", "permission_id", name="uq_workspace_role_permission"
        ),
    )
    op.create_index(
        "ix_workspace_role_permissions_permission_id",
        "workspace_role_permissions",
        ["permission_id"],
    )

    op.add_column(
        "workspace_memberships",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "workspace_invitations",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    _seed_and_backfill()

    op.alter_column("workspace_memberships", "role_id", nullable=False)
    op.create_foreign_key(
        "fk_workspace_memberships_role_id",
        "workspace_memberships",
        "workspace_roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_workspace_memberships_role_id", "workspace_memberships", ["role_id"]
    )
    op.drop_column("workspace_memberships", "role")

    op.drop_constraint(
        "ck_workspace_invitations_role", "workspace_invitations", type_="check"
    )
    op.alter_column("workspace_invitations", "role_id", nullable=False)
    op.create_foreign_key(
        "fk_workspace_invitations_role_id",
        "workspace_invitations",
        "workspace_roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_workspace_invitations_role_id", "workspace_invitations", ["role_id"]
    )
    op.drop_column("workspace_invitations", "role")


def _seed_and_backfill() -> None:
    """Seed catalog + default roles, then map legacy role strings to role_id."""
    from sqlalchemy.orm import Session

    from app.workspaces.rbac_seed import (
        ensure_default_workspace_roles,
        seed_permission_catalog,
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        seed_permission_catalog(session)
        workspace_ids = [
            row[0]
            for row in session.execute(sa.text("SELECT id FROM workspaces")).all()
        ]
        for workspace_id in workspace_ids:
            ensure_default_workspace_roles(
                session, workspace_id, reset_system_permissions=True
            )
        session.flush()

        session.execute(
            sa.text(
                """
                UPDATE workspace_memberships AS m
                SET role_id = r.id
                FROM workspace_roles AS r
                WHERE r.workspace_id = m.workspace_id
                  AND r.system_key = m.role
                """
            )
        )
        session.execute(
            sa.text(
                """
                UPDATE workspace_invitations AS i
                SET role_id = r.id
                FROM workspace_roles AS r
                WHERE r.workspace_id = i.workspace_id
                  AND r.system_key = i.role
                """
            )
        )
        leftover_m = session.execute(
            sa.text("SELECT count(*) FROM workspace_memberships WHERE role_id IS NULL")
        ).scalar_one()
        leftover_i = session.execute(
            sa.text("SELECT count(*) FROM workspace_invitations WHERE role_id IS NULL")
        ).scalar_one()
        if leftover_m:
            raise RuntimeError(
                f"RBAC backfill left {leftover_m} memberships without role_id"
            )
        if leftover_i:
            raise RuntimeError(
                f"RBAC backfill left {leftover_i} invitations without role_id"
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    op.add_column(
        "workspace_invitations",
        sa.Column("role", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE workspace_invitations AS i
            SET role = COALESCE(r.system_key, 'member')
            FROM workspace_roles AS r
            WHERE r.id = i.role_id
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE workspace_invitations SET role = 'member' WHERE role IS NULL"
        )
    )
    op.alter_column("workspace_invitations", "role", nullable=False)
    op.drop_constraint(
        "fk_workspace_invitations_role_id", "workspace_invitations", type_="foreignkey"
    )
    op.drop_index("ix_workspace_invitations_role_id", table_name="workspace_invitations")
    op.drop_column("workspace_invitations", "role_id")
    op.create_check_constraint(
        "ck_workspace_invitations_role",
        "workspace_invitations",
        "role IN ('admin', 'member')",
    )

    op.add_column(
        "workspace_memberships",
        sa.Column("role", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE workspace_memberships AS m
            SET role = COALESCE(r.system_key, 'member')
            FROM workspace_roles AS r
            WHERE r.id = m.role_id
            """
        )
    )
    op.execute(
        sa.text("UPDATE workspace_memberships SET role = 'member' WHERE role IS NULL")
    )
    op.alter_column("workspace_memberships", "role", nullable=False)
    op.drop_constraint(
        "fk_workspace_memberships_role_id", "workspace_memberships", type_="foreignkey"
    )
    op.drop_index("ix_workspace_memberships_role_id", table_name="workspace_memberships")
    op.drop_column("workspace_memberships", "role")

    op.drop_table("workspace_role_permissions")
    op.drop_index(
        "uq_workspace_roles_workspace_system_key", table_name="workspace_roles"
    )
    op.drop_index("ix_workspace_roles_workspace_id", table_name="workspace_roles")
    op.drop_table("workspace_roles")
    op.drop_index("ix_permissions_group_key", table_name="permissions")
    op.drop_table("permissions")
