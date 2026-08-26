"""DB-free SQL-shape checks for MCP restrictive mutations."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.documents.repository import ilike_contains_pattern
from app.mcp.constants import MCP_LISTED_CONNECTION_STATUSES
from app.mcp.repository import McpRepository


class _Result:
    rowcount = 2


class _RecordingSession:
    def __init__(self) -> None:
        self.statements: list = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result()


class _Rows:
    @staticmethod
    def all() -> list:
        return []


class _ListRecordingSession:
    def __init__(self) -> None:
        self.statements: list = []

    def scalar(self, statement):
        self.statements.append(statement)
        return 0

    def scalars(self, statement):
        self.statements.append(statement)
        return _Rows()


def _postgres_sql(statement) -> str:
    return " ".join(
        str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    ).lower()


def test_classification_change_stales_external_bindings_and_grants_atomically() -> None:
    session = _RecordingSession()
    tool_id = uuid.uuid4()

    changed = McpRepository(session).stale_grants_for_classification(tool_id)

    assert changed == 2
    assert len(session.statements) == 2
    surface_sql, grant_sql = map(_postgres_sql, session.statements)
    assert surface_sql.startswith("update mcp_tool_surface_bindings")
    assert "state='stale_classification'" in surface_sql.replace(" ", "")
    assert "mcp_tool_surface_bindings.state = 'active'" in surface_sql
    assert "mcp_tool_grants.mcp_server_tool_id" in surface_sql
    assert str(tool_id) in surface_sql
    assert grant_sql.startswith("update mcp_tool_grants")
    assert "state='stale_classification'" in grant_sql.replace(" ", "")
    assert str(tool_id) in grant_sql


def test_connection_inventory_excludes_terminal_soft_deleted_rows() -> None:
    session = _ListRecordingSession()

    rows, total = McpRepository(session).list_connections(
        uuid.uuid4(),
        limit=100,
        offset=0,
    )

    assert rows == []
    assert total == 0
    assert len(session.statements) == 2
    for statement in session.statements:
        sql = _postgres_sql(statement)
        assert "app_connections.status in (" in sql
        for status in MCP_LISTED_CONNECTION_STATUSES:
            assert f"'{status}'" in sql
        assert "'disconnected'" not in sql
        assert "'revoked'" not in sql


def test_tool_search_is_literal_scoped_and_applied_before_pagination() -> None:
    session = _ListRecordingSession()
    workspace_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    needle = "100%_\\"

    rows, total = McpRepository(session).list_tools(
        workspace_id,
        connection_id,
        limit=25,
        offset=50,
        q=f"  {needle}  ",
    )

    assert rows == []
    assert total == 0
    assert len(session.statements) == 2
    expected_pattern = ilike_contains_pattern(needle)
    for statement in session.statements:
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = " ".join(str(compiled).split()).lower()
        assert "mcp_server_tools.workspace_id =" in sql
        assert "mcp_server_tools.app_connection_id =" in sql
        for field in ("title", "tool_name", "llm_tool_name", "description"):
            assert f"mcp_server_tools.{field} ilike" in sql
        assert sql.count(" escape ") == 4
        assert list(compiled.params.values()).count(expected_pattern) == 4

    page_sql = _postgres_sql(session.statements[1])
    assert "order by mcp_server_tools.tool_name, mcp_server_tools.id" in page_sql
    assert "limit 25 offset 50" in page_sql
