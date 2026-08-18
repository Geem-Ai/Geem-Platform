"""Advisory locks for invitation uniqueness (workspace + email)."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

# Distinct from usage (2–4) and connector (5–6) namespaces.
INVITATION_LOCK_NS = 7


def workspace_invitation_email_lock(
    db: Session,
    workspace_id: uuid.UUID,
    email: str,
) -> None:
    """Serialize create/resend for one (workspace, normalized email) pair."""
    digest = hashlib.sha256(f"{workspace_id.hex}:{email}".encode("utf-8")).digest()
    key1 = int.from_bytes(workspace_id.bytes[0:4], "big", signed=True)
    mixed = (
        int.from_bytes(digest[0:4], "big", signed=False) ^ (INVITATION_LOCK_NS & 0xFFFFFFFF)
    ) & 0xFFFFFFFF
    key2 = mixed - 0x100000000 if mixed >= 0x80000000 else mixed
    db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})
