"""Phase 9A — App Store catalog, plans, entitlements, workspace installations.

Tables:
* ``app_categories`` — global category taxonomy
* ``apps`` — global App Store listings
* ``app_plans`` — commercial plan metadata (checkout in 9B)
* ``app_plan_entitlements`` — generic plan limit key/value pairs
* ``app_installations`` — one logical installation per (workspace, app)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_app_store_catalog"
down_revision: Union[str, None] = "0016_chat_attachment_expires"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name_key", sa.String(length=128), nullable=False),
        sa.Column("description_key", sa.String(length=128), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("slug", name="uq_app_categories_slug"),
    )

    op.create_table(
        "apps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short_description", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("icon_url", sa.String(length=1024), nullable=True),
        sa.Column("billing_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("config_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
            ["category_id"],
            ["app_categories.id"],
            name="fk_apps_category_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("slug", name="uq_apps_slug"),
    )
    op.create_index("ix_apps_category_id", "apps", ["category_id"])
    op.create_index("ix_apps_status", "apps", ["status"])
    op.create_index("ix_apps_status_sort", "apps", ["status", "sort_order"])
    op.create_index("ix_apps_billing_type", "apps", ["billing_type"])

    op.create_table(
        "app_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("billing_interval", sa.String(length=32), nullable=False),
        sa.Column(
            "price_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="SAR"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name="fk_app_plans_app_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("app_id", "code", name="uq_app_plans_app_code"),
    )
    op.create_index("ix_app_plans_app_id", "app_plans", ["app_id"])

    op.create_table(
        "app_plan_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("app_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            ["app_plan_id"],
            ["app_plans.id"],
            name="fk_app_plan_entitlements_plan_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("app_plan_id", "key", name="uq_app_plan_entitlement_key"),
    )
    op.create_index(
        "ix_app_plan_entitlements_plan_id", "app_plan_entitlements", ["app_plan_id"]
    )

    op.create_table(
        "app_installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("installed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("config_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_app_installations_workspace_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name="fk_app_installations_app_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["installed_by_user_id"],
            ["users.id"],
            name="fk_app_installations_installed_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "workspace_id", "app_id", name="uq_app_installations_workspace_app"
        ),
    )
    op.create_index("ix_app_installations_workspace_id", "app_installations", ["workspace_id"])
    op.create_index("ix_app_installations_app_id", "app_installations", ["app_id"])
    op.create_index(
        "ix_app_installations_installed_by_user_id",
        "app_installations",
        ["installed_by_user_id"],
    )
    op.create_index(
        "ix_app_installations_workspace_status",
        "app_installations",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_app_installations_workspace_status", table_name="app_installations")
    op.drop_index(
        "ix_app_installations_installed_by_user_id", table_name="app_installations"
    )
    op.drop_index("ix_app_installations_app_id", table_name="app_installations")
    op.drop_index("ix_app_installations_workspace_id", table_name="app_installations")
    op.drop_table("app_installations")

    op.drop_index("ix_app_plan_entitlements_plan_id", table_name="app_plan_entitlements")
    op.drop_table("app_plan_entitlements")

    op.drop_index("ix_app_plans_app_id", table_name="app_plans")
    op.drop_table("app_plans")

    op.drop_index("ix_apps_billing_type", table_name="apps")
    op.drop_index("ix_apps_status_sort", table_name="apps")
    op.drop_index("ix_apps_status", table_name="apps")
    op.drop_index("ix_apps_category_id", table_name="apps")
    op.drop_table("apps")

    op.drop_table("app_categories")
