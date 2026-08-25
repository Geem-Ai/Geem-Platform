from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentFunctionCall,
    AgentProviderResult,
    AgentProviderStreamEvent,
    AgentProviderToolCallDelta,
    AgentProtocolError,
    AgentToolCall,
    AgentUsage,
)
from app.api.v1.agent_compat import (
    AgentErrorBoundaryMiddleware,
    AgentStreamOutcome,
    agent_aware_http_exception_handler,
    agent_completion_response,
    agent_error_body,
    agent_error_status,
    agent_model_list_response,
    agent_model_object,
    is_agent_compat_path,
    iter_agent_completion_sse,
    resolve_agent_model,
)
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.errors import AppError, ErrorCategory


GEEM = {
    "retrieval": "executed",
    "citations": [],
    "insufficient_context": False,
    "billed_tokens": 11,
}


def _text_result() -> AgentProviderResult:
    return AgentProviderResult(
        message=AgentAssistantResponseMessage(content="Hello", tool_calls=None),
        finish_reason="stop",
        usage=AgentUsage(prompt_tokens=8, completion_tokens=3, total_tokens=11),
        provider_model="private/provider",
    )


def _tool_result() -> AgentProviderResult:
    return AgentProviderResult(
        message=AgentAssistantResponseMessage(
            content=None,
            tool_calls=[
                AgentToolCall(
                    id="call_1",
                    type="function",
                    function=AgentFunctionCall(
                        name="lookup",
                        arguments='{"id":"1"}',
                    ),
                )
            ],
        ),
        finish_reason="tool_calls",
        usage=AgentUsage(prompt_tokens=8, completion_tokens=3, total_tokens=11),
    )


def _payload(frame: str) -> dict:
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    return json.loads(frame[6:-2])


def test_model_discovery_is_stable_and_path_specific() -> None:
    model = agent_model_object()
    assert model.model_dump() == {
        "id": PUBLIC_MODEL_ID,
        "object": "model",
        "created": 1770000000,
        "owned_by": "geem",
    }
    assert agent_model_list_response().data == [model]
    assert resolve_agent_model(PUBLIC_MODEL_ID) == PUBLIC_MODEL_ID
    assert is_agent_compat_path("/api/v1/agent/models") is True
    assert is_agent_compat_path("/api/v1/chat/completions") is False


def test_nonstream_text_and_tool_shapes_hide_provider_model() -> None:
    text = agent_completion_response(
        _text_result(), geem=GEEM, completion_id="chatcmpl-fixed", created=123
    ).model_dump(mode="json")
    assert text["id"] == "chatcmpl-fixed"
    assert text["model"] == PUBLIC_MODEL_ID
    assert text["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Hello",
    }
    assert text["usage"]["total_tokens"] == 11
    assert text["geem"] == GEEM
    assert "private/provider" not in repr(text)

    tool = agent_completion_response(
        _tool_result(), geem=GEEM, completion_id="chatcmpl-tool", created=123
    ).model_dump(mode="json")
    message = tool["choices"][0]["message"]
    assert message["content"] is None
    assert message["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "lookup", "arguments": '{"id":"1"}'},
    }
    assert tool["choices"][0]["finish_reason"] == "tool_calls"


def test_text_sse_without_usage_has_stable_fields_and_geem_once() -> None:
    events = iter(
        [
            AgentProviderStreamEvent(type="start"),
            AgentProviderStreamEvent(type="content_delta", content="Hel"),
            AgentProviderStreamEvent(type="content_delta", content="lo"),
            AgentProviderStreamEvent(type="done", result=_text_result()),
        ]
    )
    frames = list(
        iter_agent_completion_sse(
            events,
            geem=GEEM,
            completion_id="chatcmpl-fixed",
            created=123,
            include_usage=False,
        )
    )
    assert frames[-1] == "data: [DONE]\n\n"
    chunks = [_payload(frame) for frame in frames[:-1]]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert [chunk["choices"][0]["delta"].get("content") for chunk in chunks[1:3]] == [
        "Hel",
        "lo",
    ]
    assert chunks[-1]["choices"][0] == {
        "index": 0,
        "delta": {},
        "finish_reason": "stop",
    }
    assert chunks[-1]["geem"] == GEEM
    assert all("usage" not in chunk for chunk in chunks)
    assert sum("geem" in chunk for chunk in chunks) == 1
    assert {chunk["id"] for chunk in chunks} == {"chatcmpl-fixed"}


def test_tool_sse_exact_indexed_deltas_and_usage_only_chunk() -> None:
    events = iter(
        [
            AgentProviderStreamEvent(type="start"),
            AgentProviderStreamEvent(
                type="tool_call_delta",
                tool_call=AgentProviderToolCallDelta(
                    index=0,
                    id="call_1",
                    type="function",
                    name="lookup",
                    arguments="{",
                ),
            ),
            AgentProviderStreamEvent(
                type="tool_call_delta",
                tool_call=AgentProviderToolCallDelta(index=0, arguments='"id":"1"}'),
            ),
            AgentProviderStreamEvent(type="done", result=_tool_result()),
        ]
    )
    frames = list(
        iter_agent_completion_sse(
            events,
            geem=lambda result: GEEM | {"billed_tokens": result.usage.total_tokens},
            completion_id="chatcmpl-tool",
            created=123,
            include_usage=True,
        )
    )
    chunks = [_payload(frame) for frame in frames[:-1]]
    first_call = chunks[1]["choices"][0]["delta"]["tool_calls"][0]
    assert first_call == {
        "index": 0,
        "function": {"name": "lookup", "arguments": "{"},
        "id": "call_1",
        "type": "function",
    }
    assert chunks[2]["choices"][0]["delta"]["tool_calls"][0] == {
        "index": 0,
        "function": {"arguments": '"id":"1"}'},
    }
    assert chunks[-2]["choices"][0]["finish_reason"] == "tool_calls"
    assert chunks[-1]["choices"] == []
    assert chunks[-1]["usage"] == {
        "prompt_tokens": 8,
        "completion_tokens": 3,
        "total_tokens": 11,
    }
    assert chunks[-1]["geem"] == GEEM
    assert all(chunk.get("usage") is None for chunk in chunks[:-1])
    assert sum("geem" in chunk for chunk in chunks) == 1


def test_post_200_error_is_one_frame_without_done() -> None:
    def events() -> Iterator[AgentProviderStreamEvent]:
        yield AgentProviderStreamEvent(type="start")
        raise AppError(ErrorCategory.GENERATION_FAILED, "provider broke")

    outcome = AgentStreamOutcome()
    frames = list(
        iter_agent_completion_sse(
            events(),
            geem=GEEM,
            completion_id="chatcmpl-error",
            created=123,
            outcome=outcome,
        )
    )
    assert frames[0].startswith("data: {")
    error = _payload(frames[-1])
    assert error == {
        "error": {
            "message": "provider broke",
            "type": "server_error",
            "param": None,
            "code": "generation_failed",
        }
    }
    assert frames.count("data: [DONE]\n\n") == 0
    assert sum('"error"' in frame for frame in frames) == 1
    assert outcome.status == "error"
    assert outcome.error_code == "generation_failed"


def test_protocol_error_envelope_preserves_exact_model_contract() -> None:
    exc = AgentProtocolError(
        "Unknown model.",
        code="model_not_found",
        param="model",
        status_code=404,
    )
    assert agent_error_status(exc) == 404
    assert agent_error_body(exc) == {
        "error": {
            "message": "Unknown model.",
            "type": "invalid_request_error",
            "param": "model",
            "code": "model_not_found",
        }
    }


def test_daily_quota_error_exposes_safe_reset_metadata() -> None:
    exc = AppError(
        ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED,
        "Agents AI daily request quota exceeded.",
        details={
            "metric": "app:agents-ai:requests",
            "limit": 100,
            "used": 100,
            "remaining": 0,
            "reset_at": "2026-08-26T00:00:00+00:00",
            "internal": "must-not-leak",
        },
        headers={"Retry-After": "3600"},
    )

    assert agent_error_status(exc) == 429
    assert agent_error_body(exc) == {
        "error": {
            "message": "Agents AI daily request quota exceeded.",
            "type": "insufficient_quota",
            "param": None,
            "code": "agent_request_quota_exceeded",
            "details": {
                "metric": "app:agents-ai:requests",
                "limit": 100,
                "used": 100,
                "remaining": 0,
                "reset_at": "2026-08-26T00:00:00+00:00",
            },
        }
    }


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("test", 123),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "status", "detail", "code"),
    [
        ("/api/v1/agent/unknown", 404, "Not Found", "not_found"),
        (
            "/api/v1/agent/chat/completions",
            405,
            "Method Not Allowed",
            "method_not_allowed",
        ),
    ],
)
async def test_agent_routing_http_errors_use_exact_openai_envelope(
    path: str,
    status: int,
    detail: str,
    code: str,
) -> None:
    response = await agent_aware_http_exception_handler(
        _request(path),
        StarletteHTTPException(
            status,
            detail,
            headers={"Allow": "POST"} if status == 405 else None,
        ),
    )

    assert response.status_code == status
    assert json.loads(response.body) == {
        "error": {
            "message": detail,
            "type": "invalid_request_error",
            "param": None,
            "code": code,
        }
    }
    if status == 405:
        assert response.headers["allow"] == "POST"


@pytest.mark.anyio
async def test_non_agent_routing_http_error_keeps_fastapi_body() -> None:
    response = await agent_aware_http_exception_handler(
        _request("/not-an-agent-route"),
        StarletteHTTPException(404, "Not Found"),
    )

    assert response.status_code == 404
    assert json.loads(response.body) == {"detail": "Not Found"}


@pytest.mark.anyio
async def test_agent_error_boundary_wraps_unexpected_pre_response_failure() -> None:
    async def failing_app(_scope, _receive, _send) -> None:
        raise RuntimeError("private failure")

    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = AgentErrorBoundaryMiddleware(failing_app)
    await middleware(
        {"type": "http", "path": "/api/v1/agent/models"}, receive, send
    )

    assert sent[0]["status"] == 500
    body = json.loads(sent[1]["body"])
    assert body == {
        "error": {
            "message": "Agent generation failed.",
            "type": "server_error",
            "param": None,
            "code": "generation_failed",
        }
    }


@pytest.mark.anyio
async def test_agent_error_boundary_maps_raw_database_failure_to_locked_503() -> None:
    from sqlalchemy.exc import OperationalError

    async def failing_app(_scope, _receive, _send) -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = AgentErrorBoundaryMiddleware(failing_app)
    await middleware(
        {"type": "http", "path": "/api/v1/agent/chat/completions"},
        receive,
        send,
    )

    assert sent[0]["status"] == 503
    assert json.loads(sent[1]["body"])["error"] == {
        "message": "Agent runtime authority is temporarily unavailable.",
        "type": "server_error",
        "param": None,
        "code": "app_runtime_access_unavailable",
    }
