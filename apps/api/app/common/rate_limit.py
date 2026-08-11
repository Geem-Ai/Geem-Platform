from __future__ import annotations

import logging
import time
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

# Process-local fallback when Redis is unavailable (tests / degraded local).
_memory_buckets: dict[str, list[float]] = {}


def _memory_allow(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    bucket = _memory_buckets.setdefault(key, [])
    cutoff = now - window_seconds
    _memory_buckets[key] = [t for t in bucket if t > cutoff]
    if len(_memory_buckets[key]) >= limit:
        return False
    _memory_buckets[key].append(now)
    return True


def check_auth_rate_limit(
    action: str,
    identity_key: str,
    *,
    settings: Settings | None = None,
    redis_factory: Callable[[], Redis] | None = None,
) -> None:
    """Sliding-window rate limit for auth endpoints (login/register/refresh)."""
    cfg = settings or get_settings()
    limit = cfg.auth_rate_limit_per_minute
    window = 60
    key = f"auth_rl:{action}:{identity_key}"

    try:
        client = redis_factory() if redis_factory else Redis.from_url(cfg.redis_url, socket_connect_timeout=1)
        pipe = client.pipeline()
        now = time.time()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = pipe.execute()
        count = int(results[2])
        if count > limit:
            raise AppError(
                ErrorCategory.RATE_LIMITED,
                "Too many authentication attempts. Please try again later.",
            )
        return
    except AppError:
        raise
    except (RedisError, OSError) as exc:
        logger.warning("auth_rate_limit_redis_unavailable", extra={"error": str(exc)})
        if not _memory_allow(key, limit, window):
            raise AppError(
                ErrorCategory.RATE_LIMITED,
                "Too many authentication attempts. Please try again later.",
            ) from None
