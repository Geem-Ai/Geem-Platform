"""Task-name-only Celery Beat schedule shared with the worker application."""

from __future__ import annotations

from celery.schedules import crontab


BEAT_SCHEDULE = {
    # Safety net for ETA misses / worker downtime (TTL is 12h by default).
    "purge-expired-chat-attachments": {
        "task": "purge_expired_chat_attachments",
        "schedule": 900.0,
        "kwargs": {"limit": 200},
    },
    # Chat Widget visitor messages TTL (default 1h); catch abandoned sessions.
    "purge-expired-widget-messages": {
        "task": "purge_expired_widget_messages",
        "schedule": 900.0,
        "kwargs": {"limit": 500},
    },
    "recover-mcp-widget-turn-receipts": {
        "task": "recover_mcp_widget_turn_receipts",
        "schedule": 30.0,
        "kwargs": {"limit": 100},
    },
    "recover-mcp-approval-state": {
        "task": "recover_mcp_approval_state",
        "schedule": 30.0,
        "kwargs": {"limit": 100},
    },
    "recover-mcp-surface-deliveries": {
        "task": "recover_mcp_surface_deliveries",
        "schedule": 30.0,
        "kwargs": {"limit": 100},
    },
    "poll-mcp-connections": {
        "task": "poll_mcp_connections",
        "schedule": 120.0,
        "kwargs": {"limit": 100},
    },
    "renew-google-drive-watches": {
        "task": "renew_google_drive_watches",
        "schedule": 21_600.0,
    },
    "renew-microsoft-onedrive-subscriptions": {
        "task": "renew_microsoft_onedrive_subscriptions",
        "schedule": 21_600.0,
    },
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
}


__all__ = ["BEAT_SCHEDULE"]
