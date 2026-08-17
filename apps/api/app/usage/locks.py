"""Workspace-scoped PostgreSQL advisory locks for quota mutations.

AI token metering (Phase 5B) uses the single-argument ``pg_advisory_xact_lock``
form with the first 8 UUID bytes. Expert and storage locks use the two-int
form so they do not serialize with AI reserve/settle.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


class LockNamespace(enum.IntEnum):
    EXPERTS = 2
    STORAGE = 3
    APP_COMMERCE = 4


def workspace_advisory_lock(
    db: Session,
    workspace_id: uuid.UUID,
    namespace: LockNamespace | int,
) -> None:
    """Take a transaction-scoped lock for one Workspace resource class."""
    ns = int(namespace)
    key1 = int.from_bytes(workspace_id.bytes[0:4], "big", signed=True)
    mixed = int.from_bytes(workspace_id.bytes[4:8], "big", signed=False) ^ (ns & 0xFFFFFFFF)
    key2 = mixed - 0x100000000 if mixed >= 0x80000000 else mixed
    db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})


def workspace_app_advisory_lock(
    db: Session,
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
) -> None:
    """Serialize App Store checkout/fulfill for one (workspace, app) pair."""
    ns = int(LockNamespace.APP_COMMERCE)
    key1 = int.from_bytes(workspace_id.bytes[0:4], "big", signed=True)
    mixed = (
        int.from_bytes(app_id.bytes[0:4], "big", signed=False)
        ^ int.from_bytes(app_id.bytes[4:8], "big", signed=False)
        ^ (ns & 0xFFFFFFFF)
    ) & 0xFFFFFFFF
    key2 = mixed - 0x100000000 if mixed >= 0x80000000 else mixed
    db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})
