from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.mcp.router as router_module
import app.mcp.runtime_router as runtime_router_module
from app.connectors.providers.mcp_remote.adapter import McpRemoteConnector
from app.connectors.service import ConnectorConnectionService
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access
from app.mcp.router import create_expert_mcp_grant, create_mcp_server, list_mcp_servers
from app.mcp.schemas import McpGrantCreateIn, McpServerCreateIn
from app.mcp.surfaces import McpApprovalListOut
from app.workspaces.permissions import WorkspacePermission
from tests.support.rbac import fake_membership


def _access(*permissions: WorkspacePermission) -> DocumentAccess:
    return DocumentAccess(
        user=SimpleNamespace(id=uuid.uuid4()),
        workspace=SimpleNamespace(id=uuid.uuid4()),
        membership=fake_membership(keys={item.value for item in permissions}),
    )


@pytest.mark.parametrize("route", ["list", "connect", "grant"])
def test_mcp_routes_fail_before_service_without_permission(monkeypatch, route: str) -> None:
    class _NeverService:
        def __init__(self, _db) -> None:
            raise AssertionError("service must not be reached")

    monkeypatch.setattr(router_module, "McpServerService", _NeverService)
    monkeypatch.setattr(router_module, "McpGrantService", _NeverService)
    access = _access()
    with pytest.raises(AppError) as caught:
        if route == "list":
            list_mcp_servers(50, 0, access, SimpleNamespace())
        elif route == "connect":
            create_mcp_server(
                McpServerCreateIn.model_validate(
                    {
                        "display_name": "Docs",
                        "server_url": "https://mcp.example/tools",
                        "auth": {"mode": "none"},
                    }
                ),
                access,
                SimpleNamespace(),
            )
        else:
            create_expert_mcp_grant(
                uuid.uuid4(),
                McpGrantCreateIn(
                    tool_id=uuid.uuid4(), outbound_data_acknowledged=True
                ),
                access,
                SimpleNamespace(),
            )
    assert caught.value.category == ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE


def test_browse_permission_dispatches_to_scoped_service(monkeypatch) -> None:
    sentinel = object()
    calls: list[tuple] = []

    class _Service:
        def __init__(self, db) -> None:
            calls.append(("db", db))

        def list_servers(self, **kwargs):
            calls.append(("list", kwargs))
            return sentinel

    monkeypatch.setattr(router_module, "McpServerService", _Service)
    db = SimpleNamespace()
    access = _access(WorkspacePermission.APPS_VIEW)
    assert list_mcp_servers(25, 5, access, db) is sentinel
    assert calls[-1] == (
        "list",
        {"workspace_id": access.workspace.id, "limit": 25, "offset": 5},
    )


def test_generic_connector_start_cannot_create_malformed_mcp_row() -> None:
    service = object.__new__(ConnectorConnectionService)
    installation = SimpleNamespace(id=uuid.uuid4())
    app = SimpleNamespace(connector_key="mcp_remote")
    service._require_app_and_installation = lambda *_args, **_kwargs: (  # type: ignore[method-assign]
        app,
        installation,
    )

    with pytest.raises(AppError) as caught:
        service.start_connection(
            workspace=SimpleNamespace(id=uuid.uuid4()),
            membership=fake_membership(keys={WorkspacePermission.APPS_CONNECT.value}),
            actor_id=uuid.uuid4(),
            app_slug="mcp-connectors",
        )

    assert caught.value.category == ErrorCategory.CONNECTOR_NOT_SUPPORTED


def test_generic_connector_disconnect_cannot_bypass_mcp_invalidation() -> None:
    service = object.__new__(ConnectorConnectionService)
    connection = SimpleNamespace(
        id=uuid.uuid4(),
        app_installation_id=uuid.uuid4(),
        connector_key="mcp_remote",
    )
    installation = SimpleNamespace(id=connection.app_installation_id)
    app = SimpleNamespace(connector_key="mcp_remote")
    service._require_app_and_installation = lambda *_args, **_kwargs: (  # type: ignore[method-assign]
        app,
        installation,
    )
    service.repo = SimpleNamespace(
        get_connection=lambda *_args, **_kwargs: connection
    )

    with pytest.raises(AppError) as caught:
        service.disconnect(
            workspace=SimpleNamespace(id=uuid.uuid4()),
            membership=fake_membership(keys={WorkspacePermission.APPS_CONNECT.value}),
            actor_id=uuid.uuid4(),
            app_slug="mcp-connectors",
            connection_id=connection.id,
        )

    assert caught.value.category == ErrorCategory.CONNECTOR_NOT_SUPPORTED


def test_mcp_adapter_does_not_advertise_generic_sync() -> None:
    adapter = McpRemoteConnector(
        settings=Settings(_env_file=None, mcp_connector_enabled=True)
    )

    assert adapter.capabilities.supports_sync is False


def test_permission_gated_approval_responses_are_private_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = _access(WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL)

    class _Operations:
        @staticmethod
        def list_approvals(**_kwargs):
            return McpApprovalListOut(items=[], total=0, limit=50, offset=0)

    monkeypatch.setattr(
        runtime_router_module,
        "McpExternalOperationsService",
        lambda _db: _Operations(),
    )
    app = FastAPI()
    app.include_router(runtime_router_module.router)
    app.dependency_overrides[get_document_access] = lambda: access
    app.dependency_overrides[get_db] = lambda: object()

    response = TestClient(app).get("/api/apps/mcp/external-approvals")

    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("private, no-store")
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_workspace_mcp_responses_are_no_store_but_cimd_remains_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = _access(WorkspacePermission.APPS_VIEW)

    class _Servers:
        @staticmethod
        def list_servers(**_kwargs):
            return {"items": [], "total": 0, "limit": 50, "offset": 0}

    class _OAuth:
        @staticmethod
        def public_client_metadata():
            return {"client_id": "https://api.example/client-metadata.json"}

    monkeypatch.setattr(router_module, "McpServerService", lambda _db: _Servers())
    monkeypatch.setattr(router_module, "McpOAuthService", lambda: _OAuth())
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[get_document_access] = lambda: access
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    protected = client.get("/api/apps/mcp/servers")
    cimd = client.get(router_module._CIMD_ROUTE_PATH)

    assert protected.status_code == 200
    assert protected.headers["cache-control"].startswith("private, no-store")
    assert protected.headers["x-content-type-options"] == "nosniff"
    assert cimd.status_code == 200
    assert cimd.headers["cache-control"] == "public, max-age=300"
    assert cimd.headers["x-content-type-options"] == "nosniff"
