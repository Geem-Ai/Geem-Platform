"""Document WorkspaceStatus.pending for tenant approval gate.

Revision ID: 0042_workspace_pending_status
Revises: 0041_openwa_binding_backfill

Existing rows remain active/suspended/archived. New tenant creates use pending
until Platform Admin approve/reject (application-enforced).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0042_workspace_pending_status"
down_revision: Union[str, None] = "0041_openwa_binding_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_workspaces_status",
        "workspaces",
        "status IN ('pending', 'active', 'suspended', 'archived')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workspaces_status", "workspaces", type_="check")
