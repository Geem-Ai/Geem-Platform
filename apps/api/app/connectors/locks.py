"""Advisory locks for connector connection limits and sync concurrency."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.usage.locks import LockNamespace


# Extend lock namespaces without colliding with experts/storage/commerce.
class ConnectorLockNamespace:
    CONNECTIONS = 5
    SYNC = 6


def workspace_app_connection_lock(
    db: Session,
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
) -> None:
    """Serialize connection create against the ``connections`` entitlement."""
    ns = ConnectorLockNamespace.CONNECTIONS
    key1 = int.from_bytes(workspace_id.bytes[0:4], "big", signed=True)
    mixed = (
        int.from_bytes(app_id.bytes[0:4], "big", signed=False)
        ^ int.from_bytes(app_id.bytes[4:8], "big", signed=False)
        ^ (ns & 0xFFFFFFFF)
    ) & 0xFFFFFFFF
    key2 = mixed - 0x100000000 if mixed >= 0x80000000 else mixed
    db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})


def connection_sync_lock(
    db: Session,
    connection_id: uuid.UUID,
) -> None:
    """Serialize sync runs for one connection (transaction-scoped)."""
    ns = ConnectorLockNamespace.SYNC
    key1 = int.from_bytes(connection_id.bytes[0:4], "big", signed=True)
    mixed = (
        int.from_bytes(connection_id.bytes[4:8], "big", signed=False) ^ (ns & 0xFFFFFFFF)
    ) & 0xFFFFFFFF
    key2 = mixed - 0x100000000 if mixed >= 0x80000000 else mixed
    db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})


# Re-export for callers that already import LockNamespace from usage.
__all__ = [
    "ConnectorLockNamespace",
    "LockNamespace",
    "workspace_app_connection_lock",
    "connection_sync_lock",
]
