"""Redis-backed, entitlement-driven public API rate limiting.

Limits come from ``api_requests_per_minute`` via EntitlementService /
QuotaService — never from plan names. Missing entitlement fails closed (0).

Two buckets share the same maximum:

* ``rate:api:ws:{workspace_id}:{window}``
* ``rate:api:key:{api_key_id}:{window}``

Increments are atomic (Lua INCR+EXPIRE). Production fails closed if Redis
is unavailable. Local/test may use a process-local locked counter.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import raise_rate_limit_exceeded
from app.entitlements.quota import QuotaService

logger = logging.getLogger(__name__)

_LUA_INCR_EXPIRE = """
local ws_count = redis.call('INCR', KEYS[1])
if ws_count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local key_count = redis.call('INCR', KEYS[2])
if key_count == 1 then
  redis.call('EXPIRE', KEYS[2], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
local key_ttl = redis.call('TTL', KEYS[2])
if key_ttl < 0 then
  redis.call('EXPIRE', KEYS[2], ARGV[1])
  key_ttl = tonumber(ARGV[1])
end
if key_ttl > ttl then
  ttl = key_ttl
end
return {ws_count, key_count, ttl}
"""

_memory_guard = threading.Lock()
_memory_buckets: dict[str, tuple[int, float]] = {}


@dataclass(frozen=True, slots=True)
class ApiRateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_at: int

    def as_headers(self, *, include_retry_after: bool = False) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
        }
        if include_retry_after:
            headers["Retry-After"] = str(max(0, self.retry_after))
        return headers


def workspace_bucket_key(workspace_id: uuid.UUID, window: int) -> str:
    return f"rate:api:ws:{workspace_id}:{window}"


def api_key_bucket_key(api_key_id: uuid.UUID, window: int) -> str:
    return f"rate:api:key:{api_key_id}:{window}"


class ApiRateLimiter:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        redis_factory: Callable[[], Redis] | None = None,
        allow_memory_fallback: bool | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.quota = QuotaService(db, self.settings)
        self.redis_factory = redis_factory
        if allow_memory_fallback is None:
            allow_memory_fallback = self.settings.is_local
        self.allow_memory_fallback = allow_memory_fallback

    def consume(
        self,
        *,
        workspace_id: uuid.UUID,
        api_key_id: uuid.UUID,
        now: float | None = None,
        limit: int | None = None,
    ) -> ApiRateLimitResult:
        """Increment Workspace + API-key buckets. Raises on exceed.

        Entitlement lookup runs once per call (pass ``limit`` to skip it —
        used by concurrency tests that must not share a SQLAlchemy session).
        """
        if limit is None:
            limit = max(0, int(self.quota.get_api_requests_per_minute(workspace_id)))
        else:
            limit = max(0, int(limit))
        instant = time.time() if now is None else float(now)
        window = int(instant // 60)
        ttl = int(60 - (instant % 60))
        if ttl <= 0:
            ttl = 1
        reset_at = (window + 1) * 60
        ws_key = workspace_bucket_key(workspace_id, window)
        key_key = api_key_bucket_key(api_key_id, window)

        if limit <= 0:
            raise_rate_limit_exceeded(
                limit=0,
                remaining=0,
                retry_after=ttl,
                reset_at=reset_at,
            )

        ws_count, key_count, observed_ttl = self._incr_both(ws_key, key_key, ttl)
        retry_after = max(1, int(observed_ttl))
        remaining = max(0, limit - max(ws_count, key_count))
        allowed = ws_count <= limit and key_count <= limit
        result = ApiRateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after=retry_after,
            reset_at=reset_at,
        )
        if not allowed:
            raise_rate_limit_exceeded(
                limit=result.limit,
                remaining=0,
                retry_after=result.retry_after,
                reset_at=result.reset_at,
            )
        return result

    def _incr_both(self, ws_key: str, key_key: str, ttl: int) -> tuple[int, int, int]:
        try:
            client = self._client()
            raw = client.eval(_LUA_INCR_EXPIRE, 2, ws_key, key_key, int(ttl))
            ws_count = int(raw[0])
            key_count = int(raw[1])
            observed_ttl = int(raw[2])
            if observed_ttl < 0:
                observed_ttl = ttl
            return ws_count, key_count, observed_ttl
        except (RedisError, OSError) as exc:
            logger.warning(
                "api_rate_limit_redis_unavailable",
                extra={"error": str(exc), "fail_closed": not self.allow_memory_fallback},
            )
            if self.allow_memory_fallback:
                return self._memory_incr_both(ws_key, key_key, ttl)
            raise_rate_limit_exceeded(
                limit=0,
                remaining=0,
                retry_after=ttl,
                reset_at=int(time.time()) + ttl,
            )
            raise  # pragma: no cover

    def _client(self) -> Redis:
        if self.redis_factory is not None:
            return self.redis_factory()
        return Redis.from_url(self.settings.redis_url, socket_connect_timeout=1)

    @staticmethod
    def _memory_incr_both(ws_key: str, key_key: str, ttl: int) -> tuple[int, int, int]:
        now = time.time()
        expires = now + ttl
        with _memory_guard:
            ws_count = _memory_bump(ws_key, now, expires)
            key_count = _memory_bump(key_key, now, expires)
            left = min(
                _memory_buckets[ws_key][1] - now,
                _memory_buckets[key_key][1] - now,
            )
        return ws_count, key_count, max(1, int(left))


def _memory_bump(key: str, now: float, expires: float) -> int:
    count, until = _memory_buckets.get(key, (0, 0.0))
    if until <= now:
        count = 0
        until = expires
    count += 1
    _memory_buckets[key] = (count, until)
    return count


def reset_memory_rate_limit_buckets() -> None:
    """Test helper — clear the process-local fallback buckets."""
    with _memory_guard:
        _memory_buckets.clear()
