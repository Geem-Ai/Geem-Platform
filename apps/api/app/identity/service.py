from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import PlatformRole, Session as AuthSession, User, UserStatus
from app.identity.repository import SessionRepository, UserRepository
from app.identity.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    normalize_email,
    validate_password,
    verify_password,
)


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    session_id: uuid.UUID


class AuthService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def register(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise AppError(ErrorCategory.VALIDATION, "Invalid email address.")
        if self.users.get_by_email(normalized) is not None:
            raise AppError(ErrorCategory.EMAIL_ALREADY_EXISTS, "Email is already registered.")

        validate_password(password)
        user = User(
            email=normalized,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE.value,
            platform_role=PlatformRole.NONE.value,
        )
        self.users.create(user)
        tokens = self._issue_session(user, user_agent=user_agent, ip_address=ip_address)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(ErrorCategory.EMAIL_ALREADY_EXISTS, "Email is already registered.") from exc
        security_log("auth.register", user_id=str(user.id), email=normalized)
        return user, tokens

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        normalized = normalize_email(email)
        user = self.users.get_by_email(normalized)
        # Equalize timing when user is missing/disabled by verifying against a dummy hash.
        if user is None or user.status != UserStatus.ACTIVE.value:
            verify_password(password, DUMMY_PASSWORD_HASH)
            security_log("auth.login_failed", email=normalized, reason="unknown_or_disabled")
            raise AppError(ErrorCategory.INVALID_CREDENTIALS, "Invalid email or password.")

        if not verify_password(password, user.password_hash):
            security_log("auth.login_failed", user_id=str(user.id), reason="bad_password")
            raise AppError(ErrorCategory.INVALID_CREDENTIALS, "Invalid email or password.")

        tokens = self._issue_session(user, user_agent=user_agent, ip_address=ip_address)
        self.db.commit()
        security_log("auth.login_success", user_id=str(user.id))
        return user, tokens

    def refresh(
        self,
        *,
        raw_refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        token_hash = hash_refresh_token(raw_refresh_token)
        session = self.sessions.get_by_token_hash(token_hash)
        if session is None:
            security_log("auth.refresh_failed", reason="unknown_token")
            raise AppError(ErrorCategory.SESSION_REVOKED, "Session is invalid or revoked.")

        now = datetime.now(timezone.utc)
        if session.revoked_at is not None:
            # Multi-tab / concurrent refresh: within grace, continue from replacement tip.
            # Delayed reuse after grace (or no valid tip) → revoke session family (theft).
            tip = self._replacement_tip(session)
            grace = timedelta(seconds=self.settings.refresh_reuse_grace_seconds)
            within_grace = (
                tip is not None
                and tip.revoked_at is None
                and tip.expires_at > now
                and session.revoked_at >= now - grace
            )
            if within_grace and tip is not None:
                security_log(
                    "auth.refresh_reuse_grace",
                    user_id=str(session.user_id),
                    session_id=str(session.id),
                    tip_session_id=str(tip.id),
                )
                session = tip
            else:
                self.sessions.revoke_all_for_user(session.user_id, when=now)
                self.db.commit()
                security_log(
                    "auth.refresh_replay",
                    user_id=str(session.user_id),
                    session_id=str(session.id),
                )
                raise AppError(ErrorCategory.SESSION_REVOKED, "Session is invalid or revoked.")

        if session.expires_at <= now:
            self.sessions.revoke(session, when=now)
            self.db.commit()
            security_log("auth.refresh_expired", session_id=str(session.id))
            raise AppError(ErrorCategory.SESSION_EXPIRED, "Session expired.")

        user = self.users.get_by_id(session.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            self.sessions.revoke(session, when=now)
            self.db.commit()
            raise AppError(ErrorCategory.UNAUTHORIZED, "User is not active.")

        return self._rotate_session(
            user,
            session,
            user_agent=user_agent,
            ip_address=ip_address,
            now=now,
        )

    def _replacement_tip(self, session: AuthSession) -> AuthSession | None:
        """Follow replaced_by links to the newest session in the rotation chain."""
        seen: set[uuid.UUID] = set()
        current: AuthSession | None = session
        tip: AuthSession | None = None
        while current is not None and current.replaced_by_session_id is not None:
            nxt_id = current.replaced_by_session_id
            if nxt_id in seen:
                break
            seen.add(nxt_id)
            nxt = self.sessions.get_by_id(nxt_id)
            if nxt is None:
                break
            tip = nxt
            current = nxt
        return tip

    def _rotate_session(
        self,
        user: User,
        session: AuthSession,
        *,
        user_agent: str | None,
        ip_address: str | None,
        now: datetime,
    ) -> tuple[User, AuthTokens]:
        new_raw = generate_refresh_token()
        new_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(new_raw),
            user_agent=user_agent or session.user_agent,
            ip_address=ip_address or session.ip_address,
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            last_used_at=now,
        )
        self.sessions.create(new_session)
        self.sessions.revoke(session, when=now)
        session.replaced_by_session_id = new_session.id

        access, access_exp = create_access_token(
            user_id=str(user.id),
            platform_role=user.platform_role,
            session_id=str(new_session.id),
            settings=self.settings,
        )
        self.db.commit()
        security_log(
            "auth.refresh_success",
            user_id=str(user.id),
            old_session_id=str(session.id),
            session_id=str(new_session.id),
        )
        return user, AuthTokens(
            access_token=access,
            refresh_token=new_raw,
            access_expires_at=access_exp,
            session_id=new_session.id,
        )

    def logout(self, *, raw_refresh_token: str | None, session_id: uuid.UUID | None = None) -> None:
        now = datetime.now(timezone.utc)
        session: AuthSession | None = None
        if raw_refresh_token:
            session = self.sessions.get_by_token_hash(hash_refresh_token(raw_refresh_token))
        elif session_id is not None:
            session = self.sessions.get_by_id(session_id)

        if session is not None and session.revoked_at is None:
            self.sessions.revoke(session, when=now)
            self.db.commit()
            security_log("auth.logout", user_id=str(session.user_id), session_id=str(session.id))

    def logout_all(self, user_id: uuid.UUID) -> int:
        count = self.sessions.revoke_all_for_user(user_id)
        self.db.commit()
        security_log("auth.logout_all", user_id=str(user_id), revoked_count=count)
        return count

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise AppError(ErrorCategory.UNAUTHORIZED, "User not found.")
        return user

    def _issue_session(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthTokens:
        now = datetime.now(timezone.utc)
        raw = generate_refresh_token()
        session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(raw),
            user_agent=(user_agent or "")[:512] or None,
            ip_address=(ip_address or "")[:64] or None,
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            last_used_at=now,
        )
        self.sessions.create(session)
        access, access_exp = create_access_token(
            user_id=str(user.id),
            platform_role=user.platform_role,
            session_id=str(session.id),
            settings=self.settings,
        )
        return AuthTokens(
            access_token=access,
            refresh_token=raw,
            access_expires_at=access_exp,
            session_id=session.id,
        )
