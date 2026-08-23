"""App commercial provenance for Platform Admin grants (Phase 12E).

Adds optional purchase_id on licenses, source/granted_by/idempotency on licenses
and subscriptions. Existing rows backfill source=purchase.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_app_commercial_provenance"
down_revision = "0033_usage_events_partition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_licenses",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="purchase",
        ),
    )
    op.add_column(
        "app_licenses",
        sa.Column("grant_idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "app_licenses",
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("app_licenses", "purchase_id", existing_type=postgresql.UUID(), nullable=True)
    op.create_foreign_key(
        "fk_app_licenses_granted_by_user_id",
        "app_licenses",
        "users",
        ["granted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_app_licenses_grant_idempotency_key",
        "app_licenses",
        ["grant_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("grant_idempotency_key IS NOT NULL"),
    )

    op.add_column(
        "app_subscriptions",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="purchase",
        ),
    )
    op.add_column(
        "app_subscriptions",
        sa.Column("grant_idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "app_subscriptions",
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_app_subscriptions_granted_by_user_id",
        "app_subscriptions",
        "users",
        ["granted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_app_subscriptions_grant_idempotency_key",
        "app_subscriptions",
        ["grant_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("grant_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_app_subscriptions_grant_idempotency_key",
        table_name="app_subscriptions",
    )
    op.drop_constraint(
        "fk_app_subscriptions_granted_by_user_id",
        "app_subscriptions",
        type_="foreignkey",
    )
    op.drop_column("app_subscriptions", "granted_by_user_id")
    op.drop_column("app_subscriptions", "grant_idempotency_key")
    op.drop_column("app_subscriptions", "source")

    op.drop_index("ix_app_licenses_grant_idempotency_key", table_name="app_licenses")
    op.drop_constraint("fk_app_licenses_granted_by_user_id", "app_licenses", type_="foreignkey")
    op.execute(
        sa.text(
            "DELETE FROM app_licenses WHERE purchase_id IS NULL"
        )
    )
    op.alter_column("app_licenses", "purchase_id", existing_type=postgresql.UUID(), nullable=False)
    op.drop_column("app_licenses", "granted_by_user_id")
    op.drop_column("app_licenses", "grant_idempotency_key")
    op.drop_column("app_licenses", "source")
