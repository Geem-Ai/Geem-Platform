"""Phase 9B — App licenses, subscriptions, and purchase kinds.

Tables:
* ``app_licenses`` — one-time commercial entitlement per (workspace, app)
* ``app_subscriptions`` — monthly App subscription lifecycle per (workspace, app)

Also extends ``purchases.kind`` CHECK for App Store commerce.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_app_billing"
down_revision: Union[str, None] = "0017_app_store_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_licenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["app_plan_id"], ["app_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("workspace_id", "app_id", name="uq_app_licenses_workspace_app"),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_app_licenses_status",
        ),
    )
    op.create_index("ix_app_licenses_workspace_id", "app_licenses", ["workspace_id"])
    op.create_index("ix_app_licenses_app_id", "app_licenses", ["app_id"])
    op.create_index("ix_app_licenses_purchase_id", "app_licenses", ["purchase_id"])
    op.create_index(
        "ix_app_licenses_workspace_app",
        "app_licenses",
        ["workspace_id", "app_id"],
    )

    op.create_table(
        "app_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["app_plan_id"], ["app_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["latest_purchase_id"], ["purchases.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "workspace_id", "app_id", name="uq_app_subscriptions_workspace_app"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'cancelled')",
            name="ck_app_subscriptions_status",
        ),
    )
    op.create_index(
        "ix_app_subscriptions_workspace_id", "app_subscriptions", ["workspace_id"]
    )
    op.create_index("ix_app_subscriptions_app_id", "app_subscriptions", ["app_id"])
    op.create_index(
        "ix_app_subscriptions_workspace_status",
        "app_subscriptions",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_app_subscriptions_period_end",
        "app_subscriptions",
        ["current_period_end"],
    )

    op.drop_constraint("ck_purchases_kind", "purchases", type_="check")
    op.create_check_constraint(
        "ck_purchases_kind",
        "purchases",
        "kind IN ("
        "'subscription', 'credit_pack', "
        "'app_one_time', 'app_subscription', 'app_subscription_renewal'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_purchases_kind", "purchases", type_="check")
    op.create_check_constraint(
        "ck_purchases_kind",
        "purchases",
        "kind IN ('subscription', 'credit_pack')",
    )

    op.drop_index("ix_app_subscriptions_period_end", table_name="app_subscriptions")
    op.drop_index(
        "ix_app_subscriptions_workspace_status", table_name="app_subscriptions"
    )
    op.drop_index("ix_app_subscriptions_app_id", table_name="app_subscriptions")
    op.drop_index("ix_app_subscriptions_workspace_id", table_name="app_subscriptions")
    op.drop_table("app_subscriptions")

    op.drop_index("ix_app_licenses_workspace_app", table_name="app_licenses")
    op.drop_index("ix_app_licenses_purchase_id", table_name="app_licenses")
    op.drop_index("ix_app_licenses_app_id", table_name="app_licenses")
    op.drop_index("ix_app_licenses_workspace_id", table_name="app_licenses")
    op.drop_table("app_licenses")
