from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db.session import get_db
from app.mcp.public_tokens import (
    derive_initial_widget_session_id,
    derive_turn_handle,
    normalize_client_turn_id,
    origin_digest,
    turn_handle_digest,
)
from app.widgets import cors_middleware, public_router
from app.widgets.cors_middleware import PublicWidgetCorsMiddleware
from app.widgets.service import WidgetService
from app.widgets.schemas import (
    WidgetMcpTurnIn,
    WidgetMcpTurnStatusIn,
    WidgetMcpTurnStatusOut,
)


def test_first_token_retry_derives_one_audience_bound_receipt() -> None:
    widget_id = uuid.uuid4()
    other_widget_id = uuid.uuid4()
    client_turn_id = str(uuid.uuid4())
    exact_origin = origin_digest("https://customer.example", secret="secret")
    other_origin = origin_digest("https://other.example", secret="secret")

    first_session = derive_initial_widget_session_id(
        client_turn_id=client_turn_id,
        widget_id=widget_id,
        origin_digest=exact_origin,
        secret="secret",
    )
    retry_session = derive_initial_widget_session_id(
        client_turn_id=client_turn_id,
        widget_id=widget_id,
        origin_digest=exact_origin,
        secret="secret",
    )
    raw_handle = derive_turn_handle(
        client_turn_id=client_turn_id,
        widget_id=widget_id,
        session_id=first_session,
        origin_digest=exact_origin,
        secret="secret",
    )

    assert first_session == retry_session
    assert raw_handle == derive_turn_handle(
        client_turn_id=client_turn_id,
        widget_id=widget_id,
        session_id=retry_session,
        origin_digest=exact_origin,
        secret="secret",
    )
    assert first_session != derive_initial_widget_session_id(
        client_turn_id=client_turn_id,
        widget_id=other_widget_id,
        origin_digest=exact_origin,
        secret="secret",
    )
    assert first_session != derive_initial_widget_session_id(
        client_turn_id=client_turn_id,
        widget_id=widget_id,
        origin_digest=other_origin,
        secret="secret",
    )
    assert turn_handle_digest(
        raw_handle,
        widget_id=widget_id,
        session_id=first_session,
        origin_digest=exact_origin,
        secret="secret",
    ) != turn_handle_digest(
        raw_handle,
        widget_id=other_widget_id,
        session_id=first_session,
        origin_digest=exact_origin,
        secret="secret",
    )


def test_widget_turn_inputs_require_high_entropy_redacted_values() -> None:
    with pytest.raises(ValueError):
        normalize_client_turn_id("short")
    with pytest.raises(ValidationError):
        WidgetMcpTurnIn(message="hello", client_turn_id="short")

    client_turn_id = str(uuid.uuid4())
    handle = "h" * 43
    turn = WidgetMcpTurnIn(message="hello", client_turn_id=client_turn_id)
    status = WidgetMcpTurnStatusIn(turn_handle=handle)

    assert turn.client_turn_id == client_turn_id
    assert status.turn_handle == handle
    assert client_turn_id not in repr(turn)
    assert handle not in repr(status)


def test_disabled_connector_hides_widget_transport_without_database_lookup() -> None:
    service = SimpleNamespace(
        settings=SimpleNamespace(mcp_connector_enabled=False),
        db=SimpleNamespace(
            scalar=lambda _query: (_ for _ in ()).throw(
                AssertionError("disabled MCP must not inspect surface bindings")
            )
        ),
    )

    assert not WidgetService._has_active_mcp_surface(  # type: ignore[arg-type]
        service,
        SimpleNamespace(),
    )


def _public_widget_test_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Mock]:
    app = FastAPI()
    app.include_router(public_router.router)
    app.dependency_overrides[get_db] = lambda: object()

    service = Mock()
    monkeypatch.setattr(public_router, "WidgetService", lambda _db: service)
    monkeypatch.setattr(public_router, "check_auth_rate_limit", lambda *_args: None)
    return TestClient(app), service


def test_widget_stream_and_status_use_locked_post_only_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = _public_widget_test_client(monkeypatch)
    widget_id = uuid.uuid4()
    handle = "t" * 43
    token = "audience-bound-token"
    origin = "https://customer.example"
    service.begin_mcp_turn.return_value = (
        WidgetMcpTurnStatusOut(
            turn_handle=handle,
            status="completed",
            answer="Final answer",
            session_token=token,
        ),
        origin,
    )

    stream = client.post(
        f"/api/public/widgets/{widget_id}/messages/stream",
        headers={"Origin": origin, "Accept": "text/event-stream"},
        json={"message": "hello", "client_turn_id": str(uuid.uuid4())},
    )

    assert stream.status_code == 200
    assert stream.headers["cache-control"].startswith("private, no-store")
    assert stream.headers["x-accel-buffering"] == "no"
    assert stream.headers["access-control-allow-origin"] == origin
    assert stream.headers["access-control-allow-methods"] == "POST, OPTIONS"
    frames = [frame for frame in stream.text.split("\n\n") if frame.strip()]
    assert [frame.splitlines()[0] for frame in frames] == [
        "event: accepted",
        "event: final",
    ]
    accepted = json.loads(frames[0].split("data: ", 1)[1])
    final = json.loads(frames[1].split("data: ", 1)[1])
    assert accepted == {
        "turn_handle": handle,
        "status": "accepted",
        "session_token": token,
    }
    assert final["answer"] == "Final answer"
    assert "citations" not in final
    assert "tool" not in final

    service.mcp_turn_status.return_value = (
        WidgetMcpTurnStatusOut(
            turn_handle=handle,
            status="completed",
            answer="Approved final",
            session_token="refreshed-token",
        ),
        origin,
    )
    status = client.post(
        f"/api/public/widgets/{widget_id}/tool-turns/status",
        headers={"Origin": origin, "X-Geem-Widget-Session": token},
        json={"turn_handle": handle},
    )

    assert status.status_code == 200
    assert status.headers["cache-control"].startswith("private, no-store")
    assert status.headers["access-control-allow-methods"] == "POST, OPTIONS"
    assert status.json() == {
        "turn_handle": handle,
        "status": "completed",
        "answer": "Approved final",
        "session_token": "refreshed-token",
    }
    assert service.mcp_turn_status.call_args.kwargs["raw_handle"] == handle
    assert service.mcp_turn_status.call_args.kwargs["session_token"] == token

    assert (
        client.get(f"/api/public/widgets/{widget_id}/turns/{handle}/status").status_code
        == 404
    )
    assert (
        client.get(f"/api/public/widgets/{widget_id}/turns/{handle}/stream").status_code
        == 404
    )


def test_legacy_widget_message_is_private_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = _public_widget_test_client(monkeypatch)
    widget_id = uuid.uuid4()
    origin = "https://customer.example"
    service.message.return_value = (
        SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "answer": "Private answer",
                "session_id": "opaque-session",
            }
        ),
        origin,
    )

    response = client.post(
        f"/api/public/widgets/{widget_id}/messages",
        headers={"Origin": origin},
        json={"message": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("private, no-store")
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_widget_cors_is_exact_per_public_route(monkeypatch: pytest.MonkeyPatch) -> None:
    widget_id = uuid.uuid4()
    origin = "https://customer.example"
    monkeypatch.setattr(
        cors_middleware,
        "_resolve_cors_origin",
        lambda *_args, **_kwargs: (origin, "ok"),
    )
    app = FastAPI()
    app.add_middleware(PublicWidgetCorsMiddleware)
    client = TestClient(app)

    status_preflight = client.options(
        f"/api/public/widgets/{widget_id}/tool-turns/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type,x-geem-widget-session"
            ),
        },
    )
    assert status_preflight.status_code == 204
    assert status_preflight.headers["access-control-allow-methods"] == "POST, OPTIONS"
    assert status_preflight.headers["access-control-allow-headers"] == (
        "Content-Type, X-Geem-Widget-Session"
    )

    overbroad_stream = client.options(
        f"/api/public/widgets/{widget_id}/messages/stream",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-geem-widget-session",
        },
    )
    assert overbroad_stream.status_code == 403

    wrong_method = client.options(
        f"/api/public/widgets/{widget_id}/tool-turns/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert wrong_method.status_code == 405

    old_secret_path = client.options(
        f"/api/public/widgets/{widget_id}/turns/{'s' * 43}/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert old_secret_path.status_code == 404

    # A malformed value that used to satisfy the middleware's broad
    # 36-character regex must remain an ordinary missing path, never a 500.
    malformed_widget_id = "f" * 36
    malformed = client.options(
        f"/api/public/widgets/{malformed_widget_id}/messages/stream",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert malformed.status_code == 404

    # Cache denial is attached by middleware even when validation or the
    # downstream route fails before its success response can add headers.
    error_response = client.post(
        f"/api/public/widgets/{widget_id}/tool-turns/status",
        headers={"Origin": origin},
    )
    assert error_response.status_code == 404
    assert error_response.headers["cache-control"].startswith("private, no-store")
