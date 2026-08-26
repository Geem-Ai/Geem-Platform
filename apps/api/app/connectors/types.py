"""Connector domain enums (Phase 9C)."""

from __future__ import annotations

import enum


class ConnectorKind(str, enum.Enum):
    KNOWLEDGE_SOURCE = "knowledge_source"
    CHANNEL = "channel"
    TOOL_SOURCE = "tool_source"


class ConnectorAuthMode(str, enum.Enum):
    NONE = "none"
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    CUSTOM = "custom"


class ConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    CONNECTING = "connecting"
    ACTIVE = "active"
    DEGRADED = "degraded"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    REVOKED = "revoked"


class ConnectionHealth(str, enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class SyncTrigger(str, enum.Enum):
    INITIAL = "initial"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    RECONCILE = "reconcile"


class SyncRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConnectorItemType(str, enum.Enum):
    FILE = "file"
    FOLDER = "folder"
    OTHER = "other"


class ConnectorItemStatus(str, enum.Enum):
    ACTIVE = "active"
    DELETED = "deleted"
    UNAVAILABLE = "unavailable"


class WebhookEventStatus(str, enum.Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


# Active / countable toward the ``connections`` entitlement.
CONNECTION_LIMIT_STATUSES: frozenset[str] = frozenset(
    {
        ConnectionStatus.PENDING.value,
        ConnectionStatus.CONNECTING.value,
        ConnectionStatus.ACTIVE.value,
        ConnectionStatus.DEGRADED.value,
        ConnectionStatus.ERROR.value,
    }
)

# Statuses that may execute provider operations (sync/health).
CONNECTION_USABLE_STATUSES: frozenset[str] = frozenset(
    {
        ConnectionStatus.ACTIVE.value,
        ConnectionStatus.DEGRADED.value,
    }
)

# Allowed lifecycle transitions (from → to).
CONNECTION_TRANSITIONS: dict[str, frozenset[str]] = {
    ConnectionStatus.PENDING.value: frozenset(
        {
            ConnectionStatus.CONNECTING.value,
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.ERROR.value,
        }
    ),
    ConnectionStatus.CONNECTING.value: frozenset(
        {
            ConnectionStatus.ACTIVE.value,
            ConnectionStatus.ERROR.value,
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
        }
    ),
    ConnectionStatus.ACTIVE.value: frozenset(
        {
            ConnectionStatus.DEGRADED.value,
            ConnectionStatus.ERROR.value,
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
            ConnectionStatus.CONNECTING.value,  # reconnect
        }
    ),
    ConnectionStatus.DEGRADED.value: frozenset(
        {
            ConnectionStatus.ACTIVE.value,
            ConnectionStatus.ERROR.value,
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
            ConnectionStatus.CONNECTING.value,
        }
    ),
    ConnectionStatus.ERROR.value: frozenset(
        {
            ConnectionStatus.CONNECTING.value,
            ConnectionStatus.ACTIVE.value,
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
            ConnectionStatus.DEGRADED.value,
        }
    ),
    ConnectionStatus.DISCONNECTED.value: frozenset(
        {
            ConnectionStatus.CONNECTING.value,  # reconnect
            ConnectionStatus.PENDING.value,
        }
    ),
    ConnectionStatus.REVOKED.value: frozenset(
        {
            ConnectionStatus.CONNECTING.value,  # reauthorize
            ConnectionStatus.DISCONNECTED.value,
        }
    ),
}
