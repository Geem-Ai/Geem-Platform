"""Phase 3A — Experts domain + Workspace kind (system / Platform Knowledge).

* ``workspaces.kind`` — tenant | system (default tenant)
* ``experts`` / ``expert_sources`` / ``expert_documents`` / ``workspace_expert_grants``
* DB check: workspace experts require workspace_id; platform experts require NULL

No Qdrant / MinIO path / RAG contract changes in this revision.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_experts_domain"
down_revision: Union[str, None] = "0004_docs_workspace_nn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="tenant",
        ),
    )
    op.create_index("ix_workspaces_kind", "workspaces", ["kind"])

    op.create_table(
        "experts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon_url", sa.String(length=1024), nullable=True),
        sa.Column("icon_key", sa.String(length=512), nullable=True),
        sa.Column("system_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "rag_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="workspace"),
        sa.Column(
            "availability_mode",
            sa.String(length=32),
            nullable=False,
            server_default="selected_workspaces",
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(type = 'workspace' AND workspace_id IS NOT NULL) OR "
            "(type = 'platform' AND workspace_id IS NULL)",
            name="ck_experts_type_workspace_ownership",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_experts_workspace_id", "experts", ["workspace_id"])
    op.create_index("ix_experts_type", "experts", ["type"])
    op.create_index("ix_experts_status", "experts", ["status"])
    op.create_index("ix_experts_visibility", "experts", ["visibility"])
    op.create_index("ix_experts_created_by", "experts", ["created_by"])
    op.create_index("ix_experts_deleted_at", "experts", ["deleted_at"])

    op.create_table(
        "expert_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="upload"),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["expert_id"], ["experts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_expert_sources_expert_id", "expert_sources", ["expert_id"])
    op.create_index("ix_expert_sources_deleted_at", "expert_sources", ["deleted_at"])

    op.create_table(
        "expert_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["expert_id"], ["experts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["expert_sources.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("expert_id", "document_id", name="uq_expert_document"),
    )
    op.create_index("ix_expert_documents_expert_id", "expert_documents", ["expert_id"])
    op.create_index("ix_expert_documents_document_id", "expert_documents", ["document_id"])

    op.create_table(
        "workspace_expert_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expert_id"], ["experts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("workspace_id", "expert_id", name="uq_workspace_expert_grant"),
    )
    op.create_index(
        "ix_workspace_expert_grants_workspace_id", "workspace_expert_grants", ["workspace_id"]
    )
    op.create_index(
        "ix_workspace_expert_grants_expert_id", "workspace_expert_grants", ["expert_id"]
    )


def downgrade() -> None:
    op.drop_table("workspace_expert_grants")
    op.drop_table("expert_documents")
    op.drop_table("expert_sources")
    op.drop_table("experts")
    op.drop_index("ix_workspaces_kind", table_name="workspaces")
    op.drop_column("workspaces", "kind")
