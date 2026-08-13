"""OpenAI Chat Completions wire adapters for the public Workspace API.

Expert identity is a header, not ``model``. Generation stays on
``ChatTurnExecutor``; this module only maps messages, SSE, and errors.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import Citation
from app.api.v1.schemas import (
    ChatCompletionChoice,
    ChatCompletionChoiceMessage,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ModelObject,
)
from app.core.errors import HTTP_STATUS_BY_CATEGORY, AppError, ErrorCategory
from app.experts.models import Expert

EXPERT_HEADER = "X-Geem-Expert-Id"
EXPERT_HEADER_ALIAS = "X-Expert-Id"

_OPENAI_PREFIXES = ("/api/v1/chat/completions", "/api/v1/models")

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
        ErrorCategory.EXPERT_DISABLED,
        ErrorCategory.EXPERT_ACCESS_DENIED,
        ErrorCategory.WORKSPACE_ACCESS_DENIED,
        ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
        ErrorCategory.PLATFORM_ADMIN_REQUIRED,
    }
)
_RATE_CATEGORIES = frozenset(
    {
        ErrorCategory.RATE_LIMIT_EXCEEDED,
        ErrorCategory.QUOTA_EXCEEDED,
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.EXPERT_LIMIT_REACHED,
        ErrorCategory.STORAGE_QUOTA_EXCEEDED,
    }
)


def is_openai_compat_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in _OPENAI_PREFIXES
    )


def parse_expert_id(request: Request) -> uuid.UUID:
    raw = request.headers.get(EXPERT_HEADER)
    if raw is None or not str(raw).strip():
        alias = request.headers.get(EXPERT_HEADER_ALIAS)
        raw = alias
    value = str(raw or "").strip()
    if not value:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Missing X-Geem-Expert-Id header.",
            details={"param": EXPERT_HEADER},
        )
    try:
        return uuid.UUID(value)
    except ValueError:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Invalid X-Geem-Expert-Id header.",
            details={"param": EXPERT_HEADER},
        ) from None


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return ""


def messages_to_question(messages: Sequence[ChatCompletionMessage]) -> str:
    """Fold OpenAI messages into one Expert question.

    Client ``system`` messages are ignored (Expert instructions stay
    server-owned). Prior user/assistant turns become a compact transcript
    prefix; the last user content is the question.
    """
    turns: list[tuple[str, str]] = []
    for message in messages:
        role = (message.role or "").strip().lower()
        if role in {"system", "developer", "tool", "function"}:
            continue
        if role not in {"user", "assistant"}:
            continue
        text = _message_text(message.content).strip()
        if not text:
            continue
        turns.append((role, text))

    user_indices = [index for index, (role, _) in enumerate(turns) if role == "user"]
    if not user_indices:
        raise AppError(
            ErrorCategory.VALIDATION,
            "At least one user message is required.",
            details={"param": "messages"},
        )

    last_user = user_indices[-1]
    question = turns[last_user][1]
    prior = turns[:last_user]
    if not prior:
        return question

    lines = [
        f"{'User' if role == 'user' else 'Assistant'}: {text}" for role, text in prior
    ]
    return "\n".join(lines) + "\n\n" + question


def completion_id(turn_id: str) -> str:
    return f"chatcmpl-{turn_id}"


def completion_response(
    *,
    turn_id: str,
    model: str,
    created: int,
    answer: str,
    citations: list[Any],
    billed_tokens: int,
) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id=completion_id(turn_id),
        created=created,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionChoiceMessage(role="assistant", content=answer),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=int(billed_tokens),
        ),
        citations=[Citation.model_validate(item) for item in citations],
    )


def model_object(expert: Expert, ownership: str) -> ModelObject:
    created = 0
    if expert.created_at is not None:
        created = int(expert.created_at.timestamp())
    owned_by = "platform" if ownership == "platform" else "workspace"
    return ModelObject(
        id=str(expert.id),
        created=created,
        owned_by=owned_by,
    )


def openai_error_type(category: ErrorCategory, status: int) -> str:
    if category in _AUTH_CATEGORIES:
        return "authentication_error"
    if category in _PERMISSION_CATEGORIES or status == 403:
        return "permission_error"
    if category == ErrorCategory.INSUFFICIENT_CREDITS:
        return "insufficient_quota"
    if category in _RATE_CATEGORIES:
        return "rate_limit_error"
    if status >= 500:
        return "api_error"
    return "invalid_request_error"


def openai_http_status(category: ErrorCategory) -> int:
    status = HTTP_STATUS_BY_CATEGORY.get(category.value, 500)
    if status == 500 and (category.value.endswith("_failed") or "rate" in category.value):
        status = 502
    if status == 422:
        return 400
    return status


def openai_error_body(
    *,
    message: str,
    category: ErrorCategory,
    status: int,
    param: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": openai_error_type(category, status),
            "param": param,
            "code": category.value,
        }
    }


def openai_error_response(exc: AppError) -> JSONResponse:
    status = openai_http_status(exc.category)
    param = None
    if isinstance(exc.details, dict):
        raw_param = exc.details.get("param")
        if isinstance(raw_param, str) and raw_param:
            param = raw_param
    return JSONResponse(
        status_code=status,
        content=openai_error_body(
            message=exc.message,
            category=exc.category,
            status=status,
            param=param,
        ),
        headers=exc.headers or None,
    )


def openai_validation_response(exc: RequestValidationError) -> JSONResponse:
    param: str | None = None
    message = "Invalid request."
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = [str(part) for part in first.get("loc", ()) if part not in {"body", "query", "path"}]
        if loc:
            param = loc[-1] if loc[-1] != "header" else (loc[0] if loc else None)
            if len(loc) >= 2 and loc[0] in {"header", "headers"}:
                param = loc[-1]
        msg = first.get("msg")
        if isinstance(msg, str) and msg:
            message = msg
    return JSONResponse(
        status_code=400,
        content=openai_error_body(
            message=message,
            category=ErrorCategory.VALIDATION,
            status=400,
            param=param,
        ),
    )


def _sse_data(payload: Any) -> str:
    if payload == "[DONE]":
        return "data: [DONE]\n\n"
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _chunk(
    *,
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    extra: dict[str, Any] | None = None,
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
    if extra:
        payload.update(extra)
    return payload


def iter_completion_sse(
    events: Iterator[dict[str, Any]],
    *,
    turn_id: str,
    model: str,
    created: int,
) -> Iterator[str]:
    """Map Geem executor events onto OpenAI concatenative SSE chunks."""
    cid = completion_id(turn_id)
    sent_tokens = False
    emitted_role = False

    def role_delta(content: str | None = None) -> dict[str, Any]:
        delta: dict[str, Any] = {"role": "assistant"}
        if content is not None:
            delta["content"] = content
        return delta

    for item in events:
        event = item.get("event")
        data = item.get("data") or {}
        if event == "message_start":
            continue
        if event == "delta":
            text = data.get("content") or ""
            if not text:
                continue
            delta = role_delta(text) if not emitted_role else {"content": text}
            emitted_role = True
            sent_tokens = True
            yield _sse_data(
                _chunk(completion_id=cid, created=created, model=model, delta=delta)
            )
        elif event == "replace":
            text = data.get("content") or ""
            if not text:
                continue
            if sent_tokens:
                # OpenAI clients concatenate deltas and cannot rewind.
                continue
            emitted_role = True
            sent_tokens = True
            yield _sse_data(
                _chunk(
                    completion_id=cid,
                    created=created,
                    model=model,
                    delta=role_delta(text),
                )
            )
        elif event == "message_complete":
            if not emitted_role:
                yield _sse_data(
                    _chunk(
                        completion_id=cid,
                        created=created,
                        model=model,
                        delta=role_delta(),
                    )
                )
                emitted_role = True
            extra: dict[str, Any] = {}
            citations = data.get("citations") or []
            if citations:
                extra["citations"] = citations
            usage = data.get("usage") or {}
            billed = int(usage.get("billed_tokens") or 0)
            extra["usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": billed,
            }
            yield _sse_data(
                _chunk(
                    completion_id=cid,
                    created=created,
                    model=model,
                    delta={},
                    finish_reason="stop",
                    extra=extra,
                )
            )
            yield _sse_data("[DONE]")
            return
        elif event == "error":
            code = data.get("code") or ErrorCategory.GENERATION_FAILED.value
            try:
                category = ErrorCategory(code)
            except ValueError:
                category = ErrorCategory.GENERATION_FAILED
            status = openai_http_status(category)
            yield _sse_data(
                openai_error_body(
                    message=data.get("message") or "Generation failed.",
                    category=category,
                    status=status,
                )
            )
            yield _sse_data("[DONE]")
            return

    if not emitted_role:
        yield _sse_data(
            _chunk(
                completion_id=cid,
                created=created,
                model=model,
                delta=role_delta(),
            )
        )
    yield _sse_data(
        _chunk(
            completion_id=cid,
            created=created,
            model=model,
            delta={},
            finish_reason="stop",
        )
    )
    yield _sse_data("[DONE]")


def iter_sse_error(exc: AppError | Exception) -> Iterator[str]:
    if isinstance(exc, AppError):
        category = exc.category
        message = exc.message
    else:
        category = ErrorCategory.GENERATION_FAILED
        message = "Generation failed."
    yield _sse_data(
        openai_error_body(
            message=message,
            category=category,
            status=openai_http_status(category),
        )
    )
    yield _sse_data("[DONE]")
