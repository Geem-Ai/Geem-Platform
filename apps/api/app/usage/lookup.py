"""Optional UsageEvent lookup by logical UUID (not a database FK).

``messages.usage_event_id`` stores only the event UUID. Partitioned
``usage_events`` uses primary key ``(id, created_at)``, so there is no FK.
After 13-month raw retention, the UUID may point at nothing. Callers must
treat a missing row as normal.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UsageEvent


def get_usage_event_by_id(db: Session, event_id: uuid.UUID | None) -> UsageEvent | None:
    """Return the telemetry row if it still exists, otherwise ``None``.

    Never use ``Session.get(UsageEvent, event_id)`` — identity key is composite.
    """
    if event_id is None:
        return None
    return db.scalars(
        select(UsageEvent).where(UsageEvent.id == event_id).limit(1)
    ).first()
