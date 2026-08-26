"""Canonical MCP endpoint and advertised tool-definition normalization.

Only tool descriptors are normalized here. Tool result normalization belongs
to the runtime executor and intentionally lives outside this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from jsonschema import Draft202012Validator, SchemaError

from app.common.outbound_http import OutboundTargetBlocked, canonicalize_outbound_url
from app.core.errors import AppError, ErrorCategory
from app.mcp.constants import (
    MCP_ARGUMENT_HEADER_FORBIDDEN,
    MCP_NORMALIZATION_VERSION,
    MCP_TOOL_ALIAS_MAX_LENGTH,
    MCP_TOOL_DESCRIPTOR_MAX_BYTES,
    MCP_TOOL_NAME_MAX_LENGTH,
)
from app.mcp.types import McpCompatibilityStatus

_ALIAS_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_SECRET_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "key",
        "password",
        "secret",
        "token",
    }
)
_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "$dynamicRef",
        "$recursiveRef",
        "contentEncoding",
        "contentMediaType",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_UNSUPPORTED_CAPABILITY_KEYS = frozenset(
    {
        "input_required",
        "elicitation",
        "task",
        "tasks",
        "sampling",
        "roots",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedToolDefinition:
    tool_name: str
    llm_tool_name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]
    raw_definition: dict[str, Any]
    normalization_version: str
    compatibility_status: str
    compatibility_reason: str | None
    definition_hash: str


def canonicalize_mcp_url(
    value: str,
    *,
    allow_http: bool = False,
    allow_private_hostnames: bool = False,
) -> str:
    """Apply the shared syntactic egress policy and reject URL credentials."""

    try:
        canonical = canonicalize_outbound_url(
            value,
            allow_http=allow_http,
            allow_private_hostnames=allow_private_hostnames,
        )
    except OutboundTargetBlocked as exc:
        raise AppError(
            ErrorCategory.EGRESS_TARGET_BLOCKED,
            "The MCP server URL is not an allowed outbound target.",
            details={"reason": exc.code},
        ) from exc
    query_keys = {
        key.strip().casefold() for key, _ in parse_qsl(urlsplit(canonical.url).query)
    }
    if query_keys & _SECRET_QUERY_KEYS:
        raise AppError(
            ErrorCategory.EGRESS_TARGET_BLOCKED,
            "Credentials are not allowed in an MCP server URL.",
            details={"reason": "query_credentials_blocked"},
        )
    return canonical.url


def endpoint_host(canonical_url: str) -> str:
    """Return only a display-safe hostname, never path/query/user material."""

    return str(urlsplit(canonical_url).hostname or "")


def principal_fingerprint(
    *,
    server_url: str,
    resource_uri: str,
    auth_mode: str,
    issuer: str | None = None,
    client_id: str | None = None,
    external_subject: str | None = None,
    static_header_name: str | None = None,
) -> str:
    material = {
        "server_url": server_url,
        "resource_uri": resource_uri,
        "auth_mode": auth_mode,
        "issuer": issuer or "",
        "client_id": client_id or "",
        "external_subject": external_subject or "",
        "static_header_name": (static_header_name or "").casefold(),
    }
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def stable_tool_alias(connection_id: uuid.UUID, tool_name: str) -> str:
    cleaned = _ALIAS_CHARS.sub("_", tool_name).strip("_-") or "tool"
    if not cleaned[0].isalpha():
        cleaned = f"t_{cleaned}"
    suffix = hashlib.sha256(
        f"{connection_id}:{tool_name}".encode("utf-8")
    ).hexdigest()[:12]
    prefix_budget = MCP_TOOL_ALIAS_MAX_LENGTH - len("mcp__") - len(suffix)
    prefix = cleaned[:prefix_budget]
    return f"mcp_{prefix}_{suffix}"


def normalize_tool_definition(
    raw: Any,
    *,
    connection_id: uuid.UUID,
    protocol_version: str,
    malformed_ordinal: int = 0,
) -> NormalizedToolDefinition:
    """Normalize one untrusted tools/list descriptor without network resolution."""

    bounded, oversized = _bounded_json_object(raw)
    name = bounded.get("name")
    malformed_reason: str | None = None
    if not isinstance(name, str) or not name.strip() or len(name) > MCP_TOOL_NAME_MAX_LENGTH:
        digest = hashlib.sha256(_canonical_json(bounded)).hexdigest()[:16]
        name = f"__malformed_{malformed_ordinal}_{digest}"
        malformed_reason = "Tool name is missing or invalid."
    else:
        name = name.strip()

    title = _bounded_text(bounded.get("title"), 512)
    description = _bounded_text(bounded.get("description"), 8_000)
    input_schema = bounded.get("inputSchema", {})
    output_schema = bounded.get("outputSchema")
    annotations = bounded.get("annotations", {})

    if not isinstance(input_schema, dict):
        input_schema = {}
        malformed_reason = malformed_reason or "inputSchema must be an object."
    if output_schema is not None and not isinstance(output_schema, dict):
        output_schema = None
        malformed_reason = malformed_reason or "outputSchema must be an object."
    if not isinstance(annotations, dict):
        annotations = {}
        malformed_reason = malformed_reason or "annotations must be an object."

    compatibility = McpCompatibilityStatus.COMPATIBLE.value
    reason: str | None = None
    if malformed_reason or oversized:
        compatibility = McpCompatibilityStatus.MALFORMED.value
        reason = malformed_reason or "Tool descriptor exceeded the storage bound."
    else:
        try:
            unsupported_capability = _first_key(
                bounded, _UNSUPPORTED_CAPABILITY_KEYS
            )
            if unsupported_capability is not None:
                compatibility = McpCompatibilityStatus.UNSUPPORTED_CAPABILITY.value
                reason = f"Unsupported MCP capability: {unsupported_capability}."
            else:
                schema_reason = _schema_compatibility_reason(
                    input_schema, allow_argument_headers=True
                )
                if schema_reason is None and output_schema is not None:
                    schema_reason = _schema_compatibility_reason(
                        output_schema, allow_argument_headers=False
                    )
                if schema_reason is not None:
                    compatibility = McpCompatibilityStatus.UNSUPPORTED_SCHEMA.value
                    reason = schema_reason
        except RecursionError:
            compatibility = McpCompatibilityStatus.MALFORMED.value
            reason = "Tool descriptor nesting is too deep."

    # The full bounded descriptor is hashed, including model/execution-relevant
    # annotations, execution declarations, and safe metadata/header mappings.
    definition_material = {
        "protocol_version": protocol_version,
        "descriptor": bounded,
        "normalization_version": MCP_NORMALIZATION_VERSION,
    }
    definition_hash = hashlib.sha256(_canonical_json(definition_material)).hexdigest()
    return NormalizedToolDefinition(
        tool_name=name,
        llm_tool_name=stable_tool_alias(connection_id, name),
        title=title,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        annotations=annotations,
        raw_definition=bounded,
        normalization_version=MCP_NORMALIZATION_VERSION,
        compatibility_status=compatibility,
        compatibility_reason=reason,
        definition_hash=definition_hash,
    )


def _schema_compatibility_reason(
    schema: dict[str, Any], *, allow_argument_headers: bool
) -> str | None:
    if _contains_key(schema, "$ref"):
        return "$ref is unsupported for MCP tool schemas."
    unsupported = _first_key(schema, _UNSUPPORTED_SCHEMA_KEYS)
    if unsupported is not None:
        return f"Unsupported JSON Schema keyword: {unsupported}."
    dialect = schema.get("$schema")
    if dialect not in {None, "https://json-schema.org/draft/2020-12/schema"}:
        return "Only JSON Schema 2020-12 is supported."
    header_reason = _argument_header_compatibility_reason(
        schema, allow=allow_argument_headers
    )
    if header_reason is not None:
        return header_reason
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        return "The advertised JSON Schema is malformed."
    return None


def _argument_header_compatibility_reason(
    schema: dict[str, Any], *, allow: bool
) -> str | None:
    found: list[tuple[tuple[str, ...], Any, dict[str, Any]]] = []

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            if "x-mcp-header" in value:
                found.append((path, value.get("x-mcp-header"), value))
            for key, child in value.items():
                visit(child, (*path, str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*path, str(index)))

    visit(schema, ())
    if not found:
        return None
    if not allow:
        return "x-mcp-header is supported only on input-schema properties."
    required = schema.get("required")
    required_names = set(required) if isinstance(required, list) else set()
    seen_headers: set[str] = set()
    for path, raw_header, property_schema in found:
        if len(path) != 2 or path[0] != "properties":
            return "x-mcp-header is supported only on top-level input properties."
        property_name = path[1]
        if property_name not in required_names:
            return "x-mcp-header properties must be required."
        if property_schema.get("type") != "string":
            return "x-mcp-header properties must have type string."
        if not isinstance(raw_header, str):
            return "x-mcp-header must name a request header."
        header = raw_header.strip()
        lowered = header.casefold()
        if (
            not header
            or len(header) > 64
            or not _HEADER_NAME.fullmatch(header)
            or lowered in MCP_ARGUMENT_HEADER_FORBIDDEN
            or lowered.startswith(("mcp-", "sec-", "proxy-", "x-forwarded-"))
        ):
            return "x-mcp-header names a forbidden request header."
        if lowered in seen_headers:
            return "x-mcp-header names must be unique."
        seen_headers.add(lowered)
    return None


def _bounded_json_object(raw: Any) -> tuple[dict[str, Any], bool]:
    if not isinstance(raw, dict):
        raw = {"_malformed_value_type": type(raw).__name__}
    try:
        encoded = _canonical_json(raw)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return {"_malformed": "not_json_serializable"}, False
    if len(encoded) <= MCP_TOOL_DESCRIPTOR_MAX_BYTES:
        return json.loads(encoded), False
    # Never store a partially decoded attacker-controlled descriptor. Keep only
    # a deterministic digest and safe size for inventory/audit visibility.
    return {
        "_malformed": "descriptor_too_large",
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "byte_size": len(encoded),
    }, True


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:limit]


def _contains_key(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        return needle in value or any(_contains_key(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, needle) for item in value)
    return False


def _first_key(value: Any, needles: frozenset[str]) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in needles:
                return key
            nested = _first_key(item, needles)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _first_key(item, needles)
            if nested is not None:
                return nested
    return None


__all__ = [
    "NormalizedToolDefinition",
    "canonicalize_mcp_url",
    "endpoint_host",
    "normalize_tool_definition",
    "principal_fingerprint",
    "stable_tool_alias",
]
