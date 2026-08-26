"""Workspace-filtered MCP persistence queries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.connectors.models import AppConnection
from app.documents.repository import ilike_contains_pattern
from app.experts.models import Expert
from app.mcp.constants import MCP_CONNECTOR_KEY, MCP_LISTED_CONNECTION_STATUSES
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.runtime_models import McpToolSurfaceBinding
from app.mcp.types import McpGrantState, McpToolStatus


@dataclass(frozen=True, slots=True)
class McpGrantRecord:
    grant: McpToolGrant
    tool: McpServerTool
    connection: AppConnection


class McpRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_connection(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        for_update: bool = False,
        for_share: bool = False,
    ) -> AppConnection | None:
        stmt = select(AppConnection).where(
            AppConnection.workspace_id == workspace_id,
            AppConnection.id == connection_id,
            AppConnection.connector_key == MCP_CONNECTOR_KEY,
        )
        if for_update or for_share:
            stmt = stmt.with_for_update(read=for_share and not for_update)
        return self.db.scalar(stmt)

    def list_connections(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AppConnection], int]:
        where = (
            AppConnection.workspace_id == workspace_id,
            AppConnection.connector_key == MCP_CONNECTOR_KEY,
            AppConnection.status.in_(tuple(MCP_LISTED_CONNECTION_STATUSES)),
        )
        total = int(
            self.db.scalar(select(func.count()).select_from(AppConnection).where(*where))
            or 0
        )
        rows = list(
            self.db.scalars(
                select(AppConnection)
                .where(*where)
                .order_by(AppConnection.created_at.desc(), AppConnection.id)
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return rows, total

    def count_tools(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        include_withdrawn: bool = True,
    ) -> int:
        stmt = select(func.count()).select_from(McpServerTool).where(
            McpServerTool.workspace_id == workspace_id,
            McpServerTool.app_connection_id == connection_id,
        )
        if not include_withdrawn:
            stmt = stmt.where(McpServerTool.status != McpToolStatus.WITHDRAWN.value)
        return int(self.db.scalar(stmt) or 0)

    def list_tools(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> tuple[list[McpServerTool], int]:
        filters = [
            McpServerTool.workspace_id == workspace_id,
            McpServerTool.app_connection_id == connection_id,
        ]
        needle = (q or "").strip()
        if needle:
            pattern = ilike_contains_pattern(needle)
            filters.append(
                or_(
                    McpServerTool.title.ilike(pattern, escape="\\"),
                    McpServerTool.tool_name.ilike(pattern, escape="\\"),
                    McpServerTool.llm_tool_name.ilike(pattern, escape="\\"),
                    McpServerTool.description.ilike(pattern, escape="\\"),
                )
            )
        total = int(
            self.db.scalar(
                select(func.count()).select_from(McpServerTool).where(*filters)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(McpServerTool)
                .where(*filters)
                .order_by(McpServerTool.tool_name, McpServerTool.id)
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return rows, total

    def get_tool(
        self,
        workspace_id: uuid.UUID,
        tool_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> McpServerTool | None:
        stmt = select(McpServerTool).where(
            McpServerTool.workspace_id == workspace_id,
            McpServerTool.id == tool_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def tools_by_name_for_update(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> dict[str, McpServerTool]:
        rows = self.db.scalars(
            select(McpServerTool)
            .where(
                McpServerTool.workspace_id == workspace_id,
                McpServerTool.app_connection_id == connection_id,
            )
            .with_for_update()
        ).all()
        return {row.tool_name: row for row in rows}

    def stale_grants_for_definition(self, tool_id: uuid.UUID) -> int:
        result = self.db.execute(
            update(McpToolGrant)
            .where(
                McpToolGrant.mcp_server_tool_id == tool_id,
                McpToolGrant.state != McpGrantState.REVOKED.value,
            )
            .values(state=McpGrantState.STALE_DEFINITION.value)
        )
        return int(result.rowcount or 0)

    def stale_grants_for_classification(self, tool_id: uuid.UUID) -> int:
        affected_grant_ids = select(McpToolGrant.id).where(
            McpToolGrant.mcp_server_tool_id == tool_id,
            McpToolGrant.state != McpGrantState.REVOKED.value,
        )
        # Classification is part of both review boundaries.  Mark exact
        # external bindings inert in the same transaction before staling the
        # grants so a later grant re-review cannot silently resurrect a public
        # read/write exposure.
        self.db.execute(
            update(McpToolSurfaceBinding)
            .where(
                McpToolSurfaceBinding.mcp_tool_grant_id.in_(affected_grant_ids),
                McpToolSurfaceBinding.state == "active",
            )
            .values(state="stale_classification")
            .execution_options(synchronize_session=False)
        )
        result = self.db.execute(
            update(McpToolGrant)
            .where(
                McpToolGrant.mcp_server_tool_id == tool_id,
                McpToolGrant.state != McpGrantState.REVOKED.value,
            )
            .values(state=McpGrantState.STALE_CLASSIFICATION.value)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

    def stale_grants_for_principal(self, connection_id: uuid.UUID) -> int:
        result = self.db.execute(
            update(McpToolGrant)
            .where(
                McpToolGrant.app_connection_id == connection_id,
                McpToolGrant.state != McpGrantState.REVOKED.value,
            )
            .values(state=McpGrantState.STALE_PRINCIPAL.value)
        )
        return int(result.rowcount or 0)

    def get_expert(
        self,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Expert | None:
        stmt = select(Expert).where(
            Expert.workspace_id == workspace_id,
            Expert.id == expert_id,
            Expert.deleted_at.is_(None),
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def get_grant(
        self,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        grant_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> McpToolGrant | None:
        stmt = select(McpToolGrant).where(
            McpToolGrant.workspace_id == workspace_id,
            McpToolGrant.expert_id == expert_id,
            McpToolGrant.id == grant_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def get_grant_for_tool(
        self,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        tool_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> McpToolGrant | None:
        stmt = select(McpToolGrant).where(
            McpToolGrant.workspace_id == workspace_id,
            McpToolGrant.expert_id == expert_id,
            McpToolGrant.mcp_server_tool_id == tool_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def list_grant_records(
        self,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        *,
        active_only: bool = False,
        for_share: bool = False,
    ) -> list[McpGrantRecord]:
        stmt = (
            select(McpToolGrant, McpServerTool, AppConnection)
            .join(
                McpServerTool,
                (McpServerTool.workspace_id == McpToolGrant.workspace_id)
                & (McpServerTool.id == McpToolGrant.mcp_server_tool_id)
                & (
                    McpServerTool.app_connection_id
                    == McpToolGrant.app_connection_id
                ),
            )
            .join(
                AppConnection,
                (AppConnection.workspace_id == McpToolGrant.workspace_id)
                & (AppConnection.id == McpToolGrant.app_connection_id),
            )
            .where(
                McpToolGrant.workspace_id == workspace_id,
                McpToolGrant.expert_id == expert_id,
                AppConnection.connector_key == MCP_CONNECTOR_KEY,
            )
            .order_by(AppConnection.display_name, McpServerTool.tool_name)
        )
        if active_only:
            stmt = stmt.where(McpToolGrant.state == McpGrantState.ACTIVE.value)
        if for_share:
            stmt = stmt.with_for_update(read=True)
        return [McpGrantRecord(*row) for row in self.db.execute(stmt).all()]

    def has_eligible_source_grant(
        self,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        *,
        allow_field: str,
    ) -> bool:
        surface_column = getattr(McpToolGrant, allow_field)
        return bool(
            self.db.scalar(
                select(McpToolGrant.id)
                .where(
                    McpToolGrant.workspace_id == workspace_id,
                    McpToolGrant.expert_id == expert_id,
                    McpToolGrant.state == McpGrantState.ACTIVE.value,
                    surface_column.is_(True),
                )
                .limit(1)
            )
        )


__all__ = ["McpGrantRecord", "McpRepository"]
