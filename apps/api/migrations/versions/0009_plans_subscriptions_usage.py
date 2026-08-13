"""Phase 5A — plans, subscriptions, entitlements, credits, usage counters.

* ``plans`` / ``plan_entitlements`` — catalog; limits are entitlement keys, never plan names
* ``subscriptions`` — one active subscription per Workspace (partial unique index)
* ``credit_accounts`` / ``credit_ledger_entries`` — append-only ledger + cached balance
* ``usage_period_counters`` — daily/weekly/monthly meters (mutation in 5B)
* ``storage_usage_events`` — append-only storage audit

No payment-provider columns. Bootstrap plan is seeded in application code, not SQL.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_plans_subscriptions_usage"
down_revision: Union[str, None] = "0008_conversation_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("code", name="uq_plans_code"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_plans_status"),
    )
    op.create_index("ix_plans_status", "plans", ["status"])

    op.create_table(
        "plan_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False, server_default="integer"),
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
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("plan_id", "key", name="uq_plan_entitlement_key"),
        sa.CheckConstraint(
            "value_type IN ('integer', 'boolean', 'string')",
            name="ck_plan_entitlements_value_type",
        ),
    )
    op.create_index("ix_plan_entitlements_plan_id", "plan_entitlements", ["plan_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('active', 'canceled', 'expired')",
            name="ck_subscriptions_status",
        ),
    )
    op.create_index("ix_subscriptions_workspace_id", "subscriptions", ["workspace_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "ix_subscriptions_workspace_status",
        "subscriptions",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_subscriptions_workspace_active",
        "subscriptions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "credit_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("workspace_id", name="uq_credit_accounts_workspace_id"),
    )

    op.create_table(
        "credit_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("remaining_amount", sa.BigInteger(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["credit_account_id"], ["credit_accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "entry_type IN ('grant', 'consume', 'reserve', 'release', 'expire', 'adjust')",
            name="ck_credit_ledger_entry_type",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_credit_ledger_amount_non_negative"),
    )
    op.create_index(
        "ix_credit_ledger_workspace_id",
        "credit_ledger_entries",
        ["workspace_id"],
    )
    op.create_index(
        "ix_credit_ledger_account_id",
        "credit_ledger_entries",
        ["credit_account_id"],
    )
    op.create_index(
        "ix_credit_ledger_workspace_created",
        "credit_ledger_entries",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "uq_credit_ledger_workspace_request_id",
        "credit_ledger_entries",
        ["workspace_id", "request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
    )

    op.create_table(
        "usage_period_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("period_type", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint(
            "workspace_id",
            "metric",
            "period_type",
            "period_start",
            name="uq_usage_period_counter",
        ),
        sa.CheckConstraint(
            "period_type IN ('daily', 'weekly', 'monthly')",
            name="ck_usage_period_counters_period_type",
        ),
        sa.CheckConstraint("used >= 0", name="ck_usage_period_counters_used_non_negative"),
        sa.CheckConstraint(
            "reserved >= 0",
            name="ck_usage_period_counters_reserved_non_negative",
        ),
    )
    op.create_index(
        "ix_usage_period_counters_workspace",
        "usage_period_counters",
        ["workspace_id"],
    )

    op.create_table(
        "storage_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delta_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "reason IN ('upload', 'delete', 'recompute', 'adjust')",
            name="ck_storage_usage_events_reason",
        ),
    )
    op.create_index(
        "ix_storage_usage_events_workspace_id",
        "storage_usage_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_storage_usage_events_document_id",
        "storage_usage_events",
        ["document_id"],
    )
    op.create_index(
        "ix_storage_usage_events_workspace_created",
        "storage_usage_events",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_storage_usage_events_workspace_created", table_name="storage_usage_events")
    op.drop_index("ix_storage_usage_events_document_id", table_name="storage_usage_events")
    op.drop_index("ix_storage_usage_events_workspace_id", table_name="storage_usage_events")
    op.drop_table("storage_usage_events")

    op.drop_index("ix_usage_period_counters_workspace", table_name="usage_period_counters")
    op.drop_table("usage_period_counters")

    op.drop_index(
        "uq_credit_ledger_workspace_request_id",
        table_name="credit_ledger_entries",
    )
    op.drop_index("ix_credit_ledger_workspace_created", table_name="credit_ledger_entries")
    op.drop_index("ix_credit_ledger_account_id", table_name="credit_ledger_entries")
    op.drop_index("ix_credit_ledger_workspace_id", table_name="credit_ledger_entries")
    op.drop_table("credit_ledger_entries")
    op.drop_table("credit_accounts")

    op.drop_index("uq_subscriptions_workspace_active", table_name="subscriptions")
    op.drop_index("ix_subscriptions_workspace_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_workspace_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_plan_entitlements_plan_id", table_name="plan_entitlements")
    op.drop_table("plan_entitlements")
    op.drop_index("ix_plans_status", table_name="plans")
    op.drop_table("plans")
