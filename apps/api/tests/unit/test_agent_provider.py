from __future__ import annotations

import concurrent.futures
import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

import app.openrouter.client as openrouter_client_module
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.openrouter.chat import OpenRouterChatProvider, validate_agent_provider_response
from app.openrouter.client import OpenRouterClient, OpenRouterStreamCancellation


def _tool(name: str = "lookup") -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _text_body(content: str = "answer", *, model: str = "test/chat") -> dict:
    return {
        "id": "gen_1",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


class FakeClient:
    def __init__(
        self,
        *,
        responses: list[tuple[dict | None, dict, int]] | None = None,
        streams: list[list[dict | Exception]] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.streams = list(streams or [])
        self.request_payloads: list[dict] = []
        self.stream_payloads: list[dict] = []

    def provider_preferences(self) -> dict[str, Any]:
        return {"allow_fallbacks": False, "data_collection": "deny"}

    def request(self, *_args: Any, json_body: dict, **_kwargs: Any):
        self.request_payloads.append(json_body.copy())
        return self.responses.pop(0)

    def stream(self, *_args: Any, json_body: dict, **_kwargs: Any) -> Iterator[dict]:
        self.stream_payloads.append(json_body.copy())
        for item in self.streams.pop(0):
            if isinstance(item, Exception):
                raise item
            yield item


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openrouter_chat_model="test/chat",
        openrouter_chat_fallback_model="test/fallback",
    )


def test_complete_for_agent_payload_isolated_and_validated(settings: Settings) -> None:
    client = FakeClient(
        responses=[
            (
                {
                    "id": "gen_tool",
                    "model": "provider/model",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "lookup",
                                            "arguments": '{"id":"1"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 4,
                        "total_tokens": 13,
                    },
                },
                {"request_id": "request_1"},
                200,
            )
        ]
    )
    provider = OpenRouterChatProvider(client=client, settings=settings, system_prompt="legacy")
    result = provider.complete_for_agent(
        [{"role": "user", "content": "question"}],
        system_prompt="locked agent policy",
        tools=[_tool()],
        tool_choice="required",
        temperature=0,
        top_p=1,
        max_tokens=256,
        parallel_tool_calls=True,
    )
    payload = client.request_payloads[0]
    assert payload["messages"][0] == {
        "role": "system",
        "content": "locked agent policy",
    }
    assert sum(item["role"] == "system" for item in payload["messages"]) == 1
    assert payload["tools"] == [_tool()]
    assert payload["tool_choice"] == "required"
    assert payload["parallel_tool_calls"] is True
    assert payload["temperature"] == 0
    assert "response_format" not in payload
    assert "stream" not in payload
    assert result.finish_reason == "tool_calls"
    assert result.message.content is None
    assert result.message.tool_calls and result.message.tool_calls[0].id == "call_1"
    assert result.usage.total_tokens == 13
    assert result.provider_model == "provider/model"


def test_complete_falls_back_before_public_response(settings: Settings) -> None:
    client = FakeClient(
        responses=[
            ({"error": {}}, {"openrouter_id": "bad"}, 500),
            (_text_body(model="test/fallback"), {"request_id": "r2"}, 200),
        ]
    )
    result = OpenRouterChatProvider(client=client, settings=settings).complete_for_agent(
        [{"role": "user", "content": "q"}], system_prompt="policy"
    )
    assert [payload["model"] for payload in client.request_payloads] == [
        "test/chat",
        "test/fallback",
    ]
    assert result.message.content == "answer"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda body: body.update(choices=[]),
        lambda body: body["choices"][0].update(finish_reason="tool_calls"),
        lambda body: body["choices"][0]["message"].update(content=None),
        lambda body: body["choices"][0]["message"].update(tool_calls=[]),
    ],
)
def test_invalid_provider_text_output_never_escapes(mutation) -> None:
    body = _text_body()
    mutation(body)
    with pytest.raises(AppError) as raised:
        validate_agent_provider_response(
            body, declared_names=frozenset({"lookup"}), fallback_model="test/chat"
        )
    assert raised.value.category == ErrorCategory.GENERATION_FAILED


def test_invalid_provider_tool_metadata_is_rejected() -> None:
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "same",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        },
                        {
                            "id": "same",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    with pytest.raises(AppError):
        validate_agent_provider_response(body, declared_names=frozenset({"lookup"}))
    body["choices"][0]["message"]["tool_calls"] = [
        {
            "id": "call",
            "type": "function",
            "function": {"name": "undeclared", "arguments": "{}"},
        }
    ]
    with pytest.raises(AppError):
        validate_agent_provider_response(body, declared_names=frozenset({"lookup"}))


def test_provider_usage_is_required_and_must_balance() -> None:
    missing = _text_body()
    missing.pop("usage")
    with pytest.raises(AppError):
        validate_agent_provider_response(missing, declared_names=frozenset())
    inconsistent = _text_body()
    inconsistent["usage"]["total_tokens"] = 99
    with pytest.raises(AppError):
        validate_agent_provider_response(inconsistent, declared_names=frozenset())


def test_stream_maps_fragmented_parallel_calls_and_raw_usage(settings: Settings) -> None:
    client = FakeClient(
        streams=[
            [
                {
                    "id": "gen_stream",
                    "model": "provider/model",
                    "_request_id": "request_1",
                    "choices": [{"delta": {"role": "assistant"}, "finish_reason": None}],
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_a",
                                        "type": "function",
                                        "function": {"name": "a", "arguments": "{"},
                                    },
                                    {
                                        "index": 1,
                                        "id": "call_b",
                                        "type": "function",
                                        "function": {"name": "b", "arguments": "{"},
                                    },
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 1, "function": {"arguments": '"b":2}'}},
                                    {"index": 0, "function": {"arguments": '"a":1}'}},
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 7,
                        "total_tokens": 27,
                    },
                },
            ]
        ]
    )
    events = list(
        OpenRouterChatProvider(client=client, settings=settings).stream_for_agent(
            [{"role": "user", "content": "q"}],
            system_prompt="policy",
            tools=[_tool("a"), _tool("b")],
            tool_choice="auto",
        )
    )
    assert [event.type for event in events] == [
        "start",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_delta",
        "done",
    ]
    result = events[-1].result
    assert result and result.message.tool_calls
    assert [call.id for call in result.message.tool_calls] == ["call_a", "call_b"]
    assert result.message.tool_calls[0].function.arguments == '{"a":1}'
    assert result.message.tool_calls[1].function.arguments == '{"b":2}'
    assert result.usage.total_tokens == 27
    payload = client.stream_payloads[0]
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}


def test_stream_fallback_only_before_first_event(settings: Settings) -> None:
    before = FakeClient(
        streams=[
            [AppError(ErrorCategory.GENERATION_FAILED, "primary failed")],
            [
                {"choices": [{"delta": {"content": "ok"}, "finish_reason": None}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            ],
        ]
    )
    events = list(
        OpenRouterChatProvider(client=before, settings=settings).stream_for_agent(
            [{"role": "user", "content": "q"}], system_prompt="policy"
        )
    )
    assert len(before.stream_payloads) == 2
    assert events[-1].result and events[-1].result.message.content == "ok"

    after = FakeClient(
        streams=[
            [
                {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]},
                AppError(ErrorCategory.GENERATION_FAILED, "mid-stream"),
            ],
            [
                {"choices": [{"delta": {"content": "must not run"}, "finish_reason": None}]}
            ],
        ]
    )
    with pytest.raises(AppError):
        list(
            OpenRouterChatProvider(client=after, settings=settings).stream_for_agent(
                [{"role": "user", "content": "q"}], system_prompt="policy"
            )
        )
    assert len(after.stream_payloads) == 1


def test_stream_transport_failure_before_first_event_is_wrapped_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    payload_models: list[str] = []

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        @staticmethod
        def iter_lines():
            yield 'data: {"choices":[{"delta":{"content":"fallback"},"finish_reason":null}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
            yield (
                'data: {"choices":[],"usage":{"prompt_tokens":2,'
                '"completion_tokens":1,"total_tokens":3}}'
            )
            yield "data: [DONE]"

    class HttpClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def stream(self, _method, url, **kwargs):
            payload_models.append(kwargs["json"]["model"])
            if len(payload_models) == 1:
                raise httpx.ReadTimeout(
                    "primary timed out",
                    request=httpx.Request("POST", url),
                )
            return Response()

    monkeypatch.setattr(openrouter_client_module.httpx, "Client", HttpClient)
    transport = OpenRouterClient(
        settings.model_copy(update={"openrouter_api_key": "test-agent-key"})
    )
    events = list(
        OpenRouterChatProvider(client=transport, settings=settings).stream_for_agent(
            [{"role": "user", "content": "q"}],
            system_prompt="policy",
        )
    )

    assert payload_models == ["test/chat", "test/fallback"]
    assert events[-1].result is not None
    assert events[-1].result.message.content == "fallback"
    assert events[-1].result.usage.total_tokens == 3


@pytest.mark.parametrize(
    "data",
    [
        '{"choices":[{"delta":{"content":"truncated"}}]',
        "[]",
    ],
)
def test_stream_rejects_malformed_provider_data_instead_of_dropping_it(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    data: str,
) -> None:
    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        @staticmethod
        def iter_lines():
            yield f"data: {data}"

    class HttpClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def stream(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(openrouter_client_module.httpx, "Client", HttpClient)
    transport = OpenRouterClient(
        settings.model_copy(update={"openrouter_api_key": "test-agent-key"})
    )

    with pytest.raises(AppError) as raised:
        list(
            transport.stream(
                "POST",
                "/chat/completions",
                json_body={"model": "test/chat"},
            )
        )

    assert raised.value.category == ErrorCategory.GENERATION_FAILED
    assert raised.value.retryable is True
    assert isinstance(raised.value.details.get("request_id"), str)


def test_stream_cancellation_closes_a_blocked_httpx_response(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    read_started = threading.Event()
    release_read = threading.Event()

    class Response:
        status_code = 200

        def __init__(self) -> None:
            self.close_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def close(self) -> None:
            self.close_calls += 1
            release_read.set()

        @staticmethod
        def iter_lines():
            yield 'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}'
            read_started.set()
            release_read.wait()
            raise httpx.ReadError(
                "stream closed",
                request=httpx.Request("POST", "https://openrouter.test"),
            )

    response = Response()

    class HttpClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def stream(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(openrouter_client_module.httpx, "Client", HttpClient)
    transport = OpenRouterClient(
        settings.model_copy(update={"openrouter_api_key": "test-agent-key"})
    )
    cancellation = OpenRouterStreamCancellation()
    chunks = transport.stream(
        "POST",
        "/chat/completions",
        json_body={"model": "test/chat"},
        cancellation=cancellation,
    )
    assert next(chunks)["choices"][0]["delta"] == {"role": "assistant"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        blocked = executor.submit(next, chunks)
        assert read_started.wait(timeout=1)
        cancellation.cancel()
        with pytest.raises(AppError) as raised:
            blocked.result(timeout=1)

    assert raised.value.category == ErrorCategory.GENERATION_FAILED
    assert response.close_calls == 1
