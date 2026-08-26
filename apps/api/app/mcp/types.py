"""MCP persistence and authorization enums."""

from __future__ import annotations

from enum import StrEnum


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


__all__ = [
    "McpAuthMode",
    "McpCompatibilityStatus",
    "McpGrantState",
    "McpOAuthRegistrationStrategy",
    "McpSessionMode",
    "McpToolClassification",
    "McpToolStatus",
]
