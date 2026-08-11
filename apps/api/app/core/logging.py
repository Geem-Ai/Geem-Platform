from __future__ import annotations

import logging
import sys
from typing import Any

import orjson

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "job_id",
            "document_id",
            "page_number",
            "stage",
            "provider",
            "model",
            "latency_ms",
            "attempt",
            "status",
            "openrouter_id",
            "usage",
            "security_event",
            "user_id",
            "workspace_id",
            "session_id",
            "email",
            "slug",
            "reason",
            "actor_id",
            "target_user_id",
            "role",
            "revoked_count",
            "old_session_id",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return orjson.dumps(payload).decode()


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
