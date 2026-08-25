"""Exact OpenAI-compatible wire mapping for the separate Phase 14 Agent API."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.exception_handlers import (
    http_exception_handler as fastapi_http_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.agent.constants import (
    PUBLIC_AGENT_MODEL_CREATED,
    PUBLIC_AGENT_MODEL_IDS,
    PUBLIC_AGENT_MODEL_OWNER,
)
from app.agent.schemas import (
    AgentCompletionChoice,
    AgentCompletionResponse,
    AgentGeemExtension,
    AgentModelListResponse,
    AgentModelObject,
    AgentProtocolError,
    AgentProviderResult,
    AgentProviderStreamEvent,
)
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.errors import HTTP_STATUS_BY_CATEGORY, AppError, ErrorCategory


AGENT_API_PREFIX = "/api/v1/agent"
logger = logging.getLogger(__name__)

_AUTH_CATEGORIES = frozenset(
    {
        ErrorCategory.UNAUTHORIZED,
        ErrorCategory.INVALID_CREDENTIALS,
        ErrorCategory.SESSION_EXPIRED,
        ErrorCategory.SESSION_REVOKED,
    }
)
_PERMISSION_CATEGORIES = frozenset(
    {
        ErrorCategory.FORBIDDEN,
        ErrorCategory.WORKSPACE_ACCESS_DENIED,
        ErrorCategory.EXPERT_ACCESS_DENIED,
        ErrorCategory.AGENT_SCOPE_REQUIRED,
    }
)
_RATE_CATEGORIES = frozenset(
    {
        ErrorCategory.RATE_LIMIT_EXCEEDED,
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.QUOTA_EXCEEDED,
    }
)
_QUOTA_CATEGORIES = frozenset(
    {
        ErrorCategory.INSUFFICIENT_CREDITS,
        ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED,
    }
)

_PUBLIC_QUOTA_DETAIL_KEYS = (
    "metric",
    "limit",
    "used",
    "remaining",
    "reset_at",
)


@dataclass(slots=True)
class AgentStreamOutcome:
    """Explicit terminal state shared with request telemetry."""

    status: str = "pending"
    error_code: str | None = None

    def succeed(self) -> None:
        self.status = "ok"
        self.error_code = None

    def fail(self, code: str) -> None:
        self.status = "error"
        self.error_code = code


class AgentErrorBoundaryMiddleware:
    """Keep every pre-response Agent failure inside the OpenAI envelope.

    FastAPI exception handlers cover the public typed failures. This narrow
    outer boundary also catches failures from dependencies and transaction
    cleanup that occur before a response has started. Post-200 stream failures
    remain owned by :func:`iter_agent_completion_sse`.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not is_agent_compat_path(
            str(scope.get("path") or "")
        ):
            await self.app(scope, receive, send)
            return

        response_started = False

        async def guarded_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, guarded_send)
        except Exception as exc:
            if response_started:
                raise
            public_exc: Exception = exc
            if isinstance(exc, SQLAlchemyError):
                # SQLAlchemy exception strings may include bound values. Keep
                # the public failure typed without copying SQL/parameters into
                # logs at this last-resort boundary.
                logger.error("unhandled_agent_request_database_error")
                public_exc = AppError(
                    ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                    "Agent runtime authority is temporarily unavailable.",
                    retryable=True,
                )
            else:
                logger.exception("unhandled_agent_request_error")
            await agent_error_response(public_exc)(scope, receive, send)


def is_agent_compat_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized == AGENT_API_PREFIX or normalized.startswith(
        AGENT_API_PREFIX + "/"
    )


async def agent_aware_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> Response:
    """Wrap routing errors only on the Agent compatibility surface."""

    if not is_agent_compat_path(request.url.path):
        return await fastapi_http_exception_handler(request, exc)

    status = int(exc.status_code)
    message = (
        exc.detail
        if isinstance(exc.detail, str) and exc.detail
        else f"HTTP {status} error."
    )
    code = {
        404: ErrorCategory.NOT_FOUND.value,
        405: "method_not_allowed",
    }.get(status, f"http_{status}_error")
    error_type = "invalid_request_error"
    if status == 401:
        error_type = "authentication_error"
    elif status == 403:
        error_type = "permission_error"
    elif status == 429:
        error_type = "rate_limit_error"
    elif status >= 500:
        error_type = "server_error"
    protocol_error = AgentProtocolError(
        message,
        code=code,
        param=None,
        status_code=status,
        error_type=error_type,
    )
    return JSONResponse(
        status_code=status,
        content=agent_error_body(protocol_error),
        headers=exc.headers,
    )


def resolve_agent_model(model_id: str, *, param: str = "model_id") -> str:
    if model_id not in PUBLIC_AGENT_MODEL_IDS:
        raise AgentProtocolError(
            f"The model '{model_id}' does not exist or is not available.",
            code="model_not_found",
            param=param,
            status_code=404,
        )
    return model_id


def agent_model_object(model_id: str = PUBLIC_MODEL_ID) -> AgentModelObject:
    resolved = resolve_agent_model(model_id)
    return AgentModelObject(
        id=resolved,
        created=PUBLIC_AGENT_MODEL_CREATED,
        owned_by=PUBLIC_AGENT_MODEL_OWNER,
    )


def agent_model_list_response() -> AgentModelListResponse:
    return AgentModelListResponse(data=[agent_model_object()])


def agent_completion_id(turn_id: str | None = None) -> str:
    token = str(turn_id).strip() if turn_id is not None else uuid.uuid4().hex
    return token if token.startswith("chatcmpl-") else f"chatcmpl-{token}"


def agent_completion_response(
    result: AgentProviderResult,
    *,
    geem: AgentGeemExtension | Mapping[str, Any],
    completion_id: str | None = None,
    turn_id: str | None = None,
    created: int | None = None,
    model: str = PUBLIC_MODEL_ID,
) -> AgentCompletionResponse:
    resolved_model = resolve_agent_model(model, param="model")
    return AgentCompletionResponse(
        id=completion_id or agent_completion_id(turn_id),
        created=int(time.time()) if created is None else int(created),
        model=resolved_model,
        choices=[
            AgentCompletionChoice(
                message=result.message,
                finish_reason=result.finish_reason,
            )
        ],
        usage=result.usage,
        geem=_coerce_geem(geem),
    )


def iter_agent_completion_sse(
    events: Iterator[AgentProviderStreamEvent],
    *,
    geem: (
        AgentGeemExtension
        | Mapping[str, Any]
        | Callable[[AgentProviderResult], AgentGeemExtension | Mapping[str, Any]]
    ),
    completion_id: str | None = None,
    turn_id: str | None = None,
    created: int | None = None,
    model: str = PUBLIC_MODEL_ID,
    include_usage: bool = False,
    outcome: AgentStreamOutcome | None = None,
) -> Iterator[str]:
    """Map validated provider events to exact Chat Completions SSE frames.

    The router should prime the provider iterator before returning HTTP 200 so
    failures that occur before its first event remain ordinary non-2xx errors.
    Once this adapter emits a frame, failures become one SSE error frame and
    the stream closes without ``[DONE]``.
    """

    resolved_model = resolve_agent_model(model, param="model")
    cid = completion_id or agent_completion_id(turn_id)
    timestamp = int(time.time()) if created is None else int(created)
    role_emitted = False

    try:
        for event in events:
            if event.type == "start":
                if not role_emitted:
                    yield _sse_data(
                        _agent_chunk(
                            completion_id=cid,
                            created=timestamp,
                            model=resolved_model,
                            delta={"role": "assistant"},
                            include_usage=include_usage,
                        )
                    )
                    role_emitted = True
                continue

            if event.type == "content_delta":
                if event.content is None:
                    raise ValueError("content_delta is missing content")
                if not role_emitted:
                    yield _sse_data(
                        _agent_chunk(
                            completion_id=cid,
                            created=timestamp,
                            model=resolved_model,
                            delta={"role": "assistant"},
                            include_usage=include_usage,
                        )
                    )
                    role_emitted = True
                yield _sse_data(
                    _agent_chunk(
                        completion_id=cid,
                        created=timestamp,
                        model=resolved_model,
                        delta={"content": event.content},
                        include_usage=include_usage,
                    )
                )
                continue

            if event.type == "tool_call_delta":
                if event.tool_call is None:
                    raise ValueError("tool_call_delta is missing tool data")
                if not role_emitted:
                    yield _sse_data(
                        _agent_chunk(
                            completion_id=cid,
                            created=timestamp,
                            model=resolved_model,
                            delta={"role": "assistant"},
                            include_usage=include_usage,
                        )
                    )
                    role_emitted = True
                call = event.tool_call
                function: dict[str, Any] = {}
                if call.name is not None:
                    function["name"] = call.name
                if call.arguments is not None:
                    function["arguments"] = call.arguments
                tool_delta: dict[str, Any] = {"index": call.index, "function": function}
                if call.id is not None:
                    tool_delta["id"] = call.id
                if call.type is not None:
                    tool_delta["type"] = call.type
                yield _sse_data(
                    _agent_chunk(
                        completion_id=cid,
                        created=timestamp,
                        model=resolved_model,
                        delta={"tool_calls": [tool_delta]},
                        include_usage=include_usage,
                    )
                )
                continue

            if event.type != "done" or event.result is None:
                raise ValueError("invalid Agent provider event")
            result = event.result
            if not role_emitted:
                yield _sse_data(
                    _agent_chunk(
                        completion_id=cid,
                        created=timestamp,
                        model=resolved_model,
                        delta={"role": "assistant"},
                        include_usage=include_usage,
                    )
                )
            extension = geem(result) if callable(geem) else geem
            extension_payload = _coerce_geem(extension).model_dump(mode="json")
            terminal_extra: dict[str, Any] | None = None
            if not include_usage:
                terminal_extra = {"geem": extension_payload}
            if outcome is not None:
                outcome.succeed()
            yield _sse_data(
                _agent_chunk(
                    completion_id=cid,
                    created=timestamp,
                    model=resolved_model,
                    delta={},
                    finish_reason=result.finish_reason,
                    include_usage=include_usage,
                    extra=terminal_extra,
                )
            )
            if include_usage:
                yield _sse_data(
                    {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": timestamp,
                        "model": resolved_model,
                        "choices": [],
                        "usage": result.usage.model_dump(mode="json"),
                        "geem": extension_payload,
                    }
                )
            yield _sse_data("[DONE]")
            return
        raise RuntimeError("Agent provider stream ended without a terminal event")
    except Exception as exc:
        error = agent_error_body(exc)
        if outcome is not None:
            outcome.fail(str(error["error"]["code"]))
        yield _sse_data(error)


def agent_error_body(exc: AgentProtocolError | AppError | Exception) -> dict[str, Any]:
    public_details: dict[str, Any] | None = None
    if isinstance(exc, AgentProtocolError):
        message = exc.message
        code = exc.code
        param = exc.param
        error_type = exc.error_type
    elif isinstance(exc, AppError):
        status = agent_error_status(exc)
        message = exc.message
        code = exc.category.value
        param = None
        if isinstance(exc.details, Mapping) and isinstance(exc.details.get("param"), str):
            param = exc.details["param"]
        if (
            exc.category == ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED
            and isinstance(exc.details, Mapping)
        ):
            public_details = {
                key: exc.details[key]
                for key in _PUBLIC_QUOTA_DETAIL_KEYS
                if key in exc.details
            } or None
        error_type = agent_error_type(exc.category, status)
    else:
        message = "Agent generation failed."
        code = ErrorCategory.GENERATION_FAILED.value
        param = None
        error_type = "server_error"
    error: dict[str, Any] = {
        "message": message,
        "type": error_type,
        "param": param,
        "code": code,
    }
    if public_details is not None:
        # OpenAI clients ignore unknown error properties, while integrators can
        # use this stable Geem extension to schedule an exact daily-quota retry.
        error["details"] = public_details
    return {"error": error}


def agent_error_status(exc: AgentProtocolError | AppError | Exception) -> int:
    if isinstance(exc, AgentProtocolError):
        return exc.status_code
    if not isinstance(exc, AppError):
        return 500
    status = HTTP_STATUS_BY_CATEGORY.get(exc.category.value, 500)
    if status == 500 and (
        exc.category.value.endswith("_failed") or "rate" in exc.category.value
    ):
        status = 502
    return 400 if status == 422 else status


def agent_error_type(category: ErrorCategory, status: int) -> str:
    if category in _AUTH_CATEGORIES:
        return "authentication_error"
    if category in _QUOTA_CATEGORIES:
        return "insufficient_quota"
    if category in _PERMISSION_CATEGORIES or status == 403:
        return "permission_error"
    if category in _RATE_CATEGORIES:
        return "rate_limit_error"
    if status >= 500:
        return "server_error"
    return "invalid_request_error"


def agent_error_response(exc: AgentProtocolError | AppError | Exception) -> JSONResponse:
    headers = exc.headers if isinstance(exc, AppError) else None
    return JSONResponse(
        status_code=agent_error_status(exc),
        content=agent_error_body(exc),
        headers=headers or None,
    )


def agent_validation_response(exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = [str(part) for part in first.get("loc", ()) if part != "body"]
    param = ".".join(loc) or None
    protocol_error = AgentProtocolError(
        str(first.get("msg") or "Invalid request."),
        code=(
            "agent_invalid_tool_transcript"
            if loc and loc[0] == "messages"
            else "agent_unsupported_parameter"
        ),
        param=param,
    )
    return agent_error_response(protocol_error)


def iter_agent_sse_error(exc: AgentProtocolError | AppError | Exception) -> Iterator[str]:
    yield _sse_data(agent_error_body(exc))


def _agent_chunk(
    *,
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    include_usage: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    if include_usage:
        payload["usage"] = None
    if extra:
        payload.update(extra)
    return payload


def _sse_data(payload: Any) -> str:
    if payload == "[DONE]":
        return "data: [DONE]\n\n"
    return "data: " + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ) + "\n\n"


def _coerce_geem(value: AgentGeemExtension | Mapping[str, Any]) -> AgentGeemExtension:
    if isinstance(value, AgentGeemExtension):
        return value
    return AgentGeemExtension.model_validate(value)


__all__ = [
    "AgentErrorBoundaryMiddleware",
    "AGENT_API_PREFIX",
    "AgentStreamOutcome",
    "agent_aware_http_exception_handler",
    "agent_completion_id",
    "agent_completion_response",
    "agent_error_body",
    "agent_error_response",
    "agent_error_status",
    "agent_error_type",
    "agent_model_list_response",
    "agent_model_object",
    "agent_validation_response",
    "is_agent_compat_path",
    "iter_agent_completion_sse",
    "iter_agent_sse_error",
    "resolve_agent_model",
]
