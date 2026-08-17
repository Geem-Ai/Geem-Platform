"""OAuth state store — CSRF / binding / one-time / short-lived (Phase 9C).

Stores PKCE verifier server-side. Never expose to SPA.
No provider OAuth endpoints or scopes live here.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes
_RETURN_PATH_MAX = 512

_memory_store: dict[str, tuple[float, str]] = {}
_memory_guard = threading.Lock()

_shared_redis: Redis | None = None
_shared_redis_url: str | None = None
_shared_redis_guard = threading.Lock()


def _shared_redis_client(url: str) -> Redis:
    global _shared_redis, _shared_redis_url
    with _shared_redis_guard:
        if _shared_redis is None or _shared_redis_url != url:
            if _shared_redis is not None:
                try:
                    _shared_redis.close()
                except Exception:  # noqa: BLE001
                    pass
            _shared_redis = Redis.from_url(url, socket_connect_timeout=1)
            _shared_redis_url = url
        return _shared_redis


def validate_oauth_return_path(return_path: str | None) -> str | None:
    """Accept only relative SPA paths. Reject absolute / protocol-relative URLs."""
    if return_path is None:
        return None
    path = return_path.strip()
    if not path:
        return None
    if len(path) > _RETURN_PATH_MAX:
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_RETURN_PATH_INVALID,
            "OAuth return path is too long.",
        )
    if not path.startswith("/") or path.startswith("//"):
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_RETURN_PATH_INVALID,
            "OAuth return path must be a relative SPA path.",
        )
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_RETURN_PATH_INVALID,
            "OAuth return path must be a relative SPA path.",
        )
    # Disallow backslash tricks / control chars
    if "\\" in path or any(ord(c) < 32 for c in path):
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_RETURN_PATH_INVALID,
            "OAuth return path contains invalid characters.",
        )
    return path


@dataclass(frozen=True, slots=True)
class OAuthStatePayload:
    state: str
    workspace_id: uuid.UUID
    actor_id: uuid.UUID
    app_installation_id: uuid.UUID
    connector_key: str
    connection_id: uuid.UUID | None = None
    return_path: str | None = None
    code_verifier: str | None = None
    created_at: float = 0.0

    def to_public_dict(self) -> dict[str, Any]:
        """Safe fields — never includes code_verifier."""
        return {
            "state": self.state,
            "workspace_id": str(self.workspace_id),
            "actor_id": str(self.actor_id),
            "app_installation_id": str(self.app_installation_id),
            "connector_key": self.connector_key,
            "connection_id": str(self.connection_id) if self.connection_id else None,
            "return_path": self.return_path,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            **self.to_public_dict(),
            "code_verifier": self.code_verifier,
            "created_at": self.created_at,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> OAuthStatePayload:
        return cls(
            state=str(data["state"]),
            workspace_id=uuid.UUID(str(data["workspace_id"])),
            actor_id=uuid.UUID(str(data["actor_id"])),
            app_installation_id=uuid.UUID(str(data["app_installation_id"])),
            connector_key=str(data["connector_key"]),
            connection_id=(
                uuid.UUID(str(data["connection_id"]))
                if data.get("connection_id")
                else None
            ),
            return_path=data.get("return_path"),
            code_verifier=data.get("code_verifier"),
            created_at=float(data.get("created_at") or 0),
        )


class ConnectorOAuthStateService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        redis_factory: Callable[[], Redis] | None = None,
        ttl_seconds: int = OAUTH_STATE_TTL_SECONDS,
        allow_memory_fallback: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis_factory = redis_factory
        self.ttl_seconds = ttl_seconds
        if allow_memory_fallback is None:
            allow_memory_fallback = self.settings.is_local
        self.allow_memory_fallback = allow_memory_fallback

    def _key(self, state: str) -> str:
        return f"connector:oauth:state:{state}"

    def _client(self) -> Redis:
        if self.redis_factory is not None:
            return self.redis_factory()
        return _shared_redis_client(self.settings.redis_url)

    def create(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        app_installation_id: uuid.UUID,
        connector_key: str,
        connection_id: uuid.UUID | None = None,
        return_path: str | None = None,
        code_verifier: str | None = None,
        include_pkce: bool = False,
    ) -> OAuthStatePayload:
        safe_return = validate_oauth_return_path(return_path)
        state = secrets.token_urlsafe(32)
        verifier = code_verifier
        if include_pkce and not verifier:
            verifier = secrets.token_urlsafe(64)
        payload = OAuthStatePayload(
            state=state,
            workspace_id=workspace_id,
            actor_id=actor_id,
            app_installation_id=app_installation_id,
            connector_key=connector_key,
            connection_id=connection_id,
            return_path=safe_return,
            code_verifier=verifier,
            created_at=time.time(),
        )
        raw = json.dumps(payload.to_storage_dict(), separators=(",", ":"))
        self._store(state, raw)
        return payload

    def consume(
        self,
        state: str,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        connector_key: str,
        app_installation_id: uuid.UUID | None = None,
    ) -> OAuthStatePayload:
        if not state or not isinstance(state, str):
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state is missing or invalid.",
            )
        raw = self._pop(state)
        if raw is None:
            # Distinguish replay vs never-existed is hard after delete; treat as invalid/replayed.
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state is invalid, expired, or already used.",
            )
        try:
            data = json.loads(raw)
            payload = OAuthStatePayload.from_storage(data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state payload is corrupt.",
            ) from exc

        if time.time() - payload.created_at > self.ttl_seconds:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_EXPIRED,
                "OAuth state has expired.",
            )
        if payload.workspace_id != workspace_id:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state workspace mismatch.",
                details={"expected_workspace": str(payload.workspace_id)},
            )
        if payload.actor_id != actor_id:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state actor mismatch.",
            )
        if payload.connector_key != connector_key:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state connector mismatch.",
            )
        if (
            app_installation_id is not None
            and payload.app_installation_id != app_installation_id
        ):
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state installation mismatch.",
            )
        return payload

    def peek_public(self, state: str) -> dict[str, Any] | None:
        """Test helper — never used for authorization decisions."""
        raw = self._get(state)
        if raw is None:
            return None
        try:
            payload = OAuthStatePayload.from_storage(json.loads(raw))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None
        return payload.to_public_dict()

    def _store(self, state: str, raw: str) -> None:
        key = self._key(state)
        try:
            client = self._client()
            client.set(key, raw, ex=self.ttl_seconds, nx=True)
            return
        except (RedisError, OSError) as exc:
            logger.warning(
                "connector_oauth_state_redis_unavailable",
                extra={"error": str(exc), "fallback": self.allow_memory_fallback},
            )
            if not self.allow_memory_fallback:
                raise AppError(
                    ErrorCategory.CONNECTOR_CONNECTION_FAILED,
                    "Unable to store OAuth state.",
                ) from exc
        now = time.time()
        with _memory_guard:
            _memory_store[key] = (now + self.ttl_seconds, raw)

    def _pop(self, state: str) -> str | None:
        key = self._key(state)
        try:
            client = self._client()
            # GETDEL if available; else GET + DEL
            try:
                raw = client.getdel(key)
            except AttributeError:
                pipe = client.pipeline()
                pipe.get(key)
                pipe.delete(key)
                results = pipe.execute()
                raw = results[0]
            if raw is None:
                return self._memory_pop(key)
            if isinstance(raw, bytes):
                return raw.decode("utf-8")
            return str(raw)
        except (RedisError, OSError):
            return self._memory_pop(key)

    def _get(self, state: str) -> str | None:
        key = self._key(state)
        try:
            client = self._client()
            raw = client.get(key)
            if raw is None:
                return self._memory_get(key)
            if isinstance(raw, bytes):
                return raw.decode("utf-8")
            return str(raw)
        except (RedisError, OSError):
            return self._memory_get(key)

    def _memory_pop(self, key: str) -> str | None:
        now = time.time()
        with _memory_guard:
            entry = _memory_store.pop(key, None)
            if entry is None:
                return None
            expires, raw = entry
            if expires < now:
                return None
            return raw

    def _memory_get(self, key: str) -> str | None:
        now = time.time()
        with _memory_guard:
            entry = _memory_store.get(key)
            if entry is None:
                return None
            expires, raw = entry
            if expires < now:
                _memory_store.pop(key, None)
                return None
            return raw


def clear_oauth_memory_store() -> None:
    """Test helper."""
    with _memory_guard:
        _memory_store.clear()
