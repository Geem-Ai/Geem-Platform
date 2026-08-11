from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# Fixed dummy hash for login timing equalization when the user does not exist.
# Generated with the same PasswordHasher parameters; never a real credential.
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=2$"
    "yeTDrgd+G63iCvHjMluNwg$N9Zl3BjDVi/I1FVN0FHyVh3aBd2eP4nrCAqMTScWz7w"
)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    """Length-based rules only — avoid complexity theater that reduces entropy."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AppError(
            ErrorCategory.WEAK_PASSWORD,
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AppError(
            ErrorCategory.WEAK_PASSWORD,
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters.",
        )


def hash_password(password: str) -> str:
    validate_password(password)
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: str,
    platform_role: str,
    session_id: str,
    settings: Settings | None = None,
) -> tuple[str, datetime]:
    cfg = settings or get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=cfg.access_token_ttl_seconds)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "pr": platform_role,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str, *, settings: Settings | None = None) -> dict:
    cfg = settings or get_settings()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(ErrorCategory.SESSION_EXPIRED, "Access token expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid access token.") from exc
    if payload.get("typ") != "access":
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid access token type.")
    return payload
