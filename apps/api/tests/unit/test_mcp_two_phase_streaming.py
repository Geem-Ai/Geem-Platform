from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace

import pytest

from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentFunctionCall,
    AgentProviderResult,
    AgentToolCall,
    AgentUsage,
)
from app.api.v1.openai_compat import iter_completion_sse
from app.conversations import turn as turn_module
from app.conversations.invocation import ChatInvocationContext
from app.conversations.turn import ChatTurnExecutor
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.executor import (
    ToolLoopResult,
    ToolLoopStreamEvent,
    ToolLoopTurnExecutor,
    _PreparedTurn,
)
from app.mcp.result import NormalizedToolResult


def _settings():
    return get_settings().model_copy(
        update={
            "openrouter_chat_model": "test/tool-model",
            "openrouter_chat_fallback_model": "",
            "mcp_tool_provider_capability_matrix": json.dumps(
                {
                    "test/tool-model": [
                        "function_calling",
                        "parallel_tool_calls_false",
                    ]
                }
            ),
        }
    )


class _TwoRoundProvider:
    def __init__(self, *, delay: float = 0.0, final_content: str = "Final answer") -> None:
        self.delay = delay
        self.final_content = final_content
        self.messages: list[list[dict]] = []
        self.json_responses: list[bool] = []
        self.tool_sets: list[list[dict]] = []

    def answer_with_tools(self, messages, **_kwargs) -> AgentProviderResult:
        self.messages.append(list(messages))
        self.json_responses.append(bool(_kwargs.get("json_response")))
        self.tool_sets.append(list(_kwargs.get("tools") or []))
        if self.delay:
            time.sleep(self.delay)
        if len(self.messages) == 1:
            return AgentProviderResult(
                message=AgentAssistantResponseMessage(
                    content=None,
                    tool_calls=[
                        AgentToolCall(
                            id="call-1",
                            type="function",
                            function=AgentFunctionCall(
                                name="mcp_read",
                                arguments='{"customer_id":7}',
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
                usage=AgentUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
                provider_model="test/tool-model",
            )
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(
                content=self.final_content,
                tool_calls=None,
            ),
            finish_reason="stop",
            usage=AgentUsage(prompt_tokens=3, completion_tokens=1, total_tokens=4),
            provider_model="test/tool-model",
        )


class _ScriptedToolProvider:
    def __init__(self, arguments: list[str], *, final_content: str) -> None:
        self.arguments = arguments
        self.final_content = final_content
        self.messages: list[list[dict]] = []
        self.tool_sets: list[list[dict]] = []

    def answer_with_tools(self, messages, **_kwargs) -> AgentProviderResult:
        self.messages.append(list(messages))
        tool_set = list(_kwargs.get("tools") or [])
        self.tool_sets.append(tool_set)
        round_index = len(self.messages) - 1
        if tool_set and round_index < len(self.arguments):
            return AgentProviderResult(
                message=AgentAssistantResponseMessage(
                    content=None,
                    tool_calls=[
                        AgentToolCall(
                            id=f"call-{round_index + 1}",
                            type="function",
                            function=AgentFunctionCall(
                                name="mcp_read",
                                arguments=self.arguments[round_index],
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
                usage=AgentUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
                provider_model="test/tool-model",
            )
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(
                content=self.final_content,
                tool_calls=None,
            ),
            finish_reason="stop",
            usage=AgentUsage(prompt_tokens=3, completion_tokens=1, total_tokens=4),
            provider_model="test/tool-model",
        )


def _normalized_json_result(value) -> NormalizedToolResult:
    encoded = json.dumps(value, separators=(",", ":"))
    return NormalizedToolResult(
        model_content=(
            "<untrusted_mcp_tool_result>\n"
            + json.dumps(
                {
                    "content_kind": "text",
                    "is_error": False,
                    "truncated": False,
                    "value": encoded,
                },
                separators=(",", ":"),
            )
            + "\n</untrusted_mcp_tool_result>"
        ),
        is_error=False,
        transport_bytes=len(encoded.encode("utf-8")),
        content_types=("text",),
        unsupported_blocks=(),
    )


class _RecordingDispatcher:
    def __init__(self, *, delay: float = 0.0, is_error: bool = False) -> None:
        self.delay = delay
        self.calls = 0
        self.arguments: list[dict] = []
        self.normalized = NormalizedToolResult(
            model_content=(
                "<untrusted_mcp_tool_result>repository not found"
                "</untrusted_mcp_tool_result>"
                if is_error
                else "<untrusted_mcp_tool_result>safe</untrusted_mcp_tool_result>"
            ),
            is_error=is_error,
            transport_bytes=12,
            content_types=("text",),
            unsupported_blocks=(),
        )
        self.normalized_results: list[NormalizedToolResult] | None = None

    def dispatch(self, **_kwargs):
        call_index = self.calls
        self.calls += 1
        self.arguments.append(dict(_kwargs["arguments"]))
        if self.delay:
            time.sleep(self.delay)
        normalized = (
            self.normalized_results[call_index]
            if self.normalized_results is not None
            else self.normalized
        )
        return normalized, {
            "kind": "tool",
            "connection_display_name": "CRM",
            "tool_name": "lookup_customer",
        }


class _RecordingDocumentRag:
    def __init__(self) -> None:
        self.generation_calls: list[dict] = []

    @staticmethod
    def _validate_citations(result, _allowed_ids, _context_chunks):
        return {
            "answer": result.get("answer_markdown") or "",
            "citations": [],
            "insufficient_context": bool(result.get("insufficient_context")),
            "model": result.get("model"),
        }

    def _record_generation_usage(
        self,
        validated,
        payload,
        *,
        operation_type,
        scope,
        usage_context,
    ) -> None:
        self.generation_calls.append(
            {
                "validated": dict(validated),
                "payload": dict(payload),
                "operation_type": operation_type,
                "scope": scope,
                "usage_context": usage_context,
            }
        )


def _tool_loop(
    provider: _TwoRoundProvider | _ScriptedToolProvider,
    dispatcher: _RecordingDispatcher,
    *,
    general: bool = True,
) -> tuple[ToolLoopTurnExecutor, SimpleNamespace, ChatInvocationContext]:
    rag = SimpleNamespace() if general else _RecordingDocumentRag()
    executor = ToolLoopTurnExecutor(
        SimpleNamespace(),  # type: ignore[arg-type]
        settings=_settings(),
        rag=rag,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        dispatcher=dispatcher,  # type: ignore[arg-type]
    )
    prepared = _PreparedTurn(
        system_prompt="Use tools safely.",
        messages=[{"role": "user", "content": "question"}],
        scope=None,
        allowed_ids=set(),
        context_chunks=[],
        general=general,
    )
    executor._prepare = lambda **_kwargs: prepared  # type: ignore[method-assign]
    executor._record_intermediate_usage = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    if general:
        executor._finalize = (  # type: ignore[method-assign]
            lambda result, **_kwargs: ToolLoopResult(
                answer=result.message.content or "",
                citations=[],
                insufficient_context=False,
                model=result.provider_model,
                usage={},
                billed_chat_tokens=0,
            )
        )
    tool = SimpleNamespace(
        llm_tool_name="mcp_read",
        tool_name="lookup_customer",
        title="Customer lookup",
        input_schema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "page": {
                    "type": "number",
                    "minimum": 1,
                    "description": "Page number for pagination (min 1)",
                },
                "perPage": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 100,
                    "description": (
                        "Results per page for pagination (min 1, max 100)"
                    ),
                },
            },
            "required": ["customer_id"],
            "additionalProperties": False,
        },
        classification="read_only",
    )
    resolved = SimpleNamespace(
        tool=tool,
        connection=SimpleNamespace(display_name="CRM"),
        provider_tool_schema={
            "type": "function",
            "function": {
                "name": "mcp_read",
                "parameters": tool.input_schema,
            },
        },
    )
    expert_id = uuid.uuid4()
    invocation = ChatInvocationContext.workspace_user(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        expert_id=expert_id,
    )
    return executor, resolved, invocation


def test_tool_loop_streams_ordered_safe_events_and_periodic_keepalives() -> None:
    provider = _TwoRoundProvider(delay=0.035)
    dispatcher = _RecordingDispatcher(delay=0.035)
    executor, resolved, invocation = _tool_loop(provider, dispatcher)

    events: list[ToolLoopStreamEvent] = []
    for event in executor.execute_events(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
        keepalive_interval_seconds=0.01,
    ):
        if event.event == "tool_call":
            assert dispatcher.calls == 0
        if event.event == "tool_result":
            assert dispatcher.calls == 1
        events.append(event)

    lifecycle = [event for event in events if event.event != "keepalive"]
    assert [event.event for event in lifecycle] == [
        "tool_call",
        "tool_result",
        "complete",
    ]
    assert sum(event.event == "keepalive" for event in events) >= 3
    assert lifecycle[0].data == {
        "connection_name": "CRM",
        "tool_name": "Customer lookup",
        "status": "dispatching",
    }
    assert lifecycle[1].data == {
        "connection_name": "CRM",
        "tool_name": "Customer lookup",
        "status": "completed",
    }
    assert "customer_id" not in repr(lifecycle[0].data)
    assert "untrusted_mcp_tool_result" not in repr(lifecycle[1].data)
    assert lifecycle[2].result is not None
    assert lifecycle[2].result.answer == "Final answer"

    # The model-owned transcript still receives the exact call/result pair.
    assert provider.messages[1][-2]["tool_calls"][0]["id"] == "call-1"
    assert provider.messages[1][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": dispatcher.normalized.model_content,
    }


def test_closing_after_tool_call_cancels_undispatched_work() -> None:
    provider = _TwoRoundProvider()
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(provider, dispatcher)
    stream = executor.execute_events(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
        keepalive_interval_seconds=0.01,
    )

    event = next(stream)
    while event.event == "keepalive":
        event = next(stream)
    assert event.event == "tool_call"
    assert dispatcher.calls == 0
    stream.close()
    assert dispatcher.calls == 0


def test_synchronous_tool_loop_callers_remain_supported() -> None:
    provider = _TwoRoundProvider()
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(provider, dispatcher)

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert result.answer == "Final answer"
    assert dispatcher.calls == 1


def test_reordered_identical_success_dispatches_once_then_synthesizes_tool_free() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7,"page":1,"perPage":100}',
            '{"perPage":100,"customer_id":7,"page":1}',
        ],
        final_content=(
            '{"answer_markdown":"One page checked.",'
            '"citation_chunk_ids":[],"insufficient_context":false}'
        ),
    )
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )

    events = list(
        executor.execute_events(
            knowledge=SimpleNamespace(),  # type: ignore[arg-type]
            expert_id=invocation.expert_id,
            question="check page one",
            invocation=invocation,
            usage_context=SimpleNamespace(),  # type: ignore[arg-type]
            tools=[resolved],  # type: ignore[list-item]
            keepalive_interval_seconds=None,
        )
    )

    assert dispatcher.calls == 1
    assert dispatcher.arguments == [{"customer_id": 7, "page": 1, "perPage": 100}]
    assert [event.event for event in events] == [
        "tool_call",
        "tool_result",
        "complete",
    ]
    assert len(provider.tool_sets) == 3
    assert provider.tool_sets[0]
    assert provider.tool_sets[1]
    assert provider.tool_sets[2] == []
    assert provider.messages[2][-1]["tool_call_id"] == "call-2"
    assert "No new tool request was dispatched" in provider.messages[2][-1]["content"]
    assert dispatcher.normalized.model_content not in provider.messages[2][-1]["content"]
    result = events[-1].result
    assert result is not None
    assert result.answer == "One page checked."
    assert result.citations == [
        {
            "kind": "tool",
            "connection_display_name": "CRM",
            "tool_name": "lookup_customer",
        }
    ]


def test_repeated_success_at_iteration_ceiling_synthesizes_tool_free() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7}',
            '{"customer_id":7}',
        ],
        final_content="Used the first result.",
    )
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(provider, dispatcher)
    executor.settings = executor.settings.model_copy(
        update={"mcp_max_tool_iterations": 1}
    )

    events = list(
        executor.execute_events(
            knowledge=SimpleNamespace(),  # type: ignore[arg-type]
            expert_id=invocation.expert_id,
            question="question",
            invocation=invocation,
            usage_context=SimpleNamespace(),  # type: ignore[arg-type]
            tools=[resolved],  # type: ignore[list-item]
            keepalive_interval_seconds=None,
        )
    )

    assert dispatcher.calls == 1
    assert [event.event for event in events] == [
        "tool_call",
        "tool_result",
        "complete",
    ]
    assert [bool(tool_set) for tool_set in provider.tool_sets] == [True, True, False]
    assert events[-1].result is not None
    assert events[-1].result.answer == "Used the first result."


def test_distinct_page_arguments_dispatch_both_calls() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7,"page":1,"perPage":100}',
            '{"customer_id":7,"page":2,"perPage":100}',
        ],
        final_content=(
            '{"answer_markdown":"Two pages checked.",'
            '"citation_chunk_ids":[],"insufficient_context":false}'
        ),
    )
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="check pages one and two",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 2
    assert dispatcher.arguments == [
        {"customer_id": 7, "page": 1, "perPage": 100},
        {"customer_id": 7, "page": 2, "perPage": 100},
    ]
    assert len(provider.tool_sets) == 3
    assert all(provider.tool_sets)
    assert result.answer == "Two pages checked."
    assert result.citations == [
        {
            "kind": "tool",
            "connection_display_name": "CRM",
            "tool_name": "lookup_customer",
        }
    ]


def test_pagination_profile_change_stops_observed_refetch_sequence() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7}',
            '{"customer_id":7,"page":2}',
            '{"customer_id":7,"page":2,"perPage":100}',
            '{"customer_id":7,"page":1,"perPage":100}',
        ],
        final_content=(
            '{"answer_markdown":"One branch found.",'
            '"citation_chunk_ids":[],"insufficient_context":false}'
        ),
    )
    dispatcher = _RecordingDispatcher()
    dispatcher.normalized_results = [
        _normalized_json_result([{"name": "master"}]),
        _normalized_json_result([]),
    ]
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )

    events = list(
        executor.execute_events(
            knowledge=SimpleNamespace(),  # type: ignore[arg-type]
            expert_id=invocation.expert_id,
            question="count all branches",
            invocation=invocation,
            usage_context=SimpleNamespace(),  # type: ignore[arg-type]
            tools=[resolved],  # type: ignore[list-item]
            keepalive_interval_seconds=None,
        )
    )

    assert dispatcher.calls == 2
    assert dispatcher.arguments == [
        {"customer_id": 7},
        {"customer_id": 7, "page": 2},
    ]
    assert [event.event for event in events] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "complete",
    ]
    assert [bool(tool_set) for tool_set in provider.tool_sets] == [
        True,
        True,
        True,
        False,
    ]
    assert not any(
        call.get("id") == "call-4"
        for messages in provider.messages
        for message in messages
        for call in message.get("tool_calls") or []
    )
    result = events[-1].result
    assert result is not None
    assert result.answer == "One branch found."
    assert result.citations == [
        {
            "kind": "tool",
            "connection_display_name": "CRM",
            "tool_name": "lookup_customer",
        }
    ]


def test_short_generic_page_does_not_suppress_an_unseen_page() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7,"page":1,"perPage":100}',
            '{"customer_id":7,"page":2,"perPage":100}',
        ],
        final_content=(
            '{"answer_markdown":"One branch found.",'
            '"citation_chunk_ids":[],"insufficient_context":false}'
        ),
    )
    dispatcher = _RecordingDispatcher()
    page_value = json.dumps([{"name": "master"}], separators=(",", ":"))
    dispatcher.normalized = NormalizedToolResult(
        model_content=(
            "<untrusted_mcp_tool_result>\n"
            + json.dumps(
                {
                    "content_kind": "text",
                    "is_error": False,
                    "truncated": False,
                    "value": page_value,
                },
                separators=(",", ":"),
            )
            + "\n</untrusted_mcp_tool_result>"
        ),
        is_error=False,
        transport_bytes=12,
        content_types=("text",),
        unsupported_blocks=(),
    )
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="count all branches",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 2
    assert [bool(tool_set) for tool_set in provider.tool_sets] == [True, True, True]
    assert result.answer == "One branch found."


def test_empty_page_with_continuation_does_not_end_pagination() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7,"page":1,"perPage":100}',
            '{"customer_id":7,"page":2,"perPage":100}',
            '{"customer_id":7,"page":3,"perPage":100}',
        ],
        final_content="Continuation followed.",
    )
    dispatcher = _RecordingDispatcher()
    dispatcher.normalized_results = [
        _normalized_json_result([{"name": "master"}]),
        _normalized_json_result({"items": [], "hasNextPage": True}),
        _normalized_json_result([{"name": "later"}]),
    ]
    executor, resolved, invocation = _tool_loop(provider, dispatcher)

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 3
    assert result.answer == "Continuation followed."


def test_larger_page_size_can_expand_nonempty_page_coverage() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7,"page":1,"perPage":1}',
            '{"customer_id":7,"page":1,"perPage":100}',
        ],
        final_content="Expanded page used.",
    )
    dispatcher = _RecordingDispatcher()
    dispatcher.normalized = _normalized_json_result([{"name": "master"}])
    executor, resolved, invocation = _tool_loop(provider, dispatcher)

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 2
    assert result.answer == "Expanded page used."


def test_zero_based_numbered_pages_are_not_mistaken_for_repeats() -> None:
    provider = _ScriptedToolProvider(
        [
            '{"customer_id":7,"page":0,"perPage":100}',
            '{"customer_id":7,"page":1,"perPage":100}',
        ],
        final_content="Both pages used.",
    )
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(provider, dispatcher)
    resolved.tool.input_schema["properties"]["page"]["minimum"] = 0

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 2
    assert dispatcher.arguments == [
        {"customer_id": 7, "page": 0, "perPage": 100},
        {"customer_id": 7, "page": 1, "perPage": 100},
    ]
    assert result.answer == "Both pages used."


def test_large_page_integer_does_not_overflow_pagination_identity() -> None:
    provider = _ScriptedToolProvider(
        [
            json.dumps(
                {"customer_id": 7, "page": 10**400, "perPage": 100},
                separators=(",", ":"),
            )
        ],
        final_content="Large page handled.",
    )
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(provider, dispatcher)

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="question",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 1
    assert result.answer == "Large page handled."


def test_document_tool_loop_requests_json_and_accepts_fenced_synthesis() -> None:
    provider = _TwoRoundProvider(
        final_content=(
            "```json\n"
            '{"answer_markdown":"Seven commits found.",'
            '"citation_chunk_ids":[],"insufficient_context":false}'
            "\n```"
        )
    )
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )
    usage_context = SimpleNamespace()

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="list commits",
        invocation=invocation,
        usage_context=usage_context,  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert provider.json_responses == [True, True]
    assert result.answer == "Seven commits found."
    assert result.citations == [
        {
            "kind": "tool",
            "connection_display_name": "CRM",
            "tool_name": "lookup_customer",
        }
    ]
    rag = executor.rag
    assert isinstance(rag, _RecordingDocumentRag)
    assert len(rag.generation_calls) == 1
    assert rag.generation_calls[0]["operation_type"] == "mcp_final_synthesis"
    assert rag.generation_calls[0]["usage_context"] is usage_context


def test_remote_tool_error_forces_one_tool_free_synthesis_without_citation() -> None:
    provider = _TwoRoundProvider(
        final_content=(
            '{"answer_markdown":"The repository was not found.",'
            '"citation_chunk_ids":[],"insufficient_context":false}'
        )
    )
    dispatcher = _RecordingDispatcher(is_error=True)
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )

    result = executor.execute(
        knowledge=SimpleNamespace(),  # type: ignore[arg-type]
        expert_id=invocation.expert_id,
        question="list commits",
        invocation=invocation,
        usage_context=SimpleNamespace(),  # type: ignore[arg-type]
        tools=[resolved],  # type: ignore[list-item]
    )

    assert dispatcher.calls == 1
    assert provider.json_responses == [True, True]
    assert provider.tool_sets[0]
    assert provider.tool_sets[1] == []
    assert result.answer == "The repository was not found."
    assert result.citations == []


@pytest.mark.parametrize(
    "final_content",
    ["", "plain prose", '["not", "an object"]'],
)
def test_document_tool_loop_rejects_invalid_synthesis(final_content: str) -> None:
    provider = _TwoRoundProvider(final_content=final_content)
    dispatcher = _RecordingDispatcher()
    executor, resolved, invocation = _tool_loop(
        provider,
        dispatcher,
        general=False,
    )

    with pytest.raises(AppError) as raised:
        executor.execute(
            knowledge=SimpleNamespace(),  # type: ignore[arg-type]
            expert_id=invocation.expert_id,
            question="list commits",
            invocation=invocation,
            usage_context=SimpleNamespace(),  # type: ignore[arg-type]
            tools=[resolved],  # type: ignore[list-item]
        )

    assert raised.value.category == ErrorCategory.GENERATION_FAILED
    assert provider.json_responses == [True, True]
    rag = executor.rag
    assert isinstance(rag, _RecordingDocumentRag)
    assert rag.generation_calls == []


def test_public_answer_stream_suppresses_tool_details_but_keeps_heartbeats(
    monkeypatch,
) -> None:
    class _FakeLoopExecutor:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def execute_events(self, **_kwargs):
            yield ToolLoopStreamEvent(
                event="tool_call",
                data={"tool_name": "private_tool", "connection_name": "private_server"},
            )
            yield ToolLoopStreamEvent(event="keepalive", data={})
            yield ToolLoopStreamEvent(
                event="tool_result",
                data={"tool_name": "private_tool", "status": "completed"},
            )
            yield ToolLoopStreamEvent(
                event="complete",
                data={},
                result=ToolLoopResult(
                    answer="Public answer",
                    citations=[],
                    insufficient_context=False,
                    model="private-provider-model",
                    usage={},
                    billed_chat_tokens=0,
                ),
            )

    class _Meter:
        closed = False

        @staticmethod
        def context():
            return SimpleNamespace(extra_billed_tokens=0)

        def settle(self, _payload) -> None:
            self.closed = True

        def release(self) -> None:
            self.closed = True

    expert_query = SimpleNamespace(
        _rag=SimpleNamespace(),
        resolve_knowledge_for_workspace=lambda **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(turn_module, "ToolLoopTurnExecutor", _FakeLoopExecutor)
    monkeypatch.setattr(turn_module, "settled_tokens_from_payload", lambda *_a, **_k: 7)
    executor = ChatTurnExecutor(
        SimpleNamespace(),  # type: ignore[arg-type]
        settings=_settings(),
        expert_query=expert_query,  # type: ignore[arg-type]
    )
    workspace = SimpleNamespace(id=uuid.uuid4())
    events = list(
        executor.stream(
            workspace=workspace,  # type: ignore[arg-type]
            expert_id=uuid.uuid4(),
            question="question",
            invocation=SimpleNamespace(api_key_id=uuid.uuid4()),  # type: ignore[arg-type]
            meter=_Meter(),  # type: ignore[arg-type]
            request_id="request-1",
            mcp_tools=[SimpleNamespace()],  # type: ignore[list-item]
        )
    )

    assert "tool_call" not in [event["event"] for event in events]
    assert "tool_result" not in [event["event"] for event in events]
    assert "keepalive" in [event["event"] for event in events]
    wire = list(
        iter_completion_sse(
            iter(events),
            turn_id="request-1",
            model="geem-expert",
            created=1,
        )
    )
    serialized = "".join(wire)
    assert ": keepalive\n\n" in wire
    assert "private_tool" not in serialized
    assert "private_server" not in serialized
    assert "private-provider-model" not in serialized
    assert "Public answer" in serialized
