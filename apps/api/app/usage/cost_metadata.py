"""Allowlist sanitizer for ``usage_events.cost_metadata`` (Phase 11C).

Accounting fields are preserved with correct numeric types. Diagnostic
fields are omitted when oversized, unknown, nested, or secret-like.
Existing rows are not rewritten by the sanitizer.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import event

ACCOUNTING_KEYS = (
    "family",
    "model",
    "multiplier",
    "raw_prompt_tokens",
    "raw_completion_tokens",
    "raw_total_tokens",
    "billed_tokens",
)

DIAGNOSTIC_KEYS = (
    "token_source",
    "total_tokens",
    "prompt_version",
    "workspace_id",
    "expert_id",
    "knowledge_workspace_id",
    "expert_type",
    "population",
    "provider_request_id",
    "billing_request_id",
    "chunk_count",
    "duration_seconds",
    "audio_format",
    "byte_size",
)

ALLOWED_KEYS = frozenset(ACCOUNTING_KEYS + DIAGNOSTIC_KEYS)

_MAX_STRING = 256
_MAX_JSON_BYTES = 2048
_INT_MAX = 10**15


def sanitize_cost_metadata(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    accounting: dict[str, Any] = {}
    diagnostic: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key not in ALLOWED_KEYS:
            continue
        cleaned = _clean_value(key, value)
        if cleaned is None:
            continue
        if key in ACCOUNTING_KEYS:
            accounting[key] = cleaned
        else:
            diagnostic[key] = cleaned
    out = {**accounting, **diagnostic}
    encoded = json.dumps(out, default=str, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= _MAX_JSON_BYTES:
        return out or None
    encoded_acc = json.dumps(accounting, default=str, separators=(",", ":")).encode("utf-8")
    if len(encoded_acc) <= _MAX_JSON_BYTES:
        return accounting or None
    # Accounting-only still too large: keep billed/family/multiplier only.
    core = {
        k: accounting[k]
        for k in ("family", "multiplier", "billed_tokens")
        if k in accounting
    }
    return core or None


def _clean_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if abs(value) > _INT_MAX:
            return None
        return int(value)
    if isinstance(value, float):
        if key not in {"multiplier", "duration_seconds"}:
            if not value.is_integer():
                return None
            return int(value)
        if value != value or value in {float("inf"), float("-inf")}:
            return None
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or len(text) > _MAX_STRING:
            return None
        if key in {
            "raw_prompt_tokens",
            "raw_completion_tokens",
            "raw_total_tokens",
            "billed_tokens",
            "total_tokens",
            "chunk_count",
            "byte_size",
        }:
            try:
                number = int(text)
            except ValueError:
                return None
            return number if abs(number) <= _INT_MAX else None
        return text
    return None


def register_usage_event_sanitizer() -> None:
    from app.db.models import UsageEvent

    if getattr(UsageEvent, "_geem_cost_metadata_sanitizer", False):
        return

    @event.listens_for(UsageEvent, "before_insert")
    def _before_insert(_mapper, _connection, target) -> None:  # noqa: ANN001
        target.cost_metadata = sanitize_cost_metadata(target.cost_metadata)

    UsageEvent._geem_cost_metadata_sanitizer = True
