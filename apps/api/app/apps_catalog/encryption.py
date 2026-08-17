"""Encrypted installation config boundary (Phase 9A).

Reuses ``app.common.crypto`` (Fernet). No provider credentials are stored yet;
this service exists so 9C+ can attach OAuth/token payloads without redesign.
"""

from __future__ import annotations

from typing import Any

from app.common.crypto import decrypt_json, encrypt_json
from app.core.config import Settings, get_settings


class AppConfigEncryptionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def encrypt(self, payload: dict[str, Any]) -> str:
        return encrypt_json(payload, settings=self.settings)

    def decrypt(self, token: str) -> dict[str, Any]:
        return decrypt_json(token, settings=self.settings)
