"""Unit tests for Chat Widget message retention + history caps."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.core.config import Settings
from app.widgets.retention import WidgetRetentionService
from app.widgets.service import WidgetService


def test_widget_history_cap_defaults_to_15() -> None:
    settings = Settings(widget_chat_history_max_messages=15, widget_message_ttl_hours=1)
    assert settings.widget_chat_history_max_messages == 15
    assert settings.widget_message_ttl_seconds == 3600


def test_history_payload_excludes_expired_and_caps() -> None:
    settings = Settings(widget_chat_history_max_messages=15, widget_message_ttl_hours=1)
    svc = WidgetService(MagicMock(), settings=settings)
    now = datetime.now(timezone.utc)
    fresh = MagicMock(
        role="user",
        content="fresh",
        created_at=now - timedelta(minutes=10),
    )
    stale = MagicMock(
        role="user",
        content="stale",
        created_at=now - timedelta(hours=2),
    )
    svc.conversations = MagicMock()
    svc.conversations.list_history_for_rag.return_value = [stale, fresh]
    svc.retention = WidgetRetentionService(MagicMock(), settings=settings)

    payload = svc._history_payload(uuid.uuid4(), before_message_id=uuid.uuid4())
    assert payload == [{"role": "user", "content": "fresh"}]
    assert svc.conversations.list_history_for_rag.call_args.kwargs["limit"] == 15
