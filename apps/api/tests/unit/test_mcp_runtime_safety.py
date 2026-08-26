from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import app.db.models  # noqa: F401  # register relationship targets for isolated runs
import app.mcp.executor as executor_module
import app.mcp.surfaces as surfaces_module
from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentFunctionCall,
    AgentProviderResult,
    AgentToolCall,
    AgentUsage,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.conversations.invocation import ChatInvocationContext
from app.mcp.executor import (
    ToolLoopResult,
    ToolLoopTurnExecutor,
    _PreparedTurn,
    _require_write_dispatch_authority,
)
from app.mcp.gateway import McpDiscoveryRequest
from app.mcp.gateway_client import (
    HttpMcpGatewayClient,
    McpToolCallRequest,
    _gateway_error_category,
    _safe_gateway_message,
)
from app.mcp.public_tokens import (
    channel_external_principal_fingerprint,
    mint_widget_mcp_session,
    new_turn_handle,
    origin_digest,
    parse_widget_mcp_session,
    turn_handle_digest,
    widget_external_principal_fingerprint,
)
from app.mcp.result import NormalizedToolResult
from app.mcp.runtime_models import McpToolSurfaceBinding
from app.mcp.surfaces import McpSurfaceBindingService, McpSurfaceResolver


def _settings():
    return get_settings().model_copy(
        update={
            "mcp_connector_enabled": True,
            "mcp_egress_gateway_url": "https://gateway.internal",
            "mcp_egress_max_request_bytes": 65_536,
            "mcp_egress_max_response_bytes": 65_536,
        }
    )


def test_gateway_discovery_reuses_and_closes_legacy_session() -> None:
    handle = "a" * 43
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if payload["operation"] == "discover":
            return httpx.Response(
                200,
                json={
                    "operation_id": payload["operation_id"],
                    "negotiated_protocol_version": "2025-11-25",
                    "session_mode": "legacy",
                    "capabilities": {"tools": {}},
                    "server_info": {"name": "fixture"},
                    "session_handle": handle,
                },
            )
        if payload["operation"] == "tools_list" and payload["cursor"] is None:
            return httpx.Response(
                200,
                json={
                    "operation_id": payload["operation_id"],
                    "negotiated_protocol_version": "2025-11-25",
                    "session_mode": "legacy",
                    "capabilities": {"tools": {}},
                    "session_handle": handle,
                    "tools": [{"name": "first", "inputSchema": {"type": "object"}}],
                    "next_cursor": "next",
                },
            )
        if payload["operation"] == "tools_list":
            return httpx.Response(
                200,
                json={
                    "operation_id": payload["operation_id"],
                    "negotiated_protocol_version": "2025-11-25",
                    "session_mode": "legacy",
                    "capabilities": {"tools": {}},
                    "session_handle": handle,
                    "tools": [{"name": "second", "inputSchema": {"type": "object"}}],
                    "next_cursor": None,
                },
            )
        assert {
            key: value
            for key, value in payload.items()
            if key not in {"deadline_seconds", "deadline_unix_ms"}
        } == {
            "operation_id": f"close:{connection_id.hex}",
            "operation": "session_close",
            "mode": "legacy",
            "caller_binding": requests[0]["caller_binding"],
            "session_handle": handle,
        }
        return httpx.Response(
            200,
            json={"operation_id": payload["operation_id"], "closed": True},
        )

    workspace_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    transport = httpx.MockTransport(handler)
    raw_client = httpx.Client(transport=transport)
    client = HttpMcpGatewayClient(_settings(), client=raw_client)
    result = client.discover(
        McpDiscoveryRequest(
            workspace_id=workspace_id,
            connection_id=connection_id,
            server_url="https://mcp.example/rpc",
            resource_uri="https://mcp.example/",
            auth={"mode": "static", "header_name": "Authorization", "value": "Bearer x"},
            credential_epoch=1,
            deadline_seconds=10,
        )
    )

    assert [tool["name"] for tool in result.tools] == ["first", "second"]
    assert [request["operation"] for request in requests] == [
        "discover",
        "tools_list",
        "tools_list",
        "session_close",
    ]
    binding = requests[0]["caller_binding"]
    assert len(binding) == 64 and set(binding) <= set("0123456789abcdef")
    assert all(request["caller_binding"] == binding for request in requests)
    assert requests[1]["session_handle"] == handle
    assert requests[2]["session_handle"] == handle


def test_gateway_discovery_caps_unique_empty_pages() -> None:
    page_requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["operation"] == "discover":
            return httpx.Response(
                200,
                json={
                    "operation_id": payload["operation_id"],
                    "negotiated_protocol_version": "2026-07-28",
                    "session_mode": "modern",
                    "capabilities": {"tools": {}},
                    "server_info": {"name": "fixture"},
                },
            )
        assert payload["operation"] == "tools_list"
        page_requests.append(payload)
        return httpx.Response(
            200,
            json={
                "operation_id": payload["operation_id"],
                "negotiated_protocol_version": "2026-07-28",
                "session_mode": "modern",
                "tools": [],
                "next_cursor": f"unique-cursor-{len(page_requests)}",
            },
        )

    client = HttpMcpGatewayClient(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppError) as caught:
        client.discover(
            McpDiscoveryRequest(
                workspace_id=uuid.uuid4(),
                connection_id=uuid.uuid4(),
                server_url="https://mcp.example/rpc",
                resource_uri="https://mcp.example/",
                auth={"mode": "none"},
                credential_epoch=1,
                deadline_seconds=10,
            )
        )

    assert caught.value.category == ErrorCategory.MCP_TOOL_LIMIT_REACHED
    assert caught.value.details == {"limit": 64}
    assert len(page_requests) == 64
    assert page_requests[0]["operation_id"].startswith("list0:")
    assert page_requests[-1]["operation_id"].startswith("list63:")


def test_gateway_closes_legacy_tool_session_and_write_transport_is_ambiguous() -> None:
    handle = "b" * 43
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if payload["operation"] == "tools_call":
            return httpx.Response(
                200,
                json={
                    "operation_id": payload["operation_id"],
                    "negotiated_protocol_version": "2025-11-25",
                    "session_mode": "legacy",
                    "capabilities": {"tools": {}},
                    "session_handle": handle,
                    "result": {"content": [{"type": "text", "text": "ok"}]},
                },
            )
        return httpx.Response(
            200,
            json={"operation_id": payload["operation_id"], "closed": True},
        )

    client = HttpMcpGatewayClient(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = client.call_tool(
        McpToolCallRequest(
            operation_id="mcp:0123456789abcdef",
            target_url="https://mcp.example/rpc",
            auth={"mode": "none"},
            tool_name="read",
            arguments={},
            write=False,
            protocol_version="2025-11-25",
        )
    )
    assert result.result["content"][0]["text"] == "ok"
    assert [request["operation"] for request in requests] == [
        "tools_call",
        "session_close",
    ]
    assert requests[1]["caller_binding"] == requests[0]["caller_binding"]

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lost acknowledgement")

    ambiguous = HttpMcpGatewayClient(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(timeout))
    )
    with pytest.raises(AppError) as caught:
        ambiguous.call_tool(
            McpToolCallRequest(
                operation_id="mcp:write",
                target_url="https://mcp.example/rpc",
                auth={"mode": "none"},
                tool_name="write",
                arguments={"id": 1},
                write=True,
            )
        )
    assert caught.value.category == ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN


def test_gateway_connect_failure_is_pre_dispatch_for_a_write() -> None:
    def connection_refused(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gateway connection refused")

    client = HttpMcpGatewayClient(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(connection_refused)),
    )
    with pytest.raises(AppError) as caught:
        client.call_tool(
            McpToolCallRequest(
                operation_id="mcp:write-connect-failure",
                target_url="https://mcp.example/rpc",
                auth={"mode": "none"},
                tool_name="write",
                arguments={},
                write=True,
            )
        )

    assert caught.value.category == ErrorCategory.MCP_SERVER_UNREACHABLE
    assert caught.value.retryable is True


def test_gateway_explicit_pre_dispatch_timeout_is_not_reclassified_unknown() -> None:
    def timed_out(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["operation"] == "tools_call"
        return httpx.Response(
            503,
            json={
                "error": {
                    "code": "mcp_operation_timeout",
                    "message": "safe fixed gateway message",
                    "retryable": True,
                    "outcome_unknown": False,
                }
            },
        )

    client = HttpMcpGatewayClient(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(timed_out)),
    )
    with pytest.raises(AppError) as caught:
        client.call_tool(
            McpToolCallRequest(
                operation_id="mcp:write-timeout",
                target_url="https://mcp.example/rpc",
                auth={"mode": "none"},
                tool_name="write",
                arguments={},
                write=True,
            )
        )

    assert caught.value.category == ErrorCategory.MCP_SERVER_UNREACHABLE
    assert caught.value.retryable is True


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("mcp_tool_inventory_too_large", ErrorCategory.MCP_TOOL_LIMIT_REACHED),
        ("mcp_response_too_large", ErrorCategory.MCP_RESPONSE_TOO_LARGE),
        ("mcp_arguments_too_large", ErrorCategory.MCP_TOOL_INCOMPATIBLE),
        ("mcp_session_binding_mismatch", ErrorCategory.MCP_PROTOCOL_UNSUPPORTED),
        ("mcp_session_target_mismatch", ErrorCategory.MCP_PROTOCOL_UNSUPPORTED),
        ("mcp_session_not_found", ErrorCategory.MCP_SERVER_UNREACHABLE),
        ("mcp_session_expired", ErrorCategory.MCP_SERVER_UNREACHABLE),
        ("mcp_session_capacity", ErrorCategory.MCP_SERVER_UNREACHABLE),
    ],
)
def test_gateway_maps_bounded_inventory_argument_and_session_errors(
    code: str, expected: ErrorCategory
) -> None:
    assert _gateway_error_category(code, outcome_unknown=False) == expected


def test_gateway_reports_oversized_response_without_calling_it_unsupported() -> None:
    category = _gateway_error_category(
        "mcp_response_too_large", outcome_unknown=False
    )

    assert category == ErrorCategory.MCP_RESPONSE_TOO_LARGE
    assert _safe_gateway_message(category) == (
        "The MCP server response exceeds the configured limit."
    )


def test_api_default_response_budget_supports_large_tool_inventories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCP_EGRESS_MAX_RESPONSE_BYTES", raising=False)

    assert Settings(_env_file=None).mcp_egress_max_response_bytes == 262_144


def test_widget_session_and_turn_tokens_are_audience_bound_and_bounded() -> None:
    secret = "unit-test-secret"
    widget_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    digest = origin_digest("https://EXAMPLE.com/", secret=secret)
    token = mint_widget_mcp_session(
        session_id=session_id,
        widget_id=widget_id,
        origin_digest=digest,
        ttl_seconds=60,
        secret=secret,
    )

    parsed = parse_widget_mcp_session(
        token,
        expected_widget_id=widget_id,
        expected_origin_digest=digest,
        secret=secret,
    )
    assert parsed is not None and parsed.session_id == session_id
    assert (
        parse_widget_mcp_session(
            token,
            expected_widget_id=uuid.uuid4(),
            expected_origin_digest=digest,
            secret=secret,
        )
        is None
    )
    assert (
        parse_widget_mcp_session(
            f"{token}x",
            expected_widget_id=widget_id,
            expected_origin_digest=digest,
            secret=secret,
        )
        is None
    )
    assert (
        parse_widget_mcp_session(
            "v2." + "a" * 3_000 + ".x",
            expected_widget_id=widget_id,
            expected_origin_digest=digest,
            secret=secret,
        )
        is None
    )
    assert (
        parse_widget_mcp_session(
            "v2.é.x",
            expected_widget_id=widget_id,
            expected_origin_digest=digest,
            secret=secret,
        )
        is None
    )

    handle = new_turn_handle()
    first = turn_handle_digest(
        handle,
        widget_id=widget_id,
        session_id=session_id,
        origin_digest=digest,
        secret=secret,
    )
    second = turn_handle_digest(
        handle,
        widget_id=uuid.uuid4(),
        session_id=session_id,
        origin_digest=digest,
        secret=secret,
    )
    assert len(first) == 64 and first != second
    with pytest.raises(ValueError):
        turn_handle_digest(
            "short",
            widget_id=widget_id,
            session_id=session_id,
            origin_digest=digest,
            secret=secret,
        )


def test_surface_without_exact_binding_returns_before_paid_access() -> None:
    class _NoBindingDb:
        def scalar(self, _statement):
            return None

    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    invocation = ChatInvocationContext.widget(
        workspace_id=workspace_id,
        widget_id=uuid.uuid4(),
        expert_id=expert_id,
        conversation_id=uuid.uuid4(),
        source_binding_id=uuid.uuid4(),
        external_principal_fingerprint="a" * 64,
        initiating_origin="https://example.com",
        external_turn_handle_digest="b" * 64,
    )
    resolver = McpSurfaceResolver(
        _NoBindingDb(),  # type: ignore[arg-type]
        session_factory=lambda: (_ for _ in ()).throw(
            AssertionError("paid App access must not start")
        ),
    )

    assert resolver.resolve(invocation, expert_id) == []


def test_surface_with_stale_inventory_returns_before_paid_access() -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    widget_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    source_binding_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    surface = SimpleNamespace(write_policy="deny")
    grant = SimpleNamespace(
        state="active",
        approved_definition_hash="a" * 64,
        approved_classification="read_only",
        approved_principal_fingerprint="b" * 64,
        approved_credential_epoch=1,
    )
    tool = SimpleNamespace(
        status="active",
        compatibility_status="compatible",
        classification="read_only",
        definition_hash="a" * 64,
    )
    connection = SimpleNamespace(
        mcp_principal_fingerprint="b" * 64,
        mcp_credential_epoch=1,
        status="active",
        health="healthy",
        mcp_reauthorization_required=False,
        mcp_inventory_refreshed_at=datetime.now(timezone.utc)
        - timedelta(hours=1),
    )

    class _Rows:
        @staticmethod
        def all():
            return [(surface, grant, tool, connection)]

    class _Db:
        def scalar(self, statement):
            rendered = str(statement)
            if "FROM mcp_tool_surface_bindings" in rendered:
                return uuid.uuid4()
            if "FROM widget_instances" in rendered:
                return SimpleNamespace(
                    id=widget_id,
                    status="active",
                    allowed_origins=["https://example.com"],
                )
            if "FROM widget_conversation_bindings" in rendered:
                return SimpleNamespace(id=source_binding_id, session_id=session_id)
            raise AssertionError(rendered)

        @staticmethod
        def execute(_statement):
            return _Rows()

    invocation = ChatInvocationContext.widget(
        workspace_id=workspace_id,
        widget_id=widget_id,
        expert_id=expert_id,
        conversation_id=conversation_id,
        source_binding_id=source_binding_id,
        external_principal_fingerprint=widget_external_principal_fingerprint(
            session_id,
            widget_id=widget_id,
            secret=_settings().jwt_secret,
        ),
        initiating_origin="https://example.com",
        external_turn_handle_digest="d" * 64,
    )
    resolver = McpSurfaceResolver(
        _Db(),  # type: ignore[arg-type]
        _settings(),
        session_factory=lambda: (_ for _ in ()).throw(
            AssertionError("paid App access must not start for stale inventory")
        ),
    )

    assert resolver.resolve(invocation, expert_id) == []


def test_widget_surface_preflight_rejects_forged_session_fingerprint() -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    widget_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    widget = SimpleNamespace(
        id=widget_id,
        status="active",
        allowed_origins=["https://widget.example"],
    )
    binding = SimpleNamespace(id=binding_id, session_id=session_id)

    class _Db:
        @staticmethod
        def scalar(statement):
            rendered = str(statement)
            if "FROM widget_instances" in rendered:
                return widget
            if "FROM widget_conversation_bindings" in rendered:
                return binding
            raise AssertionError(rendered)

    valid = widget_external_principal_fingerprint(
        session_id,
        widget_id=widget_id,
        secret=_settings().jwt_secret,
    )
    resolver = McpSurfaceResolver(_Db(), _settings())  # type: ignore[arg-type]

    def invocation(fingerprint: str) -> ChatInvocationContext:
        return ChatInvocationContext.widget(
            workspace_id=workspace_id,
            widget_id=widget_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            source_binding_id=binding_id,
            external_principal_fingerprint=fingerprint,
            initiating_origin="https://widget.example",
        )

    assert resolver._source_is_locally_eligible(
        _Db(),  # type: ignore[arg-type]
        invocation=invocation(valid),
        expert_id=expert_id,
    )
    assert not resolver._source_is_locally_eligible(
        _Db(),  # type: ignore[arg-type]
        invocation=invocation("f" * 64),
        expert_id=expert_id,
    )


def test_whatsapp_surface_preflight_rejects_changed_sender_fingerprint() -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    channel = SimpleNamespace(
        enabled=True,
        auto_reply_enabled=True,
        respond_to_groups=False,
    )
    binding = SimpleNamespace(
        id=binding_id,
        external_chat_id="chat-1",
        external_sender_id="sender-1",
    )
    connection = SimpleNamespace(status="active")

    class _Db:
        @staticmethod
        def scalar(statement):
            rendered = str(statement)
            if "FROM channel_bindings" in rendered:
                return channel
            if "FROM channel_conversation_bindings" in rendered:
                return binding
            if "FROM app_connections" in rendered:
                return connection
            raise AssertionError(rendered)

    fingerprint = channel_external_principal_fingerprint(
        external_chat_id=binding.external_chat_id,
        external_sender_id=binding.external_sender_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        binding_id=binding_id,
        secret=_settings().jwt_secret,
    )
    invocation = ChatInvocationContext.channel(
        workspace_id=workspace_id,
        connection_id=connection_id,
        expert_id=expert_id,
        conversation_id=conversation_id,
        source_binding_id=binding_id,
        external_principal_fingerprint=fingerprint,
    )
    resolver = McpSurfaceResolver(_Db(), _settings())  # type: ignore[arg-type]
    assert resolver._source_is_locally_eligible(
        _Db(),  # type: ignore[arg-type]
        invocation=invocation,
        expert_id=expert_id,
    )

    binding.external_sender_id = "sender-2"
    assert not resolver._source_is_locally_eligible(
        _Db(),  # type: ignore[arg-type]
        invocation=invocation,
        expert_id=expert_id,
    )


def test_surface_revoke_takes_target_fence_before_row_lock(monkeypatch) -> None:
    widget_id = uuid.uuid4()
    row = SimpleNamespace(
        surface_kind="chat_widget",
        widget_instance_id=widget_id,
        channel_binding_id=None,
        state="active",
    )

    class _SnapshotResult:
        @staticmethod
        def one_or_none():
            return SimpleNamespace(
                surface_kind="chat_widget",
                widget_instance_id=widget_id,
                channel_binding_id=None,
                app_connection_id=None,
            )

    class _Db:
        def __init__(self) -> None:
            self.events: list[str] = []

        def execute(self, statement, _params=None):
            rendered = str(statement)
            if "pg_advisory_xact_lock" in rendered:
                self.events.append("target_fence")
                return SimpleNamespace()
            self.events.append("target_snapshot")
            return _SnapshotResult()

        def scalar(self, statement):
            assert "FOR UPDATE" in str(statement)
            self.events.append("binding_row_lock")
            return row

        def commit(self) -> None:
            self.events.append("commit")

    db = _Db()
    audits: list[dict] = []
    monkeypatch.setattr(
        surfaces_module,
        "record_audit",
        lambda *_args, **kwargs: audits.append(kwargs),
    )
    actor_id = uuid.uuid4()
    McpSurfaceBindingService(db, _settings()).revoke_binding(  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        expert_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        actor_id=actor_id,
    )

    assert db.events == [
        "target_snapshot",
        "target_fence",
        "binding_row_lock",
        "commit",
    ]
    assert row.state == "revoked"
    assert audits[0]["action"].value == "app.mcp.surface_unbound"
    assert audits[0]["actor_user_id"] == actor_id


def test_mid_loop_access_loss_forces_tool_free_safe_synthesis() -> None:
    call = AgentToolCall(
        id="call-1",
        type="function",
        function=AgentFunctionCall(name="mcp_read", arguments="{}"),
    )

    class _Provider:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def answer_with_tools(
            self,
            messages,
            *,
            model,
            system_prompt,
            tools,
            max_tokens=None,
            timeout_seconds=None,
        ) -> AgentProviderResult:
            self.calls.append(
                {
                    "messages": list(messages),
                    "model": model,
                    "system_prompt": system_prompt,
                    "tools": list(tools),
                    "timeout_seconds": timeout_seconds,
                }
            )
            if len(self.calls) == 1:
                return AgentProviderResult(
                    message=AgentAssistantResponseMessage(
                        content=None,
                        tool_calls=[call],
                    ),
                    finish_reason="tool_calls",
                    usage=AgentUsage(
                        prompt_tokens=4,
                        completion_tokens=2,
                        total_tokens=6,
                    ),
                    provider_model="test/tool-model",
                )
            return AgentProviderResult(
                message=AgentAssistantResponseMessage(
                    content="Safe answer from authorized context.",
                    tool_calls=None,
                ),
                finish_reason="stop",
                usage=AgentUsage(
                    prompt_tokens=7,
                    completion_tokens=3,
                    total_tokens=10,
                ),
                provider_model="test/tool-model",
            )

    class _DeniedDispatcher:
        @staticmethod
        def dispatch(**_kwargs):
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
                "MCP subscription expired.",
            )

    provider = _Provider()
    settings = get_settings().model_copy(
        update={
            "openrouter_chat_model": "test/tool-model",
            "openrouter_chat_fallback_model": "",
            "mcp_tool_provider_capability_matrix": json.dumps(
                {
                    "test/tool-model": [
                        "function_calling",
                        "parallel_tool_calls_false",
                    ]
                }
            ),
        }
    )
    executor = ToolLoopTurnExecutor(
        SimpleNamespace(),  # type: ignore[arg-type]
        settings=settings,
        rag=SimpleNamespace(),  # type: ignore[arg-type]
        provider=provider,
        dispatcher=_DeniedDispatcher(),  # type: ignore[arg-type]
    )
    prepared = _PreparedTurn(
        system_prompt="Use only authorized context.",
        messages=[{"role": "user", "content": "question"}],
        scope=None,
        allowed_ids=set(),
        context_chunks=[],
        general=True,
    )
    executor._prepare = lambda **_kwargs: prepared  # type: ignore[method-assign]
    executor._record_intermediate_usage = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )

    def _finalize(result, *, prepared, tool_citations, usage_context):
        assert tool_citations == []
        return ToolLoopResult(
            answer=result.message.content or "",
            citations=[],
            insufficient_context=False,
            model=result.provider_model,
            usage={},
            billed_chat_tokens=0,
        )

    executor._finalize = _finalize  # type: ignore[method-assign]
    expert_id = uuid.uuid4()
    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=expert_id,
        question="question",
        invocation=ChatInvocationContext.workspace_user(
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            expert_id=expert_id,
        ),
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[
            SimpleNamespace(
                tool=SimpleNamespace(
                    llm_tool_name="mcp_read",
                    input_schema={"type": "object", "additionalProperties": False},
                    classification="read_only",
                ),
                provider_tool_schema={
                    "type": "function",
                    "function": {
                        "name": "mcp_read",
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                        },
                    },
                },
            )
        ],
    )

    assert result.answer == "Safe answer from authorized context."
    assert len(provider.calls) == 2
    assert provider.calls[1]["tools"] == []
    fallback_messages = provider.calls[1]["messages"]
    assert fallback_messages[-2]["tool_calls"][0]["id"] == "call-1"
    assert fallback_messages[-1]["tool_call_id"] == "call-1"
    assert "Do not claim" in fallback_messages[-1]["content"]


@pytest.mark.parametrize("source", ["workspace", "widget", "channel"])
def test_unapproved_non_api_write_dispatch_remains_denied(source: str) -> None:
    with pytest.raises(AppError) as denied:
        _require_write_dispatch_authority(
            classification="write",
            invocation_source=source,
            unattended_write_allowed=False,
            approved_write_resume=False,
        )

    assert denied.value.category == ErrorCategory.MCP_EXTERNAL_APPROVAL_REQUIRED


def test_approval_resume_authority_cannot_widen_api_or_read_dispatch() -> None:
    for classification, source in (("read_only", "workspace"), ("write", "api")):
        with pytest.raises(AppError) as denied:
            _require_write_dispatch_authority(
                classification=classification,
                invocation_source=source,
                unattended_write_allowed=True,
                approved_write_resume=True,
            )
        assert denied.value.category == ErrorCategory.MCP_TOOL_NOT_GRANTED


@pytest.mark.parametrize("source", ["workspace", "widget", "channel"])
def test_approved_write_resume_marks_only_the_fresh_dispatch_admission(
    source: str,
) -> None:
    schema = {
        "type": "function",
        "function": {
            "name": "mcp_write",
            "parameters": {"type": "object", "additionalProperties": False},
        },
    }
    resolved = SimpleNamespace(
        grant=SimpleNamespace(id=uuid.uuid4()),
        tool=SimpleNamespace(
            id=uuid.uuid4(),
            llm_tool_name="mcp_write",
            tool_name="write",
            classification="write",
            input_schema={"type": "object", "additionalProperties": False},
        ),
        connection=SimpleNamespace(id=uuid.uuid4()),
        provider_tool_schema=schema,
    )
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    if source == "workspace":
        invocation = ChatInvocationContext.workspace_user(
            workspace_id=workspace_id,
            user_id=uuid.uuid4(),
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
        )
    elif source == "widget":
        invocation = ChatInvocationContext.widget(
            workspace_id=workspace_id,
            widget_id=uuid.uuid4(),
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
            source_binding_id=uuid.uuid4(),
            external_principal_fingerprint="a" * 64,
            initiating_origin="https://widget.example",
        )
    else:
        invocation = ChatInvocationContext.channel(
            workspace_id=workspace_id,
            connection_id=uuid.uuid4(),
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
            source_binding_id=uuid.uuid4(),
            external_principal_fingerprint="b" * 64,
        )

    class _ApprovedDispatcher:
        def __init__(self) -> None:
            self.kwargs: dict | None = None

        def dispatch(self, **kwargs):
            self.kwargs = kwargs
            kwargs["before_gateway"]()
            return (
                NormalizedToolResult(
                    model_content="<untrusted_mcp_tool_result>ok</untrusted_mcp_tool_result>",
                    is_error=False,
                    transport_bytes=2,
                    content_types=("text",),
                    unsupported_blocks=(),
                ),
                {
                    "kind": "tool",
                    "connection_display_name": "MCP",
                    "tool_name": "write",
                },
            )

    class _FinalProvider:
        @staticmethod
        def answer_with_tools(*_args, **_kwargs) -> AgentProviderResult:
            return AgentProviderResult(
                message=AgentAssistantResponseMessage(
                    content="Approved write completed.",
                    tool_calls=None,
                ),
                finish_reason="stop",
                usage=AgentUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                provider_model="test/tool-model",
            )

    dispatcher = _ApprovedDispatcher()
    settings = get_settings().model_copy(
        update={
            "openrouter_chat_model": "test/tool-model",
            "openrouter_chat_fallback_model": "",
            "mcp_tool_provider_capability_matrix": json.dumps(
                {
                    "test/tool-model": [
                        "function_calling",
                        "parallel_tool_calls_false",
                    ]
                }
            ),
        }
    )
    executor = ToolLoopTurnExecutor(
        SimpleNamespace(),  # type: ignore[arg-type]
        settings=settings,
        rag=SimpleNamespace(),  # type: ignore[arg-type]
        provider=_FinalProvider(),  # type: ignore[arg-type]
        dispatcher=dispatcher,  # type: ignore[arg-type]
    )
    executor._prepare = lambda **_kwargs: _PreparedTurn(  # type: ignore[method-assign]
        system_prompt="Use tools safely.",
        messages=[],
        scope=None,
        allowed_ids=set(),
        context_chunks=[],
        general=True,
    )
    executor._finalize = (  # type: ignore[method-assign]
        lambda result, **_kwargs: ToolLoopResult(
            answer=result.message.content or "",
            citations=[],
            insufficient_context=False,
            model=result.provider_model,
            usage={},
            billed_chat_tokens=0,
        )
    )
    before: list[str] = []
    after: list[str] = []
    tool_call = AgentToolCall(
        id="call-approved",
        type="function",
        function=AgentFunctionCall(name="mcp_write", arguments="{}"),
    )

    result = executor.resume_after_approved_write(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=expert_id,
        question="approve",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        resolved=resolved,  # type: ignore[arg-type]
        tool_call=tool_call,
        arguments={},
        loop_state={
            "model": "test/tool-model",
            "iteration": 0,
            "messages": [],
            "tools": [schema],
        },
        history=[],
        before_gateway=lambda: before.append("before"),
        after_gateway=lambda: after.append("after"),
    )

    assert result.answer == "Approved write completed."
    assert dispatcher.kwargs is not None
    assert dispatcher.kwargs["approved_write_resume"] is True
    assert dispatcher.kwargs["resolved"] is resolved
    assert dispatcher.kwargs["invocation"] is invocation
    assert before == ["before"]
    assert after == ["after"]


def test_confirmed_write_is_marked_executed_before_post_dispatch_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {
        "type": "function",
        "function": {
            "name": "mcp_write",
            "parameters": {"type": "object", "additionalProperties": False},
        },
    }
    events: list[str] = []

    class _Dispatcher:
        @staticmethod
        def dispatch(**kwargs):
            kwargs["before_gateway"]()
            events.append("gateway_confirmed")
            return (
                NormalizedToolResult(
                    model_content="<untrusted_mcp_tool_result>ok</untrusted_mcp_tool_result>",
                    is_error=False,
                    transport_bytes=2,
                    content_types=("text",),
                    unsupported_blocks=(),
                ),
                {"kind": "tool", "connection_display_name": "MCP", "tool_name": "write"},
            )

    class _ForbiddenProvider:
        @staticmethod
        def answer_with_tools(*_args, **_kwargs):
            raise AssertionError("expired turns must not start final synthesis")

    settings = get_settings().model_copy(
        update={
            "openrouter_chat_model": "test/tool-model",
            "openrouter_chat_fallback_model": "",
            "mcp_tool_provider_capability_matrix": json.dumps(
                {
                    "test/tool-model": [
                        "function_calling",
                        "parallel_tool_calls_false",
                    ]
                }
            ),
        }
    )
    executor = ToolLoopTurnExecutor(
        SimpleNamespace(),  # type: ignore[arg-type]
        settings=settings,
        rag=SimpleNamespace(),  # type: ignore[arg-type]
        provider=_ForbiddenProvider(),  # type: ignore[arg-type]
        dispatcher=_Dispatcher(),  # type: ignore[arg-type]
    )
    executor._prepare = lambda **_kwargs: _PreparedTurn(  # type: ignore[method-assign]
        system_prompt="Use tools safely.",
        messages=[],
        scope=None,
        allowed_ids=set(),
        context_chunks=[],
        general=True,
    )
    deadline_checks = 0

    def expire_after_dispatch(_deadline: float) -> None:
        nonlocal deadline_checks
        deadline_checks += 1
        if deadline_checks == 3:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "The MCP turn exceeded its deadline.",
            )

    monkeypatch.setattr(executor_module, "_require_deadline", expire_after_dispatch)
    expert_id = uuid.uuid4()
    with pytest.raises(AppError) as expired:
        executor.resume_after_approved_write(
            knowledge=SimpleNamespace(),  # type: ignore[arg-type]
            expert_id=expert_id,
            question="approve",
            invocation=ChatInvocationContext.workspace_user(
                workspace_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                expert_id=expert_id,
                conversation_id=uuid.uuid4(),
                message_id=uuid.uuid4(),
                request_id=str(uuid.uuid4()),
            ),
            usage_context=SimpleNamespace(),  # type: ignore[arg-type]
            resolved=SimpleNamespace(
                grant=SimpleNamespace(id=uuid.uuid4()),
                tool=SimpleNamespace(
                    id=uuid.uuid4(),
                    llm_tool_name="mcp_write",
                ),
                connection=SimpleNamespace(id=uuid.uuid4()),
                provider_tool_schema=schema,
            ),  # type: ignore[arg-type]
            tool_call=AgentToolCall(
                id="call-approved",
                type="function",
                function=AgentFunctionCall(name="mcp_write", arguments="{}"),
            ),
            arguments={},
            loop_state={
                "model": "test/tool-model",
                "iteration": 0,
                "messages": [],
                "tools": [schema],
            },
            history=[],
            before_gateway=lambda: events.append("dispatch_started"),
            after_gateway=lambda: events.append("approval_executed"),
        )

    assert expired.value.category == ErrorCategory.GENERATION_FAILED
    assert events == ["dispatch_started", "gateway_confirmed", "approval_executed"]


@pytest.mark.parametrize(
    ("source", "source_slug"),
    [("widget", "chat-widget"), ("channel", "whatsapp")],
)
def test_approved_external_write_keeps_dual_app_and_exact_surface_admission(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    source_slug: str,
) -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    source_binding_id = uuid.uuid4()
    source_target_id = uuid.uuid4()
    source_connection_id = uuid.uuid4()
    mcp_installation_id = uuid.uuid4()
    source_installation_id = uuid.uuid4()
    grant = SimpleNamespace(id=uuid.uuid4(), unattended_write_allowed=False)
    tool = SimpleNamespace(
        id=uuid.uuid4(),
        llm_tool_name="mcp_write",
        tool_name="write",
        classification="write",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema=None,
        protocol_version="2025-11-25",
    )
    connection = SimpleNamespace(
        id=uuid.uuid4(),
        app_installation_id=mcp_installation_id,
        display_name="MCP",
    )
    surface = McpToolSurfaceBinding(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        expert_id=expert_id,
        mcp_tool_grant_id=grant.id,
        surface_kind=("chat_widget" if source == "widget" else "whatsapp_openwa"),
        widget_instance_id=(source_target_id if source == "widget" else None),
        channel_binding_id=(source_target_id if source == "channel" else None),
        state="active",
        write_policy="workspace_operator_approval",
        approved_surface_config_hash="a" * 64,
        approved_source_principal_fingerprint="b" * 64,
        approved_source_epoch=1,
    )
    target_key = (
        f"widget:{source_target_id}"
        if source == "widget"
        else f"whatsapp:{source_connection_id}:{source_target_id}"
    )
    resolved = SimpleNamespace(
        grant=grant,
        tool=tool,
        connection=connection,
        surface_binding=surface,
        source_app_slug=source_slug,
        surface_target_key=target_key,
    )
    if source == "widget":
        invocation = ChatInvocationContext.widget(
            workspace_id=workspace_id,
            widget_id=source_target_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
            source_binding_id=source_binding_id,
            external_principal_fingerprint="c" * 64,
            initiating_origin="https://widget.example",
        )
    else:
        invocation = ChatInvocationContext.channel(
            workspace_id=workspace_id,
            connection_id=source_connection_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
            source_binding_id=source_binding_id,
            external_principal_fingerprint="d" * 64,
        )

    class _RowResult:
        @staticmethod
        def one_or_none():
            return grant, tool, connection

    class _Db:
        def __init__(self) -> None:
            self.committed = False
            self.closed = False

        @staticmethod
        def execute(_statement):
            return _RowResult()

        def commit(self) -> None:
            self.committed = True

        @staticmethod
        def rollback() -> None:
            pass

        def close(self) -> None:
            self.closed = True

    db = _Db()
    access_calls: list[dict] = []
    fence_calls: list[dict] = []
    surface_checks: list[dict] = []
    quota_calls: list[dict] = []

    class _AccessSet:
        decision_at = datetime.now(timezone.utc)

        @staticmethod
        def require(slug: str):
            return SimpleNamespace(
                installation_id=(
                    mcp_installation_id
                    if slug == "mcp-connectors"
                    else source_installation_id
                ),
                decision_at=datetime.now(timezone.utc),
            )

    class _AccessService:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def require_runtime_active_set(_workspace_id, **kwargs):
            access_calls.append(kwargs)
            return _AccessSet()

    class _Credentials:
        def __init__(self, _db, **_kwargs) -> None:
            pass

        @staticmethod
        def get_credentials(_connection):
            return {
                "mcp": {
                    "server_url": "https://mcp.example/rpc",
                    "auth": {"mode": "none"},
                }
            }

    class _Quota:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def admit_in_transaction(**kwargs):
            quota_calls.append(kwargs)
            return SimpleNamespace(
                should_dispatch=True,
                invocation_id=uuid.uuid4(),
            )

    monkeypatch.setattr(
        executor_module, "begin_runtime_admission_transaction", lambda _db: None
    )
    monkeypatch.setattr(
        executor_module,
        "acquire_runtime_admission_fences",
        lambda _db, **kwargs: fence_calls.append(kwargs),
    )
    monkeypatch.setattr(executor_module, "AppAccessService", _AccessService)
    monkeypatch.setattr(executor_module, "ConnectorCredentialService", _Credentials)
    monkeypatch.setattr(executor_module, "McpToolQuotaService", _Quota)
    monkeypatch.setattr(executor_module, "_grant_current", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        executor_module,
        "_recheck_surface_in_admission",
        lambda _db, **kwargs: surface_checks.append(kwargs),
    )
    service = executor_module.McpDispatchService(
        _settings(),
        session_factory=lambda: db,  # type: ignore[arg-type]
        gateway=SimpleNamespace(),  # type: ignore[arg-type]
        oauth=SimpleNamespace(),  # type: ignore[arg-type]
    )

    snapshot = service._admit(
        resolved=resolved,  # type: ignore[arg-type]
        invocation=invocation,
        expert_id=expert_id,
        tool_call=AgentToolCall(
            id="call-approved",
            type="function",
            function=AgentFunctionCall(name="mcp_write", arguments="{}"),
        ),
        arguments={},
        admission_id="approved-admission",
        approved_write_resume=True,
    )

    assert snapshot.receipt.should_dispatch is True
    assert access_calls == [
        {
            "requirements_by_app_slug": {
                "mcp-connectors": ("connections", "tool_calls_daily"),
                source_slug: (),
            }
        }
    ]
    assert fence_calls[0]["app_slugs"] == ["mcp-connectors", source_slug]
    assert fence_calls[0]["surface_target_keys"] == (target_key,)
    assert surface_checks[0]["source_installation_id"] == source_installation_id
    assert surface_checks[0]["invocation"] is invocation
    assert quota_calls[0]["surface_binding_id"] == surface.id
    assert quota_calls[0]["invocation_source"] == source
    assert db.committed is True
    assert db.closed is True


@pytest.mark.parametrize("source", ["widget", "channel"])
def test_locked_dispatch_rechecks_current_external_principal(
    source: str,
) -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    source_installation_id = uuid.uuid4()
    surface_id = uuid.uuid4()
    grant_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    if source == "widget":
        widget_id = uuid.uuid4()
        widget = SimpleNamespace(
            id=widget_id,
            expert_id=expert_id,
            status="active",
            app_installation_id=source_installation_id,
            mcp_source_epoch=4,
            mcp_source_principal_fingerprint="a" * 64,
            allowed_origins=["https://widget.example"],
        )
        binding = SimpleNamespace(id=binding_id, session_id=str(uuid.uuid4()))
        surface = McpToolSurfaceBinding(
            id=surface_id,
            workspace_id=workspace_id,
            expert_id=expert_id,
            mcp_tool_grant_id=grant_id,
            surface_kind="chat_widget",
            widget_instance_id=widget_id,
            state="active",
            write_policy="workspace_operator_approval",
            approved_surface_config_hash=surfaces_module._widget_config_hash(widget),
            approved_source_principal_fingerprint=(
                widget.mcp_source_principal_fingerprint
            ),
            approved_source_epoch=widget.mcp_source_epoch,
        )
        fingerprint = widget_external_principal_fingerprint(
            binding.session_id,
            widget_id=widget_id,
            secret=_settings().jwt_secret,
        )
        invocation = ChatInvocationContext.widget(
            workspace_id=workspace_id,
            widget_id=widget_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            source_binding_id=binding_id,
            external_principal_fingerprint=fingerprint,
            initiating_origin="https://widget.example",
        )
        source_connection = None
        channel = None
    else:
        source_connection_id = uuid.uuid4()
        channel_id = uuid.uuid4()
        channel = SimpleNamespace(
            id=channel_id,
            app_connection_id=source_connection_id,
            expert_id=expert_id,
            enabled=True,
            auto_reply_enabled=True,
            respond_to_groups=False,
            mcp_source_epoch=7,
            mcp_source_principal_fingerprint="b" * 64,
        )
        binding = SimpleNamespace(
            id=binding_id,
            external_chat_id="chat-1",
            external_sender_id="sender-1",
        )
        source_connection = SimpleNamespace(
            id=source_connection_id,
            app_installation_id=source_installation_id,
            status="active",
            external_account_id="account-1",
        )
        surface = McpToolSurfaceBinding(
            id=surface_id,
            workspace_id=workspace_id,
            expert_id=expert_id,
            mcp_tool_grant_id=grant_id,
            surface_kind="whatsapp_openwa",
            channel_binding_id=channel_id,
            state="active",
            write_policy="workspace_operator_approval",
            approved_surface_config_hash=surfaces_module._channel_config_hash(
                channel,
                source_connection,
            ),
            approved_source_principal_fingerprint=(
                channel.mcp_source_principal_fingerprint
            ),
            approved_source_epoch=channel.mcp_source_epoch,
        )
        fingerprint = channel_external_principal_fingerprint(
            external_chat_id=binding.external_chat_id,
            external_sender_id=binding.external_sender_id,
            workspace_id=workspace_id,
            connection_id=source_connection_id,
            binding_id=binding_id,
            secret=_settings().jwt_secret,
        )
        invocation = ChatInvocationContext.channel(
            workspace_id=workspace_id,
            connection_id=source_connection_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            source_binding_id=binding_id,
            external_principal_fingerprint=fingerprint,
        )
        widget = None

    resolved = SimpleNamespace(
        grant=SimpleNamespace(id=grant_id),
        surface_binding=surface,
    )

    class _Db:
        @staticmethod
        def scalar(statement):
            rendered = str(statement)
            if "FROM mcp_tool_surface_bindings" in rendered:
                return surface
            if "FROM widget_instances" in rendered:
                return widget
            if "FROM widget_conversation_bindings" in rendered:
                return binding
            if "FROM channel_bindings" in rendered:
                return channel
            if "FROM channel_conversation_bindings" in rendered:
                return binding
            if "FROM app_connections" in rendered:
                return source_connection
            raise AssertionError(rendered)

    executor_module._recheck_surface_in_admission(
        _Db(),  # type: ignore[arg-type]
        resolved=resolved,  # type: ignore[arg-type]
        invocation=invocation,
        expert_id=expert_id,
        source_installation_id=source_installation_id,
        settings=_settings(),
    )

    if source == "widget":
        binding.session_id = str(uuid.uuid4())
    else:
        binding.external_sender_id = "sender-2"
    with pytest.raises(AppError) as changed:
        executor_module._recheck_surface_in_admission(
            _Db(),  # type: ignore[arg-type]
            resolved=resolved,  # type: ignore[arg-type]
            invocation=invocation,
            expert_id=expert_id,
            source_installation_id=source_installation_id,
            settings=_settings(),
        )
    assert changed.value.category == ErrorCategory.MCP_TOOL_NOT_GRANTED
