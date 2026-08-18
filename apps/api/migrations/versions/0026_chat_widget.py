"""Chat Widget instances (embeddable site widget) — Alembic revision.

Revision ID: 0026_chat_widget
Revises: 0025_purchase_invoices
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_chat_widget"
down_revision: Union[str, None] = "0025_purchase_invoices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "widget_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "app_installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "expert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=128), nullable=False, server_default="Geem"),
        sa.Column("subtitle", sa.String(length=256), nullable=True),
        sa.Column("greeting", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(length=1024), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ar"),
        sa.Column(
            "position",
            sa.String(length=32),
            nullable=False,
            server_default="bottom-right",
        ),
        sa.Column(
            "primary_color",
            sa.String(length=16),
            nullable=False,
            server_default="#0e2f44",
        ),
        sa.Column(
            "text_color",
            sa.String(length=16),
            nullable=False,
            server_default="#f2f2f2",
        ),
        sa.Column("allowed_origins", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.UniqueConstraint(
            "workspace_id",
            "app_installation_id",
            name="uq_widget_instances_workspace_installation",
        ),
    )
    op.create_index(
        "ix_widget_instances_workspace_id",
        "widget_instances",
        ["workspace_id"],
    )
    op.create_index(
        "ix_widget_instances_workspace_status",
        "widget_instances",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_widget_instances_workspace_status", table_name="widget_instances")
    op.drop_index("ix_widget_instances_workspace_id", table_name="widget_instances")
    op.drop_table("widget_instances")
