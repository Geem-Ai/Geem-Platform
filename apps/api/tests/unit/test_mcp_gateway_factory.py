"""DB-free runtime wiring checks for the isolated MCP gateway client."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import httpx
import pytest

import app.core.config as config_module
import app.db.models  # noqa: F401 - register isolated SQLAlchemy relationships
import app.mcp.executor as executor_module
import app.mcp.gateway as gateway_module
import app.mcp.gateway_client as gateway_client_module
import app.mcp.router as router_module
import app.mcp.services as services_module
import app.worker.tasks as worker_tasks
from app.common.request_context import get_request_context
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.gateway import (
    McpDiscoveryRequest,
    McpTargetValidationRequest,
    UnavailableMcpGatewayClient,
)
from app.mcp.gateway_client import HttpMcpGatewayClient
from app.mcp.executor import McpDispatchService
from app.mcp.services import McpServerService


@pytest.fixture(autouse=True)
def _reset_gateway_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        gateway_client_module,
        "mcp_gateway_ssl_context",
        lambda _settings: object(),
    )
    gateway_module.reset_mcp_gateway_client()
    yield
    gateway_module.reset_mcp_gateway_client()


def _enabled_settings():
    return get_settings().model_copy(
        update={
            "mcp_connector_enabled": True,
            "mcp_egress_gateway_url": "https://mcp-gateway.internal:8443",
            "mcp_egress_client_cert_file": "/run/secrets/client.crt",
            "mcp_egress_client_key_file": "/run/secrets/client.key",
            "mcp_egress_ca_cert_file": "/run/secrets/ca.crt",
        }
    )


def test_gateway_factory_is_deterministically_unavailable_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_connector_enabled=False),
    )

    client = gateway_module.get_mcp_gateway_client()

    assert isinstance(client, UnavailableMcpGatewayClient)
    with pytest.raises(AppError) as raised:
        client.discover(  # type: ignore[arg-type]
            McpDiscoveryRequest(
                workspace_id=uuid.uuid4(),
                connection_id=uuid.uuid4(),
                server_url="https://tenant-secret.example/mcp",
                resource_uri="https://tenant-secret.example/",
                auth={"mode": "none"},
                credential_epoch=1,
                deadline_seconds=1,
            )
        )
    assert raised.value.category == ErrorCategory.MCP_SERVER_UNREACHABLE
    assert "tenant-secret.example" not in str(raised.value)


def test_tool_dispatch_uses_disabled_factory_without_transport_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(update={"mcp_connector_enabled": False})
    constructed = 0

    class ForbiddenClient:
        def __init__(self, _settings) -> None:
            nonlocal constructed
            constructed += 1
            raise AssertionError("disabled MCP must not construct a transport")

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(gateway_client_module, "HttpMcpGatewayClient", ForbiddenClient)

    service = McpDispatchService(
        settings,
        session_factory=lambda: object(),
        oauth=object(),  # type: ignore[arg-type]
    )

    assert isinstance(service.gateway, UnavailableMcpGatewayClient)
    assert constructed == 0
    with pytest.raises(AppError) as raised:
        service.gateway.call_tool(
            SimpleNamespace(target_url="https://tenant-secret.example/mcp")
        )
    assert raised.value.category == ErrorCategory.MCP_SERVER_UNREACHABLE
    assert "tenant-secret.example" not in str(raised.value)


def test_disabled_dispatch_stops_before_oauth_database_or_gateway() -> None:
    settings = get_settings().model_copy(update={"mcp_connector_enabled": False})

    class ForbiddenOAuth:
        @staticmethod
        def refresh_if_needed(**_kwargs) -> None:
            raise AssertionError("disabled MCP must not refresh OAuth")

    class ForbiddenGateway:
        @staticmethod
        def call_tool(_request):
            raise AssertionError("disabled MCP must not reach the gateway")

    service = McpDispatchService(
        settings,
        session_factory=lambda: (_ for _ in ()).throw(
            AssertionError("disabled MCP must not start admission")
        ),
        gateway=ForbiddenGateway(),  # type: ignore[arg-type]
        oauth=ForbiddenOAuth(),  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as raised:
        service.dispatch(
            resolved=SimpleNamespace(
                connection=SimpleNamespace(auth_mode="oauth2")
            ),  # type: ignore[arg-type]
            invocation=SimpleNamespace(),  # type: ignore[arg-type]
            expert_id=uuid.uuid4(),
            tool_call=SimpleNamespace(),  # type: ignore[arg-type]
            arguments={},
            iteration=1,
        )

    assert raised.value.category == ErrorCategory.APP_NOT_AVAILABLE
    assert raised.value.message == "MCP Connectors are unavailable."


def test_tool_dispatch_preserves_explicit_gateway_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    injected = SimpleNamespace(call_tool=lambda _request: object())
    monkeypatch.setattr(
        executor_module,
        "get_mcp_gateway_client",
        lambda: (_ for _ in ()).throw(
            AssertionError("an explicit gateway must bypass the process factory")
        ),
    )

    service = McpDispatchService(
        _enabled_settings(),
        session_factory=lambda: object(),
        gateway=injected,  # type: ignore[arg-type]
        oauth=object(),  # type: ignore[arg-type]
    )

    assert service.gateway is injected


def test_gateway_factory_fail_closes_without_logging_misconfiguration(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _enabled_settings()
    secret_path = "/run/secrets/client-key-must-not-leak"
    attempts = 0

    class BrokenClient:
        def __init__(self, _settings) -> None:
            nonlocal attempts
            attempts += 1
            raise RuntimeError(secret_path)

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(gateway_client_module, "HttpMcpGatewayClient", BrokenClient)

    client = gateway_module.get_mcp_gateway_client()
    same_client = gateway_module.get_mcp_gateway_client()

    assert isinstance(client, UnavailableMcpGatewayClient)
    assert same_client is client
    assert attempts == 1
    assert secret_path not in caplog.text
    assert "mcp_gateway_client_initialization_failed" in caplog.text


def test_api_service_uses_one_lazy_real_mtls_client_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _enabled_settings()
    constructed: list[dict] = []

    class DummyHttpClient:
        def close(self) -> None:
            pass

    def build_http_client(**kwargs):
        constructed.append(kwargs)
        return DummyHttpClient()

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(gateway_client_module.httpx, "Client", build_http_client)

    first = gateway_module.get_mcp_gateway_client()
    second = gateway_module.get_mcp_gateway_client()
    service = McpServerService(  # type: ignore[arg-type]
        object(),
        settings=settings,
        oauth=object(),
    )
    dispatch = McpDispatchService(
        settings,
        session_factory=lambda: object(),
        oauth=object(),  # type: ignore[arg-type]
    )

    assert isinstance(first, HttpMcpGatewayClient)
    assert second is first
    assert service.gateway is first
    assert dispatch.gateway is first
    assert len(constructed) == 1
    assert constructed[0]["trust_env"] is False
    assert constructed[0]["follow_redirects"] is False


def test_api_discovery_entrypoint_selects_the_real_lazy_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _enabled_settings()
    observed: dict[str, object] = {}

    class DummyHttpClient:
        def close(self) -> None:
            pass

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(services_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        gateway_client_module.httpx,
        "Client",
        lambda **_kwargs: DummyHttpClient(),
    )
    monkeypatch.setattr(router_module, "require_connect_apps", lambda _membership: None)

    expected = object()

    def discover(self, **kwargs):
        observed["gateway"] = self.gateway
        observed["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(McpServerService, "discover", discover)
    workspace_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    access = SimpleNamespace(
        membership=object(),
        workspace=SimpleNamespace(id=workspace_id),
        user=SimpleNamespace(id=actor_id),
    )

    result = router_module.discover_mcp_server(
        connection_id,
        access=access,
        db=object(),  # type: ignore[arg-type]
    )

    assert result is expected
    assert isinstance(observed["gateway"], HttpMcpGatewayClient)
    assert observed["kwargs"] == {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "connection_id": connection_id,
    }


def test_worker_health_discovery_binds_actor_and_selects_real_lazy_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _enabled_settings()
    observed: dict[str, object] = {}

    class DummyHttpClient:
        def close(self) -> None:
            pass

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(services_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        gateway_client_module.httpx,
        "Client",
        lambda **_kwargs: DummyHttpClient(),
    )

    workspace_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    row = SimpleNamespace(
        connector_key="mcp_remote",
        workspace_id=workspace_id,
        connected_by_user_id=actor_id,
        last_health_check_at=None,
    )

    class FakeDb:
        def get(self, _model, row_id):
            assert row_id == connection_id
            return row

        def expire_all(self) -> None:
            pass

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(worker_tasks, "SessionLocal", FakeDb)

    def discover(self, **kwargs):
        context = get_request_context()
        observed["gateway"] = self.gateway
        observed["workspace_id"] = context.workspace_id
        observed["actor_id"] = context.user_id
        observed["kwargs"] = kwargs
        return SimpleNamespace(complete=True)

    monkeypatch.setattr(McpServerService, "discover", discover)

    outcome = worker_tasks.discover_mcp_connection.apply(args=[str(connection_id)])

    assert outcome.successful()
    assert outcome.result["status"] == "complete"
    assert isinstance(observed["gateway"], HttpMcpGatewayClient)
    assert observed["workspace_id"] == workspace_id
    assert observed["actor_id"] == actor_id
    assert observed["kwargs"] == {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "connection_id": connection_id,
    }


def test_factory_discards_an_inherited_prefork_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _enabled_settings()
    created: list[object] = []

    class FakeClient:
        def __init__(self, _settings) -> None:
            created.append(self)

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(gateway_client_module, "HttpMcpGatewayClient", FakeClient)
    monkeypatch.setattr(gateway_module.os, "getpid", lambda: 100)
    first = gateway_module.get_mcp_gateway_client()
    monkeypatch.setattr(gateway_module.os, "getpid", lambda: 101)
    second = gateway_module.get_mcp_gateway_client()

    assert first is not second
    assert len(created) == 2


def test_target_preflight_wire_contract_has_no_credentials_or_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _enabled_settings()
    captured: list[dict] = []
    workspace_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    monotonic = gateway_client_module.time.monotonic
    monkeypatch.setattr(
        gateway_client_module,
        "time",
        SimpleNamespace(monotonic=monotonic, time=lambda: 1_000.0),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/target-validation"
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "operation_id": payload["operation_id"],
                "origin_digest": "a" * 64,
            },
        )

    client = HttpMcpGatewayClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = client.validate_target(
        McpTargetValidationRequest(
            workspace_id=workspace_id,
            connection_id=connection_id,
            target_url="https://tools.example.com/mcp",
            deadline_seconds=5,
        )
    )

    assert result.origin_digest == "a" * 64
    assert set(captured[0]) == {
        "operation_id",
        "target_url",
        "caller_binding",
        "deadline_seconds",
        "deadline_unix_ms",
    }
    assert 0 < captured[0]["deadline_seconds"] <= 5
    assert 1_000_000 < captured[0]["deadline_unix_ms"] <= 1_005_000
    assert "auth" not in captured[0]
    assert "headers" not in captured[0]
    assert "body" not in captured[0]
