"""Per-conversation generation lock (Phase 4B).

Prevents overlapping assistant generations that would corrupt message ordering.

* Prefers a shared Redis client (SET NX + TTL).
* On Redis failure: **fail closed** in non-local environments (acquire → False).
* In local/test only: in-process memory fallback so single-process DX/tests work
  without Redis.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_memory_locks: dict[str, float] = {}
_memory_guard = threading.Lock()

_shared_redis: Redis | None = None
_shared_redis_url: str | None = None
_shared_redis_guard = threading.Lock()


def _shared_redis_client(url: str) -> Redis:
    """Lazy process-wide Redis client — avoids connect/close per lock op."""
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


class ConversationGenerationLock:
    """SET NX lock keyed by conversation id with TTL safety."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        redis_factory: Callable[[], Redis] | None = None,
        ttl_seconds: int | None = None,
        allow_memory_fallback: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis_factory = redis_factory
        self.ttl_seconds = int(
            ttl_seconds
            if ttl_seconds is not None
            else getattr(self.settings, "conversation_generation_lock_ttl_seconds", 300)
        )
        # Fail closed when Redis is down unless local/test (or explicitly overridden).
        if allow_memory_fallback is None:
            allow_memory_fallback = self.settings.is_local
        self.allow_memory_fallback = allow_memory_fallback

    def _key(self, conversation_id: uuid.UUID) -> str:
        return f"chat:gen:{conversation_id}"

    def _client(self) -> Redis:
        if self.redis_factory is not None:
            return self.redis_factory()
        return _shared_redis_client(self.settings.redis_url)

    def acquire(self, conversation_id: uuid.UUID) -> bool:
        key = self._key(conversation_id)
        try:
            client = self._client()
            ok = client.set(key, "1", nx=True, ex=self.ttl_seconds)
            return bool(ok)
        except (RedisError, OSError) as exc:
            logger.warning(
                "conversation_generation_lock_redis_unavailable",
                extra={"error": str(exc), "fail_closed": not self.allow_memory_fallback},
            )
            if self.allow_memory_fallback:
                return self._memory_acquire(key)
            # Fail closed: treat as busy so two workers cannot both proceed.
            return False

    def release(self, conversation_id: uuid.UUID) -> None:
        key = self._key(conversation_id)
        try:
            client = self._client()
            client.delete(key)
        except (RedisError, OSError):
            pass
        if self.allow_memory_fallback:
            self._memory_release(key)

    def _memory_acquire(self, key: str) -> bool:
        now = time.time()
        with _memory_guard:
            expires = _memory_locks.get(key)
            if expires is not None and expires > now:
                return False
            _memory_locks[key] = now + self.ttl_seconds
            return True

    def _memory_release(self, key: str) -> None:
        with _memory_guard:
            _memory_locks.pop(key, None)
