"""Optional OpenTelemetry bootstrap. Disabled by default; no exporter on local."""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.trace import Status, StatusCode

from app.core.config import get_settings
from app.observability.logging_filter import ObservabilityLogFilter

logger = logging.getLogger(__name__)

_STATE: dict[str, Any] = {
    "log_filter": False,
    "provider": False,
    "libs": False,
    "test_exporter": None,
}


def parse_otlp_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for part in (raw or "").split(","):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return headers


def _sampler():
    settings = get_settings()
    name = (settings.otel_traces_sampler or "parentbased_traceidratio").strip().lower()
    arg = float(settings.otel_traces_sampler_arg)
    arg = min(1.0, max(0.0, arg))
    if name in {"always_on", "alwayson"}:
        return ALWAYS_ON
    if name in {"always_off", "alwaysoff"}:
        return ALWAYS_OFF
    if name in {"traceidratio", "trace_id_ratio"}:
        return TraceIdRatioBased(arg)
    return ParentBased(TraceIdRatioBased(arg))


def tracing_active() -> bool:
    return bool(_STATE["provider"])


def _install_log_filter() -> None:
    if _STATE["log_filter"]:
        return
    filt = ObservabilityLogFilter()
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig()
    for handler in root.handlers:
        handler.addFilter(filt)
    _STATE["log_filter"] = True


def setup_observability(app: Any | None = None) -> None:
    """Initialize tracing once. No-op when ``OTEL_ENABLED`` is false."""
    _install_log_filter()
    settings = get_settings()
    if not settings.otel_enabled:
        return
    _ensure_provider(test_exporter=None)
    _instrument_libraries()


def configure_test_tracing(app: Any, exporter: SpanExporter) -> None:
    """In-memory exporter for tests. Does not open network connections."""
    _install_log_filter()
    _STATE["test_exporter"] = exporter
    _ensure_provider(test_exporter=exporter)


def _ensure_provider(*, test_exporter: SpanExporter | None) -> None:
    if _STATE["provider"]:
        if test_exporter is not None:
            provider = trace.get_tracer_provider()
            if isinstance(provider, TracerProvider):
                provider.add_span_processor(SimpleSpanProcessor(test_exporter))
        return

    settings = get_settings()
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.namespace": "geem",
            "deployment.environment": settings.app_env,
        }
    )
    sampler = ALWAYS_ON if test_exporter is not None else _sampler()
    provider = TracerProvider(resource=resource, sampler=sampler)
    if test_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(test_exporter))
    elif (settings.otel_exporter_otlp_endpoint or "").strip():
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = settings.otel_exporter_otlp_endpoint.strip()
        headers = parse_otlp_headers(settings.otel_exporter_otlp_headers)
        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(
            "otel.exporter.configured",
            extra={"status": "otlp", "operation": "otel_setup"},
        )
    else:
        logger.info(
            "otel.exporter.skipped",
            extra={"reason": "empty_endpoint", "operation": "otel_setup"},
        )
    trace.set_tracer_provider(provider)
    _STATE["provider"] = True


def _instrument_libraries() -> None:
    if _STATE["libs"]:
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.db.session import engine

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except Exception:
        logger.debug("otel.sqlalchemy.instrument_skipped", exc_info=True)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.debug("otel.httpx.instrument_skipped", exc_info=True)
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception:
        logger.debug("otel.redis.instrument_skipped", exc_info=True)
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except Exception:
        logger.debug("otel.celery.instrument_skipped", exc_info=True)
    _STATE["libs"] = True


def record_http_error_on_span(*, status_code: int, message: str | None = None) -> None:
    if status_code < 500:
        return
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.set_status(Status(StatusCode.ERROR, (message or "http_error")[:200]))
