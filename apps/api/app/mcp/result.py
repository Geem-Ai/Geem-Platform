"""Bounded, prompt-isolated MCP tool-result normalization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

_UNSUPPORTED_BLOCK_TYPES = frozenset(
    {"image", "audio", "resource", "resource_link", "embedded_resource"}
)


@dataclass(frozen=True, slots=True)
class NormalizedToolResult:
    model_content: str
    is_error: bool
    transport_bytes: int
    content_types: tuple[str, ...]
    unsupported_blocks: tuple[dict[str, Any], ...]


def normalize_tool_result(
    payload: dict[str, Any],
    *,
    output_schema: dict[str, Any] | None,
    settings: Settings,
) -> NormalizedToolResult:
    """Validate supported result content without fetching remote resources."""

    if not isinstance(payload, dict):
        raise AppError(
            ErrorCategory.MCP_TOOL_CALL_FAILED,
            "The MCP server returned a malformed tool result.",
        )
    try:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppError(
            ErrorCategory.MCP_TOOL_CALL_FAILED,
            "The MCP server returned a non-JSON tool result.",
        ) from exc
    byte_cap = int(settings.mcp_tool_result_max_bytes)
    if len(raw) > byte_cap:
        raise AppError(
            ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
            "The MCP tool result exceeded the transport size limit.",
            details={"max_bytes": byte_cap},
        )

    structured = payload.get("structuredContent")
    if structured is None:
        structured = payload.get("structured_content")
    if structured is not None:
        _validate_structured_output(structured, output_schema)

    texts: list[str] = []
    types: list[str] = []
    unsupported: list[dict[str, Any]] = []
    content = payload.get("content") or []
    if not isinstance(content, list):
        raise AppError(
            ErrorCategory.MCP_TOOL_CALL_FAILED,
            "The MCP tool result content must be an array.",
        )
    for block in content:
        if not isinstance(block, dict):
            unsupported.append({"type": "malformed", "size": 0})
            continue
        kind = str(block.get("type") or "unknown").strip().lower()
        types.append(kind)
        if kind == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
            continue
        if kind in _UNSUPPORTED_BLOCK_TYPES or kind != "text":
            unsupported.append(
                {
                    "type": kind[:64],
                    "size": _safe_block_size(block),
                }
            )

    if structured is not None:
        useful = json.dumps(
            structured,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        content_kind = "structured_json"
    else:
        useful = "\n".join(texts)
        content_kind = "text"
    if not useful and unsupported:
        raise AppError(
            ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
            "The MCP tool returned only unsupported content blocks.",
            details={"content_types": sorted(set(types))},
        )

    char_cap = int(settings.mcp_tool_result_max_chars)
    clipped = useful[:char_cap]
    envelope = {
        "content_kind": content_kind,
        "is_error": bool(payload.get("isError", payload.get("is_error", False))),
        "truncated": len(useful) > len(clipped),
        "value": clipped,
    }
    model_content = (
        "<untrusted_mcp_tool_result>\n"
        + json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
        + "\n</untrusted_mcp_tool_result>"
    )
    return NormalizedToolResult(
        model_content=model_content,
        is_error=envelope["is_error"],
        transport_bytes=len(raw),
        content_types=tuple(types),
        unsupported_blocks=tuple(unsupported),
    )


def _validate_structured_output(
    value: Any,
    output_schema: dict[str, Any] | None,
) -> None:
    if output_schema is None:
        return
    if not isinstance(output_schema, dict):
        raise AppError(
            ErrorCategory.MCP_TOOL_INCOMPATIBLE,
            "The MCP tool output schema is invalid.",
        )
    _reject_remote_refs(output_schema)
    try:
        Draft202012Validator.check_schema(output_schema)
        Draft202012Validator(output_schema).validate(value)
    except (SchemaError, ValidationError) as exc:
        raise AppError(
            ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
            "The MCP structured result did not match its reviewed output schema.",
        ) from exc


def _reject_remote_refs(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"$ref", "$dynamicRef"} and (
                not isinstance(value, str) or not value.startswith("#")
            ):
                raise AppError(
                    ErrorCategory.MCP_TOOL_INCOMPATIBLE,
                    "Remote JSON Schema references are not supported.",
                )
            _reject_remote_refs(value)
    elif isinstance(node, list):
        for value in node:
            _reject_remote_refs(value)


def _safe_block_size(block: dict[str, Any]) -> int:
    try:
        return len(
            json.dumps(block, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError):
        return 0


__all__ = ["NormalizedToolResult", "normalize_tool_result"]
