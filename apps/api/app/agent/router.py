"""OpenAI-compatible public routes for the paid Agents AI App."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass
from itertools import chain
from typing import Any

import anyio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect
from starlette.types import Receive, Scope, Send

from app.agent.admission import admit_agent_completion, require_agent_models_access
from app.agent.messages import normalize_agent_messages
from app.agent.schemas import (
    AgentCompletionRequest,
    AgentCompletionResponse,
    AgentModelListResponse,
    AgentModelObject,
    AgentProtocolError,
    AgentProviderStreamEvent,
    parse_agent_completion_request,
)
from app.agent.service import AgentCompletionService, PreparedAgentRound
from app.api.v1.agent_compat import (
    AgentStreamOutcome,
    agent_completion_response,
    agent_model_list_response,
    agent_model_object,
    iter_agent_completion_sse,
    resolve_agent_model,
)
from app.api.v1.openai_compat import parse_expert_id
from app.api_keys.dependencies import require_api_scope
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.scopes import SCOPE_AGENT_WRITE
from app.core.config import (
    Settings,
    assert_agent_provider_settings,
    get_settings,
)
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.openrouter.client import OpenRouterStreamCancellation
from app.rate_limits.service import ApiRateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent-api"])


@dataclass(frozen=True, slots=True)
class AuthenticatedAgentBody:
    principal: ApiKeyPrincipal
    payload: Mapping[str, Any]
    raw: bytes
    settings: Settings


_COMPLETION_EXAMPLE = {
    "id": "chatcmpl-018f4f0a",
    "object": "chat.completion",
    "created": 1_770_000_000,
    "model": "dalseen/geem-1.0",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_01",
                        "type": "function",
                        "function": {
                            "name": "lookup_order",
                            "arguments": '{"order_id":"123"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 34, "total_tokens": 1034},
    "geem": {
        "retrieval": "executed",
        "citations": [],
        "insufficient_context": False,
        "billed_tokens": 1034,
    },
}

_ERROR_EXAMPLE = {
    "error": {
        "message": "The submitted tool transcript is invalid.",
        "type": "invalid_request_error",
        "param": "messages",
        "code": "agent_invalid_tool_transcript",
    }
}

_CHAT_RESPONSES = {
    200: {
        "description": (
            "One OpenAI Chat Completion, or an SSE Chat Completions stream "
            "terminated by `data: [DONE]`."
        ),
        "content": {
            "application/json": {"example": _COMPLETION_EXAMPLE},
            "text/event-stream": {
                "example": (
                    'data: {"id":"chatcmpl-018f4f0a","object":'
                    '"chat.completion.chunk","created":1770000000,"model":'
                    '"dalseen/geem-1.0","choices":[{"index":0,"delta":'
                    '{"role":"assistant"},"finish_reason":null}],"usage":null}\n\n'
                    'data: {"id":"chatcmpl-018f4f0a","object":'
                    '"chat.completion.chunk","created":1770000000,"model":'
                    '"dalseen/geem-1.0","choices":[{"index":0,"delta":'
                    '{"content":"Done."},"finish_reason":null}],"usage":null}\n\n'
                    'data: {"id":"chatcmpl-018f4f0a","object":'
                    '"chat.completion.chunk","created":1770000000,"model":'
                    '"dalseen/geem-1.0","choices":[{"index":0,"delta":{},'
                    '"finish_reason":"stop"}],"usage":null}\n\n'
                    'data: {"id":"chatcmpl-018f4f0a","object":'
                    '"chat.completion.chunk","created":1770000000,"model":'
                    '"dalseen/geem-1.0","choices":[],"usage":'
                    '{"prompt_tokens":1000,"completion_tokens":34,'
                    '"total_tokens":1034},"geem":{"retrieval":"executed",'
                    '"citations":[],"insufficient_context":false,'
                    '"billed_tokens":1034}}\n\n'
                    "data: [DONE]\n\n"
                )
            },
        },
    },
    400: {
        "description": "Invalid Agent request, controls, or tool transcript.",
        "content": {"application/json": {"example": _ERROR_EXAMPLE}},
    },
    401: {"description": "Missing or invalid Workspace API key."},
    402: {"description": "Agents AI subscription or AI credits are required."},
    403: {"description": "Missing scope or Expert client-agent opt-in."},
    404: {"description": "Unknown model or inaccessible Expert."},
    409: {"description": "Agents AI is unavailable or not installed."},
    429: {"description": "RPM, AI-token, or Agents AI daily quota exceeded."},
    503: {"description": "Agent API or paid runtime authority is unavailable."},
}


def require_agent_api_ready(settings: Settings) -> None:
    """Apply the operational and reviewed provider-capability gates."""

    if not settings.client_agent_api_enabled:
        raise AppError(
            ErrorCategory.AGENT_API_DISABLED,
            "The Agent API is not enabled.",
            retryable=True,
        )
    try:
        assert_agent_provider_settings(settings)
    except RuntimeError as exc:
        logger.error("agent_provider_readiness_failed", extra={"reason": str(exc)})
        raise AppError(
            ErrorCategory.AGENT_API_DISABLED,
            "The Agent API provider path is not ready.",
            retryable=True,
        ) from exc


async def authenticated_agent_body(
    request: Request,
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_AGENT_WRITE)),
) -> AuthenticatedAgentBody:
    """Authenticate/scope/global-gate before reading or validating JSON."""

    settings = get_settings()
    require_agent_api_ready(settings)
    raw = await _read_bounded_body(request, settings.agent_max_body_bytes)
    try:
        payload = json.loads(raw, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise AgentProtocolError(
            "Request body must contain valid JSON.",
            code="agent_unsupported_parameter",
            param=None,
        ) from None
    if not isinstance(payload, Mapping):
        raise AgentProtocolError(
            "Request body must be a JSON object.",
            code="agent_unsupported_parameter",
            param=None,
        )
    return AuthenticatedAgentBody(
        principal=principal,
        payload=payload,
        raw=raw,
        settings=settings,
    )


@router.post(
    "/chat/completions",
    response_model=AgentCompletionResponse,
    responses=_CHAT_RESPONSES,
    openapi_extra={
        "security": [{"ApiKey": []}],
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": AgentCompletionRequest.model_json_schema(),
                    "examples": {
                        "tool_round": {
                            "value": {
                                "model": "dalseen/geem-1.0",
                                "messages": [{"role": "user", "content": "Find order 123"}],
                                "tools": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": "lookup_order",
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "order_id": {"type": "string"}
                                                },
                                                "required": ["order_id"],
                                            },
                                        },
                                    }
                                ],
                            }
                        }
                    },
                }
            },
        },
    },
)
def chat_completions(
    request: Request,
    authenticated: AuthenticatedAgentBody = Depends(authenticated_agent_body),
    db: Session = Depends(get_db),
) -> JSONResponse | StreamingResponse:
    """Run one stateless model round; the caller owns all tool execution."""

    started = time.perf_counter()
    created = int(time.time())
    turn_id = str(uuid.uuid4())
    principal = authenticated.principal
    body = parse_agent_completion_request(
        authenticated.payload,
        settings=authenticated.settings,
        body_bytes=authenticated.raw,
    )
    normalized = normalize_agent_messages(body, settings=authenticated.settings)
    expert_id = parse_expert_id(request)

    rate = ApiRateLimiter(db, settings=authenticated.settings).consume(
        workspace_id=principal.workspace_id,
        api_key_id=principal.api_key_id,
    )
    rate_headers = rate.as_headers()
    # The abuse limiter's entitlement read must not retain a transaction while
    # the paid admission coordinator waits on its independent fence session.
    try:
        db.rollback()
    except SQLAlchemyError as exc:
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Agent admission is temporarily unavailable.",
            retryable=True,
            headers=rate_headers,
        ) from exc

    admission = None
    prepared: PreparedAgentRound | None = None
    try:
        admission = admit_agent_completion(
            workspace_id=principal.workspace_id,
            api_key_id=principal.api_key_id,
            expert_id=expert_id,
            request_id=turn_id,
            settings=authenticated.settings,
        )
        service = AgentCompletionService(db, settings=authenticated.settings)
        prepared = service.prepare_round(
            request=body,
            normalized=normalized,
            admission=admission,
        )
        if body.stream:
            return _stream_response(
                service=service,
                prepared=prepared,
                turn_id=turn_id,
                created=created,
                rate_headers=rate_headers,
                started=started,
                principal=principal,
                expert_id=expert_id,
            )
        completed = service.run_round(prepared)
        payload = agent_completion_response(
            completed.result,
            geem=completed.geem,
            turn_id=turn_id,
            created=created,
            model=body.model,
        )
        _log_round(
            turn_id=turn_id,
            principal=principal,
            expert_id=expert_id,
            stream=False,
            status="ok",
            started=started,
        )
        return JSONResponse(
            content=payload.model_dump(mode="json"),
            headers=rate_headers,
        )
    except AppError as exc:
        if prepared is not None:
            AgentCompletionService.abort_round(prepared)
        elif admission is not None and not admission.closed:
            admission.release()
        exc.headers = {**rate_headers, **exc.headers}
        _log_round(
            turn_id=turn_id,
            principal=principal,
            expert_id=expert_id,
            stream=body.stream,
            status="error",
            started=started,
        )
        raise
    except Exception as exc:
        if prepared is not None:
            AgentCompletionService.abort_round(prepared)
        elif admission is not None and not admission.closed:
            admission.release()
        logger.exception("agent_completion_failed")
        _log_round(
            turn_id=turn_id,
            principal=principal,
            expert_id=expert_id,
            stream=body.stream,
            status="error",
            started=started,
        )
        raise AppError(
            ErrorCategory.GENERATION_FAILED,
            "Agent generation failed.",
            retryable=True,
            headers=rate_headers,
        ) from exc


@router.get(
    "/models",
    response_model=AgentModelListResponse,
    openapi_extra={"security": [{"ApiKey": []}]},
)
def list_models(
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_AGENT_WRITE)),
) -> AgentModelListResponse:
    settings = get_settings()
    require_agent_api_ready(settings)
    require_agent_models_access(principal.workspace_id)
    return agent_model_list_response()


@router.get(
    "/models/{model_id:path}",
    response_model=AgentModelObject,
    openapi_extra={"security": [{"ApiKey": []}]},
)
def get_model(
    model_id: str,
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_AGENT_WRITE)),
) -> AgentModelObject:
    settings = get_settings()
    require_agent_api_ready(settings)
    resolved = resolve_agent_model(model_id, param="model_id")
    require_agent_models_access(principal.workspace_id)
    return agent_model_object(resolved)


def _stream_response(
    *,
    service: AgentCompletionService,
    prepared: PreparedAgentRound,
    turn_id: str,
    created: int,
    rate_headers: dict[str, str],
    started: float,
    principal: ApiKeyPrincipal,
    expert_id: uuid.UUID,
) -> StreamingResponse:
    cancellation = OpenRouterStreamCancellation()
    events = service.stream_events(prepared, cancellation=cancellation)

    def generate() -> Iterator[str]:
        outcome = AgentStreamOutcome()
        status = "error"
        try:
            # Prime the provider from the ASGI response task, not from the sync
            # route worker.  That lets a downstream disconnect cancel a socket
            # blocked before its first provider event while the response class
            # still delays HTTP 200 until the first public SSE frame exists.
            try:
                first = next(events)
            except StopIteration as exc:
                outcome.fail(ErrorCategory.GENERATION_FAILED.value)
                raise AppError(
                    ErrorCategory.GENERATION_FAILED,
                    "Agent provider stream ended before it started.",
                    retryable=True,
                    headers=rate_headers,
                ) from exc
            except AppError as exc:
                outcome.fail(exc.category.value)
                exc.headers = {**rate_headers, **exc.headers}
                raise
            except Exception as exc:
                outcome.fail(ErrorCategory.GENERATION_FAILED.value)
                logger.exception("agent_stream_preflight_failed")
                raise AppError(
                    ErrorCategory.GENERATION_FAILED,
                    "Agent generation failed before streaming started.",
                    retryable=True,
                    headers=rate_headers,
                ) from exc

            yield from iter_agent_completion_sse(
                chain((first,), events),
                geem=lambda result: service.finalize_round(prepared, result),
                turn_id=turn_id,
                created=created,
                model=prepared.request.model,
                include_usage=bool(
                    prepared.request.stream_options
                    and prepared.request.stream_options.include_usage
                ),
                outcome=outcome,
            )
            status = outcome.status if outcome.status in {"ok", "error"} else "error"
        except GeneratorExit:
            status = "cancelled"
            raise
        except BaseException:
            status = "cancelled" if cancellation.cancelled else "error"
            if status == "error" and outcome.status == "pending":
                outcome.fail(ErrorCategory.GENERATION_FAILED.value)
            raise
        finally:
            service.abort_round(prepared)
            _log_round(
                turn_id=turn_id,
                principal=principal,
                expert_id=expert_id,
                stream=True,
                status=status,
                started=started,
                error_code=None if status == "cancelled" else outcome.error_code,
            )

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        **rate_headers,
    }
    return _AgentPreflightStreamingResponse(
        _iterate_with_explicit_close(generate(), cancel_upstream=cancellation.cancel),
        media_type="text/event-stream",
        headers=headers,
    )


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"Invalid JSON constant: {value}")


async def _read_bounded_body(request: Request, limit: int) -> bytes:
    """Read at most ``limit`` bytes, including for chunked/lying clients."""

    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            declared = int(raw_length)
        except ValueError:
            declared = -1
        if declared > limit:
            _raise_body_too_large()
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            _raise_body_too_large()
        body.extend(chunk)
    return bytes(body)


def _raise_body_too_large() -> None:
    raise AgentProtocolError(
        "Request body exceeds the Agent API limit.",
        code="agent_unsupported_parameter",
        param=None,
        status_code=413,
    )


class _AgentStreamComplete(Exception):
    pass


class _AgentPreflightStreamingResponse(StreamingResponse):
    """Delay response headers until one public frame is ready.

    Starlette normally sends ``http.response.start`` before requesting the first
    body item.  Agent streaming must instead preserve ordinary non-2xx mapping
    for provider failures before the first public frame.  This response also
    listens for ``http.disconnect`` on every ASGI spec version so cancellation
    remains prompt while that pre-header provider read is blocked.
    """

    async def stream_response(self, send: Send) -> None:
        iterator = self.body_iterator.__aiter__()
        try:
            try:
                first = await anext(iterator)
            except StopAsyncIteration as exc:
                raise AppError(
                    ErrorCategory.GENERATION_FAILED,
                    "Agent provider stream ended before it started.",
                    retryable=True,
                ) from exc

            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": self._encode_chunk(first),
                    "more_body": True,
                }
            )
            async for chunk in iterator:
                await send(
                    {
                        "type": "http.response.body",
                        "body": self._encode_chunk(chunk),
                        "more_body": True,
                    }
                )
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                with anyio.CancelScope(shield=True):
                    await close()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":  # pragma: no cover - HTTP-only route
            await super().__call__(scope, receive, send)
            return

        errors: list[BaseException] = []
        cancelled_error = anyio.get_cancelled_exc_class()
        async with anyio.create_task_group() as task_group:

            async def run_stream() -> None:
                try:
                    await self.stream_response(send)
                except cancelled_error:
                    raise
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    task_group.cancel_scope.cancel()

            task_group.start_soon(run_stream)
            try:
                await self.listen_for_disconnect(receive)
            finally:
                task_group.cancel_scope.cancel()

        if errors:
            error = errors[0]
            if isinstance(error, OSError):
                raise ClientDisconnect from error
            raise error
        if self.background is not None:
            await self.background()

    def _encode_chunk(self, chunk: str | bytes | memoryview) -> bytes | memoryview:
        if isinstance(chunk, bytes | memoryview):
            return chunk
        return chunk.encode(self.charset)


def _next_stream_item(iterator: Iterator[str], completed: threading.Event) -> str:
    try:
        return next(iterator)
    except StopIteration as exc:
        raise _AgentStreamComplete from exc
    finally:
        completed.set()


def _close_stream_iterator(iterator: Iterator[str]) -> None:
    close = getattr(iterator, "close", None)
    if close is not None:
        close()


async def _iterate_with_explicit_close(
    iterator: Iterator[str],
    *,
    cancel_upstream: Callable[[], None] | None = None,
) -> AsyncIterator[str]:
    """Cancel a blocked provider read, then serialize generator cleanup."""

    active_next: threading.Event | None = None
    completed_normally = False
    try:
        while True:
            active_next = threading.Event()
            try:
                item = await anyio.to_thread.run_sync(
                    _next_stream_item,
                    iterator,
                    active_next,
                    abandon_on_cancel=True,
                )
            except _AgentStreamComplete:
                completed_normally = True
                return
            yield item
    finally:
        with anyio.CancelScope(shield=True):
            if not completed_normally and cancel_upstream is not None:
                await anyio.to_thread.run_sync(
                    cancel_upstream,
                    abandon_on_cancel=True,
                )
            if active_next is not None and not active_next.is_set():
                with anyio.move_on_after(5, shield=True):
                    await anyio.to_thread.run_sync(
                        active_next.wait,
                        abandon_on_cancel=True,
                    )
            if active_next is None or active_next.is_set():
                await anyio.to_thread.run_sync(
                    _close_stream_iterator,
                    iterator,
                    abandon_on_cancel=True,
                )


def _log_round(
    *,
    turn_id: str,
    principal: ApiKeyPrincipal,
    expert_id: uuid.UUID,
    stream: bool,
    status: str,
    started: float,
    error_code: str | None = None,
) -> None:
    logger.info(
        "agent_request",
        extra={
            "request_id": turn_id,
            "workspace_id": str(principal.workspace_id),
            "api_key_id": str(principal.api_key_id),
            "expert_id": str(expert_id),
            "stream": stream,
            "status": status,
            "error_code": error_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )


__all__ = [
    "authenticated_agent_body",
    "chat_completions",
    "get_model",
    "list_models",
    "require_agent_api_ready",
    "router",
]
