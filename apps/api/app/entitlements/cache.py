"""Optional Redis cache for resolved Workspace entitlements.

Correctness over caching: Redis failures are ignored (fail open to DB).
Key pattern: ``ws:{workspace_id}:entitlements:v1``
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
CACHE_VERSION = "v1"


def entitlements_cache_key(workspace_id: uuid.UUID) -> str:
    return f"ws:{workspace_id}:entitlements:{CACHE_VERSION}"


def _client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, socket_connect_timeout=1)


def get_cached_entitlements(
    workspace_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    redis_factory: Callable[[], Redis] | None = None,
) -> dict[str, Any] | None:
    cfg = settings or get_settings()
    try:
        client = redis_factory() if redis_factory else _client(cfg)
        raw = client.get(entitlements_cache_key(workspace_id))
        if not raw:
            return None
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except (RedisError, OSError, json.JSONDecodeError, TypeError) as exc:
        logger.debug("entitlements_cache_get_failed", extra={"error": str(exc)})
        return None


def set_cached_entitlements(
    workspace_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    redis_factory: Callable[[], Redis] | None = None,
) -> None:
    cfg = settings or get_settings()
    try:
        client = redis_factory() if redis_factory else _client(cfg)
        client.set(
            entitlements_cache_key(workspace_id),
            json.dumps(payload, default=str),
            ex=CACHE_TTL_SECONDS,
        )
    except (RedisError, OSError, TypeError) as exc:
        logger.debug("entitlements_cache_set_failed", extra={"error": str(exc)})


def invalidate_entitlements(
    workspace_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    redis_factory: Callable[[], Redis] | None = None,
) -> None:
    cfg = settings or get_settings()
    try:
        client = redis_factory() if redis_factory else _client(cfg)
        client.delete(entitlements_cache_key(workspace_id))
    except (RedisError, OSError) as exc:
        logger.debug("entitlements_cache_invalidate_failed", extra={"error": str(exc)})
