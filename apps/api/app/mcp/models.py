"""Tenant-scoped MCP inventory and Expert grant persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.mcp.constants import MCP_NORMALIZATION_VERSION
from app.mcp.types import (
    McpCompatibilityStatus,
    McpGrantState,
    McpToolClassification,
    McpToolStatus,
)


class McpServerTool(Base):
    """One normalized tool advertised by one exact Workspace connection."""

    __tablename__ = "mcp_server_tools"
    __table_args__ = (
        UniqueConstraint(
            "app_connection_id",
            "tool_name",
            name="uq_mcp_server_tools_connection_name",
        ),
        UniqueConstraint(
            "workspace_id",
            "llm_tool_name",
            name="uq_mcp_server_tools_workspace_alias",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_mcp_server_tools_workspace_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "app_connection_id",
            "id",
            name="uq_mcp_server_tools_workspace_connection_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_connection_id"],
            ["app_connections.workspace_id", "app_connections.id"],
            name="fk_mcp_server_tools_workspace_connection",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "compatibility_status IN "
            "('compatible','unsupported_schema','unsupported_capability','malformed')",
            name="ck_mcp_server_tools_compatibility",
        ),
        CheckConstraint(
            "classification IN ('read_only','write','unknown')",
            name="ck_mcp_server_tools_classification",
        ),
        CheckConstraint(
            "status IN ('active','stale','withdrawn')",
            name="ck_mcp_server_tools_status",
        ),
        CheckConstraint(
            "char_length(definition_hash) = 64",
            name="ck_mcp_server_tools_definition_hash",
        ),
        CheckConstraint(
            "discovery_generation >= 1",
            name="ck_mcp_server_tools_discovery_generation",
        ),
        Index(
            "ix_mcp_server_tools_workspace_connection_status",
            "workspace_id",
            "app_connection_id",
            "status",
        ),
        Index(
            "ix_mcp_server_tools_workspace_classification",
            "workspace_id",
            "classification",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(256), nullable=False)
    llm_tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    annotations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    raw_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalization_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=MCP_NORMALIZATION_VERSION
    )
    protocol_version: Mapped[str] = mapped_column(String(32), nullable=False)
    compatibility_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=McpCompatibilityStatus.MALFORMED.value,
    )
    compatibility_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default=McpToolClassification.UNKNOWN.value
    )
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=McpToolStatus.ACTIVE.value
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    discovery_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class McpToolGrant(Base):
    """Explicit, definition-pinned authorization for a Workspace-owned Expert."""

    __tablename__ = "mcp_tool_grants"
    __table_args__ = (
        UniqueConstraint(
            "expert_id",
            "mcp_server_tool_id",
            name="uq_mcp_tool_grants_expert_tool",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_mcp_tool_grants_workspace_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "expert_id",
            "id",
            name="uq_mcp_tool_grants_workspace_expert_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "expert_id",
            "app_connection_id",
            "mcp_server_tool_id",
            "id",
            name="uq_mcp_tool_grants_exact_chain_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "expert_id"],
            ["experts.workspace_id", "experts.id"],
            name="fk_mcp_tool_grants_workspace_expert",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_connection_id"],
            ["app_connections.workspace_id", "app_connections.id"],
            name="fk_mcp_tool_grants_workspace_connection",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_connection_id", "mcp_server_tool_id"],
            [
                "mcp_server_tools.workspace_id",
                "mcp_server_tools.app_connection_id",
                "mcp_server_tools.id",
            ],
            name="fk_mcp_tool_grants_exact_tool",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "state IN ('pending_review','active','revoked','stale_definition',"
            "'stale_classification','stale_principal')",
            name="ck_mcp_tool_grants_state",
        ),
        CheckConstraint(
            "approved_classification IS NULL OR "
            "approved_classification IN ('read_only','write')",
            name="ck_mcp_tool_grants_approved_classification",
        ),
        CheckConstraint(
            "approved_credential_epoch IS NULL OR approved_credential_epoch >= 1",
            name="ck_mcp_tool_grants_credential_epoch",
        ),
        CheckConstraint(
            "state <> 'active' OR ("
            "approved_definition_hash IS NOT NULL AND "
            "approved_classification IS NOT NULL AND "
            "approved_principal_fingerprint IS NOT NULL AND "
            "approved_credential_epoch IS NOT NULL AND "
            "approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL AND "
            "outbound_data_acknowledged_at IS NOT NULL)",
            name="ck_mcp_tool_grants_active_review",
        ),
        CheckConstraint(
            "NOT unattended_write_allowed OR ("
            "approved_classification = 'write' AND allow_public_api AND "
            "unattended_write_acknowledged_at IS NOT NULL)",
            name="ck_mcp_tool_grants_unattended_write",
        ),
        Index(
            "ix_mcp_tool_grants_workspace_expert_state",
            "workspace_id",
            "expert_id",
            "state",
        ),
        Index(
            "ix_mcp_tool_grants_workspace_connection",
            "workspace_id",
            "app_connection_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mcp_server_tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    approved_definition_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    approved_classification: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    approved_principal_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    approved_credential_epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=McpGrantState.PENDING_REVIEW.value
    )
    allow_workspace_chat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    allow_public_api: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    unattended_write_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outbound_data_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unattended_write_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["McpServerTool", "McpToolGrant"]
