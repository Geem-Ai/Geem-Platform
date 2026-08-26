"""MCP persistence and authorization enums."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


MCP_BOOLEAN_ANNOTATION_KEYS = frozenset(
    {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
)


class McpAuthMode(StrEnum):
    NONE = "none"
    STATIC = "static"
    OAUTH = "oauth"


class McpOAuthRegistrationStrategy(StrEnum):
    CIMD = "cimd"
    PRE_REGISTERED = "pre_registered"
    DYNAMIC_REGISTRATION = "dynamic_registration"


class McpCompatibilityStatus(StrEnum):
    COMPATIBLE = "compatible"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    MALFORMED = "malformed"


class McpToolClassification(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
    UNKNOWN = "unknown"


class McpToolStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    WITHDRAWN = "withdrawn"


class McpGrantState(StrEnum):
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    REVOKED = "revoked"
    STALE_DEFINITION = "stale_definition"
    STALE_CLASSIFICATION = "stale_classification"
    STALE_PRINCIPAL = "stale_principal"


class McpSessionMode(StrEnum):
    STATELESS = "stateless"
    STREAMABLE_HTTP_SESSION = "streamable_http_session"
    LEGACY_HTTP_SSE = "legacy_http_sse"


def annotations_forbid_read_only(
    annotations: Mapping[str, Any] | None,
) -> bool:
    """Return whether remote hints explicitly contradict a read-only review.

    MCP annotations are untrusted hints and can never authorize a tool.  An
    mutating/destructive hint, or a malformed known safety hint, can make a
    read-only classification unsafe, so runtime and management paths fail
    closed.
    """

    if not isinstance(annotations, Mapping):
        return False
    if any(
        key in annotations and not isinstance(annotations[key], bool)
        for key in MCP_BOOLEAN_ANNOTATION_KEYS
    ):
        return True
    return (
        annotations.get("readOnlyHint") is False
        or annotations.get("destructiveHint") is True
    )


__all__ = [
    "McpAuthMode",
    "MCP_BOOLEAN_ANNOTATION_KEYS",
    "McpCompatibilityStatus",
    "McpGrantState",
    "McpOAuthRegistrationStrategy",
    "McpSessionMode",
    "McpToolClassification",
    "McpToolStatus",
    "annotations_forbid_read_only",
]
