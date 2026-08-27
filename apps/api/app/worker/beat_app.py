"""Least-privilege Celery Beat process.

Beat only publishes fixed task names to Redis. It deliberately does not load
the application Settings object, connector registries, database credentials,
provider credentials, tenant secrets, or MCP client PKI.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from celery import Celery

from app.worker.beat_schedule import BEAT_SCHEDULE


def _broker_url() -> str:
    value = os.getenv("REDIS_URL", "redis://redis:6379/0").strip()
    app_env = os.getenv("APP_ENV", "local").strip().lower()
    if os.getenv("MCP_CONNECTOR_ENABLED", "false").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        raise RuntimeError("Celery Beat refuses MCP_CONNECTOR_ENABLED=true")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise RuntimeError("REDIS_URL is invalid for Celery Beat") from None
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise RuntimeError("REDIS_URL is invalid for Celery Beat")
    if app_env not in {"local", "dev", "development", "test"} and (
        parsed.hostname != "redis" or port not in (None, 6379)
    ):
        raise RuntimeError("Celery Beat must use the internal Redis service")
    return value


beat_app = Celery("geem_beat", broker=_broker_url())
beat_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule=BEAT_SCHEDULE,
)


__all__ = ["beat_app"]
