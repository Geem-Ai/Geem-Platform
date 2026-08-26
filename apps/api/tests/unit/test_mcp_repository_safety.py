"""DB-free SQL-shape checks for MCP restrictive mutations."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.mcp.repository import McpRepository


class _Result:
    rowcount = 2


class _RecordingSession:
    def __init__(self) -> None:
        self.statements: list = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result()


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
