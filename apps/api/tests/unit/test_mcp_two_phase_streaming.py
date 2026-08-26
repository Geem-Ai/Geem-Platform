from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace

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
    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.messages: list[list[dict]] = []

    def answer_with_tools(self, messages, **_kwargs) -> AgentProviderResult:
        self.messages.append(list(messages))
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
                content="Final answer",
                tool_calls=None,
            ),
            finish_reason="stop",
            usage=AgentUsage(prompt_tokens=3, completion_tokens=1, total_tokens=4),
            provider_model="test/tool-model",
        )


class _RecordingDispatcher:
    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls = 0
        self.normalized = NormalizedToolResult(
            model_content="<untrusted_mcp_tool_result>safe</untrusted_mcp_tool_result>",
            is_error=False,
            transport_bytes=12,
            content_types=("text",),
            unsupported_blocks=(),
        )

    def dispatch(self, **_kwargs):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.normalized, {
            "kind": "tool",
            "connection_display_name": "CRM",
            "tool_name": "lookup_customer",
        }


def _tool_loop(
    provider: _TwoRoundProvider,
    dispatcher: _RecordingDispatcher,
) -> tuple[ToolLoopTurnExecutor, SimpleNamespace, ChatInvocationContext]:
    executor = ToolLoopTurnExecutor(
        SimpleNamespace(),  # type: ignore[arg-type]
        settings=_settings(),
        rag=SimpleNamespace(),  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        dispatcher=dispatcher,  # type: ignore[arg-type]
    )
    prepared = _PreparedTurn(
        system_prompt="Use tools safely.",
        messages=[{"role": "user", "content": "question"}],
        scope=None,
        allowed_ids=set(),
        context_chunks=[],
        general=True,
    )
    executor._prepare = lambda **_kwargs: prepared  # type: ignore[method-assign]
    executor._record_intermediate_usage = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
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
            "properties": {"customer_id": {"type": "integer"}},
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
