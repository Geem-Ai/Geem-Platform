"""Phase 5B — AI usage reservations, usage_event attribution, non-negative credits.

* ``ai_usage_reservations`` — reserve/settle/release state keyed by request_id
* ``usage_events`` — Workspace/User/Expert/conversation/message attribution
* CHECK constraints so credit balance and grant remaining cannot go negative
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_ai_usage_reservations"
down_revision: Union[str, None] = "0009_plans_subscriptions_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_credit_accounts_balance_non_negative",
        "credit_accounts",
        "balance >= 0",
    )
    op.create_check_constraint(
        "ck_credit_ledger_remaining_non_negative",
        "credit_ledger_entries",
        "remaining_amount IS NULL OR remaining_amount >= 0",
    )

    op.add_column(
        "usage_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "usage_events",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "usage_events",
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "usage_events",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "usage_events",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_usage_events_workspace_id",
        "usage_events",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_usage_events_user_id",
        "usage_events",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_usage_events_expert_id",
        "usage_events",
        "experts",
        ["expert_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_usage_events_conversation_id",
        "usage_events",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_usage_events_message_id",
        "usage_events",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_usage_events_workspace_id", "usage_events", ["workspace_id"])
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_expert_id", "usage_events", ["expert_id"])
    op.create_index("ix_usage_events_conversation_id", "usage_events", ["conversation_id"])
    op.create_index("ix_usage_events_message_id", "usage_events", ["message_id"])

    op.create_table(
        "ai_usage_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="reserved"),
        sa.Column("estimated_tokens", sa.BigInteger(), nullable=False),
        sa.Column("included_reserved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_reserved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("actual_tokens", sa.BigInteger(), nullable=True),
        sa.Column("included_settled", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_settled", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "credit_allocations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("daily_counter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekly_counter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monthly_counter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["daily_counter_id"], ["usage_period_counters.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["weekly_counter_id"], ["usage_period_counters.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["monthly_counter_id"], ["usage_period_counters.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "request_id",
            name="uq_ai_usage_reservations_workspace_request",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'settled', 'released')",
            name="ck_ai_usage_reservations_status",
        ),
        sa.CheckConstraint(
            "estimated_tokens >= 0",
            name="ck_ai_usage_reservations_estimated_non_negative",
        ),
        sa.CheckConstraint(
            "included_reserved >= 0",
            name="ck_ai_usage_reservations_included_reserved_non_negative",
        ),
        sa.CheckConstraint(
            "credit_reserved >= 0",
            name="ck_ai_usage_reservations_credit_reserved_non_negative",
        ),
        sa.CheckConstraint(
            "included_settled >= 0",
            name="ck_ai_usage_reservations_included_settled_non_negative",
        ),
        sa.CheckConstraint(
            "credit_settled >= 0",
            name="ck_ai_usage_reservations_credit_settled_non_negative",
        ),
    )
    op.create_index(
        "ix_ai_usage_reservations_workspace",
        "ai_usage_reservations",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_reservations_workspace", table_name="ai_usage_reservations")
    op.drop_table("ai_usage_reservations")

    op.drop_index("ix_usage_events_message_id", table_name="usage_events")
    op.drop_index("ix_usage_events_conversation_id", table_name="usage_events")
    op.drop_index("ix_usage_events_expert_id", table_name="usage_events")
    op.drop_index("ix_usage_events_user_id", table_name="usage_events")
    op.drop_index("ix_usage_events_workspace_id", table_name="usage_events")
    op.drop_constraint("fk_usage_events_message_id", "usage_events", type_="foreignkey")
    op.drop_constraint("fk_usage_events_conversation_id", "usage_events", type_="foreignkey")
    op.drop_constraint("fk_usage_events_expert_id", "usage_events", type_="foreignkey")
    op.drop_constraint("fk_usage_events_user_id", "usage_events", type_="foreignkey")
    op.drop_constraint("fk_usage_events_workspace_id", "usage_events", type_="foreignkey")
    op.drop_column("usage_events", "message_id")
    op.drop_column("usage_events", "conversation_id")
    op.drop_column("usage_events", "expert_id")
    op.drop_column("usage_events", "user_id")
    op.drop_column("usage_events", "workspace_id")

    op.drop_constraint(
        "ck_credit_ledger_remaining_non_negative",
        "credit_ledger_entries",
        type_="check",
    )
    op.drop_constraint(
        "ck_credit_accounts_balance_non_negative",
        "credit_accounts",
        type_="check",
    )
