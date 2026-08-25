"""Normative Phase 14 router ordering and stream-lifecycle tests."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from types import SimpleNamespace

import anyio
import pytest
from starlette.requests import Request

import app.agent.router as agent_router
from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentGeemExtension,
    AgentProtocolError,
    AgentProviderResult,
    AgentProviderStreamEvent,
    AgentUsage,
    parse_agent_completion_request,
)
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.scopes import SCOPE_AGENT_WRITE
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def _principal() -> ApiKeyPrincipal:
    return ApiKeyPrincipal(
        api_key_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        scopes=(SCOPE_AGENT_WRITE,),
        key_prefix="geem_sk_test",
        name="Agent test key",
    )


def _request(expert_id: uuid.UUID | str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if expert_id is not None:
        headers.append((b"x-geem-expert-id", str(expert_id).encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/agent/chat/completions",
            "raw_path": b"/api/v1/agent/chat/completions",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("test", 443),
        }
    )


def _authenticated(
    payload: dict,
    *,
    principal: ApiKeyPrincipal | None = None,
) -> agent_router.AuthenticatedAgentBody:
    return agent_router.AuthenticatedAgentBody(
        principal=principal or _principal(),
        payload=payload,
        raw=json.dumps(payload, separators=(",", ":")).encode(),
        settings=Settings(_env_file=None),
    )


def _text_result(text: str = "done") -> AgentProviderResult:
    return AgentProviderResult(
        message=AgentAssistantResponseMessage(content=text, tool_calls=None),
        finish_reason="stop",
        usage=AgentUsage(prompt_tokens=8, completion_tokens=2, total_tokens=10),
        provider_model="private/provider",
    )


def test_openapi_stream_example_is_a_complete_successful_stream() -> None:
    example = agent_router._CHAT_RESPONSES[200]["content"]["text/event-stream"][
        "example"
    ]
    frames = [frame for frame in example.split("\n\n") if frame]

    assert frames[-1] == "data: [DONE]"
    chunks = [json.loads(frame.removeprefix("data: ")) for frame in frames[:-1]]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert chunks[-2]["choices"][0] == {
        "index": 0,
        "delta": {},
        "finish_reason": "stop",
    }
    assert chunks[-1]["choices"] == []
    assert chunks[-1]["usage"]["total_tokens"] == 1034
    assert sum("geem" in chunk for chunk in chunks) == 1


class _Db:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def rollback(self) -> None:
        self.events.append("rpm_db_rollback")


@pytest.mark.parametrize(
    ("payload", "expert_header", "expected_code"),
    [
        (
            {"model": "unknown/model", "messages": [{"role": "user", "content": "q"}]},
            uuid.uuid4(),
            "model_not_found",
        ),
        (
            {
                "model": PUBLIC_MODEL_ID,
                "messages": [
                    {"role": "user", "content": "q"},
                    {"role": "tool", "tool_call_id": "orphan", "content": "x"},
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            },
            uuid.uuid4(),
            "agent_invalid_tool_transcript",
        ),
        (
            {"model": PUBLIC_MODEL_ID, "messages": [{"role": "user", "content": "q"}]},
            "not-a-uuid",
            "validation_error",
        ),
    ],
)
def test_protocol_rejections_happen_before_rpm_and_paid_admission(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
    expert_header: uuid.UUID | str,
    expected_code: str,
) -> None:
    calls: list[str] = []

    class ForbiddenLimiter:
        def __init__(self, *_args, **_kwargs) -> None:
            calls.append("rpm")

    monkeypatch.setattr(agent_router, "ApiRateLimiter", ForbiddenLimiter)
    monkeypatch.setattr(
        agent_router,
        "admit_agent_completion",
        lambda **_kwargs: calls.append("paid_admission"),
    )

    with pytest.raises((AgentProtocolError, AppError)) as raised:
        agent_router.chat_completions(
            _request(expert_header),
            authenticated=_authenticated(payload),
            db=_Db(calls),
        )

    if isinstance(raised.value, AgentProtocolError):
        assert raised.value.code == expected_code
    else:
        assert raised.value.category == ErrorCategory.VALIDATION
    assert calls == []


def test_rpm_is_consumed_before_paid_admission_and_its_denial_stops_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class DenyingLimiter:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def consume(self, **_kwargs):
            calls.append("rpm")
            raise AppError(
                ErrorCategory.RATE_LIMIT_EXCEEDED,
                "rate limited",
                headers={"Retry-After": "20"},
            )

    monkeypatch.setattr(agent_router, "ApiRateLimiter", DenyingLimiter)
    monkeypatch.setattr(
        agent_router,
        "admit_agent_completion",
        lambda **_kwargs: calls.append("paid_admission"),
    )

    with pytest.raises(AppError) as raised:
        agent_router.chat_completions(
            _request(uuid.uuid4()),
            authenticated=_authenticated(
                {
                    "model": PUBLIC_MODEL_ID,
                    "messages": [{"role": "user", "content": "q"}],
                }
            ),
            db=_Db(calls),
        )

    assert raised.value.category == ErrorCategory.RATE_LIMIT_EXCEEDED
    assert calls == ["rpm"]


def test_rpm_transaction_cleanup_failure_is_locked_503_with_rate_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import OperationalError

    calls: list[str] = []

    class AllowingLimiter:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def consume(self, **_kwargs):
            calls.append("rpm")
            return SimpleNamespace(
                as_headers=lambda: {
                    "X-RateLimit-Limit": "50",
                    "X-RateLimit-Remaining": "49",
                    "X-RateLimit-Reset": "123",
                }
            )

    class FailingRollbackDb:
        def rollback(self) -> None:
            calls.append("rpm_db_rollback")
            raise OperationalError("ROLLBACK", {}, RuntimeError("db down"))

    monkeypatch.setattr(agent_router, "ApiRateLimiter", AllowingLimiter)
    monkeypatch.setattr(
        agent_router,
        "admit_agent_completion",
        lambda **_kwargs: calls.append("paid_admission"),
    )

    with pytest.raises(AppError) as raised:
        agent_router.chat_completions(
            _request(uuid.uuid4()),
            authenticated=_authenticated(
                {
                    "model": PUBLIC_MODEL_ID,
                    "messages": [{"role": "user", "content": "q"}],
                }
            ),
            db=FailingRollbackDb(),
        )

    assert raised.value.category == ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE
    assert raised.value.headers == {
        "X-RateLimit-Limit": "50",
        "X-RateLimit-Remaining": "49",
        "X-RateLimit-Reset": "123",
    }
    assert calls == ["rpm", "rpm_db_rollback"]


def test_nonstream_happy_path_orders_rpm_admission_prepare_provider_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    principal = _principal()
    admission = SimpleNamespace(closed=False)

    class AllowingLimiter:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def consume(self, **kwargs):
            assert kwargs == {
                "workspace_id": principal.workspace_id,
                "api_key_id": principal.api_key_id,
            }
            calls.append("rpm")
            return SimpleNamespace(
                as_headers=lambda: {
                    "X-RateLimit-Limit": "50",
                    "X-RateLimit-Remaining": "49",
                    "X-RateLimit-Reset": "123",
                }
            )

    def admit(**kwargs):
        assert kwargs["workspace_id"] == principal.workspace_id
        assert kwargs["api_key_id"] == principal.api_key_id
        calls.append("paid_admission")
        return admission

    class Service:
        def __init__(self, _db, *, settings) -> None:
            calls.append("service")

        def prepare_round(self, *, request, normalized, admission):
            assert normalized.retrieval_question == "q"
            calls.append("retrieval_prepare")
            return SimpleNamespace(request=request, admission=admission)

        def run_round(self, _prepared):
            calls.append("provider_and_settle")
            admission.closed = True
            return SimpleNamespace(
                result=_text_result(),
                geem=AgentGeemExtension(
                    retrieval="executed",
                    citations=[],
                    insufficient_context=False,
                    billed_tokens=10,
                ),
            )

    monkeypatch.setattr(agent_router, "ApiRateLimiter", AllowingLimiter)
    monkeypatch.setattr(agent_router, "admit_agent_completion", admit)
    monkeypatch.setattr(agent_router, "AgentCompletionService", Service)

    response = agent_router.chat_completions(
        _request(uuid.uuid4()),
        authenticated=_authenticated(
            {
                "model": PUBLIC_MODEL_ID,
                "messages": [{"role": "user", "content": "q"}],
            },
            principal=principal,
        ),
        db=_Db(calls),
    )

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "49"
    assert calls == [
        "rpm",
        "rpm_db_rollback",
        "paid_admission",
        "service",
        "retrieval_prepare",
        "provider_and_settle",
    ]


@pytest.mark.asyncio
async def test_global_disabled_gate_does_not_read_the_request_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = SimpleNamespace(
        headers={},
        stream=lambda: (_ for _ in ()).throw(AssertionError("body was read")),
    )
    monkeypatch.setattr(
        agent_router,
        "get_settings",
        lambda: Settings(_env_file=None, client_agent_api_enabled=False),
    )

    with pytest.raises(AppError) as raised:
        await agent_router.authenticated_agent_body(request, _principal())

    assert raised.value.category == ErrorCategory.AGENT_API_DISABLED


@pytest.mark.asyncio
async def test_bounded_reader_stops_chunked_body_at_cap() -> None:
    consumed: list[bytes] = []

    class ChunkedRequest:
        headers: dict[str, str] = {}

        async def stream(self):
            for chunk in (b"123", b"456", b"must-not-be-read"):
                consumed.append(chunk)
                yield chunk

    with pytest.raises(AgentProtocolError) as raised:
        await agent_router._read_bounded_body(ChunkedRequest(), 5)  # noqa: SLF001

    assert raised.value.status_code == 413
    assert consumed == [b"123", b"456"]


def test_models_validate_slash_model_before_paid_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(agent_router, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        agent_router, "require_agent_api_ready", lambda _settings: calls.append("global")
    )
    monkeypatch.setattr(
        agent_router,
        "require_agent_models_access",
        lambda _workspace_id: calls.append("paid_access"),
    )

    with pytest.raises(AgentProtocolError) as raised:
        agent_router.get_model("unknown/model", _principal())
    assert raised.value.code == "model_not_found"
    assert calls == ["global"]

    model = agent_router.get_model(PUBLIC_MODEL_ID, _principal())
    assert model.id == PUBLIC_MODEL_ID
    assert calls == ["global", "global", "paid_access"]


def test_enabled_agent_api_fails_ready_when_provider_credentials_are_missing() -> None:
    with pytest.raises(AppError) as raised:
        agent_router.require_agent_api_ready(
            Settings(
                _env_file=None,
                client_agent_api_enabled=True,
                openrouter_api_key="",
            )
        )

    assert raised.value.category == ErrorCategory.AGENT_API_DISABLED

    agent_router.require_agent_api_ready(
        Settings(
            _env_file=None,
            client_agent_api_enabled=True,
            openrouter_api_key="test-provider-key",
        )
    )


class _StreamingService:
    def __init__(self, events, *, finalize_error: Exception | None = None) -> None:
        self.events = events
        self.finalize_error = finalize_error
        self.calls: list[str] = []
        self.cancellation = None

    def stream_events(self, _prepared, *, cancellation=None):
        self.calls.append("stream_events")
        self.cancellation = cancellation
        return self.events

    def finalize_round(self, prepared, _result):
        self.calls.append("finalize")
        prepared.admission.closed = True
        if self.finalize_error is not None:
            raise self.finalize_error
        return AgentGeemExtension(
            retrieval="executed",
            citations=[],
            insufficient_context=False,
            billed_tokens=10,
        )

    def abort_round(self, prepared) -> None:
        self.calls.append("abort")
        prepared.admission.closed = True


def _prepared_stream():
    request = parse_agent_completion_request(
        {
            "model": PUBLIC_MODEL_ID,
            "messages": [{"role": "user", "content": "q"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
        settings=Settings(_env_file=None),
    )
    return SimpleNamespace(request=request, admission=SimpleNamespace(closed=False))


def _stream_response(service: _StreamingService, prepared):
    principal = _principal()
    return agent_router._stream_response(  # noqa: SLF001
        service=service,
        prepared=prepared,
        turn_id="turn-stream",
        created=123,
        rate_headers={"X-RateLimit-Limit": "50"},
        started=0.0,
        principal=principal,
        expert_id=uuid.uuid4(),
    )


async def _body_text(response) -> str:
    parts: list[str] = []
    async for item in response.body_iterator:
        parts.append(item.decode() if isinstance(item, bytes) else item)
    return "".join(parts)


@pytest.mark.asyncio
async def test_stream_is_primed_then_finalized_once_and_closed() -> None:
    prepared = _prepared_stream()
    service = _StreamingService(
        iter(
            [
                AgentProviderStreamEvent(type="start"),
                AgentProviderStreamEvent(type="content_delta", content="done"),
                AgentProviderStreamEvent(type="done", result=_text_result()),
            ]
        )
    )

    response = _stream_response(service, prepared)
    body = await _body_text(response)

    assert "data: [DONE]\n\n" in body
    assert body.count('"geem"') == 1
    assert service.calls == ["stream_events", "finalize", "abort"]
    assert prepared.admission.closed is True
    assert service.cancellation.cancelled is False


@pytest.mark.asyncio
async def test_stream_asgi_sends_headers_only_after_first_public_frame() -> None:
    prepared = _prepared_stream()
    service = _StreamingService(
        iter(
            [
                AgentProviderStreamEvent(type="start"),
                AgentProviderStreamEvent(type="done", result=_text_result()),
            ]
        )
    )
    response = _stream_response(service, prepared)
    sent: list[dict] = []
    no_disconnect = asyncio.Event()

    async def receive() -> dict:
        await no_disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}}
    with anyio.fail_after(1):
        await response(scope, receive, send)

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 200
    assert sent[1]["type"] == "http.response.body"
    assert b'"role":"assistant"' in sent[1]["body"]
    assert sent[-1] == {"type": "http.response.body", "body": b"", "more_body": False}
    assert service.calls == ["stream_events", "finalize", "abort"]
    assert prepared.admission.closed is True


@pytest.mark.asyncio
async def test_stream_failure_before_first_event_is_non_stream_error() -> None:
    prepared = _prepared_stream()

    def failed_events():
        raise AppError(ErrorCategory.GENERATION_FAILED, "before first event")
        yield  # pragma: no cover

    service = _StreamingService(failed_events())
    response = _stream_response(service, prepared)
    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    with pytest.raises(AppError) as raised:
        await response.stream_response(send)

    assert raised.value.category == ErrorCategory.GENERATION_FAILED
    assert raised.value.headers == {"X-RateLimit-Limit": "50"}
    assert sent == []
    assert service.calls == ["stream_events", "abort"]


@pytest.mark.asyncio
async def test_post_start_stream_error_has_one_error_frame_no_done_and_aborts() -> None:
    prepared = _prepared_stream()

    def failed_events():
        yield AgentProviderStreamEvent(type="start")
        raise AppError(ErrorCategory.GENERATION_FAILED, "after start")

    service = _StreamingService(failed_events())
    body = await _body_text(_stream_response(service, prepared))

    assert body.count('data: {"error"') == 1
    assert "data: [DONE]" not in body
    assert "finalize" not in service.calls
    assert service.calls == ["stream_events", "abort"]


@pytest.mark.asyncio
async def test_stream_settlement_failure_logs_explicit_error_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_stream()
    logged: list[dict] = []
    service = _StreamingService(
        iter(
            [
                AgentProviderStreamEvent(type="start"),
                AgentProviderStreamEvent(type="done", result=_text_result()),
            ]
        ),
        # Settlement can close/release the admission before propagating its
        # root error. Admission.closed therefore cannot be used as success.
        finalize_error=RuntimeError("settlement failed"),
    )
    monkeypatch.setattr(
        agent_router,
        "_log_round",
        lambda **fields: logged.append(fields),
    )

    body = await _body_text(_stream_response(service, prepared))

    assert body.count('data: {"error"') == 1
    assert "data: [DONE]" not in body
    assert service.calls == ["stream_events", "finalize", "abort"]
    assert logged[-1]["status"] == "error"
    assert logged[-1]["error_code"] == "generation_failed"


@pytest.mark.asyncio
async def test_stream_iterator_close_immediately_aborts_open_admission() -> None:
    prepared = _prepared_stream()
    service = _StreamingService(
        iter(
            [
                AgentProviderStreamEvent(type="start"),
                AgentProviderStreamEvent(type="content_delta", content="later"),
                AgentProviderStreamEvent(type="done", result=_text_result()),
            ]
        )
    )
    response = _stream_response(service, prepared)
    iterator = response.body_iterator

    await anext(iterator)
    await iterator.aclose()

    assert service.calls == ["stream_events", "abort"]
    assert prepared.admission.closed is True
    assert service.cancellation.cancelled is True


class _BlockedStreamingService(_StreamingService):
    def __init__(self) -> None:
        self.read_started = threading.Event()
        self.upstream_closed = threading.Event()
        self._release_read = threading.Event()
        self._bound_closer = self._close_upstream
        super().__init__(self._blocked_events())

    def stream_events(self, prepared, *, cancellation=None):
        assert cancellation is not None
        assert cancellation.bind(self._bound_closer) is True
        return super().stream_events(prepared, cancellation=cancellation)

    def _close_upstream(self) -> None:
        self.upstream_closed.set()
        self._release_read.set()

    def _blocked_events(self):
        try:
            yield AgentProviderStreamEvent(type="start")
            self.read_started.set()
            self._release_read.wait()
            raise AppError(ErrorCategory.GENERATION_FAILED, "closed upstream")
        finally:
            if self.cancellation is not None:
                self.cancellation.unbind(self._bound_closer)


class _BlockedBeforeFirstStreamingService(_StreamingService):
    def __init__(self) -> None:
        self.read_started = threading.Event()
        self.upstream_closed = threading.Event()
        self._release_read = threading.Event()
        self._bound_closer = self._close_upstream
        super().__init__(self._blocked_events())

    def _close_upstream(self) -> None:
        self.upstream_closed.set()
        self._release_read.set()

    def _blocked_events(self):
        assert self.cancellation is not None
        assert self.cancellation.bind(self._bound_closer) is True
        try:
            self.read_started.set()
            self._release_read.wait()
            raise AppError(ErrorCategory.GENERATION_FAILED, "closed upstream")
            yield  # pragma: no cover
        finally:
            self.cancellation.unbind(self._bound_closer)


@pytest.mark.asyncio
async def test_disconnect_closes_blocked_upstream_and_releases_admission() -> None:
    prepared = _prepared_stream()
    service = _BlockedStreamingService()
    iterator = _stream_response(service, prepared).body_iterator

    await anext(iterator)
    blocked_next = asyncio.create_task(anext(iterator))
    with anyio.fail_after(1):
        await anyio.to_thread.run_sync(service.read_started.wait)

    blocked_next.cancel()
    with anyio.fail_after(1):
        with pytest.raises(asyncio.CancelledError):
            await blocked_next

    assert service.upstream_closed.is_set()
    assert service.calls == ["stream_events", "abort"]
    assert prepared.admission.closed is True


@pytest.mark.asyncio
async def test_disconnect_before_first_event_closes_upstream_without_sending_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_stream()
    service = _BlockedBeforeFirstStreamingService()
    response = _stream_response(service, prepared)
    sent: list[dict] = []
    logged: list[dict] = []
    disconnected = asyncio.Event()
    monkeypatch.setattr(
        agent_router,
        "_log_round",
        lambda **fields: logged.append(fields),
    )

    async def receive() -> dict:
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}}
    response_task = asyncio.create_task(response(scope, receive, send))
    with anyio.fail_after(1):
        await anyio.to_thread.run_sync(service.read_started.wait)
    assert sent == []

    disconnected.set()
    with anyio.fail_after(1):
        await response_task

    assert sent == []
    assert service.upstream_closed.is_set()
    assert service.calls == ["stream_events", "abort"]
    assert prepared.admission.closed is True
    assert logged[-1]["status"] == "cancelled"
    assert logged[-1]["error_code"] is None
