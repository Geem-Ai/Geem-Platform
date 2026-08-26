"""mTLS client for the datastore-isolated MCP egress gateway.

Only this adapter handles the internal gateway URL. Tenant endpoint and
ephemeral connection credentials are sent in one bounded request and are never
logged, persisted by the gateway, or exposed in an application DTO.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.gateway import (
    McpDiscoveryRequest,
    McpDiscoveryResult,
    McpTargetValidationRequest,
    McpTargetValidationResult,
)
from app.mcp.mtls import mcp_gateway_ssl_context


_MAX_DISCOVERY_PAGES = 64


@dataclass(frozen=True, slots=True)
class McpToolCallRequest:
    operation_id: str
    target_url: str
    auth: dict[str, Any]
    tool_name: str
    arguments: dict[str, Any]
    write: bool
    protocol_version: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    deadline_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class McpToolCallResult:
    protocol_version: str
    session_mode: str
    result: dict[str, Any]
    outcome_unknown: bool = False


class HttpMcpGatewayClient:
    """Synchronous internal client used outside every admission transaction."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        base = (self.settings.mcp_egress_gateway_url or "").strip().rstrip("/") + "/"
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.hostname:
            raise RuntimeError("The internal MCP egress gateway is not configured safely.")
        self._endpoint = urljoin(base, "v1/mcp")
        self._target_validation_endpoint = urljoin(base, "v1/target-validation")
        self._owns_client = client is None
        if client is None:
            client = httpx.Client(
                verify=mcp_gateway_ssl_context(self.settings),
                timeout=httpx.Timeout(
                    float(self.settings.mcp_egress_total_timeout_seconds),
                    connect=float(self.settings.mcp_egress_connect_timeout_seconds),
                    read=float(self.settings.mcp_egress_read_timeout_seconds),
                ),
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json"},
            )
        self._client: httpx.Client = client

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def validate_target(
        self,
        request: McpTargetValidationRequest,
    ) -> McpTargetValidationResult:
        operation_id = _safe_operation_id(
            request.operation_name,
            request.connection_id,
        )
        deadline_at = time.monotonic() + max(
            0.001,
            float(request.deadline_seconds),
        )
        payload = self._post(
            {
                "operation_id": operation_id,
                "target_url": request.target_url,
                "caller_binding": _caller_binding(
                    f"{request.workspace_id}:{request.connection_id}"
                ),
            },
            endpoint=self._target_validation_endpoint,
            deadline_at=deadline_at,
        )
        digest = payload.get("origin_digest")
        if (
            payload.get("operation_id") != operation_id
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP gateway returned an invalid target validation response.",
                retryable=True,
            )
        return McpTargetValidationResult(origin_digest=digest)

    def discover(self, request: McpDiscoveryRequest) -> McpDiscoveryResult:
        deadline_at = time.monotonic() + max(0.001, float(request.deadline_seconds))
        operation_id = _safe_operation_id("discover", request.connection_id)
        caller_binding = _caller_binding(
            f"{request.workspace_id}:{request.connection_id}"
        )
        base_payload = {
            "operation_id": operation_id,
            "target_url": request.server_url,
            "headers": _auth_headers(request.auth),
            "mode": "auto",
            "caller_binding": caller_binding,
        }
        session_handle: str | None = None
        try:
            discovered = self._post(
                {**base_payload, "operation": "discover"},
                deadline_at=deadline_at,
            )
            protocol = str(discovered.get("negotiated_protocol_version") or "")
            session_handle = _session_handle(discovered)
            if (
                str(discovered.get("session_mode") or "modern") == "legacy"
                and session_handle is None
            ):
                raise AppError(
                    ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
                    "The MCP gateway did not preserve the negotiated legacy session.",
                )
            tools: list[dict[str, Any]] = []
            cursor: str | None = None
            seen_cursors: set[str] = set()
            page_count = 0
            while True:
                if page_count >= _MAX_DISCOVERY_PAGES:
                    raise AppError(
                        ErrorCategory.MCP_TOOL_LIMIT_REACHED,
                        "The MCP server tool inventory spans too many pages.",
                        details={"limit": _MAX_DISCOVERY_PAGES},
                    )
                page = self._post(
                    {
                        **base_payload,
                        "operation_id": _safe_operation_id(
                            f"list{page_count}", request.connection_id
                        ),
                        "operation": "tools_list",
                        "cursor": cursor,
                        "session_handle": session_handle,
                    },
                    deadline_at=deadline_at,
                )
                page_count += 1
                if str(page.get("negotiated_protocol_version") or "") != protocol:
                    raise AppError(
                        ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
                        "The MCP protocol changed during inventory discovery.",
                    )
                page_handle = _session_handle(page)
                if session_handle is not None and page_handle != session_handle:
                    raise AppError(
                        ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
                        "The MCP gateway changed the negotiated legacy session.",
                    )
                raw_tools = page.get("tools")
                if not isinstance(raw_tools, list):
                    raise AppError(
                        ErrorCategory.MCP_TOOL_SET_CHANGED,
                        "The MCP server returned an incomplete tool inventory.",
                    )
                for raw in raw_tools:
                    if not isinstance(raw, dict):
                        raise AppError(
                            ErrorCategory.MCP_TOOL_SET_CHANGED,
                            "The MCP server returned a malformed tool inventory.",
                        )
                    tools.append(copy.deepcopy(raw))
                    if len(tools) > self.settings.mcp_max_discovered_tools:
                        raise AppError(
                            ErrorCategory.MCP_TOOL_LIMIT_REACHED,
                            "The MCP server advertised too many tools.",
                            details={"limit": self.settings.mcp_max_discovered_tools},
                        )
                next_cursor = page.get("next_cursor")
                if next_cursor is None:
                    break
                if (
                    not isinstance(next_cursor, str)
                    or not next_cursor
                    or next_cursor in seen_cursors
                ):
                    raise AppError(
                        ErrorCategory.MCP_TOOL_SET_CHANGED,
                        "The MCP server returned an invalid pagination cursor.",
                    )
                seen_cursors.add(next_cursor)
                cursor = next_cursor

            server_info = discovered.get("server_info")
            identity = server_info if isinstance(server_info, dict) else {}
            return McpDiscoveryResult(
                protocol_version=protocol,
                session_mode=str(discovered.get("session_mode") or "modern"),
                capabilities=_dict(discovered.get("capabilities")),
                tools=tuple(tools),
                complete=True,
                external_subject=_optional_text(identity.get("name")),
                external_identity_label=_optional_text(
                    identity.get("title") or identity.get("name")
                ),
                resource_uri=request.resource_uri,
            )
        finally:
            if session_handle is not None:
                self._close_session(
                    session_handle=session_handle,
                    caller_binding=caller_binding,
                    operation_id=_safe_operation_id("close", request.connection_id),
                    deadline_at=deadline_at,
                )

    def call_tool(self, request: McpToolCallRequest) -> McpToolCallResult:
        deadline_at = time.monotonic() + max(
            0.001,
            float(
                request.deadline_seconds
                if request.deadline_seconds is not None
                else self.settings.mcp_tool_call_timeout_seconds
            ),
        )
        mode = (
            "2026-07-28"
            if request.protocol_version == "2026-07-28"
            else ("legacy" if request.protocol_version else "auto")
        )
        caller_binding = _caller_binding(request.operation_id)
        session_handle: str | None = None
        try:
            payload = self._post(
                {
                    "operation_id": request.operation_id,
                    "operation": "tools_call",
                    "target_url": request.target_url,
                    "headers": _merged_headers(
                        request.auth, request.extra_headers
                    ),
                    "mode": mode,
                    "caller_binding": caller_binding,
                    "tool_name": request.tool_name,
                    "arguments": copy.deepcopy(request.arguments),
                    "write": bool(request.write),
                },
                write=bool(request.write),
                deadline_at=deadline_at,
            )
            session_handle = _session_handle(payload)
            result = payload.get("result")
            if not isinstance(result, dict):
                raise AppError(
                    ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
                    "The MCP server returned an unsupported result.",
                )
            return McpToolCallResult(
                protocol_version=str(payload.get("negotiated_protocol_version") or ""),
                session_mode=str(payload.get("session_mode") or "modern"),
                result=copy.deepcopy(result),
                outcome_unknown=bool(payload.get("outcome_unknown")),
            )
        finally:
            if session_handle is not None:
                self._close_session(
                    session_handle=session_handle,
                    caller_binding=caller_binding,
                    operation_id=_close_operation_id(request.operation_id),
                    deadline_at=deadline_at,
                )

    def _post(
        self,
        payload: dict[str, Any],
        *,
        endpoint: str | None = None,
        write: bool = False,
        deadline_at: float | None = None,
    ) -> dict[str, Any]:
        wire_payload = dict(payload)
        request_timeout = None
        if deadline_at is not None:
            remaining = deadline_at - time.monotonic()
            if remaining <= 0:
                raise AppError(
                    ErrorCategory.MCP_SERVER_UNREACHABLE,
                    "The MCP operation exceeded its deadline.",
                    retryable=True,
                )
            request_timeout = max(0.001, remaining)
            # The gateway starts with the API's remaining absolute budget and
            # further subtracts mTLS/envelope ingress time. It never receives
            # a fresh timeout for negotiation or a later SDK request.
            wire_payload["deadline_seconds"] = min(180.0, request_timeout)
            # The epoch deadline additionally charges connect/TLS transit,
            # which occurs before gateway middleware can take a monotonic
            # timestamp. The duration remains a hard cap under clock skew.
            wire_payload["deadline_unix_ms"] = int(
                (time.time() + request_timeout) * 1_000
            )
        try:
            encoded = json.dumps(
                wire_payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise AppError(
                ErrorCategory.MCP_TOOL_INCOMPATIBLE,
                "The MCP gateway request is not valid JSON.",
            ) from exc
        if len(encoded) > self.settings.mcp_egress_max_request_bytes:
            raise AppError(
                ErrorCategory.MCP_TOOL_INCOMPATIBLE,
                "The MCP gateway request exceeds the configured limit.",
            )
        try:
            response = self._client.post(
                endpoint or self._endpoint,
                content=encoded,
                headers={"Content-Type": "application/json"},
                **({"timeout": request_timeout} if request_timeout is not None else {}),
            )
        except httpx.TransportError as exc:
            pre_dispatch = isinstance(
                exc,
                (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout),
            )
            category = (
                ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
                if write and not pre_dispatch
                else ErrorCategory.MCP_SERVER_UNREACHABLE
            )
            raise AppError(
                category,
                "The MCP gateway did not confirm the operation outcome."
                if write and not pre_dispatch
                else "The MCP server could not be reached.",
                retryable=not write or pre_dispatch,
            ) from exc
        content_length = response.headers.get("content-length")
        if content_length and content_length.isdecimal():
            if int(content_length) > self.settings.mcp_egress_max_response_bytes:
                raise AppError(
                    ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
                    "The MCP gateway response exceeds the configured limit.",
                )
        if len(response.content) > self.settings.mcp_egress_max_response_bytes:
            raise AppError(
                ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
                "The MCP gateway response exceeds the configured limit.",
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise AppError(
                ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
                if write
                else ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP gateway returned an invalid response.",
                retryable=not write,
            ) from exc
        if response.is_error:
            error = body.get("error") if isinstance(body, dict) else None
            error_payload = error if isinstance(error, dict) else {}
            code = str(error_payload.get("code") or "")
            raw_outcome_unknown = error_payload.get("outcome_unknown")
            outcome_unknown = (
                raw_outcome_unknown
                if isinstance(raw_outcome_unknown, bool)
                else write and response.status_code >= 500
            )
            category = _gateway_error_category(code, outcome_unknown=outcome_unknown)
            raise AppError(
                category,
                _safe_gateway_message(category),
                retryable=bool(error_payload.get("retryable")) and not outcome_unknown,
            )
        if not isinstance(body, dict):
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP gateway returned an invalid response.",
                retryable=True,
            )
        if body.get("operation_id") != wire_payload.get("operation_id"):
            raise AppError(
                (
                    ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
                    if write
                    else ErrorCategory.MCP_SERVER_UNREACHABLE
                ),
                (
                    "The MCP gateway did not confirm the operation outcome."
                    if write
                    else "The MCP gateway returned an invalid response."
                ),
                retryable=not write,
            )
        return body

    def _close_session(
        self,
        *,
        session_handle: str,
        caller_binding: str,
        operation_id: str,
        deadline_at: float | None = None,
    ) -> None:
        try:
            self._post(
                {
                    "operation_id": operation_id,
                    "operation": "session_close",
                    "mode": "legacy",
                    "caller_binding": caller_binding,
                    "session_handle": session_handle,
                },
                deadline_at=deadline_at,
            )
        except AppError:
            # The gateway owns a short hard TTL for an abandoned legacy
            # session. A completed discovery/tool outcome must not be changed
            # merely because cleanup acknowledgement was lost.
            return


def _auth_headers(auth: dict[str, Any]) -> dict[str, str]:
    mode = str(auth.get("mode") or "none")
    if mode == "none":
        return {}
    if mode == "static":
        name = str(auth.get("header_name") or "")
        value = str(auth.get("value") or "")
        if not name or not value:
            raise AppError(ErrorCategory.MCP_AUTH_REQUIRED, "MCP authorization is required.")
        return {name: value}
    if mode == "oauth":
        token = str(auth.get("access_token") or "")
        if not token:
            raise AppError(ErrorCategory.MCP_AUTH_REQUIRED, "MCP authorization is required.")
        token_type = str(auth.get("token_type") or "Bearer").strip() or "Bearer"
        return {"Authorization": f"{token_type} {token}"}
    raise AppError(ErrorCategory.MCP_AUTH_REQUIRED, "MCP authorization is required.")


def _merged_headers(
    auth: dict[str, Any], extra_headers: dict[str, str]
) -> dict[str, str]:
    result = _auth_headers(auth)
    seen = {name.casefold() for name in result}
    for raw_name, raw_value in extra_headers.items():
        name = str(raw_name)
        value = str(raw_value)
        if name.casefold() in seen:
            raise AppError(
                ErrorCategory.MCP_TOOL_INCOMPATIBLE,
                "An MCP argument header conflicts with authorization.",
            )
        seen.add(name.casefold())
        result[name] = value
    return result


def _gateway_error_category(code: str, *, outcome_unknown: bool) -> ErrorCategory:
    if outcome_unknown:
        return ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
    mapping = {
        "egress_target_blocked": ErrorCategory.EGRESS_TARGET_BLOCKED,
        "mcp_auth_required": ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
        "mcp_insufficient_scope": ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
        "mcp_protocol_unsupported": ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
        "mcp_server_unreachable": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "mcp_operation_timeout": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "operation_timeout": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "mcp_gateway_capacity": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "mcp_tool_incompatible": ErrorCategory.MCP_TOOL_INCOMPATIBLE,
        "mcp_tool_result_unsupported": ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
        "mcp_tool_not_found": ErrorCategory.MCP_TOOL_SET_CHANGED,
        "mcp_pagination_invalid": ErrorCategory.MCP_TOOL_SET_CHANGED,
        "mcp_tool_inventory_too_large": ErrorCategory.MCP_TOOL_LIMIT_REACHED,
        "mcp_arguments_too_large": ErrorCategory.MCP_TOOL_INCOMPATIBLE,
        "mcp_response_too_large": ErrorCategory.MCP_RESPONSE_TOO_LARGE,
        "mcp_session_binding_mismatch": ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
        "mcp_session_target_mismatch": ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
        "mcp_session_not_found": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "mcp_session_expired": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "mcp_session_capacity": ErrorCategory.MCP_SERVER_UNREACHABLE,
        "mcp_protocol_error": ErrorCategory.MCP_TOOL_CALL_FAILED,
    }
    return mapping.get(code, ErrorCategory.MCP_TOOL_CALL_FAILED)


def _safe_gateway_message(category: ErrorCategory) -> str:
    return {
        ErrorCategory.EGRESS_TARGET_BLOCKED: "The MCP target is blocked by egress policy.",
        ErrorCategory.MCP_REAUTHORIZATION_REQUIRED: "The MCP server must be reauthorized.",
        ErrorCategory.MCP_PROTOCOL_UNSUPPORTED: "The MCP protocol revision is unsupported.",
        ErrorCategory.MCP_SERVER_UNREACHABLE: "The MCP server could not be reached.",
        ErrorCategory.MCP_TOOL_INCOMPATIBLE: "The MCP tool uses an unsupported capability.",
        ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED: "The MCP tool returned an unsupported result.",
        ErrorCategory.MCP_RESPONSE_TOO_LARGE: (
            "The MCP server response exceeds the configured limit."
        ),
        ErrorCategory.MCP_TOOL_SET_CHANGED: "The MCP server tool inventory changed.",
        ErrorCategory.MCP_TOOL_LIMIT_REACHED: "The MCP server advertised too many tools.",
        ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN: "The MCP tool outcome could not be confirmed.",
    }.get(category, "The MCP tool call failed.")


def _safe_operation_id(prefix: str, value: uuid.UUID) -> str:
    return f"{prefix}:{value.hex}"[:128]


def _close_operation_id(operation_id: str) -> str:
    digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
    return f"close:{digest}"[:128]


def _caller_binding(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_handle(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_handle")
    if value is None:
        return None
    if not isinstance(value, str) or not 32 <= len(value) <= 128:
        raise AppError(
            ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
            "The MCP gateway returned an invalid legacy session handle.",
        )
    return value


def _dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _optional_text(value: Any) -> str | None:
    return str(value).strip()[:512] if value is not None and str(value).strip() else None


__all__ = [
    "HttpMcpGatewayClient",
    "McpToolCallRequest",
    "McpToolCallResult",
]
