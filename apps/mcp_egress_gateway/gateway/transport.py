"""Pinned-address HTTP/1.1 transport with optional CONNECT proxy."""

from __future__ import annotations

import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import urlsplit

from app.common.outbound_http import ResolvedOutboundTarget

from .config import GatewaySettings


class GatewayTransportError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        dispatch_started: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.dispatch_started = dispatch_started


class _ResponseHeadersTooLarge(http.client.HTTPException):
    """Raised before the stdlib parser can retain an oversized header block."""


class _BoundedHeaderReader:
    """Count status/header bytes while ``HTTPResponse.begin`` is parsing.

    ``http.client`` otherwise permits roughly ``_MAXHEADERS * _MAXLINE`` bytes
    before callers can inspect the parsed headers.  The wrapper limits every
    underlying ``readline`` to the remaining aggregate budget and is detached
    immediately after ``begin`` so body/chunk framing uses the original file.
    """

    def __init__(
        self,
        raw: BinaryIO,
        *,
        max_bytes: int,
        max_headers: int,
    ) -> None:
        self.raw = raw
        self.max_bytes = max(1, int(max_bytes))
        self.max_headers = max(1, int(max_headers))
        self.total = 0
        self.lines = 0

    def readline(self, size: int = -1) -> bytes:
        remaining = self.max_bytes - self.total
        if remaining <= 0:
            raise _ResponseHeadersTooLarge("response headers exceed the byte limit")
        limit = remaining + 1
        if size is not None and size >= 0:
            limit = min(limit, size)
        line = self.raw.readline(limit)
        self.total += len(line)
        if self.total > self.max_bytes:
            raise _ResponseHeadersTooLarge("response headers exceed the byte limit")
        self.lines += 1
        # First line is the HTTP status line.  Count every subsequent physical
        # non-empty line so folded/continuation abuse is bounded too.
        if self.lines > 1 and line not in {b"\r\n", b"\n", b""}:
            if self.lines - 1 > self.max_headers:
                raise _ResponseHeadersTooLarge(
                    "response headers exceed the field limit"
                )
        return line

    def __getattr__(self, name: str):
        return getattr(self.raw, name)


class _BoundedMakefileSocket:
    """Give ``HTTPResponse`` a bounded-size buffered reader.

    The stdlib constructs its file object before we can wrap ``readline``.
    Capping that buffer to the full header budget plus one sentinel byte keeps
    socket prefetch bounded while retaining already-read body bytes after the
    header wrapper is detached.
    """

    def __init__(self, sock: socket.socket | ssl.SSLSocket, max_header_bytes: int):
        self.sock = sock
        self.buffer_size = max(2, int(max_header_bytes) + 1)

    def makefile(self, mode: str):
        return self.sock.makefile(mode, buffering=self.buffer_size)


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


class StreamingTransportResponse:
    """Owned bounded response stream returned after headers are validated."""

    def __init__(
        self,
        *,
        status_code: int,
        headers: dict[str, str],
        response: http.client.HTTPResponse,
        connection: socket.socket | ssl.SSLSocket,
        settings: GatewaySettings,
        deadline: float,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self._response = response
        self._connection = connection
        self._settings = settings
        self._deadline = deadline
        self._received = 0
        self._persistent_sse = False
        self._closed = False

    def read_chunk(self) -> bytes:
        if self._closed:
            return b""
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            self.close()
            raise GatewayTransportError(
                "operation_timeout",
                "The outbound operation exceeded its deadline.",
                retryable=True,
                dispatch_started=True,
            )
        self._connection.settimeout(
            max(
                0.001,
                min(
                    (
                        self._settings.legacy_session_ttl_seconds
                        if self._persistent_sse
                        else self._settings.read_timeout_seconds
                    ),
                    remaining,
                ),
            )
        )
        try:
            chunk = self._response.read1(16_384)
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            self.close()
            raise GatewayTransportError(
                "upstream_unavailable",
                "The upstream response stream ended unsafely.",
                retryable=True,
                dispatch_started=True,
            ) from exc
        if not chunk:
            self.close()
            return b""
        self._received += len(chunk)
        if (
            (not self._persistent_sse and self._received > self._settings.max_response_bytes)
            or len(chunk) > self._settings.max_response_bytes
        ):
            self.close()
            raise GatewayTransportError(
                "upstream_response_too_large",
                "The upstream response exceeds the configured limit.",
                dispatch_started=True,
            )
        return chunk

    def activate_sse_session(self, *, absolute_deadline: float) -> None:
        """Switch a validated legacy SSE GET from handshake to session bounds.

        Only a successful ``text/event-stream`` response may transition.  The
        caller supplies the session's precomputed absolute deadline; this
        method can shorten it but never extend it beyond the configured legacy
        TTL from the transition point.  Cumulative body accounting is disabled
        only after this check because the MCP layer separately caps each SSE
        event/data message.
        """

        content_type = self.headers.get("content-type", "").split(";", 1)[0]
        if self.status_code != 200 or content_type.strip().lower() != "text/event-stream":
            raise GatewayTransportError(
                "upstream_response_invalid",
                "The upstream response is not a valid event stream.",
                dispatch_started=True,
            )
        now = time.monotonic()
        bounded_deadline = min(
            float(absolute_deadline),
            now + float(self._settings.legacy_session_ttl_seconds),
        )
        if bounded_deadline <= now:
            self.close()
            raise GatewayTransportError(
                "operation_timeout",
                "The outbound operation exceeded its deadline.",
                retryable=True,
                dispatch_started=True,
            )
        self._deadline = bounded_deadline
        self._received = 0
        self._persistent_sse = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        finally:
            self._connection.close()


class PinnedHttpTransport:
    """Connect to the policy-returned IP while preserving HTTP Host and TLS SNI.

    There are no automatic retries.  When a proxy is configured, CONNECT names
    the validated IP rather than the tenant hostname, so the proxy cannot open a
    second DNS-rebinding window.
    """

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self._tls_context = ssl.create_default_context()
        self._tls_context.minimum_version = ssl.TLSVersion.TLSv1_2

    def send(
        self,
        *,
        target: ResolvedOutboundTarget,
        method: str,
        headers: dict[str, str],
        body: bytes,
        deadline: float,
    ) -> TransportResponse:
        stream = self.open_stream(
            target=target,
            method=method,
            headers=headers,
            body=body,
            deadline=deadline,
        )
        payload = bytearray()
        try:
            while chunk := stream.read_chunk():
                payload.extend(chunk)
        finally:
            stream.close()
        return TransportResponse(stream.status_code, stream.headers, bytes(payload))

    def open_stream(
        self,
        *,
        target: ResolvedOutboundTarget,
        method: str,
        headers: dict[str, str],
        body: bytes,
        deadline: float,
    ) -> StreamingTransportResponse:
        """Dispatch once and transfer ownership of the bounded response stream."""

        raw_socket: socket.socket | ssl.SSLSocket | None = None
        response: http.client.HTTPResponse | None = None
        dispatch_started = False
        try:
            raw_socket = self._open_socket(target, deadline=deadline)
            if target.canonical.scheme == "https":
                raw_socket.settimeout(
                    self._remaining_timeout(
                        deadline, self.settings.connect_timeout_seconds
                    )
                )
                raw_socket = self._tls_context.wrap_socket(
                    raw_socket,
                    server_hostname=target.canonical.host,
                )
            raw_socket.settimeout(
                self._remaining_timeout(deadline, self.settings.read_timeout_seconds)
            )
            request = self._serialize_request(
                target=target,
                method=method,
                headers=headers,
                body=body,
            )
            # Conservatively mark before sendall: an exception can occur after a
            # partial write, which is outcome-ambiguous for a remote mutation.
            dispatch_started = True
            raw_socket.sendall(request)

            response = self._response(raw_socket)
            self._begin_response(response)
            raw_response_headers = response.getheaders()
            raw_response_names = {name.lower() for name, _value in raw_response_headers}
            if "content-length" in raw_response_names and "transfer-encoding" in raw_response_names:
                raise GatewayTransportError(
                    "upstream_headers_invalid",
                    "The upstream response headers are invalid.",
                )
            response_headers = self._bounded_response_headers(raw_response_headers)
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise GatewayTransportError(
                        "upstream_headers_invalid",
                        "The upstream response headers are invalid.",
                    ) from exc
                if declared_length < 0 or declared_length > self.settings.max_response_bytes:
                    raise GatewayTransportError(
                        "upstream_response_too_large",
                        "The upstream response exceeds the configured limit.",
                    )
            owned = StreamingTransportResponse(
                status_code=response.status,
                headers=response_headers,
                response=response,
                connection=raw_socket,
                settings=self.settings,
                deadline=deadline,
            )
            response = None
            raw_socket = None
            return owned
        except GatewayTransportError as exc:
            if dispatch_started and not exc.dispatch_started:
                raise GatewayTransportError(
                    exc.code,
                    str(exc),
                    retryable=exc.retryable,
                    dispatch_started=True,
                ) from exc
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise GatewayTransportError(
                "upstream_unavailable",
                "The upstream service could not be reached safely.",
                retryable=True,
                dispatch_started=dispatch_started,
            ) from exc
        finally:
            if response is not None:
                response.close()
            if raw_socket is not None:
                raw_socket.close()

    def _open_socket(
        self,
        target: ResolvedOutboundTarget,
        *,
        deadline: float,
    ) -> socket.socket:
        connect_timeout = self._remaining_timeout(
            deadline, self.settings.connect_timeout_seconds
        )
        proxy_url = self.settings.forward_proxy_url
        if not proxy_url:
            return socket.create_connection(
                (target.connect_address, target.canonical.port),
                timeout=connect_timeout,
            )

        proxy = urlsplit(proxy_url)
        proxy_host = proxy.hostname
        if not proxy_host:
            raise GatewayTransportError(
                "proxy_configuration_invalid",
                "The outbound proxy is not configured safely.",
            )
        proxy_port = proxy.port or 3128
        connection = socket.create_connection(
            (proxy_host, proxy_port),
            timeout=connect_timeout,
        )
        if target.canonical.scheme != "https":
            connection.close()
            raise GatewayTransportError(
                "proxy_http_unsupported",
                "Plain HTTP is not supported through the deployed proxy boundary.",
            )
        connection.settimeout(
            self._remaining_timeout(deadline, self.settings.connect_timeout_seconds)
        )

        connect_host = target.connect_address
        if ":" in connect_host:
            connect_host = f"[{connect_host}]"
        connect_authority = f"{connect_host}:{target.canonical.port}"
        tunnel_request = (
            f"CONNECT {connect_authority} HTTP/1.1\r\n"
            f"Host: {connect_authority}\r\n"
            "\r\n"
        ).encode("ascii")
        connection.sendall(tunnel_request)
        connection.settimeout(
            self._remaining_timeout(deadline, self.settings.connect_timeout_seconds)
        )
        proxy_response = self._response(connection)
        try:
            self._begin_response(proxy_response)
            proxy_status = proxy_response.status
        finally:
            # ``HTTPResponse`` owns a makefile wrapper, not the original socket.
            # Close the wrapper before TLS; the original socket remains open.
            proxy_response.close()
        if proxy_status != 200:
            connection.close()
            raise GatewayTransportError(
                "proxy_target_blocked",
                "The outbound proxy rejected the target.",
            )
        return connection

    def _response(
        self,
        connection: socket.socket | ssl.SSLSocket,
    ) -> http.client.HTTPResponse:
        return http.client.HTTPResponse(
            _BoundedMakefileSocket(connection, self.settings.max_header_bytes)  # type: ignore[arg-type]
        )

    def _begin_response(self, response: http.client.HTTPResponse) -> None:
        raw = response.fp
        if raw is None:
            raise GatewayTransportError(
                "upstream_headers_invalid",
                "The upstream response headers are invalid.",
            )
        bounded = _BoundedHeaderReader(
            raw,
            max_bytes=self.settings.max_header_bytes,
            max_headers=self.settings.max_headers,
        )
        response.fp = bounded  # type: ignore[assignment]
        try:
            response.begin()
        except _ResponseHeadersTooLarge as exc:
            raise GatewayTransportError(
                "upstream_headers_too_large",
                "The upstream response headers exceed the configured limit.",
            ) from exc
        finally:
            # Preserve any body bytes already prefetched by the bounded
            # BufferedReader; only remove the counting façade.
            if response.fp is bounded:
                response.fp = raw

    def _serialize_request(
        self,
        *,
        target: ResolvedOutboundTarget,
        method: str,
        headers: dict[str, str],
        body: bytes,
    ) -> bytes:
        rendered: list[bytes] = [
            f"{method} {target.canonical.request_target} HTTP/1.1\r\n".encode("ascii"),
            f"Host: {target.canonical.authority}\r\n".encode("ascii"),
            b"Connection: close\r\n",
            b"Accept-Encoding: identity\r\n",
        ]
        for name, value in headers.items():
            rendered.append(f"{name}: {value}\r\n".encode("latin-1"))
        if body or method == "POST":
            rendered.append(f"Content-Length: {len(body)}\r\n".encode("ascii"))
        rendered.append(b"\r\n")
        rendered.append(body)
        payload = b"".join(rendered)
        header_end = payload.find(b"\r\n\r\n") + 4
        if header_end > self.settings.max_header_bytes:
            raise GatewayTransportError(
                "request_headers_too_large",
                "The outbound request headers exceed the configured limit.",
            )
        return payload

    def _bounded_response_headers(
        self, raw_headers: list[tuple[str, str]]
    ) -> dict[str, str]:
        if len(raw_headers) > self.settings.max_headers:
            raise GatewayTransportError(
                "upstream_headers_too_large",
                "The upstream response headers exceed the configured limit.",
            )
        total = 0
        headers: dict[str, str] = {}
        for name, value in raw_headers:
            total += len(name.encode("latin-1", "replace")) + len(
                value.encode("latin-1", "replace")
            )
            if total > self.settings.max_header_bytes:
                raise GatewayTransportError(
                    "upstream_headers_too_large",
                    "The upstream response headers exceed the configured limit.",
                )
            lower = name.lower()
            if lower == "content-encoding" and value.strip().lower() not in {
                "",
                "identity",
            }:
                raise GatewayTransportError(
                    "upstream_encoding_unsupported",
                    "Compressed upstream responses are not accepted.",
                )
            # Hop-by-hop state and cookies never cross the gateway boundary.
            if lower in {
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "set-cookie",
                "te",
                "trailer",
                "transfer-encoding",
                "upgrade",
            }:
                continue
            if lower in headers:
                headers[lower] = f"{headers[lower]}, {value}"
            else:
                headers[lower] = value
        return headers

    @staticmethod
    def _remaining_timeout(deadline: float, cap: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GatewayTransportError(
                "operation_timeout",
                "The outbound operation exceeded its deadline.",
                retryable=True,
            )
        return max(0.001, min(cap, remaining))


__all__ = [
    "GatewayTransportError",
    "PinnedHttpTransport",
    "StreamingTransportResponse",
    "TransportResponse",
]
