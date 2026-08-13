"""API-key secret generation and deterministic lookup hashing.

API keys are high-entropy machine credentials, not passwords. Lookup uses
HMAC-SHA256 with a dedicated server-side pepper so the digest is deterministic
and indexable. Argon2/bcrypt are intentionally not used.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

API_KEY_PREFIX = "geem_sk_"
# 32 bytes = 256 bits of entropy before encoding.
API_KEY_RANDOM_BYTES = 32
# Display prefix: product prefix + first 8 chars of the random portion.
KEY_PREFIX_RANDOM_CHARS = 8
# Reject oversized Authorization values before hashing (DoS).
MAX_API_KEY_LENGTH = 128
HMAC_DIGEST_HEX_LENGTH = 64


def generate_api_key_secret() -> str:
    """Return ``geem_sk_`` + url-safe random with ≥256 bits of entropy."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(API_KEY_RANDOM_BYTES)}"


def display_prefix(secret: str) -> str:
    random_part = secret[len(API_KEY_PREFIX) :] if secret.startswith(API_KEY_PREFIX) else secret
    return f"{API_KEY_PREFIX}{random_part[:KEY_PREFIX_RANDOM_CHARS]}"


def last_four(secret: str) -> str:
    if len(secret) < 4:
        return secret
    return secret[-4:]


def hash_api_key(secret: str, *, settings: Settings | None = None) -> str:
    """HMAC-SHA256(key=pepper, msg=secret) as lowercase hex."""
    pepper = (settings or get_settings()).effective_api_key_hash_pepper
    digest = hmac.new(
        pepper.encode("utf-8"),
        secret.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def hashes_equal(stored_hex: str, computed_hex: str) -> bool:
    """Constant-time compare of two hex digests."""
    if len(stored_hex) != HMAC_DIGEST_HEX_LENGTH or len(computed_hex) != HMAC_DIGEST_HEX_LENGTH:
        return False
    return hmac.compare_digest(stored_hex, computed_hex)


def reject_invalid_api_key() -> None:
    """Uniform 401 — do not reveal whether a secret once existed."""
    raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid API key.")


def parse_presented_api_key(raw: str) -> str:
    """Normalize a presented Bearer secret. Never include the value in errors."""
    secret = (raw or "").strip()
    if not secret or len(secret) > MAX_API_KEY_LENGTH:
        reject_invalid_api_key()
    return secret
