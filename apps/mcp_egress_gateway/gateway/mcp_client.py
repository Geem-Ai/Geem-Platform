"""Official-SDK MCP facade over the validated pinned-address transport."""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import hashlib
import hmac
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import anyio
import httpx2
from mcp import types
from mcp.client import Client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from app.common.outbound_http import (
    AddressResolver,
    OutboundTargetBlocked,
    canonicalize_outbound_url,
    resolve_outbound_target,
)

from .config import GatewaySettings
from .models import McpOperationRequest, McpOperationResponse
from .transport import (
    GatewayTransportError,
    PinnedHttpTransport,
    StreamingTransportResponse,
)


class McpGatewayError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


class _LegacySseRequired(RuntimeError):
    """The peer selected the revision whose canonical transport is HTTP+SSE."""


_MCP_DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="mcp-egress-dns",
)
_RPC_ID_MISSING = object()


@dataclass(slots=True)
class _WriteOutcomeTracker:
    """Track the one actual JSON-RPC mutation, not surrounding SDK requests."""

    expected_id: str | None = None
    submitted_to_transport: bool = False
    dispatch_started: bool = False
    terminal_confirmed: bool = False

    def reset(self) -> None:
        self.expected_id = None
        self.submitted_to_transport = False
        self.dispatch_started = False
        self.terminal_confirmed = False

    @property
    def is_write_request(self) -> bool:
        return self.expected_id is not None

    @property
    def outcome_may_be_unknown(self) -> bool:
        return (
            self.is_write_request
            and (self.submitted_to_transport or self.dispatch_started)
            and not self.terminal_confirmed
        )


class _SseFrameGuard:
    """Incrementally bound SSE events and validate legacy endpoint frames.

    Frames are withheld from the SDK until their terminating blank line has
    been seen and validated.  That makes the endpoint event an authorization
    boundary: no credential-bearing POST can be issued to an unreviewed URL.
    """

    def __init__(
        self,
        *,
        max_message_bytes: int,
        target_url: str,
        settings: GatewaySettings,
        validate_endpoint: bool,
    ) -> None:
        self.max_message_bytes = max_message_bytes
        self.target_url = target_url
        self.settings = settings
        self.validate_endpoint = validate_endpoint
        self._buffer = bytearray()
        self._event_lines: list[bytes] = []
        self._event_bytes = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            boundary = self._next_line_boundary()
            if boundary is None:
                if self._event_bytes + len(self._buffer) > self.max_message_bytes:
                    raise _sse_too_large()
                break
            index, width = boundary
            line = bytes(self._buffer[:index])
            del self._buffer[: index + width]
            self._event_bytes += len(line) + width
            if self._event_bytes > self.max_message_bytes:
                raise _sse_too_large()
            if line:
                self._event_lines.append(line)
                continue
            frames.append(self._finish_event())
        return frames

    def finish(self) -> None:
        # An EOF in the middle of a frame is never released to the SDK.  For a
        # write this consequently remains unconfirmed; for a persistent stream
        # the caller reports the unexpected EOF as a session failure.
        if self._event_bytes + len(self._buffer) > self.max_message_bytes:
            raise _sse_too_large()

    def _next_line_boundary(self) -> tuple[int, int] | None:
        for index, value in enumerate(self._buffer):
            if value == 0x0A:  # LF
                return index, 1
            if value == 0x0D:  # CR or CRLF
                if index + 1 == len(self._buffer):
                    return None
                return index, 2 if self._buffer[index + 1] == 0x0A else 1
        return None

    def _finish_event(self) -> bytes:
        lines, self._event_lines = self._event_lines, []
        self._event_bytes = 0
        event_name = "message"
        data_lines: list[bytes] = []
        for line in lines:
            if line.startswith(b":"):
                continue
            field, separator, raw_value = line.partition(b":")
            value = raw_value[1:] if separator and raw_value.startswith(b" ") else raw_value
            if field == b"event":
                try:
                    event_name = value.decode("utf-8", "strict")
                except UnicodeDecodeError as exc:
                    raise _sse_protocol_error() from exc
            elif field == b"data":
                data_lines.append(value)
        data_size = sum(len(value) for value in data_lines) + max(
            0, len(data_lines) - 1
        )
        if data_size > self.max_message_bytes:
            raise _sse_too_large()
        if self.validate_endpoint and event_name == "endpoint":
            self._validate_endpoint(b"\n".join(data_lines))
        return b"\n".join(lines) + b"\n\n"

    def _validate_endpoint(self, raw_value: bytes) -> None:
        try:
            endpoint = raw_value.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise _sse_protocol_error() from exc
        if not endpoint or endpoint.startswith("//"):
            raise _sse_protocol_error()
        candidate_url = urljoin(self.target_url, endpoint)
        allow_private = self.settings.is_local and self.settings.allow_private_egress
        try:
            base = canonicalize_outbound_url(
                self.target_url,
                allow_http=allow_private,
                allow_private_hostnames=allow_private,
            )
            candidate = canonicalize_outbound_url(
                candidate_url,
                allow_http=allow_private,
                allow_private_hostnames=allow_private,
            )
        except OutboundTargetBlocked as exc:
            raise _sse_protocol_error() from exc
        if (
            base.scheme != candidate.scheme
            or base.host != candidate.host
            or base.port != candidate.port
        ):
            raise _sse_protocol_error()


def _sse_too_large() -> McpGatewayError:
    return McpGatewayError(
        "mcp_response_too_large",
        "The MCP event stream contains an oversized event.",
    )


def _sse_protocol_error() -> McpGatewayError:
    return McpGatewayError(
        "mcp_protocol_error",
        "The legacy MCP event stream advertised an invalid endpoint.",
    )


class _SdkAsyncResponseStream(httpx2.AsyncByteStream):
    def __init__(
        self,
        stream: StreamingTransportResponse,
        *,
        expected_write_id: str | None,
        content_type: str,
        report_fatal: Any,
        confirm_terminal: Any,
        target_url: str,
        settings: GatewaySettings,
        persistent_sse: bool,
    ) -> None:
        self.stream = stream
        self.expected_write_id = expected_write_id
        self.content_type = content_type
        self.report_fatal = report_fatal
        self.confirm_terminal = confirm_terminal
        self.persistent_sse = persistent_sse
        self._payload = bytearray()
        self._closed = False
        self._sse_guard = (
            _SseFrameGuard(
                max_message_bytes=settings.max_response_bytes,
                target_url=target_url,
                settings=settings,
                validate_endpoint=persistent_sse,
            )
            if _is_event_stream_content_type(content_type)
            else None
        )

    async def __aiter__(self):
        try:
            while chunk := await anyio.to_thread.run_sync(
                self.stream.read_chunk,
                abandon_on_cancel=True,
            ):
                output_chunks = (
                    self._sse_guard.feed(chunk) if self._sse_guard is not None else [chunk]
                )
                for output in output_chunks:
                    if self.expected_write_id is not None:
                        self._payload.extend(output)
                    yield output
            if self._sse_guard is not None:
                self._sse_guard.finish()
            if self.persistent_sse:
                error = McpGatewayError(
                    "mcp_server_unreachable",
                    "The legacy MCP event stream ended unexpectedly.",
                    retryable=True,
                )
                self.report_fatal(error)
                raise error
            self._verify_write_completion()
        except GatewayTransportError as exc:
            mapped = _map_transport_error(
                exc,
                ambiguous_write=(
                    self.expected_write_id is not None and exc.dispatch_started
                ),
            )
            self.report_fatal(mapped)
            raise mapped from exc
        except McpGatewayError as exc:
            self.report_fatal(exc)
            raise

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await anyio.to_thread.run_sync(self.stream.close)
        self._verify_write_completion()

    def _verify_write_completion(self) -> None:
        if self.expected_write_id is None:
            return
        if _has_terminal_rpc_response(
            bytes(self._payload),
            self.content_type,
            expected_id=self.expected_write_id,
        ):
            self.confirm_terminal()
            return
        error = McpGatewayError(
            "mcp_tool_outcome_unknown",
            "The write response ended before a validated terminal result.",
            outcome_unknown=True,
        )
        self.report_fatal(error)
        raise error


class _SdkPinnedAsyncTransport(httpx2.AsyncBaseTransport):
    """Bridge SDK requests to the one-shot pinned transport without retries."""

    def __init__(
        self,
        *,
        settings: GatewaySettings,
        wire_transport: PinnedHttpTransport,
        write_call: bool,
        operation_deadline: float,
        session_deadline: float,
        target_url: str,
        resolver: AddressResolver | None = None,
    ) -> None:
        self.settings = settings
        self.wire_transport = wire_transport
        self.write_call = write_call
        self.target_url = target_url
        self.resolver = resolver
        self.fatal_error: asyncio.Future[BaseException] = (
            asyncio.get_running_loop().create_future()
        )
        self.operation_deadline = operation_deadline
        self.session_deadline = session_deadline
        self.write_outcome = _WriteOutcomeTracker()

    def begin_operation(self, deadline: float, *, write_call: bool) -> float:
        self.operation_deadline = deadline
        self.write_call = write_call
        self.write_outcome.reset()
        return deadline

    def operation_timeout_error(self) -> McpGatewayError:
        if self.write_outcome.outcome_may_be_unknown:
            return McpGatewayError(
                "mcp_tool_outcome_unknown",
                "The write may have reached the remote service; it will not be retried.",
                outcome_unknown=True,
            )
        return McpGatewayError(
            "mcp_operation_timeout",
            "The MCP operation exceeded its total deadline.",
            retryable=True,
        )

    def _confirm_write_terminal(self) -> None:
        self.write_outcome.terminal_confirmed = True

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            return await self._handle_async_request(request)
        except BaseException as exc:
            if request.method == "POST":
                self._report_fatal(exc)
            raise

    async def _handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self._validate_request_origin(str(request.url))
        body = await request.aread()
        if len(body) > self.settings.max_request_bytes:
            raise McpGatewayError(
                "mcp_request_too_large", "The MCP request exceeds the configured limit."
            )
        rpc_method, rpc_id = _jsonrpc_request_identity(body)
        ambiguous_write = self.write_call and rpc_method == "tools/call"
        if ambiguous_write:
            # An invalid/missing request ID can never be safely matched to a
            # result, so retain a non-null impossible marker and fail unknown
            # after dispatch rather than accepting an unrelated response.
            self.write_outcome.expected_id = rpc_id or "invalid:"
        headers = _sdk_request_headers(request.headers, self.settings.max_header_bytes)
        kwargs: dict[str, object] = {}
        if self.resolver is not None:
            kwargs["resolver"] = self.resolver
        remaining = self.operation_deadline - time.monotonic()
        if remaining <= 0:
            raise McpGatewayError(
                "mcp_operation_timeout",
                "The MCP operation exceeded its total deadline.",
                retryable=True,
            )
        resolution = _MCP_DNS_EXECUTOR.submit(
            functools.partial(
                resolve_outbound_target,
                str(request.url),
                allow_http=(
                    self.settings.is_local and self.settings.allow_private_egress
                ),
                allow_private_egress=(
                    self.settings.is_local and self.settings.allow_private_egress
                ),
                deployment_networks=self.settings.deployment_networks,
                **kwargs,  # type: ignore[arg-type]
            )
        )
        try:
            target = await asyncio.wait_for(
                asyncio.wrap_future(resolution),
                timeout=min(self.settings.connect_timeout_seconds, remaining),
            )
        except TimeoutError as exc:
            resolution.cancel()
            raise McpGatewayError(
                "mcp_server_unreachable",
                "The remote MCP host could not be resolved within the deadline.",
                retryable=True,
            ) from exc
        if not self.settings.is_local and target.canonical.port != 443:
            raise OutboundTargetBlocked(
                "port_blocked",
                "Only the reviewed public HTTPS port is allowed.",
            )
        # Every handshake, SDK request, and termination attempt consumes the
        # same caller budget. A successful persistent SSE GET transitions to
        # its separately bounded session lifetime only after headers validate.
        deadline = self.operation_deadline
        if deadline <= time.monotonic():
            raise self.operation_timeout_error()
        try:
            open_stream = getattr(self.wire_transport, "open_stream", None)
            if callable(open_stream):
                if ambiguous_write:
                    self.write_outcome.submitted_to_transport = True
                streamed = await anyio.to_thread.run_sync(
                    functools.partial(
                        open_stream,
                        target=target,
                        method=request.method,
                        headers=headers,
                        body=body,
                        deadline=deadline,
                    )
                )
                if ambiguous_write:
                    self.write_outcome.dispatch_started = True
                auth_error = _mcp_auth_error_code(
                    streamed.status_code, streamed.headers
                )
                if auth_error is not None:
                    await anyio.to_thread.run_sync(streamed.close)
                    raise McpGatewayError(
                        auth_error,
                        "The remote MCP server requires renewed authorization.",
                    )
                if ambiguous_write and 300 <= streamed.status_code < 400:
                    await anyio.to_thread.run_sync(streamed.close)
                    raise McpGatewayError(
                        "mcp_tool_outcome_unknown",
                        "A write redirect is outcome-ambiguous and will not be followed.",
                        outcome_unknown=True,
                    )
                persistent_sse = (
                    request.method == "GET"
                    and streamed.status_code == 200
                    and _is_event_stream_content_type(
                        streamed.headers.get("content-type", "")
                    )
                )
                if persistent_sse:
                    activate_sse = getattr(streamed, "activate_sse_session", None)
                    if callable(activate_sse):
                        await anyio.to_thread.run_sync(
                            functools.partial(
                                activate_sse,
                                absolute_deadline=self.session_deadline,
                            )
                        )
                return httpx2.Response(
                    streamed.status_code,
                    headers=streamed.headers,
                    stream=_SdkAsyncResponseStream(
                        streamed,
                        expected_write_id=(
                            self.write_outcome.expected_id if ambiguous_write else None
                        ),
                        content_type=streamed.headers.get("content-type", ""),
                        report_fatal=self._report_fatal,
                        confirm_terminal=self._confirm_write_terminal,
                        target_url=self.target_url,
                        settings=self.settings,
                        persistent_sse=persistent_sse,
                    ),
                    request=request,
                )
            if ambiguous_write:
                self.write_outcome.submitted_to_transport = True
            response = await anyio.to_thread.run_sync(
                functools.partial(
                    self.wire_transport.send,
                    target=target,
                    method=request.method,
                    headers=headers,
                    body=body,
                    deadline=deadline,
                )
            )
            if ambiguous_write:
                self.write_outcome.dispatch_started = True
        except GatewayTransportError as exc:
            if ambiguous_write:
                self.write_outcome.dispatch_started = exc.dispatch_started
                if not exc.dispatch_started:
                    self.write_outcome.submitted_to_transport = False
            raise _map_transport_error(
                exc,
                ambiguous_write=ambiguous_write and exc.dispatch_started,
            ) from exc
        auth_error = _mcp_auth_error_code(response.status_code, response.headers)
        if auth_error is not None:
            raise McpGatewayError(
                auth_error,
                "The remote MCP server requires renewed authorization.",
            )
        if ambiguous_write and 300 <= response.status_code < 400:
            raise McpGatewayError(
                "mcp_tool_outcome_unknown",
                "A write redirect is outcome-ambiguous and will not be followed.",
                outcome_unknown=True,
            )
        if ambiguous_write:
            if not _has_terminal_rpc_response(
                response.body,
                response.headers.get("content-type", ""),
                expected_id=self.write_outcome.expected_id or "invalid:",
            ):
                raise McpGatewayError(
                    "mcp_tool_outcome_unknown",
                    "The write response ended before a matching terminal result.",
                    outcome_unknown=True,
                )
            self._confirm_write_terminal()
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            content=response.body,
            request=request,
        )

    def _report_fatal(self, exc: BaseException) -> None:
        if not self.fatal_error.done():
            self.fatal_error.set_result(exc)

    def _validate_request_origin(self, raw_url: str) -> None:
        allow_private = self.settings.is_local and self.settings.allow_private_egress
        base = canonicalize_outbound_url(
            self.target_url,
            allow_http=allow_private,
            allow_private_hostnames=allow_private,
        )
        candidate = canonicalize_outbound_url(
            raw_url,
            allow_http=allow_private,
            allow_private_hostnames=allow_private,
        )
        if (
            base.scheme != candidate.scheme
            or base.host != candidate.host
            or base.port != candidate.port
        ):
            raise McpGatewayError(
                "mcp_protocol_error",
                "The MCP SDK attempted a cross-origin protocol request.",
            )


@dataclass(slots=True)
class _McpConnection:
    settings: GatewaySettings
    target_url: str
    mode: str
    wire_transport: PinnedHttpTransport
    resolver: AddressResolver | None
    write_call: bool
    operation_deadline: float
    session_deadline: float
    pinned: _SdkPinnedAsyncTransport | None = field(init=False, default=None)
    http_client: httpx2.AsyncClient | None = field(init=False, default=None)
    client: Client | None = field(init=False, default=None)
    _ephemeral_header_names: set[str] = field(init=False, default_factory=set)
    _closed: bool = field(init=False, default=False)

    async def open(self, headers: dict[str, str]) -> None:
        transport_kinds = (
            ("streamable", "sse")
            if self.mode in {"auto", "legacy"}
            else ("streamable",)
        )
        last_error: BaseException | None = None
        for index, transport_kind in enumerate(transport_kinds):
            try:
                await self._open_transport(headers, transport_kind=transport_kind)
                return
            except BaseException as exc:
                last_error = exc
                self.client = None
                self.http_client = None
                self.pinned = None
                self._ephemeral_header_names.clear()
                if index + 1 >= len(transport_kinds) or not _is_legacy_fallback_error(
                    exc
                ):
                    raise
        assert last_error is not None
        raise last_error

    async def _open_transport(
        self,
        headers: dict[str, str],
        *,
        transport_kind: str,
    ) -> None:
        pinned = _SdkPinnedAsyncTransport(
            settings=self.settings,
            wire_transport=self.wire_transport,
            write_call=self.write_call,
            operation_deadline=self.operation_deadline,
            session_deadline=self.session_deadline,
            target_url=self.target_url,
            resolver=self.resolver,
        )
        self.pinned = pinned

        @asynccontextmanager
        async def sdk_transport():
            if transport_kind == "streamable":
                http_client = httpx2.AsyncClient(
                    transport=pinned,
                    follow_redirects=False,
                    trust_env=False,
                    headers=headers,
                )
                self.http_client = http_client
                self._ephemeral_header_names = {
                    name.lower() for name in headers
                }
                async with http_client:
                    async with streamable_http_client(
                        self.target_url,
                        http_client=http_client,
                        terminate_on_close=True,
                    ) as streams:
                        yield streams
                return

            def httpx_client_factory(
                *,
                headers: dict[str, object] | None = None,
                auth: httpx2.Auth | None = None,
                timeout: httpx2.Timeout | float | None = None,
            ) -> httpx2.AsyncClient:
                http_client = httpx2.AsyncClient(
                    transport=pinned,
                    follow_redirects=False,
                    trust_env=False,
                    headers=headers,
                    auth=auth,
                    timeout=timeout,
                )
                self.http_client = http_client
                self._ephemeral_header_names = {
                    name.lower() for name in (headers or {})
                }
                return http_client

            async with sse_client(
                self.target_url,
                headers=headers,
                timeout=self.settings.total_timeout_seconds,
                sse_read_timeout=float(self.settings.legacy_session_ttl_seconds),
                httpx_client_factory=httpx_client_factory,
            ) as streams:
                yield streams

        client = Client(
            sdk_transport(),
            mode=(
                "legacy" if transport_kind == "sse" else self.mode
            ),  # type: ignore[arg-type]
            read_timeout_seconds=self.settings.read_timeout_seconds,
            cache=None,
        )
        self.client = client
        enter_task = asyncio.create_task(client.__aenter__())
        done, _pending = await asyncio.wait(
            {enter_task, pinned.fatal_error},
            return_when=asyncio.FIRST_COMPLETED,
            timeout=max(0.0, self.operation_deadline - time.monotonic()),
        )
        if pinned.fatal_error in done:
            fatal = pinned.fatal_error.result()
            enter_task.cancel()
            await asyncio.gather(enter_task, return_exceptions=True)
            raise fatal
        if enter_task not in done:
            enter_task.cancel()
            await asyncio.gather(enter_task, return_exceptions=True)
            raise pinned.operation_timeout_error()
        enter_task.result()
        protocol = _negotiated_protocol(client)
        if transport_kind == "streamable" and protocol == "2024-11-05":
            await client.__aexit__(None, None, None)
            self.client = None
            raise _LegacySseRequired()
        if transport_kind == "sse" and protocol != "2024-11-05":
            await client.__aexit__(None, None, None)
            self.client = None
            raise McpGatewayError(
                "mcp_protocol_unsupported",
                "The negotiated legacy revision does not match HTTP+SSE.",
            )

    def replace_ephemeral_headers(self, headers: dict[str, str]) -> None:
        if self.http_client is None:
            raise RuntimeError("MCP connection is not open")
        for name in self._ephemeral_header_names:
            self.http_client.headers.pop(name, None)
        self.http_client.headers.update(headers)
        self._ephemeral_header_names = {name.lower() for name in headers}

    def prepare_operation(
        self,
        headers: dict[str, str],
        *,
        write_call: bool,
        deadline: float,
    ) -> float:
        self.replace_ephemeral_headers(headers)
        if self.pinned is None:
            raise RuntimeError("MCP connection is not open")
        return self.pinned.begin_operation(deadline, write_call=write_call)

    def operation_timeout_error(self) -> McpGatewayError:
        if self.pinned is not None:
            return self.pinned.operation_timeout_error()
        return McpGatewayError(
            "mcp_operation_timeout",
            "The MCP operation exceeded its total deadline.",
            retryable=True,
        )

    async def close(self) -> BaseException | None:
        if self._closed:
            return None
        self._closed = True
        client, self.client = self.client, None
        self.http_client = None
        close_error: BaseException | None = None
        if client is not None:
            try:
                remaining = max(0.001, self.operation_deadline - time.monotonic())
                await asyncio.wait_for(
                    client.__aexit__(None, None, None),
                    timeout=min(
                        2.0,
                        self.settings.read_timeout_seconds,
                        remaining,
                    ),
                )
            except BaseException as exc:
                close_error = exc
        return close_error


@dataclass(slots=True)
class _OwnerCommand:
    request: McpOperationRequest
    arguments: dict[str, object]
    future: asyncio.Future[McpOperationResponse]
    cancel_event: asyncio.Event
    deadline: float


@dataclass(slots=True)
class _SessionOwner:
    """Keep one SDK context inside one task for its entire lifetime."""

    service: "McpGatewayService"
    connection: _McpConnection
    initial_headers: dict[str, str]
    initial_deadline: float
    queue: asyncio.Queue[_OwnerCommand | None] = field(
        init=False, default_factory=asyncio.Queue
    )
    task: asyncio.Task[None] | None = field(init=False, default=None)
    ready: asyncio.Future[str] | None = field(init=False, default=None)
    poisoned: bool = field(init=False, default=False)

    async def start(self) -> str:
        loop = asyncio.get_running_loop()
        self.ready = loop.create_future()
        self.task = loop.create_task(self._run(), name="mcp-legacy-session-owner")
        remaining = _remaining_operation_seconds(self.initial_deadline)
        try:
            return await asyncio.wait_for(self.ready, remaining)
        except TimeoutError as exc:
            self.poisoned = True
            if self.task is not None:
                self.task.cancel()
            raise self.connection.operation_timeout_error() from exc

    async def execute(
        self,
        request: McpOperationRequest,
        arguments: dict[str, object],
        deadline: float,
    ) -> McpOperationResponse:
        if self.task is None or self.task.done():
            raise _missing_session()
        future: asyncio.Future[McpOperationResponse] = (
            asyncio.get_running_loop().create_future()
        )
        cancel_event = asyncio.Event()
        _remaining_operation_seconds(deadline)
        await self.queue.put(
            _OwnerCommand(request, arguments, future, cancel_event, deadline)
        )
        try:
            return await asyncio.wait_for(
                asyncio.shield(future),
                _remaining_operation_seconds(deadline),
            )
        except TimeoutError as exc:
            cancel_event.set()
            future.cancel()
            error = self.connection.operation_timeout_error()
            if error.outcome_unknown:
                self.poisoned = True
            raise error from exc
        except asyncio.CancelledError:
            cancel_event.set()
            future.cancel()
            raise

    async def close(self, *, deadline: float | None = None) -> None:
        if self.task is None:
            return
        if deadline is not None:
            self.connection.operation_deadline = deadline
            if self.connection.pinned is not None:
                self.connection.pinned.operation_deadline = deadline
        if not self.task.done():
            await self.queue.put(None)
        try:
            await self.task
        except BaseException:
            pass

    def client(self) -> Client:
        return _open_client(self.connection)

    async def _run(self) -> None:
        fatal: BaseException | None = None
        current: _OwnerCommand | None = None
        try:
            await asyncio.wait_for(
                self.connection.open(self.initial_headers),
                timeout=_remaining_operation_seconds(self.initial_deadline),
            )
            protocol = _negotiated_protocol(self.client())
            self.service._validate_protocol(protocol)
            assert self.ready is not None
            self.ready.set_result(protocol)
            while True:
                current = await self.queue.get()
                if current is None:
                    break
                try:
                    if current.cancel_event.is_set():
                        current = None
                        continue
                    _remaining_operation_seconds(current.deadline)
                    operation_deadline = self.connection.prepare_operation(
                        current.request.headers,
                        write_call=current.request.write,
                        deadline=current.deadline,
                    )
                    if current.cancel_event.is_set():
                        current = None
                        continue
                    operation_task = asyncio.create_task(
                        self.service._perform(
                            current.request,
                            current.arguments,
                            self.client(),
                            protocol,
                        )
                    )
                    cancellation_task = asyncio.create_task(
                        current.cancel_event.wait()
                    )
                    assert self.connection.pinned is not None
                    done, _pending = await asyncio.wait(
                        {
                            operation_task,
                            self.connection.pinned.fatal_error,
                            cancellation_task,
                        },
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=max(0.0, operation_deadline - time.monotonic()),
                    )
                    if not done:
                        operation_task.cancel()
                        cancellation_task.cancel()
                        await asyncio.gather(
                            operation_task,
                            cancellation_task,
                            return_exceptions=True,
                        )
                        timeout_error = self.connection.operation_timeout_error()
                        if not current.future.done():
                            current.future.set_exception(timeout_error)
                        current = None
                        self.poisoned = True
                        fatal = timeout_error
                        break
                    if self.connection.pinned.fatal_error in done:
                        transport_error = self.connection.pinned.fatal_error.result()
                        operation_task.cancel()
                        cancellation_task.cancel()
                        await asyncio.gather(operation_task, return_exceptions=True)
                        await asyncio.gather(cancellation_task, return_exceptions=True)
                        if not current.future.done():
                            current.future.set_exception(transport_error)
                        current = None
                        self.poisoned = True
                        fatal = transport_error
                        break
                    if cancellation_task in done:
                        operation_task.cancel()
                        await asyncio.gather(operation_task, return_exceptions=True)
                        cancellation_error = self.connection.operation_timeout_error()
                        if cancellation_error.outcome_unknown:
                            self.poisoned = True
                            fatal = cancellation_error
                            current = None
                            break
                        current = None
                        continue
                    cancellation_task.cancel()
                    await asyncio.gather(cancellation_task, return_exceptions=True)
                    result = operation_task.result()
                except Exception as exc:
                    fatal_transport = (
                        self.connection.pinned.fatal_error.result()
                        if self.connection.pinned is not None
                        and self.connection.pinned.fatal_error.done()
                        else None
                    )
                    effective_error = fatal_transport or exc
                    if not current.future.done():
                        current.future.set_exception(effective_error)
                    if (
                        isinstance(exc, McpGatewayError)
                        and exc.outcome_unknown
                    ) or fatal_transport is not None:
                        self.poisoned = True
                        fatal = effective_error
                        current = None
                        break
                else:
                    if not current.future.done():
                        current.future.set_result(result)
                finally:
                    if current is not None and current.future.done():
                        current = None
        except BaseException as exc:
            fatal = exc
        finally:
            close_error = await self.connection.close()
            effective = _preferred_owner_error(close_error, fatal)
            if self.ready is not None and not self.ready.done():
                self.ready.set_exception(effective)
            if current is not None and not current.future.done():
                current.future.set_exception(effective)
            while not self.queue.empty():
                queued = self.queue.get_nowait()
                if queued is not None and not queued.future.done():
                    queued.future.set_exception(effective)


@dataclass(slots=True)
class _LegacySession:
    handle: str
    caller_binding: bytes
    target_digest: bytes
    owner: _SessionOwner
    expires_at: float
    lock: anyio.Lock = field(default_factory=anyio.Lock)
    expiry_task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class McpGatewayService:
    settings: GatewaySettings
    wire_transport: PinnedHttpTransport | None = None
    resolver: AddressResolver | None = None
    _sessions: dict[str, _LegacySession] = field(init=False, default_factory=dict)
    _cache_lock: anyio.Lock = field(init=False, default_factory=anyio.Lock)
    _pending_legacy_sessions: int = field(init=False, default=0)
    _operation_slots: anyio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._operation_slots = anyio.Semaphore(
            self.settings.max_concurrent_operations
        )

    async def execute(self, request: McpOperationRequest) -> McpOperationResponse:
        caller_budget = min(
            self.settings.total_timeout_seconds,
            (
                request.deadline_seconds
                if request.deadline_seconds is not None
                else self.settings.total_timeout_seconds
            ),
        )
        deadline = time.monotonic() + max(0.001, caller_budget)
        if request.operation == "session_close":
            return await self._execute_with_errors(request, deadline)
        try:
            self._operation_slots.acquire_nowait()
        except anyio.WouldBlock as exc:
            raise McpGatewayError(
                "mcp_gateway_capacity",
                "The MCP gateway is at its bounded operation capacity.",
                retryable=True,
            ) from exc
        try:
            return await self._execute_with_errors(request, deadline)
        finally:
            self._operation_slots.release()

    async def _execute_with_errors(
        self,
        request: McpOperationRequest,
        deadline: float,
    ) -> McpOperationResponse:
        try:
            return await self._execute(request, deadline)
        except McpGatewayError:
            raise
        except BaseExceptionGroup as exc:
            nested = _find_exception(exc, McpGatewayError)
            if nested is not None:
                raise nested from exc
            if _find_exception(exc, RuntimeError) is not None:
                raise McpGatewayError(
                    "mcp_tool_result_unsupported",
                    "The MCP operation requires an unsupported interactive capability.",
                ) from exc
            if _find_exception(exc, (MCPError, ValidationError)) is not None:
                raise McpGatewayError(
                    "mcp_protocol_error",
                    "The remote MCP server returned an invalid or rejected response.",
                ) from exc
            if _find_exception(
                exc, (httpx2.HTTPError, OSError, TimeoutError)
            ) is not None:
                raise McpGatewayError(
                    "mcp_server_unreachable",
                    "The remote MCP server could not be reached safely.",
                    retryable=True,
                ) from exc
            raise
        except MCPError as exc:
            raise McpGatewayError(
                "mcp_protocol_error", "The remote MCP server rejected the operation."
            ) from exc
        except ValidationError as exc:
            raise McpGatewayError(
                "mcp_protocol_error", "The remote MCP server returned an invalid response."
            ) from exc
        except RuntimeError as exc:
            raise McpGatewayError(
                "mcp_tool_result_unsupported",
                "The MCP operation requires an unsupported interactive capability.",
            ) from exc
        except (httpx2.HTTPError, OSError, TimeoutError) as exc:
            raise McpGatewayError(
                "mcp_server_unreachable",
                "The remote MCP server could not be reached safely.",
                retryable=True,
            ) from exc

    async def _execute(
        self,
        request: McpOperationRequest,
        deadline: float,
    ) -> McpOperationResponse:
        if request.operation == "session_close":
            return await self._close_session(request, deadline)

        header_bytes = sum(
            len(name.encode("latin-1")) + len(value.encode("latin-1"))
            for name, value in request.headers.items()
        )
        if (
            len(request.headers) > self.settings.max_headers
            or header_bytes > self.settings.max_header_bytes
        ):
            raise McpGatewayError(
                "mcp_request_headers_too_large",
                "The MCP request headers exceed the configured limit.",
            )

        arguments = request.arguments or {}
        argument_bytes = json.dumps(
            arguments,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(argument_bytes) > self.settings.max_request_bytes:
            raise McpGatewayError(
                "mcp_arguments_too_large",
                "The MCP tool arguments exceed the configured limit.",
            )

        if request.session_handle is not None:
            return await self._execute_cached(request, arguments, deadline)
        await self._prune_expired_sessions(deadline)
        return await self._execute_new(request, arguments, deadline)

    async def _execute_new(
        self,
        request: McpOperationRequest,
        arguments: dict[str, object],
        deadline: float,
    ) -> McpOperationResponse:
        assert request.target_url is not None
        legacy_slot_reserved = request.mode != "2026-07-28"
        if legacy_slot_reserved:
            await self._reserve_legacy_slot(deadline)
        # The hard session lifetime begins before the first handshake and is
        # never extended by activity. Transport reads separately enforce idle
        # bounds within this absolute deadline.
        session_deadline = (
            time.monotonic() + self.settings.legacy_session_ttl_seconds
        )
        connection = _McpConnection(
            settings=self.settings,
            target_url=request.target_url,
            mode=request.mode,
            wire_transport=self.wire_transport or PinnedHttpTransport(self.settings),
            resolver=self.resolver,
            write_call=request.write,
            operation_deadline=deadline,
            session_deadline=session_deadline,
        )
        owner = _SessionOwner(
            self,
            connection,
            request.headers,
            deadline,
        )
        transferred = False
        try:
            protocol = await owner.start()
            response = await owner.execute(request, arguments, deadline)
            if protocol == "2026-07-28":
                self._validate_response_size(response)
                return response

            entry = await self._store_legacy_session(
                request,
                owner,
                reserved=legacy_slot_reserved,
                deadline=deadline,
            )
            legacy_slot_reserved = False
            transferred = True
            response = response.model_copy(
                update={
                    "session_handle": entry.handle,
                    "session_expires_in_seconds": _session_seconds_remaining(entry),
                }
            )
            self._schedule_expiry(entry)
            try:
                self._validate_response_size(response)
            except McpGatewayError:
                await self._remove_and_close(entry)
                raise
            return response
        finally:
            if legacy_slot_reserved:
                await self._release_legacy_reservation()
            if not transferred:
                await owner.close()

    async def _execute_cached(
        self,
        request: McpOperationRequest,
        arguments: dict[str, object],
        deadline: float,
    ) -> McpOperationResponse:
        entry = await self._acquire_session(request, deadline)
        poisoned = False
        try:
            response = await entry.owner.execute(request, arguments, deadline)
            response = response.model_copy(
                update={
                    "session_handle": entry.handle,
                    "session_expires_in_seconds": _session_seconds_remaining(entry),
                }
            )
            self._validate_response_size(response)
            return response
        except McpGatewayError as exc:
            poisoned = exc.outcome_unknown or exc.retryable or entry.owner.poisoned
            raise
        except BaseException:
            poisoned = True
            raise
        finally:
            if poisoned:
                # Remove under the cache lock before releasing the per-session
                # lock. A waiter can then acquire the lock only to observe a
                # missing session; it can never dispatch on an ambiguous one.
                with anyio.CancelScope(shield=True):
                    async with self._cache_lock:
                        if self._sessions.get(entry.handle) is entry:
                            self._sessions.pop(entry.handle, None)
                        self._cancel_expiry(entry)
                    entry.lock.release()
                await entry.owner.close()
            else:
                entry.lock.release()
                self._schedule_expiry(entry)

    async def _perform(
        self,
        request: McpOperationRequest,
        arguments: dict[str, object],
        client: Client,
        protocol: str,
    ) -> McpOperationResponse:
        response = self._base_response(request, client, protocol)
        if request.operation == "discover":
            return response
        if request.operation == "tools_list":
            listing = await client.session.list_tools(
                params=types.PaginatedRequestParams(cursor=request.cursor)
            )
            self._validate_tool_page(listing.tools)
            return response.model_copy(
                update={
                    "tools": [_dump_model(tool) for tool in listing.tools],
                    "next_cursor": listing.next_cursor,
                }
            )

        assert request.operation == "tools_call" and request.tool_name is not None
        tool = await self._find_tool(client, request.tool_name)
        if client.server_capabilities.tasks is not None or (
            tool.execution is not None
            and tool.execution.task_support not in {None, "forbidden"}
        ):
            raise McpGatewayError(
                "mcp_tool_incompatible", "Task-based MCP tool execution is not supported."
            )
        result = await client.session.call_tool(
            request.tool_name,
            arguments,
            read_timeout_seconds=self.settings.read_timeout_seconds,
            allow_input_required=False,
            allow_claimed=False,
        )
        if not isinstance(result, types.CallToolResult):
            raise McpGatewayError(
                "mcp_tool_result_unsupported",
                "The MCP tool returned an unsupported result type.",
            )
        return response.model_copy(update={"result": _dump_model(result)})

    async def _store_legacy_session(
        self,
        request: McpOperationRequest,
        owner: _SessionOwner,
        *,
        reserved: bool,
        deadline: float,
    ) -> _LegacySession:
        assert request.target_url is not None
        caller_binding = hashlib.sha256(request.caller_binding.encode("ascii")).digest()
        target_digest = _target_digest(request.target_url, self.settings)
        async with _lock_before_deadline(self._cache_lock, deadline):
            if not reserved or self._pending_legacy_sessions <= 0:
                raise McpGatewayError(
                    "mcp_session_capacity",
                    "The bounded legacy MCP session pool is at capacity.",
                    retryable=True,
                )
            self._pending_legacy_sessions -= 1
            handle = secrets.token_urlsafe(32)
            while handle in self._sessions:
                handle = secrets.token_urlsafe(32)
            entry = _LegacySession(
                handle=handle,
                caller_binding=caller_binding,
                target_digest=target_digest,
                owner=owner,
                expires_at=owner.connection.session_deadline,
            )
            self._sessions[handle] = entry
            return entry

    async def _reserve_legacy_slot(self, deadline: float) -> None:
        async with _lock_before_deadline(self._cache_lock, deadline):
            if (
                len(self._sessions) + self._pending_legacy_sessions
                >= self.settings.max_legacy_sessions
            ):
                raise McpGatewayError(
                    "mcp_session_capacity",
                    "The bounded legacy MCP session pool is at capacity.",
                    retryable=True,
                )
            self._pending_legacy_sessions += 1

    async def _release_legacy_reservation(self) -> None:
        async with self._cache_lock:
            if self._pending_legacy_sessions > 0:
                self._pending_legacy_sessions -= 1

    async def _acquire_session(
        self,
        request: McpOperationRequest,
        deadline: float,
    ) -> _LegacySession:
        assert request.session_handle is not None and request.target_url is not None
        now = time.monotonic()
        async with _lock_before_deadline(self._cache_lock, deadline):
            entry = self._sessions.get(request.session_handle)
            if entry is None:
                raise _missing_session()
            if not hmac.compare_digest(
                entry.caller_binding,
                hashlib.sha256(request.caller_binding.encode("ascii")).digest(),
            ):
                raise McpGatewayError(
                    "mcp_session_binding_mismatch",
                    "The legacy MCP session is not bound to this caller.",
                )
            if not hmac.compare_digest(
                entry.target_digest, _target_digest(request.target_url, self.settings)
            ):
                raise McpGatewayError(
                    "mcp_session_target_mismatch",
                    "The legacy MCP session is not bound to this target."
                )
            expired = entry.expires_at <= now
            if expired:
                self._sessions.pop(entry.handle, None)
                self._cancel_expiry(entry)
        if expired:
            entry.expiry_task = asyncio.create_task(
                self._close_detached_session(entry),
                name="mcp-expired-session-close",
            )
            raise McpGatewayError(
                "mcp_session_expired",
                "The legacy MCP session expired; reconnect before dispatch.",
            )

        try:
            await asyncio.wait_for(
                entry.lock.acquire(),
                _remaining_operation_seconds(deadline),
            )
        except TimeoutError as exc:
            raise _operation_timeout() from exc
        expired_after_lock = False
        try:
            async with _lock_before_deadline(self._cache_lock, deadline):
                if self._sessions.get(entry.handle) is not entry:
                    raise _missing_session()
                if entry.expires_at <= time.monotonic():
                    self._sessions.pop(entry.handle, None)
                    self._cancel_expiry(entry)
                    expired_after_lock = True
        except BaseException:
            entry.lock.release()
            raise
        if expired_after_lock:
            entry.lock.release()
            await entry.owner.close()
            raise McpGatewayError(
                "mcp_session_expired",
                "The legacy MCP session expired; reconnect before dispatch.",
            )
        self._cancel_expiry(entry)
        return entry

    async def _close_session(
        self,
        request: McpOperationRequest,
        deadline: float,
    ) -> McpOperationResponse:
        assert request.session_handle is not None
        async with _lock_before_deadline(self._cache_lock, deadline):
            entry = self._sessions.get(request.session_handle)
            if entry is None:
                raise _missing_session()
            if not hmac.compare_digest(
                entry.caller_binding,
                hashlib.sha256(request.caller_binding.encode("ascii")).digest(),
            ):
                raise McpGatewayError(
                    "mcp_session_binding_mismatch",
                    "The legacy MCP session is not bound to this caller.",
                )
        try:
            await asyncio.wait_for(
                entry.lock.acquire(),
                _remaining_operation_seconds(deadline),
            )
        except TimeoutError as exc:
            raise _operation_timeout() from exc
        try:
            async with _lock_before_deadline(self._cache_lock, deadline):
                if self._sessions.get(entry.handle) is not entry:
                    raise _missing_session()
                self._sessions.pop(entry.handle, None)
                self._cancel_expiry(entry)
            client = entry.owner.client()
            response = self._base_response(
                request, client, _negotiated_protocol(client)
            ).model_copy(update={"closed": True})
            await entry.owner.close(deadline=deadline)
        finally:
            entry.lock.release()
        self._validate_response_size(response)
        return response

    async def _prune_expired_sessions(self, deadline: float) -> None:
        now = time.monotonic()
        async with _lock_before_deadline(self._cache_lock, deadline):
            expired = [
                entry for entry in self._sessions.values() if entry.expires_at <= now
            ]
            for entry in expired:
                self._sessions.pop(entry.handle, None)
                self._cancel_expiry(entry)
        for entry in expired:
            entry.expiry_task = asyncio.create_task(
                self._close_detached_session(entry),
                name="mcp-expired-session-close",
            )

    async def _close_detached_session(self, entry: _LegacySession) -> None:
        try:
            async with entry.lock:
                await entry.owner.close()
        except asyncio.CancelledError:
            return
        finally:
            if entry.expiry_task is asyncio.current_task():
                entry.expiry_task = None

    async def _remove_and_close(self, entry: _LegacySession) -> None:
        async with self._cache_lock:
            self._sessions.pop(entry.handle, None)
            self._cancel_expiry(entry)
        async with entry.lock:
            await entry.owner.close()

    async def close_all(self) -> None:
        """Close every in-memory legacy session during graceful shutdown."""

        async with self._cache_lock:
            entries = list(self._sessions.values())
            self._sessions.clear()
            for entry in entries:
                self._cancel_expiry(entry)
        for entry in entries:
            async with entry.lock:
                await entry.owner.close(
                    deadline=time.monotonic()
                    + min(2.0, self.settings.read_timeout_seconds)
                )

    def _schedule_expiry(self, entry: _LegacySession) -> None:
        self._cancel_expiry(entry)
        entry.expiry_task = asyncio.create_task(
            self._expire_session(entry, entry.expires_at),
            name="mcp-legacy-session-expiry",
        )

    @staticmethod
    def _cancel_expiry(entry: _LegacySession) -> None:
        task, entry.expiry_task = entry.expiry_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _expire_session(
        self,
        entry: _LegacySession,
        expected_expiry: float,
    ) -> None:
        try:
            await asyncio.sleep(max(0.0, expected_expiry - time.monotonic()))
            async with self._cache_lock:
                if (
                    self._sessions.get(entry.handle) is not entry
                    or entry.expires_at != expected_expiry
                    or entry.expires_at > time.monotonic()
                ):
                    return
                self._sessions.pop(entry.handle, None)
                entry.expiry_task = None
            async with entry.lock:
                await entry.owner.close()
        except asyncio.CancelledError:
            return

    def _validate_protocol(self, protocol: str) -> None:
        if protocol not in self.settings.supported_protocol_versions:
            raise McpGatewayError(
                "mcp_protocol_unsupported",
                "The server negotiated an unreviewed MCP protocol revision.",
            )

    def _base_response(
        self, request: McpOperationRequest, client: Client, protocol: str
    ) -> McpOperationResponse:
        discover = client.session.discover_result
        supported = list(discover.supported_versions) if discover is not None else [protocol]
        return McpOperationResponse(
            operation_id=request.operation_id,
            negotiated_protocol_version=protocol,
            session_mode="modern" if protocol == "2026-07-28" else "legacy",
            capabilities=_dump_model(client.server_capabilities),
            server_info=(
                _dump_model(client.server_info) if client.server_info is not None else None
            ),
            supported_versions=supported,
        )

    async def _find_tool(self, client: Client, name: str) -> types.Tool:
        cursor: str | None = None
        seen: set[str] = set()
        total = 0
        pages = 0
        while True:
            pages += 1
            if pages > self.settings.max_tool_pages:
                raise McpGatewayError(
                    "mcp_pagination_invalid",
                    "The MCP tool inventory exceeds the page limit.",
                )
            listing = await client.session.list_tools(
                params=types.PaginatedRequestParams(cursor=cursor)
            )
            total += len(listing.tools)
            if total > self.settings.max_discovered_tools:
                raise McpGatewayError(
                    "mcp_tool_inventory_too_large",
                    "The MCP tool inventory exceeds the configured limit.",
                )
            for tool in listing.tools:
                if tool.name == name:
                    return tool
            cursor = listing.next_cursor
            if cursor is None:
                break
            if cursor in seen:
                raise McpGatewayError(
                    "mcp_pagination_invalid",
                    "The MCP tool inventory contains a pagination cycle.",
                )
            seen.add(cursor)
        raise McpGatewayError("mcp_tool_not_found", "The MCP tool is not advertised.")

    def _validate_tool_page(self, tools: list[types.Tool]) -> None:
        if len(tools) > self.settings.max_discovered_tools:
            raise McpGatewayError(
                "mcp_tool_inventory_too_large",
                "The MCP tool inventory exceeds the configured limit.",
            )

    def _validate_response_size(self, response: McpOperationResponse) -> None:
        if len(response.model_dump_json().encode("utf-8")) > self.settings.max_response_bytes:
            raise McpGatewayError(
                "mcp_response_too_large",
                "The normalized MCP response exceeds the configured limit.",
            )


def _missing_session() -> McpGatewayError:
    return McpGatewayError(
        "mcp_session_not_found",
        "The legacy MCP session is unavailable; reconnect before dispatch.",
    )


def _operation_timeout() -> McpGatewayError:
    return McpGatewayError(
        "mcp_operation_timeout",
        "The MCP operation exceeded its total deadline.",
        retryable=True,
    )


def _remaining_operation_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _operation_timeout()
    return max(0.001, remaining)


@asynccontextmanager
async def _lock_before_deadline(lock: Any, deadline: float):
    try:
        await asyncio.wait_for(lock.acquire(), _remaining_operation_seconds(deadline))
    except TimeoutError as exc:
        raise _operation_timeout() from exc
    try:
        yield
    finally:
        lock.release()


def _session_seconds_remaining(entry: _LegacySession) -> int:
    return max(0, int(entry.expires_at - time.monotonic()))


def _mcp_auth_error_code(
    status_code: int, headers: dict[str, str]
) -> str | None:
    """Classify only the two reviewed MCP OAuth runtime failures.

    The caller receives a fixed code/message. Challenge parameters (which can
    contain scopes, resource URLs, or attacker-controlled text) never cross the
    internal gateway boundary.
    """

    if status_code == 401:
        return "mcp_auth_required"
    if status_code != 403:
        return None
    challenge = next(
        (
            str(value)
            for name, value in headers.items()
            if str(name).casefold() == "www-authenticate"
        ),
        "",
    )
    if not re.search(r"(?i)(?:^|,)\s*Bearer(?:\s|$)", challenge):
        return None
    if re.search(
        r"(?i)\berror\s*=\s*(?:\"insufficient_scope\"|insufficient_scope)(?:\s|,|$)",
        challenge,
    ):
        return "mcp_insufficient_scope"
    return None


def _map_transport_error(
    error: GatewayTransportError,
    *,
    ambiguous_write: bool,
) -> Exception:
    if ambiguous_write:
        return McpGatewayError(
            "mcp_tool_outcome_unknown",
            "The write may have reached the remote service; it will not be retried.",
            outcome_unknown=True,
        )
    if error.code == "proxy_target_blocked":
        return OutboundTargetBlocked(
            "proxy_target_blocked",
            "The outbound proxy rejected the target.",
        )
    if error.code in {
        "upstream_headers_too_large",
        "upstream_response_too_large",
    }:
        return McpGatewayError(
            "mcp_response_too_large",
            "The MCP response exceeds the configured limit.",
        )
    if error.code in {
        "upstream_encoding_unsupported",
        "upstream_headers_invalid",
    }:
        return McpGatewayError(
            "mcp_protocol_error",
            "The remote MCP server returned an invalid response.",
        )
    return McpGatewayError(
        "mcp_server_unreachable",
        "The remote MCP server could not be reached safely.",
        retryable=error.retryable,
    )


def _preferred_owner_error(
    close_error: BaseException | None,
    fatal: BaseException | None,
) -> BaseException:
    """Prefer the transport's categorical error over task-group cancellation."""

    for error in (close_error, fatal):
        if isinstance(error, McpGatewayError):
            return error
        if isinstance(error, BaseExceptionGroup):
            nested = _find_exception(error, McpGatewayError)
            if nested is not None:
                return nested
    for error in (fatal, close_error):
        if isinstance(error, OutboundTargetBlocked):
            return error
        if isinstance(error, BaseExceptionGroup):
            nested = _find_exception(error, OutboundTargetBlocked)
            if nested is not None:
                return nested
    if fatal is not None and not isinstance(fatal, asyncio.CancelledError):
        return fatal
    return close_error or fatal or _missing_session()


def _open_client(connection: _McpConnection) -> Client:
    if connection.client is None:
        raise _missing_session()
    return connection.client


def _negotiated_protocol(client: Client) -> str:
    protocol = client.session.protocol_version
    if protocol is None:
        raise McpGatewayError(
            "mcp_protocol_error", "The MCP server did not negotiate a protocol revision."
        )
    return protocol


def _target_digest(raw_url: str, settings: GatewaySettings) -> bytes:
    target = canonicalize_outbound_url(
        raw_url,
        allow_http=settings.is_local and settings.allow_private_egress,
        allow_private_hostnames=settings.is_local and settings.allow_private_egress,
    )
    return hashlib.sha256(target.url.encode("ascii")).digest()


def _sdk_request_headers(headers: httpx2.Headers, max_bytes: int) -> dict[str, str]:
    skipped = {
        "accept-encoding",
        "connection",
        "content-length",
        "host",
        "proxy-connection",
        "transfer-encoding",
    }
    output: dict[str, str] = {}
    total = 0
    for name, value in headers.multi_items():
        lower = name.lower()
        if lower in skipped:
            continue
        total += len(name.encode("latin-1")) + len(value.encode("latin-1"))
        if total > max_bytes:
            raise McpGatewayError(
                "mcp_request_headers_too_large",
                "The MCP request headers exceed the configured limit.",
            )
        if lower in output:
            output[lower] = f"{output[lower]}, {value}"
        else:
            output[lower] = value
    return output


def _jsonrpc_request_identity(body: bytes) -> tuple[str | None, str | None]:
    if not body:
        return None, None
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    method = value.get("method") if isinstance(value, dict) else None
    if not isinstance(method, str):
        return None, None
    return method, _rpc_id_key(
        value["id"] if "id" in value else _RPC_ID_MISSING
    )


def _rpc_id_key(value: object) -> str | None:
    if isinstance(value, str):
        return f"string:{value}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"integer:{value}"
    if value is None:
        return "null:"
    return None


def _is_event_stream_content_type(value: str) -> bool:
    return value.split(";", 1)[0].strip().lower() == "text/event-stream"


def _has_terminal_rpc_response(
    payload: bytes,
    content_type: str,
    *,
    expected_id: str,
) -> bool:
    """Recognize one bounded JSON-RPC result/error without trusting its body."""

    candidates: list[bytes] = []
    if _is_event_stream_content_type(content_type):
        normalized = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        for event in normalized.split(b"\n\n"):
            data_lines = [
                line[5:].lstrip(b" ")
                for line in event.split(b"\n")
                if line.startswith(b"data:")
            ]
            if data_lines:
                candidates.append(b"\n".join(data_lines))
    else:
        candidates.append(payload)

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        messages = value if isinstance(value, list) else [value]
        if any(
            isinstance(message, dict)
            and message.get("jsonrpc") == "2.0"
            and "id" in message
            and _rpc_id_key(message.get("id")) == expected_id
            and (("result" in message) ^ ("error" in message))
            for message in messages
        ):
            return True
    return False


def _is_legacy_fallback_error(error: BaseException) -> bool:
    if isinstance(error, (_LegacySseRequired, MCPError, ValidationError)):
        return True
    if isinstance(error, BaseExceptionGroup):
        return _find_exception(error, (MCPError, ValidationError)) is not None
    return False


def _dump_model(value: Any) -> dict[str, Any]:
    return value.model_dump(by_alias=True, mode="json", exclude_none=True)


def _find_exception(
    group: BaseExceptionGroup,
    classes: type[BaseException] | tuple[type[BaseException], ...],
) -> BaseException | None:
    for exception in group.exceptions:
        if isinstance(exception, classes):
            return exception
        if isinstance(exception, BaseExceptionGroup):
            nested = _find_exception(exception, classes)
            if nested is not None:
                return nested
    return None


__all__ = ["McpGatewayError", "McpGatewayService"]
