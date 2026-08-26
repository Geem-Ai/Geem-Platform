from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.core.errors import AppError, ErrorCategory
from app.mcp.executor import _validate_argument_header_values
from app.mcp.normalization import canonicalize_mcp_url, normalize_tool_definition
from app.mcp.schemas import McpServerCreateIn
from app.mcp.types import McpCompatibilityStatus


def test_tool_definition_hash_covers_complete_descriptor() -> None:
    connection_id = uuid.uuid4()
    first = normalize_tool_definition(
        {
            "name": "search",
            "description": "Search records",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
            "annotations": {"readOnlyHint": True},
        },
        connection_id=connection_id,
        protocol_version="2026-07-28",
    )
    second = normalize_tool_definition(
        {
            "name": "search",
            "description": "Search records",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
            "annotations": {"readOnlyHint": False},
        },
        connection_id=connection_id,
        protocol_version="2026-07-28",
    )

    assert first.definition_hash != second.definition_hash
    assert first.compatibility_status == McpCompatibilityStatus.COMPATIBLE.value


def test_remote_schema_reference_is_inventory_visible_but_incompatible() -> None:
    normalized = normalize_tool_definition(
        {"name": "unsafe", "inputSchema": {"$ref": "https://attacker.test/schema"}},
        connection_id=uuid.uuid4(),
        protocol_version="2026-07-28",
    )
    assert normalized.compatibility_status == McpCompatibilityStatus.UNSUPPORTED_SCHEMA.value
    assert "$ref" in (normalized.compatibility_reason or "")


def test_url_credentials_are_rejected() -> None:
    with pytest.raises(AppError) as caught:
        canonicalize_mcp_url("https://mcp.example/tools?access_token=secret")
    assert caught.value.category == ErrorCategory.EGRESS_TARGET_BLOCKED


def test_static_auth_rejects_cookie_and_extra_transport_fields() -> None:
    with pytest.raises(ValidationError):
        McpServerCreateIn.model_validate(
            {
                "display_name": "Unsafe",
                "server_url": "https://mcp.example/tools",
                "command": "node",
                "auth": {"mode": "static", "header_name": "Cookie", "secret": "x"},
            }
        )


def test_required_top_level_argument_header_is_hash_pinned_for_sdk_transport() -> None:
    schema = {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "x-mcp-header": "X-Tenant-Scope"},
            "query": {"type": "string"},
        },
        "required": ["tenant", "query"],
        "additionalProperties": False,
    }
    normalized = normalize_tool_definition(
        {"name": "scoped_search", "inputSchema": schema},
        connection_id=uuid.uuid4(),
        protocol_version="2026-07-28",
    )
    assert normalized.compatibility_status == McpCompatibilityStatus.COMPATIBLE.value

    arguments = {"tenant": "acme", "query": "hello"}
    _validate_argument_header_values(arguments, normalized.input_schema)
    # The API must not strip or project annotated arguments. The gateway SDK
    # owns the protocol-defined Mcp-Param-* mirroring after tools/list.
    assert arguments == {"tenant": "acme", "query": "hello"}

    changed = normalize_tool_definition(
        {
            "name": "scoped_search",
            "inputSchema": {
                **schema,
                "properties": {
                    **schema["properties"],
                    "tenant": {
                        "type": "string",
                        "x-mcp-header": "X-Other-Scope",
                    },
                },
            },
        },
        connection_id=uuid.uuid4(),
        protocol_version="2026-07-28",
    )
    assert changed.definition_hash != normalized.definition_hash


@pytest.mark.parametrize(
    "schema",
    [
        {
            "type": "object",
            "properties": {
                "tenant": {"type": "string", "x-mcp-header": "Authorization"}
            },
            "required": ["tenant"],
        },
        {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {
                        "tenant": {"type": "string", "x-mcp-header": "X-Tenant"}
                    },
                }
            },
            "required": ["nested"],
        },
        {
            "type": "object",
            "properties": {
                "tenant": {"type": "string", "x-mcp-header": "X-Tenant"}
            },
        },
    ],
)
def test_unsafe_argument_header_mapping_is_inventory_visible_but_incompatible(
    schema: dict,
) -> None:
    normalized = normalize_tool_definition(
        {"name": "unsafe_header", "inputSchema": schema},
        connection_id=uuid.uuid4(),
        protocol_version="2026-07-28",
    )
    assert normalized.compatibility_status == McpCompatibilityStatus.UNSUPPORTED_SCHEMA.value
    assert "x-mcp-header" in (normalized.compatibility_reason or "")


def test_argument_header_value_rejects_control_and_non_latin1() -> None:
    schema = {
        "type": "object",
        "properties": {
            "tenant": {"type": "string", "x-mcp-header": "X-Tenant"}
        },
        "required": ["tenant"],
    }
    for unsafe in ("acme\r\nInjected: yes", "شركة"):
        with pytest.raises(AppError) as caught:
            _validate_argument_header_values({"tenant": unsafe}, schema)
        assert caught.value.category == ErrorCategory.MCP_TOOL_INCOMPATIBLE
