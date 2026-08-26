"""Bounded wire contract for one outbound operation."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CALLER_BINDING = re.compile(r"^[a-f0-9]{64}$")
_SESSION_HANDLE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_MCP_RESERVED_HEADERS = frozenset(
    {
        "accept",
        "content-type",
        "last-event-id",
        "mcp-method",
        "mcp-name",
        "mcp-protocol-version",
        "mcp-session-id",
    }
)
_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "accept-encoding",
        "connection",
        "content-length",
        "cookie",
        "forwarded",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "set-cookie",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
    }
)


def _validated_headers(value: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    seen: set[str] = set()
    for name, header_value in value.items():
        lower = name.lower()
        if (
            not _HEADER_NAME.fullmatch(name)
            or lower in _FORBIDDEN_REQUEST_HEADERS
            or lower in seen
            or lower.startswith("sec-")
        ):
            raise ValueError("request contains a forbidden header")
        if not isinstance(header_value, str) or any(
            (ord(char) < 0x20 and char != "\t") or ord(char) == 0x7F
            for char in header_value
        ):
            raise ValueError("request contains an invalid header value")
        try:
            header_value.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError("request header values must be latin-1") from exc
        seen.add(lower)
        normalized[name] = header_value
    return normalized


class OutboundOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    operation_id: str = Field(min_length=1, max_length=128)
    method: Literal["GET", "HEAD", "POST"]
    url: str = Field(min_length=1, max_length=2_048)
    headers: dict[str, str] = Field(default_factory=dict)
    body_base64: str | None = None
    follow_redirects: bool = False

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str) -> str:
        if not _OPERATION_ID.fullmatch(value):
            raise ValueError("operation_id has an invalid format")
        return value

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return _validated_headers(value)

    @model_validator(mode="after")
    def validate_method_shape(self) -> "OutboundOperationRequest":
        if self.method in {"GET", "HEAD"} and self.body_base64 is not None:
            raise ValueError("GET and HEAD requests cannot carry a body")
        if self.follow_redirects and self.method not in {"GET", "HEAD"}:
            raise ValueError("redirect following is limited to safe methods")
        return self

    def decoded_body(self, *, max_bytes: int) -> bytes:
        if self.body_base64 is None:
            return b""
        try:
            value = base64.b64decode(self.body_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("body_base64 is invalid") from exc
        if len(value) > max_bytes:
            raise ValueError("request body exceeds the configured limit")
        return value


class OutboundOperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    status_code: int
    headers: dict[str, str]
    body_base64: str
    redirects_followed: int
    final_origin_digest: str


class TargetValidationRequest(BaseModel):
    """Resolve-only target preflight; credentials and payloads are impossible."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    operation_id: str = Field(min_length=1, max_length=128)
    target_url: str = Field(min_length=1, max_length=2_048)
    caller_binding: str = Field(min_length=64, max_length=64)
    deadline_seconds: float | None = Field(default=None, gt=0, le=180)
    deadline_unix_ms: int | None = Field(default=None, gt=0)

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str) -> str:
        if not _OPERATION_ID.fullmatch(value):
            raise ValueError("operation_id has an invalid format")
        return value

    @field_validator("caller_binding")
    @classmethod
    def validate_caller_binding(cls, value: str) -> str:
        if not _CALLER_BINDING.fullmatch(value):
            raise ValueError("caller_binding must be a lowercase SHA-256 digest")
        return value


class TargetValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    origin_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class McpOperationRequest(BaseModel):
    """SDK-mediated MCP operation accepted only over the mTLS listener."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    operation_id: str = Field(min_length=1, max_length=128)
    operation: Literal["discover", "tools_list", "tools_call", "session_close"]
    target_url: str | None = Field(default=None, min_length=1, max_length=2_048)
    headers: dict[str, str] = Field(default_factory=dict)
    mode: Literal["auto", "legacy", "2026-07-28"] = "auto"
    caller_binding: str = Field(min_length=64, max_length=64)
    session_handle: str | None = Field(default=None, min_length=32, max_length=128)
    cursor: str | None = Field(default=None, max_length=1_024)
    tool_name: str | None = Field(default=None, min_length=1, max_length=256)
    arguments: dict[str, object] | None = None
    write: bool = False
    deadline_seconds: float | None = Field(default=None, gt=0, le=180)
    deadline_unix_ms: int | None = Field(default=None, gt=0)

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str) -> str:
        if not _OPERATION_ID.fullmatch(value):
            raise ValueError("operation_id has an invalid format")
        return value

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = _validated_headers(value)
        if any(
            name.lower() in _MCP_RESERVED_HEADERS
            or name.lower().startswith("mcp-param-")
            for name in normalized
        ):
            raise ValueError("request contains an MCP protocol-controlled header")
        return normalized

    @field_validator("caller_binding")
    @classmethod
    def validate_caller_binding(cls, value: str) -> str:
        if not _CALLER_BINDING.fullmatch(value):
            raise ValueError("caller_binding must be a lowercase SHA-256 digest")
        return value

    @field_validator("session_handle")
    @classmethod
    def validate_session_handle(cls, value: str | None) -> str | None:
        if value is not None and not _SESSION_HANDLE.fullmatch(value):
            raise ValueError("session_handle has an invalid format")
        return value

    @field_validator("arguments")
    @classmethod
    def validate_arguments_json(cls, value: dict[str, object] | None):
        if value is None:
            return None
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("arguments must be finite JSON") from exc
        return value

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "McpOperationRequest":
        if self.operation != "session_close" and self.target_url is None:
            raise ValueError("target_url is required for MCP operations")
        if self.operation == "discover":
            if (
                self.session_handle is not None
                or self.cursor is not None
                or self.tool_name is not None
                or self.arguments is not None
            ):
                raise ValueError(
                    "discover does not accept session_handle, cursor, tool_name, or arguments"
                )
            if self.write:
                raise ValueError("discover cannot be a write")
        elif self.operation == "tools_list":
            if self.tool_name is not None or self.arguments is not None or self.write:
                raise ValueError("tools_list accepts only an optional cursor")
        elif self.operation == "tools_call":
            if self.cursor is not None or not self.tool_name:
                raise ValueError("tools_call requires tool_name and no cursor")
        elif self.operation == "session_close":
            if (
                self.session_handle is None
                or self.target_url is not None
                or self.headers
                or self.cursor is not None
                or self.tool_name is not None
                or self.arguments is not None
                or self.write
            ):
                raise ValueError(
                    "session_close accepts only operation_id, caller_binding, "
                    "session_handle, and mode"
                )
        return self


class McpOperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    negotiated_protocol_version: str
    session_mode: Literal["modern", "legacy"]
    capabilities: dict[str, object]
    server_info: dict[str, object] | None = None
    supported_versions: list[str] = Field(default_factory=list)
    session_handle: str | None = None
    session_expires_in_seconds: int | None = None
    closed: bool = False
    tools: list[dict[str, object]] | None = None
    next_cursor: str | None = None
    result: dict[str, object] | None = None
    outcome_unknown: bool = False


class GatewayErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False


class GatewayErrorResponse(BaseModel):
    error: GatewayErrorBody


__all__ = [
    "GatewayErrorBody",
    "GatewayErrorResponse",
    "McpOperationRequest",
    "McpOperationResponse",
    "OutboundOperationRequest",
    "OutboundOperationResponse",
]
