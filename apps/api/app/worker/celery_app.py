from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from app.core.config import get_settings
from app.worker.beat_schedule import BEAT_SCHEDULE

settings = get_settings()

# Phase 9D/9E — register knowledge connectors in worker processes (same as API).
from app.connectors.providers.google_drive import register_google_drive_connector
from app.connectors.providers.microsoft_onedrive import (
    register_microsoft_onedrive_connector,
)
from app.connectors.providers.openwa import register_openwa_connector
from app.connectors.providers.mcp_remote import register_mcp_remote_connector

register_google_drive_connector()
register_microsoft_onedrive_connector()
register_openwa_connector()
register_mcp_remote_connector()

celery_app = Celery(
    "arabic_rag",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.worker.tasks",
        "app.connectors.tasks",
        "app.notifications.tasks",
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
    beat_schedule=BEAT_SCHEDULE,
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
