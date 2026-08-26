from __future__ import annotations

import base64
import io
import logging
import ssl
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.common.outbound_http import OutboundTargetBlocked, resolve_outbound_target
from gateway.config import GatewaySettings
import gateway.main as gateway_main
from gateway.main import create_app
from gateway.models import OutboundOperationRequest
from gateway.service import BoundedOutboundExecutor
from gateway.transport import (
    GatewayTransportError,
    PinnedHttpTransport,
    StreamingTransportResponse,
    TransportResponse,
)


class FakeTransport:
    def __init__(self, responses: list[TransportResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def send(self, **kwargs: object) -> TransportResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeStreamingConnection:
    def __init__(self) -> None:
        self.closed = False
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def close(self) -> None:
        self.closed = True


class FakeHttpResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.closed = False

    def read1(self, _size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def close(self) -> None:
        self.closed = True


def _settings(**overrides: object) -> GatewaySettings:
    values: dict[str, object] = {
        "app_env": "test",
        "allow_private_egress": False,
        "max_redirects": 3,
        "max_request_bytes": 32,
        "max_response_bytes": 64,
    }
    values.update(overrides)
    return GatewaySettings(**values)  # type: ignore[arg-type]


def test_executor_uses_the_policy_returned_pinned_address() -> None:
    transport = FakeTransport([TransportResponse(200, {"content-type": "text/plain"}, b"ok")])
    resolutions: list[tuple[str, int]] = []

    def resolver(host: str, port: int) -> tuple[str, ...]:
        resolutions.append((host, port))
        return ("93.184.216.34",)

    executor = BoundedOutboundExecutor(_settings(), transport, resolver)
    response = executor.execute(
        OutboundOperationRequest(
            operation_id="op-1",
            method="POST",
            url="https://tools.example.com/mcp",
            headers={"Authorization": "Bearer top-secret"},
            body_base64=base64.b64encode(b"{}").decode(),
        )
    )

    assert response.status_code == 200
    assert base64.b64decode(response.body_base64) == b"ok"
    assert resolutions == [("tools.example.com", 443)]
    sent_target = transport.calls[0]["target"]
    assert sent_target.connect_address == "93.184.216.34"  # type: ignore[union-attr]


def test_target_preflight_resolves_without_connecting_or_exposing_target() -> None:
    transport = FakeTransport([])
    executor = BoundedOutboundExecutor(
        _settings(),
        transport,
        lambda _host, _port: ("93.184.216.34",),
    )

    digest = executor.validate_target("https://tools.example.com/mcp")

    assert len(digest) == 64
    assert digest.isascii() and digest.isalnum()
    assert transport.calls == []


def test_target_preflight_forwards_only_the_remaining_caller_budget() -> None:
    class RecordingExecutor:
        deadline_seconds: float | None = None

        def validate_target(
            self,
            _target_url: str,
            *,
            deadline_seconds: float | None = None,
        ) -> str:
            self.deadline_seconds = deadline_seconds
            return "b" * 64

    executor = RecordingExecutor()
    app = create_app(_settings(total_timeout_seconds=5.0))
    app.state.executor = executor

    response = TestClient(app).post(
        "/v1/target-validation",
        json={
            "operation_id": "caller-budget",
            "target_url": "https://tools.example.com/mcp",
            "caller_binding": "a" * 64,
            "deadline_seconds": 0.5,
        },
    )

    assert response.status_code == 200
    assert executor.deadline_seconds is not None
    assert 0 < executor.deadline_seconds <= 0.5


def test_expired_ingress_budget_fails_before_resolution() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/target-validation",
            "headers": [],
        }
    )
    request.state.gateway_received_at = time.monotonic() - 1.0

    with pytest.raises(GatewayTransportError) as raised:
        gateway_main._remaining_caller_budget(
            request,
            supplied_seconds=0.1,
            maximum_seconds=5.0,
        )

    assert raised.value.code == "operation_timeout"


def test_expired_absolute_budget_charges_pre_asgi_transit() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/target-validation",
            "headers": [],
        }
    )
    request.state.gateway_received_at = time.monotonic()

    with pytest.raises(GatewayTransportError) as raised:
        gateway_main._remaining_caller_budget(
            request,
            supplied_seconds=5.0,
            deadline_unix_ms=int((time.time() - 0.1) * 1_000),
            maximum_seconds=5.0,
        )

    assert raised.value.code == "operation_timeout"


def test_target_preflight_blocks_dns_private_and_metadata_without_leaking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(_settings())
    app.state.executor = BoundedOutboundExecutor(
        _settings(),
        FakeTransport([]),
        lambda _host, _port: ("10.22.0.7",),
    )
    client = TestClient(app)
    caller_binding = "a" * 64

    with caplog.at_level(logging.INFO, logger="geem.egress_gateway"):
        private = client.post(
            "/v1/target-validation",
            json={
                "operation_id": "validate-private",
                "target_url": "https://tenant-tools.example.com/mcp",
                "caller_binding": caller_binding,
            },
        )
        metadata = client.post(
            "/v1/target-validation",
            json={
                "operation_id": "validate-metadata",
                "target_url": "https://metadata.google.internal/latest",
                "caller_binding": caller_binding,
            },
        )

    assert private.status_code == 403
    assert metadata.status_code == 403
    combined = private.text + metadata.text + caplog.text
    assert "tenant-tools.example.com" not in combined
    assert "metadata.google.internal" not in combined
    assert "10.22.0.7" not in combined


def test_preflight_does_not_create_a_rebinding_bypass() -> None:
    answers = iter((("93.184.216.34",), ("10.0.0.9",)))
    transport = FakeTransport([])
    executor = BoundedOutboundExecutor(
        _settings(),
        transport,
        lambda _host, _port: next(answers),
    )

    assert len(executor.validate_target("https://tools.example.com/mcp")) == 64
    with pytest.raises(OutboundTargetBlocked):
        executor.execute(
            OutboundOperationRequest(
                operation_id="rebind-after-preflight",
                method="POST",
                url="https://tools.example.com/mcp",
            )
        )
    assert transport.calls == []


def test_target_preflight_schema_cannot_accept_auth_or_body() -> None:
    response = TestClient(create_app(_settings())).post(
        "/v1/target-validation",
        json={
            "operation_id": "validate-extra",
            "target_url": "https://tools.example.com/mcp",
            "caller_binding": "a" * 64,
            "headers": {"Authorization": "Bearer must-not-be-accepted"},
            "body": "must-not-be-accepted",
        },
    )
    assert response.status_code == 400
    assert "must-not-be-accepted" not in response.text


def test_neutral_dns_timeout_never_dispatches_after_the_caller_fails() -> None:
    transport = FakeTransport([])

    def slow_resolver(_host: str, _port: int) -> tuple[str, ...]:
        time.sleep(0.15)
        return ("93.184.216.34",)

    executor = BoundedOutboundExecutor(
        _settings(total_timeout_seconds=0.05),
        transport,
        slow_resolver,
    )
    with pytest.raises(GatewayTransportError) as raised:
        executor.execute(
            OutboundOperationRequest(
                operation_id="dns-timeout",
                method="POST",
                url="https://tools.example.com/token",
            )
        )
    assert raised.value.code == "operation_timeout"
    time.sleep(0.16)
    assert transport.calls == []


def test_proxy_connect_authority_and_host_are_the_same_pinned_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SocketFixture:
        def __init__(self) -> None:
            self.sent = bytearray()

        def settimeout(self, _value: float) -> None:
            pass

        def sendall(self, value: bytes) -> None:
            self.sent.extend(value)

        def close(self) -> None:
            pass

    class ProxyResponseFixture:
        status = 200

        def __init__(self, _socket) -> None:
            self.fp = io.BytesIO()

        def begin(self) -> None:
            pass

        def close(self) -> None:
            pass

    connection = SocketFixture()
    monkeypatch.setattr(
        "gateway.transport.socket.create_connection",
        lambda *_args, **_kwargs: connection,
    )
    monkeypatch.setattr(
        "gateway.transport.http.client.HTTPResponse",
        ProxyResponseFixture,
    )
    settings = _settings(forward_proxy_url="http://proxy.internal:3128")
    target = resolve_outbound_target(
        "https://tenant.example.com/mcp",
        resolver=lambda _host, _port: ("93.184.216.34",),
    )
    opened = PinnedHttpTransport(settings)._open_socket(
        target,
        deadline=time.monotonic() + 3,
    )
    assert opened is connection
    assert bytes(connection.sent).startswith(
        b"CONNECT 93.184.216.34:443 HTTP/1.1\r\n"
        b"Host: 93.184.216.34:443\r\n"
    )
    assert b"tenant.example.com" not in connection.sent


def test_cross_origin_redirect_is_revalidated_and_strips_every_secret_header() -> None:
    transport = FakeTransport(
        [
            TransportResponse(
                302,
                {"location": "https://other.example.net/final"},
                b"",
            ),
            TransportResponse(200, {"content-type": "application/json"}, b"{}"),
        ]
    )

    executor = BoundedOutboundExecutor(
        _settings(),
        transport,
        lambda _host, _port: ("93.184.216.34",),
    )
    response = executor.execute(
        OutboundOperationRequest(
            operation_id="redirect-1",
            method="GET",
            url="https://tools.example.com/start",
            headers={
                "Authorization": "Bearer top-secret",
                "X-Static-Secret": "also-secret",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
    )

    assert response.redirects_followed == 1
    assert transport.calls[0]["headers"] == {
        "Authorization": "Bearer top-secret",
        "X-Static-Secret": "also-secret",
        "Accept": "application/json",
    }
    assert transport.calls[1]["headers"] == {"Accept": "application/json"}


def test_write_redirect_following_is_structurally_rejected() -> None:
    with pytest.raises(ValidationError):
        OutboundOperationRequest(
            operation_id="write-1",
            method="POST",
            url="https://tools.example.com/mcp",
            follow_redirects=True,
        )


def test_deployed_gateway_rejects_unreviewed_https_ports_before_dispatch() -> None:
    transport = FakeTransport([])
    executor = BoundedOutboundExecutor(
        _settings(app_env="production"),
        transport,
        lambda _host, _port: ("93.184.216.34",),
    )
    with pytest.raises(OutboundTargetBlocked) as raised:
        executor.execute(
            OutboundOperationRequest(
                operation_id="port-1",
                method="GET",
                url="https://tools.example.com:8443/mcp",
            )
        )
    assert raised.value.code == "port_blocked"
    assert transport.calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "internal"},
        {"Cookie": "session=secret"},
        {"Connection": "keep-alive"},
        {"X-Test": "safe\r\nAuthorization: injected"},
    ],
)
def test_hop_by_hop_cookie_and_crlf_headers_are_rejected(headers: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        OutboundOperationRequest(
            operation_id="headers-1",
            method="GET",
            url="https://tools.example.com",
            headers=headers,
        )


def test_request_body_cap_is_applied_after_strict_base64_decode() -> None:
    request = OutboundOperationRequest(
        operation_id="body-1",
        method="POST",
        url="https://tools.example.com",
        body_base64=base64.b64encode(b"x" * 33).decode(),
    )
    executor = BoundedOutboundExecutor(
        _settings(max_request_bytes=32),
        FakeTransport([]),
        lambda _host, _port: ("93.184.216.34",),
    )
    with pytest.raises(Exception, match="request body is invalid"):
        executor.execute(request)


def test_validation_response_and_logs_never_echo_secret_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(_settings())

    class BlockingExecutor:
        def execute(self, _request: OutboundOperationRequest) -> None:
            raise OutboundTargetBlocked("private_target", "Private targets are blocked.")

    app.state.executor = BlockingExecutor()
    secret = "Bearer this-must-never-appear"
    with caplog.at_level(logging.INFO, logger="geem.egress_gateway"):
        response = TestClient(app).post(
            "/v1/outbound",
            json={
                "operation_id": "blocked-1",
                "method": "GET",
                "url": "https://tools.example.com",
                "headers": {"Authorization": secret},
            },
        )
    assert response.status_code == 403
    assert secret not in response.text
    assert secret not in caplog.text
    assert "tools.example.com" not in caplog.text


def test_dispatched_neutral_post_failure_is_outcome_unknown() -> None:
    app = create_app(_settings())

    class AmbiguousExecutor:
        def execute(self, _request: OutboundOperationRequest) -> None:
            raise GatewayTransportError(
                "upstream_unavailable",
                "The upstream failed after dispatch.",
                retryable=True,
                dispatch_started=True,
            )

    app.state.executor = AmbiguousExecutor()
    response = TestClient(app).post(
        "/v1/outbound",
        json={
            "operation_id": "ambiguous-post",
            "method": "POST",
            "url": "https://tools.example.com/token",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "outbound_outcome_unknown",
        "message": "The non-idempotent outbound operation may have been dispatched.",
        "retryable": False,
        "outcome_unknown": True,
    }


def test_neutral_post_redirect_is_outcome_unknown_and_not_followed() -> None:
    transport = FakeTransport(
        [
            TransportResponse(
                307,
                {"location": "https://other.example.net/token"},
                b"",
            )
        ]
    )
    app = create_app(_settings())
    app.state.executor = BoundedOutboundExecutor(
        _settings(),
        transport,
        lambda _host, _port: ("93.184.216.34",),
    )
    response = TestClient(app).post(
        "/v1/outbound",
        json={
            "operation_id": "ambiguous-redirect",
            "method": "POST",
            "url": "https://tools.example.com/token",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["outcome_unknown"] is True
    assert len(transport.calls) == 1


def test_nonlocal_gateway_requires_proxy_and_mtls_files(tmp_path) -> None:
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    ca = tmp_path / "ca.crt"
    for path in (cert, key, ca):
        path.write_text("fixture")

    settings = _settings(
        app_env="production",
        server_cert_file=str(cert),
        server_key_file=str(key),
        client_ca_file=str(ca),
        forward_proxy_url="",
    )
    with pytest.raises(RuntimeError, match="EGRESS_FORWARD_PROXY_URL"):
        settings.validate_runtime()


def test_private_mode_is_rejected_outside_local(tmp_path) -> None:
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    ca = tmp_path / "ca.crt"
    for path in (cert, key, ca):
        path.write_text("fixture")
    settings = _settings(
        app_env="production",
        allow_private_egress=True,
        server_cert_file=str(cert),
        server_key_file=str(key),
        client_ca_file=str(ca),
        forward_proxy_url="http://mcp-egress-proxy:3128",
    )
    with pytest.raises(RuntimeError, match="only be enabled"):
        settings.validate_runtime()


def test_gateway_defaults_to_fail_closed_production(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    assert GatewaySettings.from_env().app_env == "production"


def test_gateway_default_response_budget_supports_large_tool_inventories(
    monkeypatch,
) -> None:
    monkeypatch.delenv("EGRESS_MAX_RESPONSE_BYTES", raising=False)

    assert GatewaySettings.from_env().max_response_bytes == 262_144


@pytest.mark.parametrize(
    "proxy_url",
    [
        "http://proxy.invalid:not-a-port",
        "http://proxy.invalid:3128/path",
        "http://proxy.invalid:3128?secret=value",
    ],
)
def test_proxy_origin_is_strictly_validated(tmp_path, proxy_url: str) -> None:
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    ca = tmp_path / "ca.crt"
    for path in (cert, key, ca):
        path.write_text("fixture")
    settings = _settings(
        app_env="production",
        server_cert_file=str(cert),
        server_key_file=str(key),
        client_ca_file=str(ca),
        forward_proxy_url=proxy_url,
    )
    with pytest.raises(RuntimeError, match="EGRESS_FORWARD_PROXY_URL"):
        settings.validate_runtime()


def test_streaming_response_yields_incrementally_and_enforces_total_cap() -> None:
    connection = FakeStreamingConnection()
    response = FakeHttpResponse([b"ab", b"cd", b""])
    stream = StreamingTransportResponse(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        response=response,  # type: ignore[arg-type]
        connection=connection,  # type: ignore[arg-type]
        settings=_settings(max_response_bytes=4),
        deadline=time.monotonic() + 3,
    )
    assert stream.read_chunk() == b"ab"
    assert stream.read_chunk() == b"cd"
    assert stream.read_chunk() == b""
    assert response.closed is True
    assert connection.closed is True

    capped = StreamingTransportResponse(
        status_code=200,
        headers={},
        response=FakeHttpResponse([b"abc", b"de"]),  # type: ignore[arg-type]
        connection=FakeStreamingConnection(),  # type: ignore[arg-type]
        settings=_settings(max_response_bytes=4),
        deadline=time.monotonic() + 3,
    )
    assert capped.read_chunk() == b"abc"
    with pytest.raises(GatewayTransportError) as raised:
        capped.read_chunk()
    assert raised.value.code == "upstream_response_too_large"
    assert raised.value.dispatch_started is True


def test_validated_sse_session_uses_per_message_transport_bounds() -> None:
    settings = _settings(
        max_response_bytes=4,
        read_timeout_seconds=0.5,
        legacy_session_ttl_seconds=30,
    )
    connection = FakeStreamingConnection()
    stream = StreamingTransportResponse(
        status_code=200,
        headers={"content-type": "text/event-stream; charset=utf-8"},
        response=FakeHttpResponse([b"abc", b"def", b""]),  # type: ignore[arg-type]
        connection=connection,  # type: ignore[arg-type]
        settings=settings,
        deadline=time.monotonic() + 0.5,
    )
    stream.activate_sse_session(absolute_deadline=time.monotonic() + 3)

    # More than the ordinary cumulative body cap is valid across separately
    # framed events. The MCP SSE parser owns the aggregate-per-event bound.
    assert stream.read_chunk() == b"abc"
    assert stream.read_chunk() == b"def"
    assert connection.timeouts[-1] > settings.read_timeout_seconds

    oversized = StreamingTransportResponse(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        response=FakeHttpResponse([b"abcde"]),  # type: ignore[arg-type]
        connection=FakeStreamingConnection(),  # type: ignore[arg-type]
        settings=settings,
        deadline=time.monotonic() + 1,
    )
    oversized.activate_sse_session(absolute_deadline=time.monotonic() + 3)
    with pytest.raises(GatewayTransportError) as raised:
        oversized.read_chunk()
    assert raised.value.code == "upstream_response_too_large"


def test_response_headers_are_bounded_while_read_from_the_socket() -> None:
    class CountingFile(io.BytesIO):
        def __init__(self, payload: bytes) -> None:
            super().__init__(payload)
            self.returned = 0
            self.requested: list[int] = []

        def readline(self, size: int = -1) -> bytes:
            self.requested.append(size)
            value = super().readline(size)
            self.returned += len(value)
            return value

    class HeaderSocket:
        def __init__(self, payload: bytes) -> None:
            self.file = CountingFile(payload)
            self.buffering: int | None = None

        def makefile(self, _mode: str, buffering: int = -1):
            self.buffering = buffering
            return self.file

    settings = _settings(max_header_bytes=128, max_headers=8)
    sock = HeaderSocket(
        b"HTTP/1.1 200 OK\r\nX-Attacker: " + (b"x" * 4_096) + b"\r\n\r\n"
    )
    transport = PinnedHttpTransport(settings)
    response = transport._response(sock)  # type: ignore[arg-type]

    with pytest.raises(GatewayTransportError) as raised:
        transport._begin_response(response)

    assert raised.value.code == "upstream_headers_too_large"
    # One sentinel byte is sufficient to prove overflow; neither the parser
    # nor its underlying buffer may pull the hostile multi-KiB line.
    assert sock.file.returned <= settings.max_header_bytes + 1
    assert max(sock.file.requested) <= settings.max_header_bytes + 1
    assert sock.buffering == settings.max_header_bytes + 1
    response.close()


def test_production_listener_requires_verified_client_certificate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    ca = tmp_path / "client-ca.crt"
    for path in (cert, key, ca):
        path.write_text("fixture")
    settings = _settings(
        app_env="production",
        server_cert_file=str(cert),
        server_key_file=str(key),
        client_ca_file=str(ca),
        forward_proxy_url="http://mcp-egress-proxy:3128",
    )
    monkeypatch.setattr(
        gateway_main.GatewaySettings,
        "from_env",
        classmethod(lambda _cls: settings),
    )
    captured: dict[str, object] = {}

    def fake_run(_app, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(gateway_main.uvicorn, "run", fake_run)
    gateway_main.run()

    assert captured["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert captured["ssl_certfile"] == str(cert)
    assert captured["ssl_keyfile"] == str(key)
    assert captured["ssl_ca_certs"] == str(ca)
    assert captured["access_log"] is False
    assert captured["proxy_headers"] is False


def test_http_envelope_is_rejected_before_parsing_or_secret_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(_settings(max_request_bytes=32))
    secret = "never-log-this-" + ("x" * 40_000)
    with caplog.at_level(logging.INFO, logger="geem.egress_gateway"):
        response = TestClient(app).post(
            "/v1/mcp",
            json={
                "operation_id": "oversized-envelope",
                "operation": "tools_call",
                "target_url": "https://tools.example.com/mcp",
                "caller_binding": "a" * 64,
                "tool_name": "echo",
                "arguments": {"value": secret},
            },
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert "never-log-this" not in response.text
    assert "never-log-this" not in caplog.text


def test_http_header_count_is_rejected_before_parsing() -> None:
    app = create_app(_settings(max_headers=8))
    headers = {f"X-Filler-{index}": "x" for index in range(12)}
    response = TestClient(app).post(
        "/v1/mcp",
        headers=headers,
        json={"not": "parsed"},
    )
    assert response.status_code == 431
    assert response.json()["error"]["code"] == "request_headers_too_large"


def test_json_nesting_is_rejected_before_pydantic_parsing() -> None:
    app = create_app(_settings(max_request_bytes=65_536))
    nested = (b'{"value":' * 70) + b"null" + (b"}" * 70)
    response = TestClient(app).post(
        "/v1/mcp",
        content=nested,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "nesting limit" in response.json()["error"]["message"]


def test_dependency_loggers_are_fully_suppressed() -> None:
    create_app(_settings())
    for namespace in ("mcp", "mcp_types", "httpx2", "httpx", "httpcore"):
        dependency_logger = logging.getLogger(namespace)
        assert dependency_logger.disabled is True
        assert dependency_logger.propagate is False
