from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentFunctionCall,
    AgentProviderResult,
    AgentToolCall,
    AgentUsage,
)
from app.conversations import chat_orchestrator as chat_orchestrator_module
from app.conversations.models import Message, MessageRole, MessageStatus
from app.core.config import get_settings
from app.experts.models import Expert, ExpertStatus
from app.mcp.executor import (
    ToolLoopResult,
    ToolLoopTurnExecutor,
    _PreparedTurn,
)
from app.mcp.result import NormalizedToolResult


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw.split("\n\n"):
        name = "message"
        data: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data.append(line.removeprefix("data:").lstrip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


class _ScriptedRetryProvider:
    def __init__(self, tool_names: list[str]) -> None:
        self.tool_names = tool_names
        self.index = 0
        self.without_tools_calls = 0

    def answer_with_tools(self, _messages, **_kwargs) -> AgentProviderResult:
        if self.index >= len(self.tool_names):
            return self._final()
        tool_name = self.tool_names[self.index]
        self.index += 1
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(
                content=None,
                tool_calls=[
                    AgentToolCall(
                        id=f"call-{self.index}",
                        type="function",
                        function=AgentFunctionCall(
                            name=tool_name,
                            arguments='{"owner":"MustafaTaj","repo":"mtfm_bot"}',
                        ),
                    )
                ],
            ),
            finish_reason="tool_calls",
            usage=AgentUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
            provider_model="test/tool-model",
        )

    def answer_without_tools(self, _messages, **_kwargs) -> AgentProviderResult:
        self.without_tools_calls += 1
        return self._final()

    @staticmethod
    def _final() -> AgentProviderResult:
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(
                content="The repository has 1 branch.",
                tool_calls=None,
            ),
            finish_reason="stop",
            usage=AgentUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            provider_model="test/tool-model",
        )


class _RecordingRetryDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, **kwargs):
        self.calls.append(dict(kwargs["arguments"]))
        return (
            NormalizedToolResult(
                model_content=(
                    "<untrusted_mcp_tool_result>"
                    '[{"name":"master"}]'
                    "</untrusted_mcp_tool_result>"
                ),
                is_error=False,
                transport_bytes=19,
                content_types=("text",),
                unsupported_blocks=(),
            ),
            {
                "kind": "tool",
                "connection_display_name": "GitHub",
                "tool_name": "list_branches",
            },
        )


def _resolved_list_branches() -> SimpleNamespace:
    schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
        },
        "required": ["owner", "repo"],
        "additionalProperties": False,
    }
    tool = SimpleNamespace(
        llm_tool_name="list_branches",
        tool_name="list_branches",
        title="list_branches",
        input_schema=schema,
        classification="read_only",
    )
    return SimpleNamespace(
        tool=tool,
        connection=SimpleNamespace(display_name="GitHub"),
        provider_tool_schema={
            "type": "function",
            "function": {"name": "list_branches", "parameters": schema},
        },
    )


def _executor_factory(provider, dispatcher):
    settings = get_settings().model_copy(
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

    def factory(db, **_kwargs):
        executor = ToolLoopTurnExecutor(
            db,
            settings=settings,
            rag=SimpleNamespace(),  # type: ignore[arg-type]
            provider=provider,
            dispatcher=dispatcher,
        )
        executor._prepare = lambda **_ignored: _PreparedTurn(  # type: ignore[method-assign]
            system_prompt="Use the one declared tool safely.",
            messages=[{"role": "user", "content": "How many branches?"}],
            scope=None,
            allowed_ids=set(),
            context_chunks=[],
            general=True,
        )
        executor._record_intermediate_usage = (  # type: ignore[method-assign]
            lambda *_args, **_ignored: None
        )
        executor._finalize = (  # type: ignore[method-assign]
            lambda result, *, tool_citations, **_ignored: ToolLoopResult(
                answer=result.message.content or "",
                citations=list(tool_citations),
                insufficient_context=False,
                model=result.provider_model,
                usage={},
                billed_chat_tokens=0,
            )
        )
        return executor

    return factory


@pytest.mark.parametrize(
    ("case", "tool_names"),
    [
        ("repeat", ["list_branches", "list_branches"]),
        ("undeclared", ["list_branches", "create_branch"]),
    ],
)
def test_retry_stream_dispatches_one_declared_read_and_hides_rejected_follow_up(
    case: str,
    tool_names: list[str],
    client,
    register_user,
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = register_user(email=f"mcp-retry-{case}@example.com")
    created_workspace = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": f"MCP retry {case}", "slug": f"mcp-retry-{case}"},
    )
    assert created_workspace.status_code in {200, 201}, created_workspace.text
    workspace = created_workspace.json()
    headers = _auth(
        user["access_token"],
        **{"X-Workspace-Id": workspace["id"]},
    )
    created_expert = client.post(
        "/api/experts",
        headers=headers,
        json={"name": f"Retry {case}"},
    )
    assert created_expert.status_code == 201, created_expert.text
    expert = db.get(Expert, uuid.UUID(created_expert.json()["id"]))
    assert expert is not None
    expert.status = ExpertStatus.READY.value
    db.commit()

    created_conversation = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": str(expert.id)},
    )
    assert created_conversation.status_code == 201, created_conversation.text
    conversation_id = uuid.UUID(created_conversation.json()["id"])
    now = datetime.now(timezone.utc)
    user_message = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER.value,
        content="How many branches are in MustafaTaj/mtfm_bot?",
        citations=[],
        attachments=[],
        status=MessageStatus.COMPLETED.value,
        created_at=now,
        updated_at=now,
    )
    failed_assistant = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT.value,
        content="Generation failed.",
        citations=[],
        attachments=[],
        status=MessageStatus.FAILED.value,
        created_at=now + timedelta(milliseconds=1),
        updated_at=now + timedelta(milliseconds=1),
    )
    db.add_all([user_message, failed_assistant])
    db.commit()

    resolved = _resolved_list_branches()
    provider = _ScriptedRetryProvider(tool_names)
    dispatcher = _RecordingRetryDispatcher()
    monkeypatch.setattr(
        "app.experts.query_service.ExpertQueryService.resolve_knowledge",
        lambda *_args, **_kwargs: MagicMock(),
    )
    monkeypatch.setattr(
        chat_orchestrator_module,
        "schedule_conversation_title",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_orchestrator_module.McpGrantResolver,
        "resolve",
        lambda *_args, **_kwargs: [resolved],
    )
    monkeypatch.setattr(
        chat_orchestrator_module,
        "ToolLoopTurnExecutor",
        _executor_factory(provider, dispatcher),
    )

    with client.stream(
        "POST",
        (
            f"/api/conversations/{conversation_id}/messages/"
            f"{failed_assistant.id}/retry/stream"
        ),
        headers=headers,
        json={},
    ) as response:
        assert response.status_code == 200, response.text
        events = _parse_sse("".join(response.iter_text()))

    assert dispatcher.calls == [
        {"owner": "MustafaTaj", "repo": "mtfm_bot"}
    ]
    assert provider.without_tools_calls == 1
    assert [name for name, _payload in events].count("tool_call") == 1
    assert [name for name, _payload in events].count("tool_result") == 1
    assert not any(name == "error" for name, _payload in events)
    tool_events = [
        payload
        for name, payload in events
        if name in {"tool_call", "tool_result"}
    ]
    assert {payload["tool_name"] for payload in tool_events} == {"list_branches"}
    assert not any(
        payload.get("status") in {"failed", "error"} for payload in tool_events
    )
    assert any(name == "final" for name, _payload in events)
    assert any(name == "message_complete" for name, _payload in events)
