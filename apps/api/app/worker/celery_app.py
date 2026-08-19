from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

# Phase 9D/9E — register knowledge connectors in worker processes (same as API).
from app.connectors.providers.google_drive import register_google_drive_connector
from app.connectors.providers.microsoft_onedrive import (
    register_microsoft_onedrive_connector,
)
from app.connectors.providers.openwa import register_openwa_connector

register_google_drive_connector()
register_microsoft_onedrive_connector()
register_openwa_connector()

celery_app = Celery(
    "arabic_rag",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.worker.tasks",
        "app.connectors.tasks",
        "app.retention.tasks",
        "app.usage.tasks",
    ],
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
        # Chat Widget visitor messages TTL (default 1h); catch abandoned sessions.
        "purge-expired-widget-messages": {
            "task": "purge_expired_widget_messages",
            "schedule": 900.0,  # every 15 minutes
            "kwargs": {"limit": 500},
        },
        # Google Drive changes.watch channels expire ~daily; renew when within 24h.
        "renew-google-drive-watches": {
            "task": "renew_google_drive_watches",
            "schedule": 21600.0,  # every 6 hours
        },
        # Microsoft Graph OneDrive subscriptions expire; renew when within 24h.
        "renew-microsoft-onedrive-subscriptions": {
            "task": "renew_microsoft_onedrive_subscriptions",
            "schedule": 21600.0,  # every 6 hours
        },
    },
)
