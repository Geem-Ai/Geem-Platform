"""Manual domain spans. Prefer stable operation names, not entity IDs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from app.observability.attributes import (
    attach_request_context,
    mark_span_error,
    set_safe_attributes,
)

TRACER_NAME = "geem"


def get_tracer():
    return trace.get_tracer(TRACER_NAME)


@contextmanager
def start_span(name: str, **attrs: Any) -> Iterator[Span]:
    """Start a recording span when a TracerProvider is configured.

    ``name`` must be a low-cardinality operation (``chat.turn``, ``qdrant.search``).
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        attach_request_context(span)
        set_safe_attributes(span, attrs)
        try:
            yield span
        except Exception as exc:
            mark_span_error(span, exc)
            raise


def set_ok(span: Span) -> None:
    if span.is_recording():
        span.set_status(Status(StatusCode.OK))
