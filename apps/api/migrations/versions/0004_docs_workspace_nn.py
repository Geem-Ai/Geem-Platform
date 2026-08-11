"""Phase 2C — require documents.workspace_id; drop legacy sha256 uniqueness.

Preconditions (enforced by application migration tooling, not this revision):
  - No rows with ``workspace_id IS NULL``
  - External MinIO/Qdrant ownership reconciled for migrated documents

Upgrade
-------
* Assert zero NULL ownership (fail closed if inventory incomplete)
* ``ALTER COLUMN workspace_id SET NOT NULL``
* Drop ``uq_documents_legacy_sha256_active``
* Keep workspace partial unique ``uq_documents_workspace_sha256_active``
  (predicate simplified: ``deleted_at IS NULL`` is enough once NULL ownership is gone)

Downgrade restores nullability + legacy partial unique for rollback tooling only.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_docs_workspace_nn"
down_revision: Union[str, None] = "0003_documents_workspace_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    remaining = conn.execute(
        sa.text("SELECT COUNT(*) FROM documents WHERE workspace_id IS NULL")
    ).scalar()
    if remaining and int(remaining) > 0:
        raise RuntimeError(
            f"Cannot set documents.workspace_id NOT NULL: {remaining} legacy "
            "row(s) remain. Run `python -m app.maintenance.phase2c_migrate_legacy --apply` "
            "then `--verify` before upgrading to 0004."
        )

    op.drop_index(
        "uq_documents_legacy_sha256_active",
        table_name="documents",
        postgresql_where=sa.text("deleted_at IS NULL AND workspace_id IS NULL"),
    )
    # Replace workspace unique with predicate that no longer mentions IS NOT NULL.
    op.drop_index(
        "uq_documents_workspace_sha256_active",
        table_name="documents",
        postgresql_where=sa.text("deleted_at IS NULL AND workspace_id IS NOT NULL"),
    )
    op.create_index(
        "uq_documents_workspace_sha256_active",
        "documents",
        ["workspace_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.alter_column(
        "documents",
        "workspace_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "documents",
        "workspace_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.drop_index(
        "uq_documents_workspace_sha256_active",
        table_name="documents",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
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
