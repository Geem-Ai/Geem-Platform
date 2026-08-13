from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.conversations.invocation import ChatInvocationContext
from app.conversations.turn import ChatTurnExecutor
from app.conversations.validation import validate_chat_message
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def test_workspace_invocation_forbids_api_key() -> None:
    ctx = ChatInvocationContext.workspace_user(
        workspace_id=uuid4(),
        user_id=uuid4(),
        expert_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        request_id="asst-1",
    )
    usage = ctx.to_usage_context()
    assert usage.user_id == ctx.user_id
    assert usage.api_key_id is None
    assert usage.conversation_id is not None


def test_api_invocation_forbids_user() -> None:
    ctx = ChatInvocationContext.api_key(
        workspace_id=uuid4(),
        api_key_id=uuid4(),
        expert_id=uuid4(),
        request_id="req-1",
    )
    usage = ctx.to_usage_context()
    assert usage.api_key_id == ctx.api_key_id
    assert usage.user_id is None
    assert usage.conversation_id is None
    assert usage.message_id is None


def test_invocation_rejects_ambiguous_actors() -> None:
    with pytest.raises(ValueError):
        ChatInvocationContext(
            workspace_id=uuid4(),
            source="api",
            user_id=uuid4(),
            api_key_id=uuid4(),
        )
    with pytest.raises(ValueError):
        ChatInvocationContext(
            workspace_id=uuid4(),
            source="workspace",
            user_id=uuid4(),
            api_key_id=uuid4(),
        )


def test_validate_chat_message_reuses_workspace_limit() -> None:
    settings = Settings(_env_file=None, max_chat_message_chars=8)
    assert validate_chat_message("  hello  ", settings=settings) == "hello"
    with pytest.raises(AppError) as exc:
        validate_chat_message("   ", settings=settings)
    assert exc.value.category == ErrorCategory.VALIDATION
    with pytest.raises(AppError) as exc:
        validate_chat_message("123456789", settings=settings)
    assert exc.value.category == ErrorCategory.VALIDATION


def test_stream_forwards_replace_instead_of_concatenative_delta() -> None:
    def fake_stream(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        yield {"event": "token", "data": {"text": "Hi"}}
        yield {"event": "replace", "data": {"text": ""}}
        yield {"event": "replace", "data": {"text": "Full answer"}}
        yield {
            "event": "final",
            "data": {
                "answer": "Full answer",
                "citations": [],
                "billed_chat_tokens": 2,
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "source": "provider",
                },
            },
        }

    expert_query = MagicMock()
    expert_query.query_stream_for_workspace.side_effect = fake_stream
    meter = MagicMock()
    meter.closed = False
    meter.context.return_value = MagicMock(extra_billed_tokens=0)
    invocation = ChatInvocationContext.api_key(
        workspace_id=uuid4(),
        api_key_id=uuid4(),
        expert_id=uuid4(),
        request_id="turn-1",
    )
    executor = ChatTurnExecutor(
        db=MagicMock(),
        settings=Settings(_env_file=None),
        expert_query=expert_query,
    )
    events = list(
        executor.stream(
            workspace=MagicMock(),
            expert_id=invocation.expert_id,
            question="q",
            invocation=invocation,
            meter=meter,
            request_id="turn-1",
        )
    )
    names = [item["event"] for item in events]
    assert names == ["message_start", "delta", "replace", "replace", "message_complete"]
    assert events[1]["data"]["content"] == "Hi"
    assert events[2]["data"]["content"] == ""
    assert events[3]["data"]["content"] == "Full answer"
    assert events[4]["data"]["answer"] == "Full answer"
    meter.settle.assert_called_once()
