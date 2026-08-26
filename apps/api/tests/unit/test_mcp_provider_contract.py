from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.openrouter.chat import OpenRouterChatProvider


class _RecordingClient:
    def __init__(self) -> None:
        self.options: dict[str, Any] = {}
        self.payload: dict[str, Any] = {}

    @staticmethod
    def provider_preferences() -> dict[str, Any]:
        return {"allow_fallbacks": False, "data_collection": "deny"}

    def request(self, *_args: Any, json_body: dict[str, Any], **kwargs: Any):
        self.payload = dict(json_body)
        self.options = dict(kwargs)
        return (
            {
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
            },
            {"request_id": "request_1"},
            200,
        )


def test_mcp_provider_round_disables_retries_and_obeys_remaining_deadline() -> None:
    client = _RecordingClient()
    provider = OpenRouterChatProvider(
        client=client,  # type: ignore[arg-type]
        settings=Settings(
            _env_file=None,
            openrouter_chat_model="test/tool-model",
            openrouter_chat_fallback_model="test/fallback",
        ),
    )
    result = provider.answer_with_tools(
        [{"role": "user", "content": "question"}],
        model="test/tool-model",
        system_prompt="locked policy",
        tools=[],
        timeout_seconds=3.25,
    )

    assert result.message.content == "done"
    assert client.options["max_attempts"] == 1
    assert client.options["timeout"] == 3.25
    assert client.payload["parallel_tool_calls"] is False
    assert client.payload["model"] == "test/tool-model"
