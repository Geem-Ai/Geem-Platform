"""Phase 2A — tenant-scoped documents (workspace_id, byte_size, soft-delete, hash uniqueness).

Transitional nullability
------------------------
``workspace_id`` is nullable so existing legacy MVP rows (apps/web) keep working.
New authenticated Workspace uploads MUST set ``workspace_id`` in application code.
Phase 2C will backfill legacy rows into the migration Workspace and may then set
``workspace_id NOT NULL``.

Hash uniqueness
---------------
Replaces global ``UNIQUE(sha256)`` with two partial unique indexes:

* Workspace-owned active rows: ``UNIQUE(workspace_id, sha256) WHERE deleted_at IS NULL AND workspace_id IS NOT NULL``
* Legacy active rows: ``UNIQUE(sha256) WHERE deleted_at IS NULL AND workspace_id IS NULL``

Soft-deleted rows release the uniqueness slot (re-upload allowed after soft delete).

FK: ``ON DELETE RESTRICT`` — do not cascade-destroy document history with workspace hard delete.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_documents_workspace_scope"
down_revision: Union[str, None] = "0002_identity_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("documents", sa.Column("byte_size", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        "fk_documents_workspace_id",
        "documents",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])
    op.create_index("ix_documents_workspace_created_at", "documents", ["workspace_id", "created_at"])
    op.create_index("ix_documents_workspace_status", "documents", ["workspace_id", "status"])

    # Drop global unique hash index from 0001_initial.
    op.drop_index("ix_documents_sha256", table_name="documents")

    op.create_index(
        "uq_documents_workspace_sha256_active",
        "documents",
        ["workspace_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND workspace_id IS NOT NULL"),
    )
    op.create_index(
        "uq_documents_legacy_sha256_active",
        "documents",
        ["sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND workspace_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_documents_legacy_sha256_active",
        table_name="documents",
        postgresql_where=sa.text("deleted_at IS NULL AND workspace_id IS NULL"),
    )
    op.drop_index(
        "uq_documents_workspace_sha256_active",
        table_name="documents",
        postgresql_where=sa.text("deleted_at IS NULL AND workspace_id IS NOT NULL"),
    )

    # Restore global unique — may fail if cross-workspace duplicate hashes exist.
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=True)

    op.drop_index("ix_documents_workspace_status", table_name="documents")
    op.drop_index("ix_documents_workspace_created_at", table_name="documents")
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_constraint("fk_documents_workspace_id", "documents", type_="foreignkey")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "byte_size")
    op.drop_column("documents", "workspace_id")
