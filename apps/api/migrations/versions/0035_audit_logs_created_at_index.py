"""Add created_at index for global Platform Admin audit queries (Phase 12G)."""

from __future__ import annotations

from alembic import op

revision = "0035_audit_logs_created_at_index"
down_revision = "0034_app_commercial_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
