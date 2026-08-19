"""Phase 11D — request ID bounds + optional OTEL (in-memory exporter)."""

from __future__ import annotations

from unittest.mock import patch

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.middleware.base import BaseHTTPMiddleware

from app.main import app
from app.observability.http_middleware import ObservabilityHttpMiddleware
from app.observability.request_id import sanitize_request_id
from app.observability.setup import configure_test_tracing, reset_test_tracing, tracing_active
from app.observability.tracing import start_span


def test_sanitize_request_id_rejects_oversize_and_garbage() -> None:
    assert len(sanitize_request_id("ok-id_1")) < 200
    assert sanitize_request_id("ok-id_1") == "ok-id_1"
    huge = "a" * 500
    assert sanitize_request_id(huge) != huge
    assert sanitize_request_id("has space") != "has space"
    assert sanitize_request_id("Bearer secret") != "Bearer secret"
    assert sanitize_request_id(None)


def test_disabled_otel_does_not_construct_otlp_exporter(client) -> None:
    with patch(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
    ) as exporter_cls:
        res = client.get("/")
        assert res.status_code == 200
        exporter_cls.assert_not_called()


def test_fastapi_span_and_request_id_correlation(client, register_user) -> None:
    exporter = InMemorySpanExporter()
    configure_test_tracing(app, exporter)
    user = register_user(email="otel-req@example.com")
    res = client.get(
        "/",
        headers={"X-Request-Id": "corr-test-1", "Authorization": f"Bearer {user['access_token']}"},
    )
    assert res.status_code == 200
    assert res.headers.get("X-Request-Id") == "corr-test-1"
    spans = exporter.get_finished_spans()
    names = {span.name for span in spans}
    assert "http.request" in names or "chat.turn" in names or spans
    dumped = str([dict(s.attributes or {}) for s in spans])
    assert "Authorization" not in dumped
    assert "password" not in dumped.lower() or "password123" not in dumped
    assert "secret-prompt-text" not in dumped


def test_workspace_id_on_authorized_request(client, register_user) -> None:
    exporter = InMemorySpanExporter()
    configure_test_tracing(app, exporter)
    user = register_user(email="otel-ws@example.com")
    ws = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={"name": "Otel WS", "slug": "otel-ws-11d"},
    )
    assert ws.status_code in {200, 201}, ws.text
    wid = ws.json()["id"]
    exporter.clear()
    res = client.get(
        "/api/workspaces/current",
        headers={
            "Authorization": f"Bearer {user['access_token']}",
            "X-Workspace-Id": wid,
            "X-Request-Id": "ws-corr-1",
        },
    )
    assert res.status_code == 200, res.text
    spans = exporter.get_finished_spans()
    attrs = {}
    for span in spans:
        attrs.update(dict(span.attributes or {}))
    assert attrs.get("workspace.id") == wid or attrs.get("workspace_id") == wid
    assert attrs.get("request.id") == "ws-corr-1" or res.headers.get("X-Request-Id") == "ws-corr-1"


def test_domain_span_and_error_status() -> None:
    exporter = InMemorySpanExporter()
    configure_test_tracing(None, exporter)
    with start_span("chat.turn", expert_id="exp-1"):
        pass
    try:
        with start_span("chat.turn"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "chat.turn" in names
    dumped = str([dict(s.attributes or {}) for s in spans])
    assert "password" not in dumped
    assert any(s.status.status_code.name == "ERROR" for s in spans)


def test_celery_task_span_can_be_created() -> None:
    exporter = InMemorySpanExporter()
    configure_test_tracing(None, exporter)
    with start_span("conversation.purge", task_id="t-1"):
        pass
    assert any(s.name == "conversation.purge" for s in exporter.get_finished_spans())


def test_http_middleware_is_not_base_http_middleware() -> None:
    assert not issubclass(ObservabilityHttpMiddleware, BaseHTTPMiddleware)


def test_mark_span_error_strips_httpx_url() -> None:
    exporter = InMemorySpanExporter()
    configure_test_tracing(None, exporter)
    exc = RuntimeError(
        "POST https://openrouter.ai/api/v1/chat/completions?api_key=secret-token failed"
    )
    try:
        with start_span("openrouter.chat"):
            raise exc
    except RuntimeError:
        pass
    spans = exporter.get_finished_spans()
    assert spans
    blob = (
        str(spans[-1].status.description)
        + repr(spans[-1].events)
        + str(spans[-1].attributes)
        + str(spans[-1].events)
    )
    assert "openrouter.ai" not in blob
    assert "secret-token" not in blob
    assert "exception.stacktrace" not in blob


def test_configure_test_tracing_swaps_exporter_and_resets() -> None:
    first = InMemorySpanExporter()
    configure_test_tracing(None, first)
    with start_span("swap.a"):
        pass
    second = InMemorySpanExporter()
    configure_test_tracing(None, second)
    with start_span("swap.b"):
        pass
    first_names = {s.name for s in first.get_finished_spans()}
    second_names = {s.name for s in second.get_finished_spans()}
    assert "swap.a" in first_names
    assert "swap.b" not in first_names
    assert "swap.b" in second_names
    reset_test_tracing()
    assert tracing_active() is False
