"""Phase 9C — Connector foundation.

* ``apps.connector_key`` / ``apps.connector_kind``
* ``app_connections``
* ``connector_sync_runs``
* ``connector_items``
* ``connector_webhook_events``
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_connector_foundation"
down_revision: Union[str, None] = "0018_app_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("apps", sa.Column("connector_key", sa.String(length=64), nullable=True))
    op.add_column("apps", sa.Column("connector_kind", sa.String(length=32), nullable=True))
    op.create_index("ix_apps_connector_key", "apps", ["connector_key"])

    op.create_table(
        "app_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("external_account_id", sa.String(length=512), nullable=True),
        sa.Column("external_account_name", sa.String(length=512), nullable=True),
        sa.Column("auth_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("health", sa.String(length=32), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("sync_state_encrypted", sa.Text(), nullable=True),
        sa.Column("webhook_routing_token_hash", sa.String(length=128), nullable=True),
        sa.Column("webhook_routing_token_encrypted", sa.Text(), nullable=True),
        sa.Column("credentials_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["app_installation_id"], ["app_installations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["connected_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "status IN ('pending','connecting','active','degraded','error',"
            "'disconnected','revoked')",
            name="ck_app_connections_status",
        ),
        sa.CheckConstraint(
            "health IN ('unknown','healthy','degraded','failed')",
            name="ck_app_connections_health",
        ),
        sa.CheckConstraint(
            "auth_mode IN ('oauth2','api_key','custom')",
            name="ck_app_connections_auth_mode",
        ),
    )
    op.create_index("ix_app_connections_workspace_id", "app_connections", ["workspace_id"])
    op.create_index(
        "ix_app_connections_app_installation_id",
        "app_connections",
        ["app_installation_id"],
    )
    op.create_index(
        "ix_app_connections_workspace_installation",
        "app_connections",
        ["workspace_id", "app_installation_id"],
    )
    op.create_index(
        "ix_app_connections_workspace_connector",
        "app_connections",
        ["workspace_id", "connector_key"],
    )
    op.create_index(
        "ix_app_connections_workspace_status",
        "app_connections",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_app_connections_routing_token_hash",
        "app_connections",
        ["webhook_routing_token_hash"],
        unique=True,
        postgresql_where=sa.text("webhook_routing_token_hash IS NOT NULL"),
    )

    op.create_table(
        "connector_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_deleted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["app_connection_id"], ["app_connections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "trigger IN ('initial','manual','scheduled','webhook','reconcile')",
            name="ck_connector_sync_runs_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','partial','failed','cancelled')",
            name="ck_connector_sync_runs_status",
        ),
    )
    op.create_index(
        "ix_connector_sync_runs_workspace_id", "connector_sync_runs", ["workspace_id"]
    )
    op.create_index(
        "ix_connector_sync_runs_app_connection_id",
        "connector_sync_runs",
        ["app_connection_id"],
    )
    op.create_index(
        "ix_connector_sync_runs_workspace_connection_created",
        "connector_sync_runs",
        ["workspace_id", "app_connection_id", "created_at"],
    )
    op.create_index(
        "uq_connector_sync_runs_connection_idempotency",
        "connector_sync_runs",
        ["app_connection_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "connector_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("parent_external_id", sa.String(length=512), nullable=True),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=True),
        sa.Column("mime_type", sa.String(length=256), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("external_version", sa.String(length=256), nullable=True),
        sa.Column("external_etag", sa.String(length=256), nullable=True),
        sa.Column("provider_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at_provider", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["app_connection_id"], ["app_connections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["current_document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "app_connection_id",
            "external_id",
            name="uq_connector_items_connection_external",
        ),
        sa.CheckConstraint(
            "item_type IN ('file','folder','other')",
            name="ck_connector_items_item_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','deleted','unavailable')",
            name="ck_connector_items_status",
        ),
    )
    op.create_index("ix_connector_items_workspace_id", "connector_items", ["workspace_id"])
    op.create_index(
        "ix_connector_items_app_connection_id", "connector_items", ["app_connection_id"]
    )
    op.create_index(
        "ix_connector_items_workspace_connection",
        "connector_items",
        ["workspace_id", "app_connection_id"],
    )
    op.create_index(
        "ix_connector_items_current_document_id",
        "connector_items",
        ["current_document_id"],
    )

    op.create_table(
        "connector_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.String(length=512), nullable=True),
        sa.Column("idempotency_key", sa.String(length=512), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["app_connection_id"], ["app_connections.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('received','queued','processed','ignored','failed')",
            name="ck_connector_webhook_events_status",
        ),
    )
    op.create_index(
        "ix_connector_webhook_events_workspace_id",
        "connector_webhook_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_connector_webhook_events_app_connection_id",
        "connector_webhook_events",
        ["app_connection_id"],
    )
    op.create_index(
        "ix_connector_webhook_events_connection_provider_event",
        "connector_webhook_events",
        ["app_connection_id", "provider_event_id"],
    )
    op.create_index(
        "uq_connector_webhook_events_connection_provider_event",
        "connector_webhook_events",
        ["app_connection_id", "provider_event_id"],
        unique=True,
        postgresql_where=sa.text("provider_event_id IS NOT NULL"),
    )
    op.create_index(
        "uq_connector_webhook_events_connection_idempotency",
        "connector_webhook_events",
        ["app_connection_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("connector_webhook_events")
    op.drop_table("connector_items")
    op.drop_table("connector_sync_runs")
    op.drop_table("app_connections")
    op.drop_index("ix_apps_connector_key", table_name="apps")
    op.drop_column("apps", "connector_kind")
    op.drop_column("apps", "connector_key")
