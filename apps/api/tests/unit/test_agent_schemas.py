from __future__ import annotations

import copy

import pytest

from app.agent.schemas import AgentProtocolError, parse_agent_completion_request
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.config import Settings


def _base() -> dict:
    return {
        "model": PUBLIC_MODEL_ID,
        "messages": [{"role": "user", "content": "hello"}],
    }


def _tool(name: str = "lookup") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Lookup data",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
    }


def _error(payload: dict) -> AgentProtocolError:
    with pytest.raises(AgentProtocolError) as raised:
        parse_agent_completion_request(payload, settings=Settings())
    return raised.value


def test_required_model_and_allowlist_are_locked() -> None:
    missing = _base()
    missing.pop("model")
    assert _error(missing).code == "agent_model_required"
    unknown = _error(_base() | {"model": "expert-id"})
    assert (unknown.status_code, unknown.code, unknown.param) == (
        404,
        "model_not_found",
        "model",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", True),
        ("temperature", float("nan")),
        ("temperature", 2.01),
        ("top_p", -0.01),
        ("top_p", float("nan")),
        ("max_tokens", 0),
        ("max_tokens", True),
        ("n", 2),
        ("n", True),
        ("stream", "false"),
        ("response_format", {"type": "json_object"}),
        ("seed", 7),
        ("functions", []),
    ],
)
def test_unsupported_or_invalid_controls_are_rejected(field: str, value: object) -> None:
    exc = _error(_base() | {field: value})
    assert exc.code == "agent_unsupported_parameter"
    assert exc.param and exc.param.split(".")[0] == field


def test_supported_controls_and_defaults_are_resolved() -> None:
    request = parse_agent_completion_request(
        _base()
        | {
            "temperature": 0,
            "top_p": 1,
            "max_tokens": 4096,
            "response_format": {"type": "text"},
        },
        settings=Settings(),
    )
    assert request.tool_choice == "none"
    assert request.temperature == 0
    with_tools = parse_agent_completion_request(
        _base() | {"tools": [_tool()]}, settings=Settings()
    )
    assert with_tools.tool_choice == "auto"


def test_stream_options_require_stream_and_only_include_usage() -> None:
    assert _error(_base() | {"stream_options": {"include_usage": True}}).param == (
        "stream_options"
    )
    request = parse_agent_completion_request(
        _base() | {"stream": True, "stream_options": {"include_usage": True}},
        settings=Settings(),
    )
    assert request.stream_options and request.stream_options.include_usage is True
    assert _error(
        _base()
        | {
            "stream": True,
            "stream_options": {"include_usage": True, "extra": True},
        }
    ).param == "stream_options.extra"


def test_tool_names_choices_strict_and_limits() -> None:
    duplicate = _error(_base() | {"tools": [_tool(), _tool()]})
    assert duplicate.param == "tools.1.function.name"
    bad_name = copy.deepcopy(_tool())
    bad_name["function"]["name"] = "bad name"
    assert _error(_base() | {"tools": [bad_name]}).param.endswith("name")
    strict = copy.deepcopy(_tool())
    strict["function"]["strict"] = True
    assert _error(_base() | {"tools": [strict]}).param.endswith("strict")
    named = {
        "type": "function",
        "function": {"name": "missing"},
    }
    assert _error(
        _base() | {"tools": [_tool()], "tool_choice": named}
    ).param == "tool_choice"
    assert _error(_base() | {"tool_choice": "required"}).param == "tool_choice"
    assert _error(_base() | {"parallel_tool_calls": False}).param == (
        "parallel_tool_calls"
    )


def test_tool_schema_root_local_refs_and_remote_refs() -> None:
    local = _tool()
    local["function"]["parameters"] = {
        "type": "object",
        "$defs": {"identifier": {"type": "string"}},
        "properties": {"id": {"$ref": "#/$defs/identifier"}},
    }
    assert parse_agent_completion_request(
        _base() | {"tools": [local]}, settings=Settings()
    )
    missing = copy.deepcopy(local)
    missing["function"]["parameters"]["properties"]["id"]["$ref"] = (
        "#/$defs/missing"
    )
    assert _error(_base() | {"tools": [missing]}).param.startswith("tools.0")
    remote = copy.deepcopy(local)
    remote["function"]["parameters"]["properties"]["id"]["$ref"] = (
        "https://example.test/schema.json"
    )
    assert _error(_base() | {"tools": [remote]}).code == "agent_unsupported_parameter"
    not_object = copy.deepcopy(local)
    not_object["function"]["parameters"]["type"] = "array"
    assert _error(_base() | {"tools": [not_object]}).param.startswith("tools.0")
    malformed_keyword = copy.deepcopy(local)
    malformed_keyword["function"]["parameters"]["properties"]["id"]["minLength"] = -1
    assert _error(_base() | {"tools": [malformed_keyword]}).param.endswith(
        "properties.id.minLength"
    )


def test_message_body_tool_count_and_schema_byte_limits() -> None:
    settings = Settings(
        agent_max_messages=1,
        agent_max_tools=1,
        agent_tool_schema_max_bytes=40,
        agent_max_body_bytes=10,
    )
    with pytest.raises(AgentProtocolError) as body:
        parse_agent_completion_request(_base(), settings=settings, body_bytes=b"x" * 11)
    assert body.value.status_code == 413

    settings.agent_max_body_bytes = 100_000
    with pytest.raises(AgentProtocolError) as count:
        parse_agent_completion_request(
            _base() | {"tools": [_tool("a"), _tool("b")]}, settings=settings
        )
    assert count.value.code == "agent_tool_limit_exceeded"
    with pytest.raises(AgentProtocolError) as schema_bytes:
        parse_agent_completion_request(_base() | {"tools": [_tool()]}, settings=settings)
    assert schema_bytes.value.code == "agent_tool_limit_exceeded"
