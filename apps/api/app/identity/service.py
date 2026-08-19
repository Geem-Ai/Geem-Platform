from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, record_audit
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.email_verification_email import render_email_verification_email
from app.identity.email_verification_tokens import (
    MAX_EMAIL_VERIFICATION_TOKEN_LENGTH,
    email_verification_url,
    generate_email_verification_token,
    hash_email_verification_token,
)
from app.identity.models import (
    PlatformRole,
    Session as AuthSession,
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserStatus,
)
from app.identity.password_reset_email import render_password_reset_email
from app.identity.password_reset_tokens import (
    MAX_PASSWORD_RESET_TOKEN_LENGTH,
    generate_password_reset_token,
    hash_password_reset_token,
    password_reset_url,
)
from app.identity.repository import (
    EmailVerificationTokenRepository,
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
)
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
from app.notifications.protocol import EmailMessage, EmailProvider


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    session_id: uuid.UUID


@dataclass(slots=True)
class RegisterResult:
    user: User
    tokens: AuthTokens | None
    verification_required: bool


class AuthService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        email: EmailProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)
        self.reset_tokens = PasswordResetTokenRepository(db)
        self.verify_tokens = EmailVerificationTokenRepository(db)
        self.email = email

    def register(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RegisterResult:
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise AppError(ErrorCategory.VALIDATION, "Invalid email address.")
        if self.users.get_by_email(normalized) is not None:
            raise AppError(ErrorCategory.EMAIL_ALREADY_EXISTS, "Email is already registered.")

        validate_password(password)
        now = datetime.now(timezone.utc)
        verification_required = self.settings.effective_email_verification_required
        user = User(
            email=normalized,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE.value,
            platform_role=PlatformRole.NONE.value,
            email_verified_at=None if verification_required else now,
        )
        self.users.create(user)
        tokens: AuthTokens | None = None
        try:
            if verification_required:
                self._create_and_send_verification(user, now=now)
            else:
                tokens = self._issue_session(user, user_agent=user_agent, ip_address=ip_address)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(ErrorCategory.EMAIL_ALREADY_EXISTS, "Email is already registered.") from exc
        except AppError:
            self.db.rollback()
            raise
        security_log(
            "auth.register",
            user_id=str(user.id),
            email=normalized,
            verification_required=verification_required,
        )
        return RegisterResult(
            user=user,
            tokens=tokens,
            verification_required=verification_required,
        )

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

        self._require_email_verified(user)

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
        if user.email_verified_at is None:
            self.sessions.revoke(session, when=now)
            self.db.commit()
            security_log("auth.refresh_failed", user_id=str(user.id), reason="email_not_verified")
            raise AppError(ErrorCategory.EMAIL_NOT_VERIFIED, "Email is not verified.")

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

    def forgot_password(self, *, email: str) -> None:
        """Always succeeds from the caller's perspective (no email enumeration)."""
        normalized = normalize_email(email)
        user = self.users.get_by_email(normalized)
        if user is None or user.status != UserStatus.ACTIVE.value:
            security_log("auth.forgot_password_skipped", email=normalized, reason="unknown_or_disabled")
            return

        if self.email is None:
            security_log("auth.forgot_password_failed", user_id=str(user.id), reason="no_email_provider")
            return

        now = datetime.now(timezone.utc)
        self.reset_tokens.invalidate_unused_for_user(user.id, when=now)
        raw = generate_password_reset_token()
        expires_at = now + timedelta(hours=self.settings.effective_password_reset_ttl_hours)
        row = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(raw, settings=self.settings),
            expires_at=expires_at,
        )
        self.reset_tokens.create(row)
        self.db.flush()

        reset_link = password_reset_url(raw, settings=self.settings)
        content = render_password_reset_email(
            reset_url=reset_link,
            expires_at=expires_at,
            email=user.email,
        )
        try:
            self.email.send(
                EmailMessage(
                    to=user.email,
                    subject=content.subject,
                    text_body=content.text_body,
                    html_body=content.html_body,
                )
            )
        except Exception:
            self.db.rollback()
            security_log("auth.forgot_password_failed", user_id=str(user.id), reason="email_delivery")
            return

        self.db.commit()
        security_log("auth.forgot_password_sent", user_id=str(user.id))

    def reset_password(
        self,
        *,
        token: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        raw = (token or "").strip()
        if not raw or len(raw) > MAX_PASSWORD_RESET_TOKEN_LENGTH:
            raise AppError(ErrorCategory.INVALID_RESET_TOKEN, "Invalid or expired reset link.")

        validate_password(password)
        token_hash = hash_password_reset_token(raw, settings=self.settings)
        row = self.reset_tokens.get_by_token_hash(token_hash)
        if row is None or row.used_at is not None:
            raise AppError(ErrorCategory.INVALID_RESET_TOKEN, "Invalid or expired reset link.")

        now = datetime.now(timezone.utc)
        if row.expires_at <= now:
            row.used_at = now
            self.db.commit()
            raise AppError(ErrorCategory.RESET_TOKEN_EXPIRED, "Reset link has expired.")

        user = self.users.get_by_id(row.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            row.used_at = now
            self.db.commit()
            raise AppError(ErrorCategory.INVALID_RESET_TOKEN, "Invalid or expired reset link.")

        user.password_hash = hash_password(password)
        if user.email_verified_at is None:
            user.email_verified_at = now
        row.used_at = now
        self.reset_tokens.invalidate_unused_for_user(user.id, when=now)
        self.sessions.revoke_all_for_user(user.id, when=now)
        tokens = self._issue_session(user, user_agent=user_agent, ip_address=ip_address)
        record_audit(
            self.db,
            action=AuditAction.AUTH_PASSWORD_RESET,
            entity_type=AuditEntityType.USER,
            entity_id=user.id,
            actor_user_id=user.id,
        )
        self.db.commit()
        security_log("auth.password_reset", user_id=str(user.id), session_id=str(tokens.session_id))
        return user, tokens

    def verify_email(
        self,
        *,
        token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, AuthTokens]:
        raw = (token or "").strip()
        if not raw or len(raw) > MAX_EMAIL_VERIFICATION_TOKEN_LENGTH:
            raise AppError(ErrorCategory.INVALID_VERIFICATION_TOKEN, "Invalid or expired verification link.")

        token_hash = hash_email_verification_token(raw, settings=self.settings)
        row = self.verify_tokens.get_by_token_hash(token_hash)
        if row is None or row.used_at is not None:
            raise AppError(ErrorCategory.INVALID_VERIFICATION_TOKEN, "Invalid or expired verification link.")

        now = datetime.now(timezone.utc)
        if row.expires_at <= now:
            row.used_at = now
            self.db.commit()
            raise AppError(ErrorCategory.VERIFICATION_TOKEN_EXPIRED, "Verification link has expired.")

        user = self.users.get_by_id(row.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            row.used_at = now
            self.db.commit()
            raise AppError(ErrorCategory.INVALID_VERIFICATION_TOKEN, "Invalid or expired verification link.")

        if user.email_verified_at is None:
            user.email_verified_at = now
        row.used_at = now
        self.verify_tokens.invalidate_unused_for_user(user.id, when=now)
        tokens = self._issue_session(user, user_agent=user_agent, ip_address=ip_address)
        self.db.commit()
        security_log("auth.email_verified", user_id=str(user.id), session_id=str(tokens.session_id))
        return user, tokens

    def resend_verification(self, *, email: str) -> None:
        """Always succeeds from the caller's perspective (no email enumeration)."""
        normalized = normalize_email(email)
        user = self.users.get_by_email(normalized)
        if user is None or user.status != UserStatus.ACTIVE.value:
            security_log("auth.resend_verification_skipped", email=normalized, reason="unknown_or_disabled")
            return
        if user.email_verified_at is not None:
            security_log("auth.resend_verification_skipped", user_id=str(user.id), reason="already_verified")
            return
        if self.email is None:
            security_log("auth.resend_verification_failed", user_id=str(user.id), reason="no_email_provider")
            return

        now = datetime.now(timezone.utc)
        try:
            self._create_and_send_verification(user, now=now)
            self.db.commit()
        except Exception:
            self.db.rollback()
            security_log("auth.resend_verification_failed", user_id=str(user.id), reason="email_delivery")
            return
        security_log("auth.resend_verification_sent", user_id=str(user.id))

    def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        current_session_id: uuid.UUID,
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            security_log("auth.change_password_failed", user_id=str(user.id), reason="bad_password")
            raise AppError(ErrorCategory.INVALID_CREDENTIALS, "Invalid email or password.")

        validate_password(new_password)
        if verify_password(new_password, user.password_hash):
            raise AppError(
                ErrorCategory.VALIDATION,
                "New password must be different from the current password.",
            )

        user.password_hash = hash_password(new_password)
        revoked = self.sessions.revoke_all_for_user_except(
            user.id,
            except_session_id=current_session_id,
        )
        record_audit(
            self.db,
            action=AuditAction.AUTH_PASSWORD_CHANGED,
            entity_type=AuditEntityType.USER,
            entity_id=user.id,
            actor_user_id=user.id,
        )
        self.db.commit()
        security_log(
            "auth.change_password",
            user_id=str(user.id),
            session_id=str(current_session_id),
            revoked_other_sessions=revoked,
        )

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

    def _require_email_verified(self, user: User) -> None:
        if user.email_verified_at is not None:
            return
        security_log("auth.email_not_verified", user_id=str(user.id))
        raise AppError(ErrorCategory.EMAIL_NOT_VERIFIED, "Email is not verified.")

    def _create_and_send_verification(self, user: User, *, now: datetime) -> None:
        if self.email is None:
            raise AppError(ErrorCategory.EMAIL_DELIVERY_FAILED, "Email delivery is unavailable.")

        self.verify_tokens.invalidate_unused_for_user(user.id, when=now)
        raw = generate_email_verification_token()
        expires_at = now + timedelta(hours=self.settings.effective_email_verification_ttl_hours)
        row = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_email_verification_token(raw, settings=self.settings),
            expires_at=expires_at,
        )
        self.verify_tokens.create(row)
        self.db.flush()

        verify_link = email_verification_url(raw, settings=self.settings)
        content = render_email_verification_email(
            verify_url=verify_link,
            expires_at=expires_at,
            email=user.email,
        )
        try:
            self.email.send(
                EmailMessage(
                    to=user.email,
                    subject=content.subject,
                    text_body=content.text_body,
                    html_body=content.html_body,
                )
            )
        except AppError:
            raise
        except Exception as exc:
            security_log("auth.verification_email_failed", user_id=str(user.id), reason="email_delivery")
            raise AppError(ErrorCategory.EMAIL_DELIVERY_FAILED, "Email delivery failed.") from exc
