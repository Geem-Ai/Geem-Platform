"""Invitation token generation and deterministic lookup hashing.

Invitation tokens are high-entropy secrets, not passwords. Lookup uses
HMAC-SHA256 with a server-side pepper so the digest is indexable. The raw
token is never stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.core.config import Settings, get_settings

# 32 bytes = 256 bits of entropy before url-safe encoding.
INVITATION_TOKEN_RANDOM_BYTES = 32
HMAC_DIGEST_HEX_LENGTH = 64
# Reject oversized presented tokens before hashing (DoS).
MAX_INVITATION_TOKEN_LENGTH = 256
_HMAC_MESSAGE_PREFIX = "geem-invite:"


def generate_invitation_token() -> str:
    """Return a url-safe random token with ≥256 bits of entropy."""
    return secrets.token_urlsafe(INVITATION_TOKEN_RANDOM_BYTES)


def hash_invitation_token(raw_token: str, *, settings: Settings | None = None) -> str:
    """HMAC-SHA256(key=pepper, msg='geem-invite:' + token) as lowercase hex."""
    pepper = (settings or get_settings()).effective_invitation_token_hash_pepper
    digest = hmac.new(
        pepper.encode("utf-8"),
        f"{_HMAC_MESSAGE_PREFIX}{raw_token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def hashes_equal(stored_hex: str, computed_hex: str) -> bool:
    """Constant-time compare of two hex digests."""
    if len(stored_hex) != HMAC_DIGEST_HEX_LENGTH or len(computed_hex) != HMAC_DIGEST_HEX_LENGTH:
        return False
    return hmac.compare_digest(stored_hex, computed_hex)
