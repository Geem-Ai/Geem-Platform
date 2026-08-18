"""ZATCA simplified tax invoices on paid purchases.

Revision ID: 0025_purchase_invoices
Revises: 0024_workspace_rbac
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_purchase_invoices"
down_revision: Union[str, None] = "0024_workspace_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS purchase_invoice_number_seq START 1")
    op.add_column("purchases", sa.Column("invoice_number", sa.String(length=32), nullable=True))
    op.add_column(
        "purchases",
        sa.Column("invoice_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint("uq_purchases_invoice_number", "purchases", ["invoice_number"])


def downgrade() -> None:
    op.drop_constraint("uq_purchases_invoice_number", "purchases", type_="unique")
    op.drop_column("purchases", "invoice_snapshot")
    op.drop_column("purchases", "invoice_number")
    op.execute("DROP SEQUENCE IF EXISTS purchase_invoice_number_seq")
