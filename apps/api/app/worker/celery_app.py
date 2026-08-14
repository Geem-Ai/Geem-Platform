from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "arabic_rag",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        # Safety net for ETA misses / worker downtime (TTL is 12h by default).
        "purge-expired-chat-attachments": {
            "task": "purge_expired_chat_attachments",
            "schedule": 900.0,  # every 15 minutes
            "kwargs": {"limit": 200},
        },
    },
)
