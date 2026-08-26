from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.apps_catalog.models import AppCategory, AppInstallation, CatalogApp
from app.connectors.models import AppConnection
from app.connectors.types import ConnectorAuthMode
from app.experts.models import Expert, ExpertType
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.repository import McpRepository
from app.mcp.types import McpCompatibilityStatus, McpToolStatus
from app.workspaces.models import Workspace


def _tool(workspace_id: uuid.UUID, connection_id: uuid.UUID, name: str) -> McpServerTool:
    return McpServerTool(
        workspace_id=workspace_id,
        app_connection_id=connection_id,
        tool_name=name,
        llm_tool_name=f"mcp_{name}_{uuid.uuid4().hex[:12]}",
        title=name,
        description=None,
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        raw_definition={"name": name, "inputSchema": {"type": "object"}},
        normalization_version="test-v1",
        protocol_version="2026-07-28",
        compatibility_status=McpCompatibilityStatus.COMPATIBLE.value,
        compatibility_reason=None,
        classification="unknown",
        definition_hash="a" * 64,
        status=McpToolStatus.ACTIVE.value,
        discovery_generation=1,
    )


def test_database_and_repository_reject_cross_workspace_mcp_chains(db) -> None:
    first = Workspace(name="First", slug=f"first-{uuid.uuid4().hex[:8]}")
    second = Workspace(name="Second", slug=f"second-{uuid.uuid4().hex[:8]}")
    category = AppCategory(
        slug=f"tools-{uuid.uuid4().hex[:8]}",
        name_key="tools",
    )
    db.add_all([first, second, category])
    db.flush()
    app = CatalogApp(
        slug=f"mcp-{uuid.uuid4().hex[:8]}",
        name="MCP",
        short_description="MCP",
        category_id=category.id,
        connector_key="mcp_remote",
        connector_kind="tool_source",
    )
    db.add(app)
    db.flush()
    first_install = AppInstallation(workspace_id=first.id, app_id=app.id)
    second_install = AppInstallation(workspace_id=second.id, app_id=app.id)
    db.add_all([first_install, second_install])
    db.flush()
    first_connection = AppConnection(
        workspace_id=first.id,
        app_installation_id=first_install.id,
        connector_key="mcp_remote",
        auth_mode=ConnectorAuthMode.NONE.value,
    )
    db.add(first_connection)
    db.commit()

    db.add(_tool(second.id, first_connection.id, "cross_workspace"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    valid_tool = _tool(first.id, first_connection.id, "valid")
    second_expert = Expert(
        workspace_id=second.id,
        type=ExpertType.WORKSPACE.value,
        name="Second Expert",
        system_instructions="",
    )
    db.add_all([valid_tool, second_expert])
    db.commit()

    assert McpRepository(db).get_tool(second.id, valid_tool.id) is None
    assert McpRepository(db).get_tool(first.id, valid_tool.id) is not None

    db.add(
        McpToolGrant(
            workspace_id=second.id,
            expert_id=second_expert.id,
            app_connection_id=first_connection.id,
            mcp_server_tool_id=valid_tool.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
