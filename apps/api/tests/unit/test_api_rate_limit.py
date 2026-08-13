from __future__ import annotations

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError, ErrorCategory
from app.rate_limits.service import (
    ApiRateLimiter,
    api_key_bucket_key,
    reset_memory_rate_limit_buckets,
    reset_shared_redis_client,
    workspace_bucket_key,
)


@pytest.fixture(autouse=True)
def _clear_memory_buckets() -> None:
    reset_memory_rate_limit_buckets()
    yield
    reset_memory_rate_limit_buckets()


def _limiter(limit: int) -> ApiRateLimiter:
    quota = MagicMock()
    quota.get_api_requests_per_minute.return_value = limit
    limiter = ApiRateLimiter(
        db=MagicMock(),
        allow_memory_fallback=True,
        redis_factory=lambda: (_ for _ in ()).throw(OSError("redis down")),
    )
    limiter.quota = quota
    return limiter


def test_memory_rate_limit_allows_then_blocks() -> None:
    limiter = _limiter(2)
    ws = uuid.uuid4()
    key = uuid.uuid4()
    first = limiter.consume(workspace_id=ws, api_key_id=key)
    second = limiter.consume(workspace_id=ws, api_key_id=key)
    assert first.allowed and second.allowed
    assert second.remaining == 0
    with pytest.raises(AppError) as exc:
        limiter.consume(workspace_id=ws, api_key_id=key)
    assert exc.value.category == ErrorCategory.RATE_LIMIT_EXCEEDED
    assert exc.value.details["remaining"] == 0
    assert exc.value.details["limit"] == 2
    assert "Retry-After" in exc.value.headers
    assert int(exc.value.headers["X-RateLimit-Remaining"]) >= 0


def test_workspace_bucket_blocks_second_key() -> None:
    limiter = _limiter(2)
    ws = uuid.uuid4()
    key_a = uuid.uuid4()
    key_b = uuid.uuid4()
    limiter.consume(workspace_id=ws, api_key_id=key_a)
    limiter.consume(workspace_id=ws, api_key_id=key_b)
    with pytest.raises(AppError) as exc:
        limiter.consume(workspace_id=ws, api_key_id=key_a)
    assert exc.value.category == ErrorCategory.RATE_LIMIT_EXCEEDED


def test_workspace_buckets_are_isolated() -> None:
    limiter = _limiter(1)
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    limiter.consume(workspace_id=ws_a, api_key_id=uuid.uuid4())
    with pytest.raises(AppError):
        limiter.consume(workspace_id=ws_a, api_key_id=uuid.uuid4())
    other = limiter.consume(workspace_id=ws_b, api_key_id=uuid.uuid4())
    assert other.allowed


def test_missing_entitlement_fails_closed() -> None:
    limiter = _limiter(0)
    with pytest.raises(AppError) as exc:
        limiter.consume(workspace_id=uuid.uuid4(), api_key_id=uuid.uuid4())
    assert exc.value.category == ErrorCategory.RATE_LIMIT_EXCEEDED
    assert exc.value.details["limit"] == 0


def test_concurrent_memory_increments_do_not_exceed() -> None:
    limiter = _limiter(5)
    ws = uuid.uuid4()
    key = uuid.uuid4()
    allowed = []
    blocked = []

    def _hit() -> None:
        try:
            limiter.consume(workspace_id=ws, api_key_id=key)
            allowed.append(1)
        except AppError as exc:
            assert exc.category == ErrorCategory.RATE_LIMIT_EXCEEDED
            blocked.append(1)

    threads = [threading.Thread(target=_hit) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) == 5
    assert len(blocked) == 7


def test_redis_key_shapes_use_workspace_and_key_ids() -> None:
    ws = uuid.uuid4()
    key = uuid.uuid4()
    assert workspace_bucket_key(ws, 1) == f"rate:api:ws:{ws}:1"
    assert api_key_bucket_key(key, 1) == f"rate:api:key:{key}:1"


def test_rate_limiter_reuses_process_redis_client() -> None:
    reset_shared_redis_client()
    mock_redis = MagicMock()
    mock_redis.eval.return_value = [1, 1, 60]
    quota = MagicMock()
    quota.get_api_requests_per_minute.return_value = 10
    ws = uuid.uuid4()
    key = uuid.uuid4()
    try:
        with patch("app.rate_limits.service.Redis.from_url", return_value=mock_redis) as from_url:
            first = ApiRateLimiter(db=MagicMock(), allow_memory_fallback=False)
            first.quota = quota
            first.consume(workspace_id=ws, api_key_id=key)
            first.consume(workspace_id=ws, api_key_id=key)
            second = ApiRateLimiter(db=MagicMock(), allow_memory_fallback=False)
            second.quota = quota
            second.consume(workspace_id=ws, api_key_id=key)
            assert from_url.call_count == 1
            assert mock_redis.eval.call_count == 3
    finally:
        reset_shared_redis_client()
