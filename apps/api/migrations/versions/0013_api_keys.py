"""Phase 7A — workspace API keys + usage_events.api_key_id attribution.

* ``api_keys`` — hashed Workspace credentials, scopes, persistent revocation
* ``usage_events.api_key_id`` — nullable FK for future public Chat metering (7B)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_api_keys"
down_revision: Union[str, None] = "0012_billing_gateways_purchases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("last_four", sa.String(length=4), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"chat:write\"]'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_api_keys_workspace_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_api_keys_created_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("secret_hash", name="uq_api_keys_secret_hash"),
    )
    op.create_index("ix_api_keys_workspace_id", "api_keys", ["workspace_id"])
    op.create_index("ix_api_keys_created_by", "api_keys", ["created_by"])
    op.create_index("ix_api_keys_revoked_at", "api_keys", ["revoked_at"])
    op.create_index("ix_api_keys_workspace_created", "api_keys", ["workspace_id", "created_at"])
    op.create_index("ix_api_keys_workspace_revoked", "api_keys", ["workspace_id", "revoked_at"])

    op.add_column(
        "usage_events",
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_usage_events_api_key_id", "usage_events", ["api_key_id"])
    op.create_foreign_key(
        "fk_usage_events_api_key_id",
        "usage_events",
        "api_keys",
        ["api_key_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_usage_events_api_key_id", "usage_events", type_="foreignkey")
    op.drop_index("ix_usage_events_api_key_id", table_name="usage_events")
    op.drop_column("usage_events", "api_key_id")

    op.drop_index("ix_api_keys_workspace_revoked", table_name="api_keys")
    op.drop_index("ix_api_keys_workspace_created", table_name="api_keys")
    op.drop_index("ix_api_keys_revoked_at", table_name="api_keys")
    op.drop_index("ix_api_keys_created_by", table_name="api_keys")
    op.drop_index("ix_api_keys_workspace_id", table_name="api_keys")
    op.drop_table("api_keys")
