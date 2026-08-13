"""API-key persistence. Lookups are hash-based; plaintext is never queried."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey

LAST_USED_MIN_INTERVAL = timedelta(seconds=60)


class ApiKeyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, api_key_id: uuid.UUID) -> ApiKey | None:
        return self.db.get(ApiKey, api_key_id)

    def get_by_id_for_workspace(
        self, workspace_id: uuid.UUID, api_key_id: uuid.UUID
    ) -> ApiKey | None:
        return self.db.scalar(
            select(ApiKey).where(
                ApiKey.id == api_key_id,
                ApiKey.workspace_id == workspace_id,
            )
        )

    def get_by_secret_hash(self, secret_hash: str) -> ApiKey | None:
        return self.db.scalar(select(ApiKey).where(ApiKey.secret_hash == secret_hash))

    def list_for_workspace(self, workspace_id: uuid.UUID) -> list[ApiKey]:
        return list(
            self.db.scalars(
                select(ApiKey)
                .where(ApiKey.workspace_id == workspace_id)
                .order_by(ApiKey.created_at.desc())
            )
        )

    def create(self, api_key: ApiKey) -> ApiKey:
        self.db.add(api_key)
        self.db.flush()
        return api_key

    def touch_last_used(self, api_key_id: uuid.UUID) -> None:
        """Update last_used_at at most once per LAST_USED_MIN_INTERVAL."""
        now = datetime.now(timezone.utc)
        cutoff = now - LAST_USED_MIN_INTERVAL
        self.db.execute(
            update(ApiKey)
            .where(ApiKey.id == api_key_id)
            .where(or_(ApiKey.last_used_at.is_(None), ApiKey.last_used_at <= cutoff))
            .values(last_used_at=now)
        )
