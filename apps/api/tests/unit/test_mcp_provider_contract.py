from __future__ import annotations

import copy
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.openrouter.chat import OpenRouterChatProvider


class _RecordingClient:
    def __init__(
        self,
        *,
        body: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.options: dict[str, Any] = {}
        self.payload: dict[str, Any] = {}
        self.body = body or _text_response()
        self.meta = meta or {"request_id": "request_1"}

    @staticmethod
    def provider_preferences() -> dict[str, Any]:
        return {"allow_fallbacks": False, "data_collection": "deny"}

    def request(self, *_args: Any, json_body: dict[str, Any], **kwargs: Any):
        self.payload = dict(json_body)
        self.options = dict(kwargs)
        return copy.deepcopy(self.body), dict(self.meta), 200


def _text_response() -> dict[str, Any]:
    return {
        "id": "mcp_round_1",
        "model": "test/tool-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "done"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 1,
            "total_tokens": 6,
        },
    }


def _provider(client: _RecordingClient) -> OpenRouterChatProvider:
    return OpenRouterChatProvider(
        client=client,  # type: ignore[arg-type]
        settings=Settings(
            _env_file=None,
            openrouter_chat_model="test/tool-model",
            openrouter_chat_fallback_model="test/fallback",
        ),
    )


def test_mcp_provider_round_disables_retries_and_obeys_remaining_deadline() -> None:
    client = _RecordingClient()
    provider = _provider(client)
    result = provider.answer_with_tools(
        [{"role": "user", "content": "question"}],
        model="test/tool-model",
        system_prompt="locked policy",
        tools=[],
        json_response=True,
        timeout_seconds=3.25,
    )

    assert result.message.content == "done"
    assert client.options["max_attempts"] == 1
    assert client.options["timeout"] == 3.25
    assert client.payload["parallel_tool_calls"] is False
    assert client.payload["model"] == "test/tool-model"
    assert client.payload["response_format"] == {"type": "json_object"}


def test_mcp_no_tool_round_explicitly_disables_tools() -> None:
    body = _text_response()
    valid_content = (
        '{"answer_markdown":"done","citation_chunk_ids":[],'
        '"insufficient_context":false}'
    )
    body["choices"][0]["message"]["content"] = valid_content
    client = _RecordingClient(body=body)
    result = _provider(client).answer_without_tools(
        [{"role": "user", "content": "question"}],
        model="test/tool-model",
        system_prompt="locked policy",
        fallback_content=(
            '{"answer_markdown":"Safe deterministic fallback.",'
            '"citation_chunk_ids":[],"insufficient_context":true}'
        ),
        json_response=True,
        max_tokens=128,
        timeout_seconds=2.75,
    )

    assert result.message.content == valid_content
    assert client.options["max_attempts"] == 1
    assert client.options["timeout"] == 2.75
    assert client.payload["tool_choice"] == "none"
    assert "tools" not in client.payload
    assert "parallel_tool_calls" not in client.payload
    assert client.payload["max_tokens"] == 128
    assert client.payload["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "provider_content",
    [
        "",
        "plain prose",
        "{}",
        '{"answer_markdown":"answer","citation_chunk_ids":"bad"}',
        '{"answer_markdown":"answer","insufficient_context":"false"}',
    ],
)
def test_mcp_no_tool_round_replaces_invalid_json_content(
    provider_content: str,
) -> None:
    body = _text_response()
    body["choices"][0]["message"]["content"] = provider_content
    fallback = (
        '{"answer_markdown":"Safe deterministic fallback.",'
        '"citation_chunk_ids":[],"insufficient_context":true}'
    )

    result = _provider(_RecordingClient(body=body)).answer_without_tools(
        [{"role": "user", "content": "question"}],
        model="test/tool-model",
        system_prompt="locked policy",
        fallback_content=fallback,
        json_response=True,
    )

    assert result.message.content == fallback
    assert result.usage.total_tokens == 6


def test_mcp_no_tool_round_replaces_blank_general_content() -> None:
    body = _text_response()
    body["choices"][0]["message"]["content"] = "   "

    result = _provider(_RecordingClient(body=body)).answer_without_tools(
        [{"role": "user", "content": "question"}],
        model="test/tool-model",
        system_prompt="locked policy",
        fallback_content="Safe deterministic fallback.",
    )

    assert result.message.content == "Safe deterministic fallback."
    assert result.usage.total_tokens == 6


@pytest.mark.parametrize(
    ("message", "finish_reason"),
    [
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "undeclared",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            "tool_calls",
        ),
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": {"malformed": True},
            },
            "tool_calls",
        ),
        (
            {
                "role": "assistant",
                "content": None,
                "function_call": {"name": "legacy", "arguments": "{}"},
            },
            "stop",
        ),
        ({"role": "assistant", "content": "partial"}, "length"),
        ({"role": "assistant", "content": None}, "stop"),
    ],
)
def test_mcp_no_tool_round_absorbs_invalid_output_with_usage(
    message: dict[str, Any],
    finish_reason: str,
) -> None:
    body = _text_response()
    body["choices"][0]["message"] = message
    body["choices"][0]["finish_reason"] = finish_reason
    client = _RecordingClient(
        body=body,
        meta={"request_id": "request-finalizer"},
    )

    result = _provider(client).answer_without_tools(
        [{"role": "user", "content": "question"}],
        model="test/tool-model",
        system_prompt="locked policy",
        fallback_content="Safe deterministic fallback.",
    )

    assert result.message.content == "Safe deterministic fallback."
    assert result.message.tool_calls is None
    assert result.finish_reason == "stop"
    assert result.usage.model_dump(mode="json") == {
        "prompt_tokens": 5,
        "completion_tokens": 1,
        "total_tokens": 6,
    }
    assert result.provider_model == "test/tool-model"
    assert result.provider_request_id == "request-finalizer"
    assert result.provider_completion_id == "mcp_round_1"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 99},
    ],
)
def test_mcp_no_tool_round_rejects_invalid_usage(usage: dict[str, int] | None) -> None:
    body = _text_response()
    body["choices"][0] = {
        "index": 0,
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": {"malformed": True},
        },
        "finish_reason": "tool_calls",
    }
    if usage is None:
        body.pop("usage")
    else:
        body["usage"] = usage

    with pytest.raises(AppError):
        _provider(_RecordingClient(body=body)).answer_without_tools(
            [{"role": "user", "content": "question"}],
            model="test/tool-model",
            system_prompt="locked policy",
            fallback_content="Safe deterministic fallback.",
        )
