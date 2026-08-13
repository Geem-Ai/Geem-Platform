"""Unit tests for OpenAI Chat Completions adapters."""

from __future__ import annotations

from app.api.v1.openai_compat import (
    is_openai_compat_path,
    iter_completion_sse,
    messages_to_question,
)
from app.api.v1.schemas import ChatCompletionMessage
from app.core.errors import AppError, ErrorCategory


def test_is_openai_compat_path() -> None:
    assert is_openai_compat_path("/api/v1/chat/completions")
    assert is_openai_compat_path("/api/v1/models")
    assert is_openai_compat_path("/api/v1/models/abc")
    assert not is_openai_compat_path("/api/v1/chat")
    assert not is_openai_compat_path("/api/conversations")
    assert not is_openai_compat_path("/api/api-keys")


def test_messages_ignore_system_and_require_user() -> None:
    try:
        messages_to_question(
            [ChatCompletionMessage(role="system", content="You are a bot.")]
        )
        raise AssertionError("expected AppError")
    except AppError as exc:
        assert exc.category == ErrorCategory.VALIDATION
        assert exc.details and exc.details.get("param") == "messages"


def test_messages_extract_text_parts_and_ignore_non_text() -> None:
    question = messages_to_question(
        [
            ChatCompletionMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Hello"},
                    {"type": "image_url", "image_url": {"url": "https://evil.example/x.png"}},
                ],
            )
        ]
    )
    assert question == "Hello"
    try:
        messages_to_question(
            [ChatCompletionMessage(role="user", content={"secret": "nope"})]
        )
        raise AssertionError("expected AppError")
    except AppError as exc:
        assert exc.category == ErrorCategory.VALIDATION


def test_messages_fold_prior_turns() -> None:
    question = messages_to_question(
        [
            ChatCompletionMessage(role="system", content="ignored"),
            ChatCompletionMessage(role="user", content="First"),
            ChatCompletionMessage(role="assistant", content="Ack"),
            ChatCompletionMessage(role="user", content="Second"),
        ]
    )
    assert question.endswith("Second")
    assert "User: First" in question
    assert "Assistant: Ack" in question
    assert "ignored" not in question


def test_sse_skips_empty_replace_and_does_not_rewind() -> None:
    events = [
        {"event": "message_start", "data": {"request_id": "t"}},
        {"event": "delta", "data": {"content": "Hi"}},
        {"event": "replace", "data": {"content": ""}},
        {"event": "replace", "data": {"content": "Final answer"}},
        {
            "event": "message_complete",
            "data": {"answer": "Final answer", "citations": [], "usage": {"billed_tokens": 3}},
        },
    ]
    raw = "".join(iter_completion_sse(iter(events), turn_id="t", model="geem", created=1))
    assert "event:" not in raw
    assert "data: [DONE]" in raw
    contents = []
    for block in raw.split("\n\n"):
        if not block.startswith("data:"):
            continue
        payload = block[5:].strip()
        if payload == "[DONE]":
            continue
        import json

        chunk = json.loads(payload)
        text = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
        if text:
            contents.append(text)
        finish = (chunk.get("choices") or [{}])[0].get("finish_reason")
        if finish == "stop":
            contents.append("<stop>")
    assert contents == ["Hi", "<stop>"]


def test_sse_replace_before_tokens_emits_full_text() -> None:
    events = [
        {"event": "replace", "data": {"content": ""}},
        {"event": "replace", "data": {"content": "Final answer"}},
        {
            "event": "message_complete",
            "data": {"answer": "Final answer", "citations": [], "usage": {"billed_tokens": 1}},
        },
    ]
    raw = "".join(iter_completion_sse(iter(events), turn_id="t", model="geem", created=1))
    import json

    texts = []
    for block in raw.split("\n\n"):
        if not block.startswith("data:"):
            continue
        payload = block[5:].strip()
        if payload == "[DONE]":
            continue
        chunk = json.loads(payload)
        text = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
        if text:
            texts.append(text)
    assert texts == ["Final answer"]
