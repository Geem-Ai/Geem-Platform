from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_ready

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
        # Phase 11C — UTC crontab (enable_utc=True). Roll yesterday + day-before
        # so delayed settlement still lands in the idempotent rollup.
        "rollup-usage-daily": {
            "task": "rollup_usage_daily",
            "schedule": crontab(hour=0, minute=10),
            "kwargs": {"recent_days": 2},
        },
        "ensure-usage-event-partitions": {
            "task": "ensure_usage_event_partitions",
            "schedule": crontab(hour=0, minute=20),
        },
        "retain-usage-event-partitions": {
            "task": "retain_usage_event_partitions",
            "schedule": crontab(hour=0, minute=30),
        },
        # Phase 11D — lifecycle purge (SOFT_DELETE_RETENTION_DAYS). Offset from
        # 00:10/00:20/00:30 usage maintenance.
        "purge-deleted-conversations": {
            "task": "purge_deleted_conversations",
            "schedule": crontab(hour=1, minute=0),
        },
        "purge-deleted-experts": {
            "task": "purge_deleted_experts",
            "schedule": crontab(hour=1, minute=15),
        },
        "purge-deleted-workspaces": {
            "task": "purge_deleted_workspaces",
            "schedule": crontab(hour=1, minute=30),
        },
    },
)


@worker_process_init.connect
def _setup_worker_observability(**_kwargs) -> None:
    from app.observability.setup import setup_observability

    setup_observability()


@worker_ready.connect
def _ensure_usage_partitions_on_worker(**_kwargs) -> None:
    from app.db.session import SessionLocal
    from app.usage.partitions import bootstrap_startup_partitions

    db = SessionLocal()
    try:
        bootstrap_startup_partitions(db)
    finally:
        db.close()
