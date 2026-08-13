"""Phase 5C — storage reservations + in-flight reserved_bytes counter.

* ``workspace_resource_usage`` — current reserved bytes per Workspace metric
* ``storage_reservations`` — durable hold per upload request_id

Billable storage *used* remains SUM(active documents.byte_size).
Expert allowance is counted live from ``experts`` (no extra table).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_storage_expert_quota"
down_revision: Union[str, None] = "0010_ai_usage_reservations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_resource_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False, server_default="storage_bytes"),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("workspace_id", "metric", name="uq_workspace_resource_usage"),
        sa.CheckConstraint(
            "reserved_bytes >= 0",
            name="ck_workspace_resource_usage_reserved_non_negative",
        ),
    )

    op.create_table(
        "storage_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="reserved"),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "workspace_id",
            "request_id",
            name="uq_storage_reservations_workspace_request",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'finalized', 'released')",
            name="ck_storage_reservations_status",
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name="ck_storage_reservations_byte_size_non_negative",
        ),
    )
    op.create_index(
        "ix_storage_reservations_workspace",
        "storage_reservations",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_storage_reservations_workspace", table_name="storage_reservations")
    op.drop_table("storage_reservations")
    op.drop_table("workspace_resource_usage")
