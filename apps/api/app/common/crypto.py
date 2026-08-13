"""Authenticated encryption for integration secrets at rest.

Uses Fernet (AES-128-CBC + HMAC). The key is ``SECRETS_ENCRYPTION_KEY`` when
set; otherwise it is derived from ``JWT_SECRET`` so local/dev keeps working
without a second secret. Do not log plaintext or the raw key.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings


def _fernet(settings: Settings) -> Fernet:
    raw = (settings.secrets_encryption_key or settings.jwt_secret).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, *, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    return _fernet(cfg).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str, *, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    try:
        return _fernet(cfg).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Unable to decrypt secret.") from exc


def encrypt_json(payload: dict[str, Any], *, settings: Settings | None = None) -> str:
    return encrypt_secret(json.dumps(payload, separators=(",", ":")), settings=settings)


def decrypt_json(token: str, *, settings: Settings | None = None) -> dict[str, Any]:
    raw = decrypt_secret(token, settings=settings)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Encrypted payload is not an object.")
    return data
