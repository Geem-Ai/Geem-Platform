from __future__ import annotations

from uuid import uuid4

import pytest

from app.conversations.invocation import ChatInvocationContext
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
