from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.models import Session as AuthSession
from app.identity.models import User
from app.identity.security import normalize_email


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )

    def get_by_email(self, email: str) -> User | None:
        normalized = normalize_email(email)
        return self.db.scalar(
            select(User).where(User.email == normalized, User.deleted_at.is_(None))
        )

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user


class SessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, session_id: uuid.UUID) -> AuthSession | None:
        return self.db.get(AuthSession, session_id)

    def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return self.db.scalar(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )

    def create(self, session: AuthSession) -> AuthSession:
        self.db.add(session)
        self.db.flush()
        return session

    def revoke(self, session: AuthSession, *, when: datetime | None = None) -> None:
        session.revoked_at = when or datetime.now(timezone.utc)

    def revoke_all_for_user(self, user_id: uuid.UUID, *, when: datetime | None = None) -> int:
        now = when or datetime.now(timezone.utc)
        sessions = self.db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        ).all()
        for s in sessions:
            s.revoked_at = now
        return len(sessions)

    def touch(self, session: AuthSession) -> None:
        session.last_used_at = datetime.now(timezone.utc)
