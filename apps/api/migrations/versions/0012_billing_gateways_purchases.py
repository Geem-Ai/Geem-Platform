"""Phase 6A — payment gateways, credit packs, purchases, plan pricing.

* ``plans.price_amount`` / ``plans.currency`` — commercial catalog price (SAR).
  Bootstrap/dev plans keep ``price_amount`` NULL (not purchasable).
* ``payment_gateway_configs`` — multiple adapters; at most one ``enabled=true``
* ``credit_packs`` — purchasable AI credit bundles
* ``purchases`` — workspace checkout + immutable fulfillment payload

No webhook/IPN tables. Gateway credentials are encrypted at the application layer.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_billing_gateways_purchases"
down_revision: Union[str, None] = "0011_storage_expert_quota"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="SAR",
        ),
    )

    op.create_table(
        "payment_gateway_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("test_mode", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("code", name="uq_payment_gateway_configs_code"),
    )
    op.create_index(
        "uq_payment_gateway_configs_one_enabled",
        "payment_gateway_configs",
        ["enabled"],
        unique=True,
        postgresql_where=sa.text("enabled = true"),
    )

    op.create_table(
        "credit_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credits", sa.BigInteger(), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="SAR",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("code", name="uq_credit_packs_code"),
        sa.CheckConstraint("credits > 0", name="ck_credit_packs_credits_positive"),
        sa.CheckConstraint("price_amount > 0", name="ck_credit_packs_price_positive"),
    )
    op.create_index("ix_credit_packs_active", "credit_packs", ["active"])

    op.create_table(
        "purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="SAR",
        ),
        sa.Column("payment_gateway_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cart_id", sa.String(length=64), nullable=False),
        sa.Column("provider_transaction_ref", sa.String(length=128), nullable=True),
        sa.Column("redirect_url", sa.Text(), nullable=True),
        sa.Column("return_token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_gateway_config_id"],
            ["payment_gateway_configs.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("cart_id", name="uq_purchases_cart_id"),
        sa.UniqueConstraint("return_token_hash", name="uq_purchases_return_token_hash"),
        sa.CheckConstraint(
            "kind IN ('subscription', 'credit_pack')",
            name="ck_purchases_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'redirected', 'paid', 'failed', 'cancelled', 'expired')",
            name="ck_purchases_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_purchases_amount_positive"),
    )
    op.create_index("ix_purchases_workspace_id", "purchases", ["workspace_id"])
    op.create_index("ix_purchases_actor_id", "purchases", ["actor_id"])
    op.create_index(
        "ix_purchases_payment_gateway_config_id",
        "purchases",
        ["payment_gateway_config_id"],
    )
    op.create_index("ix_purchases_status", "purchases", ["status"])
    op.create_index(
        "ix_purchases_workspace_created",
        "purchases",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_purchases_workspace_status",
        "purchases",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_purchases_provider_transaction_ref",
        "purchases",
        ["provider_transaction_ref"],
        unique=True,
        postgresql_where=sa.text("provider_transaction_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_purchases_provider_transaction_ref",
        table_name="purchases",
        postgresql_where=sa.text("provider_transaction_ref IS NOT NULL"),
    )
    op.drop_index("ix_purchases_workspace_status", table_name="purchases")
    op.drop_index("ix_purchases_workspace_created", table_name="purchases")
    op.drop_index("ix_purchases_status", table_name="purchases")
    op.drop_index("ix_purchases_payment_gateway_config_id", table_name="purchases")
    op.drop_index("ix_purchases_actor_id", table_name="purchases")
    op.drop_index("ix_purchases_workspace_id", table_name="purchases")
    op.drop_table("purchases")
    op.drop_index("ix_credit_packs_active", table_name="credit_packs")
    op.drop_table("credit_packs")
    op.drop_index(
        "uq_payment_gateway_configs_one_enabled",
        table_name="payment_gateway_configs",
        postgresql_where=sa.text("enabled = true"),
    )
    op.drop_table("payment_gateway_configs")
    op.drop_column("plans", "currency")
    op.drop_column("plans", "price_amount")
