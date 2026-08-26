from __future__ import annotations

import asyncio
import importlib.metadata
import json
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.config import GatewaySettings
from gateway.main import create_app
import gateway.mcp_client as mcp_client_module
from gateway.mcp_client import McpGatewayError, McpGatewayService
from gateway.transport import GatewayTransportError, TransportResponse


PUBLIC_TEST_ADDRESS = "93.184.216.34"


class McpWireFixture:
    """Deterministic HTTP peer; the production side still uses the real SDK."""

    def __init__(
        self,
        *,
        legacy: bool = False,
        legacy_protocol_version: str = "2025-11-25",
        session_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_pages: dict[
            str | None, tuple[list[dict[str, Any]], str | None]
        ] | None = None,
        capabilities: dict[str, Any] | None = None,
        call_result: dict[str, Any] | None = None,
        call_failure: GatewayTransportError | None = None,
        call_status: int | None = None,
        sse_methods: set[str] | None = None,
    ) -> None:
        self.legacy = legacy
        self.legacy_protocol_version = legacy_protocol_version
        self.session_id = session_id
        self.tools = tools or [
            {
                "name": "echo",
                "description": "Echo text",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            }
        ]
        self.tool_pages = tool_pages
        self.capabilities = capabilities or {"tools": {}}
        self.call_result = call_result or {
            "content": [{"type": "text", "text": "fixture-result"}],
            "isError": False,
        }
        self.call_failure = call_failure
        self.call_status = call_status
        self.sse_methods = sse_methods or set()
        self.calls: list[dict[str, Any]] = []

    def send(self, **kwargs: Any) -> TransportResponse:
        method = str(kwargs["method"])
        headers = dict(kwargs["headers"])
        body = bytes(kwargs["body"])
        message = json.loads(body) if body else None
        self.calls.append({"method": method, "headers": headers, "message": message})

        if method == "DELETE":
            return TransportResponse(204, {}, b"")
        if method == "GET":
            return TransportResponse(405, {"content-type": "text/plain"}, b"")
        if not isinstance(message, dict):
            raise AssertionError("MCP POST must carry one JSON-RPC object")

        rpc_method = message.get("method")
        if "id" not in message:
            return TransportResponse(202, {}, b"")
        if rpc_method == "server/discover":
            if self.legacy:
                return self._error(message, -32601, "Method not found", status=404)
            result = {
                "supportedVersions": ["2026-07-28"],
                "capabilities": self.capabilities,
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": "modern-fixture",
                        "version": "1.0",
                    }
                },
            }
            return self._result(message, result)
        if rpc_method == "initialize":
            result = {
                "protocolVersion": self.legacy_protocol_version,
                "capabilities": self.capabilities,
                "serverInfo": {"name": "legacy-fixture", "version": "1.0"},
            }
            return self._result(message, result, session_id=self.session_id)
        if rpc_method == "tools/list":
            cursor = (message.get("params") or {}).get("cursor")
            page_tools, next_cursor = (
                self.tool_pages.get(cursor, ([], None))
                if self.tool_pages is not None
                else (self.tools, None)
            )
            return self._result(
                message,
                {
                    "tools": page_tools,
                    "nextCursor": next_cursor,
                    "ttlMs": 0,
                    "cacheScope": "private",
                    "resultType": "complete",
                },
            )
        if rpc_method == "tools/call":
            if self.call_failure is not None:
                raise self.call_failure
            if self.call_status is not None:
                return TransportResponse(
                    self.call_status,
                    {"location": "https://redirect.example.net/mcp"},
                    b"",
                )
            result = dict(self.call_result)
            result.setdefault("resultType", "complete")
            return self._result(message, result)
        raise AssertionError(f"unexpected MCP method: {rpc_method}")

    def _result(
        self,
        request: dict[str, Any],
        result: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> TransportResponse:
        headers = {"content-type": "application/json"}
        if session_id is not None:
            headers["mcp-session-id"] = session_id
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request["id"], "result": result}
        ).encode()
        if request.get("method") in self.sse_methods:
            headers["content-type"] = "text/event-stream"
            payload = b"event: message\ndata: " + payload + b"\n\n"
        return TransportResponse(200, headers, payload)

    @staticmethod
    def _error(
        request: dict[str, Any],
        code: int,
        message: str,
        *,
        status: int = 400,
    ) -> TransportResponse:
        return TransportResponse(
            status,
            {"content-type": "application/json"},
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {"code": code, "message": message},
                }
            ).encode(),
        )

    def rpc_methods(self) -> list[str]:
        return [
            str(call["message"].get("method"))
            for call in self.calls
            if isinstance(call["message"], dict)
        ]


class AuthFailureWireFixture(McpWireFixture):
    def __init__(self, *, status_code: int, challenge: str) -> None:
        super().__init__()
        self.auth_status_code = status_code
        self.auth_challenge = challenge

    def send(self, **kwargs: Any) -> TransportResponse:
        body = bytes(kwargs["body"])
        message = json.loads(body) if body else None
        if isinstance(message, dict) and message.get("method") == "tools/call":
            self.calls.append(
                {
                    "method": str(kwargs["method"]),
                    "headers": dict(kwargs["headers"]),
                    "message": message,
                }
            )
            return TransportResponse(
                self.auth_status_code,
                {
                    "content-type": "application/json",
                    "www-authenticate": self.auth_challenge,
                },
                b'{"error":"untrusted-upstream-body"}',
            )
        return super().send(**kwargs)


class _FixtureStream:
    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        body: bytes,
        *,
        hold_open: bool = False,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self._chunks = [body] if body else []
        self._hold_open = hold_open
        self._closed = threading.Event()

    def read_chunk(self) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        if self._hold_open:
            self._closed.wait(timeout=10)
        return b""

    def close(self) -> None:
        self._closed.set()


class StreamingAuthFailureWireFixture(AuthFailureWireFixture):
    """Exercise the SDK streaming transport's pre-body auth classifier."""

    def open_stream(self, **kwargs: Any) -> _FixtureStream:
        response = super().send(**kwargs)
        return _FixtureStream(
            response.status_code,
            response.headers,
            response.body,
        )


class _LiveSseFixtureStream(_FixtureStream):
    def __init__(self) -> None:
        super().__init__(200, {"content-type": "text/event-stream"}, b"")
        self._events: queue.Queue[bytes | None] = queue.Queue()
        self.push(b"event: endpoint\ndata: /messages?sessionId=legacy-fixture\n\n")

    def push(self, payload: bytes) -> None:
        self._events.put(payload)

    def read_chunk(self) -> bytes:
        event = self._events.get(timeout=10)
        return event or b""

    def close(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            self._events.put(None)


class LegacySseWireFixture(McpWireFixture):
    """Canonical 2024-11-05 GET-endpoint + POST-message transport."""

    def __init__(self) -> None:
        super().__init__(legacy=True, legacy_protocol_version="2024-11-05")
        self.sse_opened = False
        self.sse_stream: _LiveSseFixtureStream | None = None

    def open_stream(self, **kwargs: Any) -> _FixtureStream:
        method = str(kwargs["method"])
        target = kwargs["target"]
        if method == "GET":
            self.sse_opened = True
            self.calls.append(
                {
                    "method": method,
                    "headers": dict(kwargs["headers"]),
                    "message": None,
                    "url": target.canonical.url,
                }
            )
            self.sse_stream = _LiveSseFixtureStream()
            return self.sse_stream
        if method == "POST" and not self.sse_opened:
            body = bytes(kwargs["body"])
            self.calls.append(
                {
                    "method": method,
                    "headers": dict(kwargs["headers"]),
                    "message": json.loads(body),
                    "url": target.canonical.url,
                }
            )
            return _FixtureStream(
                405,
                {"content-type": "text/plain"},
                b"SSE endpoint accepts GET only",
            )
        response = super().send(**kwargs)
        self.calls[-1]["url"] = target.canonical.url
        if response.body:
            assert self.sse_stream is not None
            self.sse_stream.push(
                b"event: message\ndata: " + response.body + b"\n\n"
            )
        return _FixtureStream(
            202,
            {},
            b"",
        )


def _settings(**overrides: object) -> GatewaySettings:
    values: dict[str, object] = {
        "app_env": "test",
        "allow_private_egress": False,
        "max_request_bytes": 65_536,
        "max_response_bytes": 65_536,
        "max_discovered_tools": 512,
        "read_timeout_seconds": 2.0,
        "total_timeout_seconds": 3.0,
    }
    values.update(overrides)
    return GatewaySettings(**values)  # type: ignore[arg-type]


def _client(
    wire: McpWireFixture,
    *,
    settings: GatewaySettings | None = None,
) -> TestClient:
    config = settings or _settings()
    app = create_app(config)
    resolver: Callable[[str, int], tuple[str, ...]] = (
        lambda _host, _port: (PUBLIC_TEST_ADDRESS,)
    )
    app.state.mcp_service = McpGatewayService(config, wire, resolver)
    return TestClient(app)


def _request(operation: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "operation_id": f"test-{operation}",
        "operation": operation,
        "target_url": "https://mcp.example.com/rpc",
        "headers": {"Authorization": "Bearer ephemeral-secret"},
        "mode": "auto",
        "caller_binding": "a" * 64,
        "write": False,
    }
    value.update(overrides)
    return value


def test_gateway_is_pinned_to_the_reviewed_official_sdk() -> None:
    assert importlib.metadata.version("mcp") == "2.0.0"


def test_legacy_2024_uses_canonical_endpoint_event_sse_channel() -> None:
    wire = LegacySseWireFixture()
    with _client(wire) as client:
        discovered = client.post("/v1/mcp", json=_request("discover"))
        assert discovered.status_code == 200, discovered.text
        assert discovered.json()["negotiated_protocol_version"] == "2024-11-05"
        handle = discovered.json()["session_handle"]

        listing = client.post(
            "/v1/mcp",
            json=_request("tools_list", mode="legacy", session_handle=handle),
        )
        assert listing.status_code == 200, listing.text

        closed = client.post(
            "/v1/mcp",
            json={
                "operation_id": "close-sse",
                "operation": "session_close",
                "caller_binding": "a" * 64,
                "session_handle": handle,
                "mode": "legacy",
            },
        )
        assert closed.status_code == 200, closed.text

    get_index = next(
        index for index, call in enumerate(wire.calls) if call["method"] == "GET"
    )
    after_endpoint = wire.calls[get_index + 1 :]
    assert [
        call["message"].get("method")
        for call in after_endpoint
        if isinstance(call["message"], dict) and "id" in call["message"]
    ] == ["initialize", "tools/list"]
    assert all(
        str(call.get("url", "")).startswith(
            "https://mcp.example.com/messages?sessionId="
        )
        for call in after_endpoint
        if call["method"] == "POST"
    )


def test_sdk_mediates_modern_discover_list_and_call() -> None:
    discover_wire = McpWireFixture()
    discover = _client(discover_wire).post("/v1/mcp", json=_request("discover"))
    assert discover.status_code == 200, discover.text
    assert discover.json()["negotiated_protocol_version"] == "2026-07-28"
    assert discover.json()["session_mode"] == "modern"
    assert discover.json()["capabilities"] == {"tools": {}}
    assert discover_wire.rpc_methods() == ["server/discover"]

    list_wire = McpWireFixture()
    listing = _client(list_wire).post("/v1/mcp", json=_request("tools_list"))
    assert listing.status_code == 200, listing.text
    assert [tool["name"] for tool in listing.json()["tools"]] == ["echo"]
    assert list_wire.rpc_methods() == ["server/discover", "tools/list"]

    call_wire = McpWireFixture()
    called = _client(call_wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "hello"},
        ),
    )
    assert called.status_code == 200, called.text
    assert called.json()["result"]["content"][0]["text"] == "fixture-result"
    assert call_wire.rpc_methods() == ["server/discover", "tools/list", "tools/call"]
    tool_call = next(
        call["message"]
        for call in call_wire.calls
        if isinstance(call["message"], dict)
        and call["message"].get("method") == "tools/call"
    )
    assert tool_call["params"]["name"] == "echo"
    assert tool_call["params"]["arguments"] == {"text": "hello"}
    for call in call_wire.calls:
        message = call["message"]
        if not isinstance(message, dict) or "id" not in message:
            continue
        method = message["method"]
        assert call["headers"]["authorization"] == "Bearer ephemeral-secret"
        assert call["headers"]["mcp-protocol-version"] == "2026-07-28"
        assert call["headers"]["mcp-method"] == method
        assert message["params"]["_meta"][
            "io.modelcontextprotocol/protocolVersion"
        ] == "2026-07-28"
    tool_call_wire = next(
        call
        for call in call_wire.calls
        if isinstance(call["message"], dict)
        and call["message"].get("method") == "tools/call"
    )
    assert tool_call_wire["headers"]["mcp-name"] == "echo"


@pytest.mark.parametrize(
    ("status_code", "challenge", "expected_code"),
    [
        (
            401,
            'Bearer resource_metadata="https://secret.example/prm"',
            "mcp_auth_required",
        ),
        (
            403,
            'Bearer error="insufficient_scope", scope="secret:scope"',
            "mcp_insufficient_scope",
        ),
    ],
)
@pytest.mark.parametrize("streamed", [False, True])
def test_runtime_oauth_failures_are_safely_classified_without_challenge_leakage(
    status_code: int,
    challenge: str,
    expected_code: str,
    streamed: bool,
) -> None:
    fixture = StreamingAuthFailureWireFixture if streamed else AuthFailureWireFixture
    wire = fixture(
        status_code=status_code,
        challenge=challenge,
    )
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "hello"},
            write=True,
        ),
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == expected_code
    assert payload["error"]["outcome_unknown"] is False
    serialized = response.text
    assert "secret.example" not in serialized
    assert "secret:scope" not in serialized
    assert "untrusted-upstream-body" not in serialized


def test_plain_403_is_not_misclassified_as_insufficient_scope() -> None:
    wire = AuthFailureWireFixture(
        status_code=403,
        challenge='Bearer error="access_denied"',
    )
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "hello"},
            write=False,
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] != "mcp_insufficient_scope"


def test_sdk_owns_validated_mcp_parameter_headers() -> None:
    wire = McpWireFixture(
        tools=[
            {
                "name": "scoped",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tenant": {
                            "type": "string",
                            "x-mcp-header": "Tenant",
                        }
                    },
                },
            }
        ]
    )
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="scoped",
            arguments={"tenant": "acme"},
        ),
    )
    assert response.status_code == 200, response.text
    tool_call = next(
        call
        for call in wire.calls
        if isinstance(call["message"], dict)
        and call["message"].get("method") == "tools/call"
    )
    assert tool_call["headers"]["mcp-param-tenant"] == "acme"


def test_paginated_list_cursor_and_call_inventory_walk_use_sdk() -> None:
    first = [{"name": "first", "inputSchema": {"type": "object"}}]
    second = [{"name": "second", "inputSchema": {"type": "object"}}]
    pages = {None: (first, "page-2"), "page-2": (second, None)}

    first_wire = McpWireFixture(tool_pages=pages)
    first_response = _client(first_wire).post(
        "/v1/mcp", json=_request("tools_list")
    )
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["next_cursor"] == "page-2"
    assert [tool["name"] for tool in first_response.json()["tools"]] == ["first"]

    second_wire = McpWireFixture(tool_pages=pages)
    second_response = _client(second_wire).post(
        "/v1/mcp", json=_request("tools_list", cursor="page-2")
    )
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["next_cursor"] is None
    assert [tool["name"] for tool in second_response.json()["tools"]] == ["second"]
    second_list = next(
        call["message"]
        for call in second_wire.calls
        if isinstance(call["message"], dict)
        and call["message"].get("method") == "tools/list"
    )
    assert second_list["params"]["cursor"] == "page-2"

    call_wire = McpWireFixture(tool_pages=pages)
    called = _client(call_wire).post(
        "/v1/mcp",
        json=_request("tools_call", tool_name="second", arguments={}),
    )
    assert called.status_code == 200, called.text
    assert call_wire.rpc_methods() == [
        "server/discover",
        "tools/list",
        "tools/list",
        "tools/call",
    ]


def test_tool_lookup_has_a_hard_page_cap() -> None:
    pages = {
        None: ([], "page-1"),
        "page-1": ([], "page-2"),
        "page-2": ([], "page-3"),
    }
    wire = McpWireFixture(tool_pages=pages)
    response = _client(wire, settings=_settings(max_tool_pages=2)).post(
        "/v1/mcp",
        json=_request("tools_call", tool_name="never-present", arguments={}),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mcp_pagination_invalid"
    assert wire.rpc_methods() == ["server/discover", "tools/list", "tools/list"]


def test_sdk_parses_request_scoped_sse_results() -> None:
    list_wire = McpWireFixture(sse_methods={"tools/list"})
    listed = _client(list_wire).post("/v1/mcp", json=_request("tools_list"))
    assert listed.status_code == 200, listed.text
    assert listed.json()["tools"][0]["name"] == "echo"

    call_wire = McpWireFixture(sse_methods={"tools/call"})
    called = _client(call_wire).post(
        "/v1/mcp",
        json=_request("tools_call", tool_name="echo", arguments={}),
    )
    assert called.status_code == 200, called.text
    assert called.json()["result"]["content"][0]["text"] == "fixture-result"


def test_clean_eof_after_dispatched_write_is_outcome_unknown_without_retry() -> None:
    class CleanEofWire(McpWireFixture):
        def open_stream(self, **kwargs: Any) -> _FixtureStream:
            body = bytes(kwargs["body"])
            message = json.loads(body) if body else None
            if isinstance(message, dict) and message.get("method") == "tools/call":
                self.calls.append(
                    {
                        "method": str(kwargs["method"]),
                        "headers": dict(kwargs["headers"]),
                        "message": message,
                    }
                )
                return _FixtureStream(
                    200,
                    {"content-type": "text/event-stream"},
                    b"",
                )
            response = super().send(**kwargs)
            return _FixtureStream(
                response.status_code,
                response.headers,
                response.body,
            )

    wire = CleanEofWire()
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={},
            write=True,
        ),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "mcp_tool_outcome_unknown"
    assert wire.rpc_methods().count("tools/call") == 1


def test_write_requires_a_terminal_response_with_the_exact_request_id() -> None:
    class WrongResultIdWire(McpWireFixture):
        def send(self, **kwargs: Any) -> TransportResponse:
            body = bytes(kwargs["body"])
            request = json.loads(body) if body else None
            response = super().send(**kwargs)
            if isinstance(request, dict) and request.get("method") == "tools/call":
                payload = json.loads(response.body)
                payload["id"] = "unrelated-request-id"
                return TransportResponse(
                    response.status_code,
                    response.headers,
                    json.dumps(payload).encode(),
                )
            return response

    wire = WrongResultIdWire()
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "mutate"},
            write=True,
        ),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "mcp_tool_outcome_unknown"
    assert wire.rpc_methods().count("tools/call") == 1


def test_write_failure_before_transport_dispatch_is_retryable_not_ambiguous() -> None:
    wire = McpWireFixture(
        call_failure=GatewayTransportError(
            "upstream_unavailable",
            "fixture pre-dispatch failure",
            retryable=True,
            dispatch_started=False,
        )
    )
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={},
            write=True,
        ),
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "mcp_server_unreachable",
        "message": "The remote MCP server could not be reached safely.",
        "retryable": True,
        "outcome_unknown": False,
    }


@pytest.mark.parametrize(
    "advertised_endpoint",
    [
        "//attacker.example.net/messages?sessionId=stolen",
        "https://attacker.example.net/messages?sessionId=stolen",
    ],
)
def test_legacy_sse_rejects_untrusted_endpoint_before_credentialed_post(
    advertised_endpoint: str,
) -> None:
    class UntrustedEndpointWire(LegacySseWireFixture):
        def __init__(self) -> None:
            super().__init__()
            self.post_sse_targets: list[str] = []

        def open_stream(self, **kwargs: Any) -> _FixtureStream:
            method = str(kwargs["method"])
            target = kwargs["target"]
            if method == "GET":
                self.sse_opened = True
                self.calls.append(
                    {
                        "method": method,
                        "headers": dict(kwargs["headers"]),
                        "message": None,
                        "url": target.canonical.url,
                    }
                )
                return _FixtureStream(
                    200,
                    {"content-type": "text/event-stream"},
                    (
                        "event: endpoint\ndata: "
                        f"{advertised_endpoint}\n\n"
                    ).encode(),
                )
            if self.sse_opened and method == "POST":
                self.post_sse_targets.append(target.canonical.url)
            return super().open_stream(**kwargs)

    wire = UntrustedEndpointWire()
    response = _client(wire).post("/v1/mcp", json=_request("discover"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mcp_protocol_error"
    assert wire.post_sse_targets == []
    assert "ephemeral-secret" not in response.text


def test_legacy_sse_caps_each_endpoint_event_before_sdk_consumption() -> None:
    class OversizedEndpointWire(LegacySseWireFixture):
        def open_stream(self, **kwargs: Any) -> _FixtureStream:
            if str(kwargs["method"]) == "GET":
                self.sse_opened = True
                return _FixtureStream(
                    200,
                    {"content-type": "text/event-stream"},
                    b"event: endpoint\ndata: /" + (b"x" * 1_024) + b"\n\n",
                )
            return super().open_stream(**kwargs)

    response = _client(
        OversizedEndpointWire(),
        settings=_settings(max_response_bytes=512),
    ).post("/v1/mcp", json=_request("discover"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mcp_response_too_large"


@pytest.mark.parametrize(
    "header",
    [
        "MCP-Protocol-Version",
        "Mcp-Session-Id",
        "Mcp-Method",
        "Mcp-Name",
        "Mcp-Param-Secret",
        "Last-Event-ID",
    ],
)
def test_caller_cannot_override_sdk_protocol_headers(header: str) -> None:
    wire = McpWireFixture()
    response = _client(wire).post(
        "/v1/mcp",
        json=_request("discover", headers={header: "attacker-controlled"}),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert wire.calls == []


def test_mcp_ephemeral_header_count_is_bounded_before_wire_dispatch() -> None:
    wire = McpWireFixture()
    headers = {f"X-Tenant-{index}": "x" for index in range(9)}
    response = _client(wire, settings=_settings(max_headers=8)).post(
        "/v1/mcp",
        json=_request("discover", headers=headers),
    )
    # The outer ASGI header count is independent; this is the credential map
    # carried inside the bounded JSON operation.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mcp_request_headers_too_large"
    assert wire.calls == []


def test_mcp_private_resolution_is_a_safe_403_before_wire_dispatch() -> None:
    wire = McpWireFixture()
    config = _settings()
    app = create_app(config)
    app.state.mcp_service = McpGatewayService(
        config,
        wire,
        lambda _host, _port: ("127.0.0.1",),
    )
    response = TestClient(app).post("/v1/mcp", json=_request("discover"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "egress_target_blocked"
    assert "ephemeral-secret" not in response.text
    assert wire.calls == []


def test_slow_dns_is_deadline_bounded_without_blocking_the_event_loop() -> None:
    def slow_resolver(_host: str, _port: int) -> tuple[str, ...]:
        time.sleep(0.2)
        return (PUBLIC_TEST_ADDRESS,)

    async def scenario() -> None:
        config = _settings(
            connect_timeout_seconds=0.05,
            total_timeout_seconds=0.1,
        )
        service = McpGatewayService(config, McpWireFixture(), slow_resolver)
        request = mcp_client_module.McpOperationRequest.model_validate(
            _request("discover")
        )
        task = asyncio.create_task(service.execute(request))
        started = time.monotonic()
        await asyncio.sleep(0.01)
        assert time.monotonic() - started < 0.05
        with pytest.raises(McpGatewayError) as raised:
            await task
        assert raised.value.code == "mcp_server_unreachable"
        await service.close_all()

    asyncio.run(scenario())


def test_expired_absolute_write_budget_fails_before_any_sdk_dispatch() -> None:
    wire = McpWireFixture()
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={},
            write=True,
            deadline_seconds=5.0,
            deadline_unix_ms=int((time.time() - 0.1) * 1_000),
        ),
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "mcp_operation_timeout",
        "message": "The MCP operation exceeded its total deadline.",
        "retryable": True,
        "outcome_unknown": False,
    }
    assert wire.calls == []


def test_legacy_capacity_is_reserved_before_upstream_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_start(_owner) -> str:
        started.set()
        await release.wait()
        return "2025-11-25"

    monkeypatch.setattr(mcp_client_module._SessionOwner, "start", blocked_start)

    async def scenario() -> None:
        service = McpGatewayService(
            _settings(max_legacy_sessions=1),
            McpWireFixture(legacy=True),
            lambda _host, _port: (PUBLIC_TEST_ADDRESS,),
        )
        request = mcp_client_module.McpOperationRequest.model_validate(
            _request("discover", mode="legacy")
        )
        first = asyncio.create_task(service.execute(request))
        await started.wait()
        with pytest.raises(McpGatewayError) as raised:
            await service.execute(request)
        assert raised.value.code == "mcp_session_capacity"
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        assert service._pending_legacy_sessions == 0

    asyncio.run(scenario())


def test_cached_write_cannot_dispatch_after_its_session_lock_deadline() -> None:
    async def scenario() -> None:
        wire = McpWireFixture(legacy=True, session_id="deadline-session")
        service = McpGatewayService(
            _settings(total_timeout_seconds=1.0),
            wire,
            lambda _host, _port: (PUBLIC_TEST_ADDRESS,),
        )
        discovered = await service.execute(
            mcp_client_module.McpOperationRequest.model_validate(
                _request("discover", mode="legacy", deadline_seconds=1.0)
            )
        )
        assert discovered.session_handle is not None
        entry = service._sessions[discovered.session_handle]
        lock_held = asyncio.Event()
        release_lock = asyncio.Event()

        async def holder() -> None:
            async with entry.lock:
                lock_held.set()
                await release_lock.wait()

        holder_task = asyncio.create_task(holder())
        await lock_held.wait()
        before = list(wire.rpc_methods())
        try:
            with pytest.raises(McpGatewayError) as raised:
                await service.execute(
                    mcp_client_module.McpOperationRequest.model_validate(
                        _request(
                            "tools_call",
                            mode="legacy",
                            session_handle=discovered.session_handle,
                            tool_name="echo",
                            arguments={},
                            write=True,
                            deadline_seconds=0.03,
                        )
                    )
                )
            assert raised.value.code == "mcp_operation_timeout"
            assert raised.value.outcome_unknown is False
            assert wire.rpc_methods() == before
        finally:
            release_lock.set()
            await holder_task
            await service.close_all()

    asyncio.run(scenario())


def test_ambiguous_legacy_session_is_removed_before_a_waiter_can_dispatch() -> None:
    entered_write = threading.Event()
    release_write = threading.Event()

    class BlockingAmbiguousWrite(McpWireFixture):
        def send(self, **kwargs: Any) -> TransportResponse:
            body = bytes(kwargs["body"])
            message = json.loads(body) if body else None
            if isinstance(message, dict) and message.get("method") == "tools/call":
                self.calls.append(
                    {
                        "method": str(kwargs["method"]),
                        "headers": dict(kwargs["headers"]),
                        "message": message,
                    }
                )
                entered_write.set()
                release_write.wait(timeout=2)
                raise GatewayTransportError(
                    "upstream_unavailable",
                    "lost write acknowledgement",
                    retryable=True,
                    dispatch_started=True,
                )
            return super().send(**kwargs)

    async def scenario() -> None:
        wire = BlockingAmbiguousWrite(
            legacy=True,
            session_id="ambiguous-session",
        )
        service = McpGatewayService(
            _settings(total_timeout_seconds=2.0),
            wire,
            lambda _host, _port: (PUBLIC_TEST_ADDRESS,),
        )
        discovered = await service.execute(
            mcp_client_module.McpOperationRequest.model_validate(
                _request("discover", mode="legacy", deadline_seconds=2.0)
            )
        )
        handle = discovered.session_handle
        assert handle is not None
        write_request = mcp_client_module.McpOperationRequest.model_validate(
            _request(
                "tools_call",
                mode="legacy",
                session_handle=handle,
                tool_name="echo",
                arguments={},
                write=True,
                deadline_seconds=2.0,
            )
        )
        waiting_request = mcp_client_module.McpOperationRequest.model_validate(
            _request(
                "tools_list",
                mode="legacy",
                session_handle=handle,
                deadline_seconds=2.0,
            )
        )
        first = asyncio.create_task(service.execute(write_request))
        await asyncio.to_thread(entered_write.wait, 1)
        second = asyncio.create_task(service.execute(waiting_request))
        await asyncio.sleep(0.01)
        release_write.set()
        with pytest.raises(McpGatewayError) as first_error:
            await first
        with pytest.raises(McpGatewayError) as second_error:
            await second
        assert first_error.value.code == "mcp_tool_outcome_unknown"
        assert second_error.value.code == "mcp_session_not_found"
        # One list is the first call's bounded tool lookup. The waiter never
        # reaches the SDK after the ambiguous session is removed.
        assert wire.rpc_methods().count("tools/list") == 1
        assert handle not in service._sessions
        await service.close_all()

    asyncio.run(scenario())


def test_legacy_session_absolute_expiry_is_not_slid_by_activity() -> None:
    async def scenario() -> None:
        wire = McpWireFixture(legacy=True, session_id="absolute-session")
        service = McpGatewayService(
            _settings(legacy_session_ttl_seconds=5),
            wire,
            lambda _host, _port: (PUBLIC_TEST_ADDRESS,),
        )
        discovered = await service.execute(
            mcp_client_module.McpOperationRequest.model_validate(
                _request("discover", mode="legacy")
            )
        )
        handle = discovered.session_handle
        assert handle is not None
        absolute_expiry = service._sessions[handle].expires_at
        await service.execute(
            mcp_client_module.McpOperationRequest.model_validate(
                _request("tools_list", mode="legacy", session_handle=handle)
            )
        )
        assert service._sessions[handle].expires_at == absolute_expiry
        await service.close_all()

    asyncio.run(scenario())


def test_mcp_dns_resolution_uses_one_process_wide_bounded_pool_and_recovers() -> None:
    active = 0
    peak = 0
    state_lock = threading.Lock()

    def resolver(_host: str, _port: int) -> tuple[str, ...]:
        nonlocal active, peak
        with state_lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.04)
            return (PUBLIC_TEST_ADDRESS,)
        finally:
            with state_lock:
                active -= 1

    async def one_discovery(index: int) -> None:
        service = McpGatewayService(
            _settings(
                connect_timeout_seconds=1.0,
                total_timeout_seconds=2.0,
            ),
            McpWireFixture(),
            resolver,
        )
        request = mcp_client_module.McpOperationRequest.model_validate(
            _request(
                "discover",
                operation_id=f"dns-{index}",
                mode="auto",
                deadline_seconds=2.0,
            )
        )
        result = await service.execute(request)
        assert result.negotiated_protocol_version == "2026-07-28"
        await service.close_all()

    async def scenario() -> None:
        await asyncio.gather(*(one_discovery(index) for index in range(16)))
        assert 1 < peak <= 8
        # A completed wave must return capacity to the same global executor.
        await one_discovery(99)
        assert active == 0

    asyncio.run(scenario())


def test_legacy_session_header_is_used_and_session_is_terminated() -> None:
    wire = McpWireFixture(legacy=True, session_id="fixture-session-id")
    with _client(wire) as client:
        discovered = client.post(
            "/v1/mcp",
            json=_request("discover", mode="legacy"),
        )
        assert discovered.status_code == 200, discovered.text
        handle = discovered.json()["session_handle"]
        assert handle

        response = client.post(
            "/v1/mcp",
            json=_request("tools_list", mode="legacy", session_handle=handle),
        )
        assert response.status_code == 200, response.text
        assert response.json()["negotiated_protocol_version"] == "2025-11-25"
        assert response.json()["session_mode"] == "legacy"
        assert response.json()["session_handle"] == handle

        closed = client.post(
            "/v1/mcp",
            json={
                "operation_id": "close-legacy",
                "operation": "session_close",
                "caller_binding": "a" * 64,
                "session_handle": handle,
                "mode": "legacy",
            },
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["closed"] is True

    session_calls = [
        call
        for call in wire.calls
        if call["method"] in {"POST", "GET", "DELETE"}
        and call["message"] is not None
        and isinstance(call["message"], dict)
        and call["message"].get("method") != "initialize"
    ]
    assert any(
        call["headers"].get("mcp-session-id") == "fixture-session-id"
        for call in session_calls
    )
    delete_calls = [call for call in wire.calls if call["method"] == "DELETE"]
    assert len(delete_calls) == 1
    assert delete_calls[0]["headers"]["mcp-session-id"] == "fixture-session-id"
    assert wire.rpc_methods().count("initialize") == 1


def test_auto_fallback_owns_streamable_2025_legacy_revision() -> None:
    protocol = "2025-11-25"
    wire = McpWireFixture(
        legacy=True,
        legacy_protocol_version=protocol,
        session_id=f"session-{protocol}",
    )
    with _client(wire) as client:
        discovered = client.post("/v1/mcp", json=_request("discover", mode="auto"))
        assert discovered.status_code == 200, discovered.text
        assert discovered.json()["negotiated_protocol_version"] == protocol
        handle = discovered.json()["session_handle"]
        assert handle
        assert wire.rpc_methods()[:3] == [
            "server/discover",
            "initialize",
            "notifications/initialized",
        ]
        closed = client.post(
            "/v1/mcp",
            json={
                "operation_id": "close-auto-fallback",
                "operation": "session_close",
                "caller_binding": "a" * 64,
                "session_handle": handle,
                "mode": "legacy",
            },
        )
        assert closed.status_code == 200


def test_legacy_handle_binding_target_and_expiry_fail_before_tool_dispatch() -> None:
    missing_wire = McpWireFixture(legacy=True)
    missing = _client(missing_wire).post(
        "/v1/mcp",
        json=_request(
            "tools_list",
            mode="legacy",
            session_handle="x" * 43,
        ),
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "mcp_session_not_found"
    assert missing_wire.calls == []

    wire = McpWireFixture(legacy=True, session_id="bound-session")
    with _client(wire) as client:
        discovered = client.post(
            "/v1/mcp", json=_request("discover", mode="legacy")
        )
        assert discovered.status_code == 200
        handle = discovered.json()["session_handle"]
        before = list(wire.rpc_methods())

        wrong_caller = client.post(
            "/v1/mcp",
            json=_request(
                "tools_list",
                mode="legacy",
                session_handle=handle,
                caller_binding="b" * 64,
            ),
        )
        assert wrong_caller.status_code == 422
        assert wrong_caller.json()["error"]["code"] == "mcp_session_binding_mismatch"

        wrong_target = client.post(
            "/v1/mcp",
            json=_request(
                "tools_list",
                mode="legacy",
                session_handle=handle,
                target_url="https://other.example.net/mcp",
            ),
        )
        assert wrong_target.status_code == 422
        assert wrong_target.json()["error"]["code"] == "mcp_session_target_mismatch"
        assert wire.rpc_methods() == before

        client.post(
            "/v1/mcp",
            json={
                "operation_id": "close-bound",
                "operation": "session_close",
                "caller_binding": "a" * 64,
                "session_handle": handle,
                "mode": "legacy",
            },
        )

    expired_wire = McpWireFixture(legacy=True, session_id="expired-session")
    with _client(
        expired_wire,
        settings=_settings(legacy_session_ttl_seconds=0),
    ) as client:
        discovered = client.post(
            "/v1/mcp", json=_request("discover", mode="legacy")
        )
        assert discovered.status_code == 200
        handle = discovered.json()["session_handle"]
        before = list(expired_wire.rpc_methods())
        expired = client.post(
            "/v1/mcp",
            json=_request("tools_list", mode="legacy", session_handle=handle),
        )
        assert expired.status_code == 422
        assert expired.json()["error"]["code"] == "mcp_session_not_found"
        assert "tools/list" not in expired_wire.rpc_methods()[len(before) :]


def test_tool_inventory_and_argument_caps_fail_closed() -> None:
    tools = [
        {"name": f"tool-{index}", "inputSchema": {"type": "object"}}
        for index in range(3)
    ]
    wire = McpWireFixture(tools=tools)
    too_many = _client(wire, settings=_settings(max_discovered_tools=2)).post(
        "/v1/mcp",
        json=_request("tools_list"),
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "mcp_tool_inventory_too_large"

    untouched_wire = McpWireFixture()
    oversized = _client(
        untouched_wire,
        settings=_settings(max_request_bytes=64),
    ).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "x" * 128},
        ),
    )
    assert oversized.status_code == 422
    assert oversized.json()["error"]["code"] == "mcp_arguments_too_large"
    assert untouched_wire.calls == []


def test_write_transport_failure_is_not_retried_and_is_marked_unknown() -> None:
    wire = McpWireFixture(
        call_failure=GatewayTransportError(
            "upstream_unavailable",
            "fixture failure",
            retryable=True,
            dispatch_started=True,
        )
    )
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "mutate"},
            write=True,
        ),
    )
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "mcp_tool_outcome_unknown",
        "message": "The write may have reached the remote service; it will not be retried.",
        "retryable": False,
        "outcome_unknown": True,
    }
    assert wire.rpc_methods().count("tools/call") == 1


def test_read_transport_failure_is_retryable_but_never_replayed_by_gateway() -> None:
    wire = McpWireFixture(
        call_failure=GatewayTransportError(
            "upstream_unavailable",
            "fixture failure",
            retryable=True,
            dispatch_started=True,
        )
    )
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={},
            write=False,
        ),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "mcp_server_unreachable"
    assert response.json()["error"]["retryable"] is True
    assert response.json()["error"]["outcome_unknown"] is False
    assert wire.rpc_methods().count("tools/call") == 1


def test_write_redirect_is_not_followed_and_is_marked_unknown() -> None:
    wire = McpWireFixture(call_status=307)
    response = _client(wire).post(
        "/v1/mcp",
        json=_request(
            "tools_call",
            tool_name="echo",
            arguments={"text": "mutate"},
            write=True,
        ),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "mcp_tool_outcome_unknown"
    assert response.json()["error"]["outcome_unknown"] is True
    assert wire.rpc_methods().count("tools/call") == 1


def test_task_and_interactive_result_paths_are_rejected() -> None:
    task_wire = McpWireFixture(capabilities={"tools": {}, "tasks": {}})
    task_response = _client(task_wire).post(
        "/v1/mcp",
        json=_request("tools_call", tool_name="echo", arguments={}),
    )
    assert task_response.status_code == 422
    assert task_response.json()["error"]["code"] == "mcp_tool_incompatible"
    assert "tools/call" not in task_wire.rpc_methods()

    input_wire = McpWireFixture(
        call_result={
            "resultType": "input_required",
            "inputRequests": {
                "request-1": {
                    "method": "elicitation/create",
                    "params": {
                        "mode": "form",
                        "message": "fixture",
                        "requestedSchema": {"type": "object", "properties": {}},
                    },
                }
            },
            "requestState": "opaque-state",
        }
    )
    input_response = _client(input_wire).post(
        "/v1/mcp",
        json=_request("tools_call", tool_name="echo", arguments={}),
    )
    assert input_response.status_code == 422
    assert input_response.json()["error"]["code"] == "mcp_tool_result_unsupported"
    assert input_wire.rpc_methods().count("tools/call") == 1
