"""Authenticated API-key actor. Not a User — Workspace comes from the key."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True, frozen=True)
class ApiKeyPrincipal:
    """Public-API actor derived solely from a valid Workspace API key.

    Rate-limit key helpers are for Phase 7B (``api_key:{id}`` / ``ws:{id}:...``).
    Entitlement-driven limits are not applied here.
    """

    api_key_id: UUID
    workspace_id: UUID
    scopes: tuple[str, ...]
    key_prefix: str
    name: str

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    @property
    def rate_limit_key(self) -> str:
        return f"api_key:{self.api_key_id}"

    def workspace_rate_limit_key(self, metric: str) -> str:
        return f"ws:{self.workspace_id}:{metric}"
