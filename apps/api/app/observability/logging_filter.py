"""Inject request/trace correlation onto log records when present."""

from __future__ import annotations

import logging

from opentelemetry.trace import get_current_span

from app.common.request_context import get_request_context


class ObservabilityLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_request_context()
        if ctx.request_id and not getattr(record, "request_id", None):
            record.request_id = ctx.request_id
        if ctx.workspace_id is not None and not getattr(record, "workspace_id", None):
            record.workspace_id = str(ctx.workspace_id)
        if ctx.user_id is not None and not getattr(record, "user_id", None):
            record.user_id = str(ctx.user_id)
        if ctx.api_key_id is not None and not getattr(record, "api_key_id", None):
            record.api_key_id = str(ctx.api_key_id)

        span = get_current_span()
        span_ctx = span.get_span_context()
        if span_ctx.is_valid:
            if not getattr(record, "trace_id", None):
                record.trace_id = format(span_ctx.trace_id, "032x")
            if not getattr(record, "span_id", None):
                record.span_id = format(span_ctx.span_id, "016x")
        return True
