"""Strict request, provider, and public-wire schemas for Phase 14 Agents AI.

The existing answer-mode Chat Completions schema is deliberately permissive for
backwards compatibility.  Agent mode is a separate surface: every recognized
field is either honored or rejected, and unknown fields are never discarded.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from app.agent.constants import (
    DEFAULT_AGENT_MAX_BODY_BYTES,
    DEFAULT_AGENT_MAX_MESSAGES,
    DEFAULT_AGENT_MAX_OUTPUT_TOKENS,
    DEFAULT_AGENT_MAX_TOOLS,
    DEFAULT_AGENT_TOOL_SCHEMA_MAX_BYTES,
    PUBLIC_AGENT_MODEL_IDS,
    TOOL_NAME_PATTERN,
)
from app.api.schemas import Citation
from app.core.config import Settings, get_settings


class AgentProtocolError(ValueError):
    """Deterministic protocol failure that a router can map to OpenAI wire."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        param: str | None,
        status_code: int = 400,
        error_type: str = "invalid_request_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.param = param
        self.status_code = int(status_code)
        self.error_type = error_type


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AgentFunctionCall(_StrictModel):
    name: str = Field(min_length=1, max_length=64, pattern=TOOL_NAME_PATTERN)
    arguments: str


class AgentToolCall(_StrictModel):
    id: str = Field(min_length=1, max_length=256)
    type: Literal["function"]
    function: AgentFunctionCall


class AgentInstructionMessage(_StrictModel):
    role: Literal["system", "developer"]
    content: str


class AgentUserMessage(_StrictModel):
    role: Literal["user"]
    content: str


class AgentAssistantMessage(_StrictModel):
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[AgentToolCall] | None = Field(default=None, min_length=1)

    @field_validator("tool_calls")
    @classmethod
    def _nonempty_tool_calls(
        cls, value: list[AgentToolCall] | None
    ) -> list[AgentToolCall] | None:
        if value == []:
            raise ValueError("tool_calls must be omitted or non-empty")
        return value


class AgentToolMessage(_StrictModel):
    role: Literal["tool"]
    content: str
    tool_call_id: str = Field(min_length=1, max_length=256)


AgentMessage = Annotated[
    AgentInstructionMessage | AgentUserMessage | AgentAssistantMessage | AgentToolMessage,
    Field(discriminator="role"),
]


class AgentFunctionDefinition(_StrictModel):
    name: str = Field(min_length=1, max_length=64, pattern=TOOL_NAME_PATTERN)
    description: str | None = None
    parameters: dict[str, Any]
    strict: bool | None = None


class AgentToolDefinition(_StrictModel):
    type: Literal["function"]
    function: AgentFunctionDefinition


class AgentNamedToolChoiceFunction(_StrictModel):
    name: str = Field(min_length=1, max_length=64, pattern=TOOL_NAME_PATTERN)


class AgentNamedToolChoice(_StrictModel):
    type: Literal["function"]
    function: AgentNamedToolChoiceFunction


AgentToolChoice = Literal["auto", "none", "required"] | AgentNamedToolChoice


class AgentStreamOptions(_StrictModel):
    include_usage: bool


class AgentTextResponseFormat(_StrictModel):
    type: Literal["text"]


class AgentCompletionRequest(_StrictModel):
    model: str
    messages: list[AgentMessage] = Field(min_length=1)
    tools: list[AgentToolDefinition] | None = None
    tool_choice: AgentToolChoice | None = None
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    parallel_tool_calls: bool | None = None
    stream_options: AgentStreamOptions | None = None
    n: int = 1
    response_format: AgentTextResponseFormat | None = None


class AgentUsage(_StrictModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _balanced_total(self) -> AgentUsage:
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens must equal prompt_tokens plus completion_tokens")
        return self

    @classmethod
    def from_provider(cls, raw: Any) -> AgentUsage:
        payload = raw if isinstance(raw, Mapping) else {}
        prompt = _nonnegative_int(payload.get("prompt_tokens"))
        completion = _nonnegative_int(payload.get("completion_tokens"))
        total_raw = payload.get("total_tokens")
        total = (
            _nonnegative_int(total_raw)
            if total_raw is not None
            else prompt + completion
        )
        return cls(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
        )


class AgentAssistantResponseMessage(_StrictModel):
    role: Literal["assistant"] = "assistant"
    content: str | None
    tool_calls: list[AgentToolCall] | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def _validate_output_mode(self) -> AgentAssistantResponseMessage:
        if self.tool_calls:
            if self.content is not None:
                raise ValueError("tool-call responses require null content")
        elif not isinstance(self.content, str):
            raise ValueError("text responses require string content")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_tool_calls(self, handler: Any) -> dict[str, Any]:
        payload = handler(self)
        if self.tool_calls is None:
            payload.pop("tool_calls", None)
        return payload


class AgentProviderResult(_StrictModel):
    """Validated provider output. Provider model IDs stay internal."""

    message: AgentAssistantResponseMessage
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter"]
    usage: AgentUsage
    provider_model: str | None = None
    provider_request_id: str | None = None
    provider_completion_id: str | None = None


class AgentProviderToolCallDelta(_StrictModel):
    index: int = Field(ge=0)
    id: str | None = None
    type: Literal["function"] | None = None
    name: str | None = None
    arguments: str | None = None


class AgentProviderStreamEvent(_StrictModel):
    """Provider-neutral event consumed by the public SSE adapter."""

    type: Literal["start", "content_delta", "tool_call_delta", "done"]
    content: str | None = None
    tool_call: AgentProviderToolCallDelta | None = None
    result: AgentProviderResult | None = None


class AgentGeemExtension(_StrictModel):
    retrieval: Literal["executed", "cache_hit", "skipped_general"]
    citations: list[Citation] = Field(default_factory=list)
    insufficient_context: bool | None
    billed_tokens: int = Field(ge=0)


class AgentCompletionChoice(_StrictModel):
    index: int = 0
    message: AgentAssistantResponseMessage
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter"]


class AgentCompletionResponse(_StrictModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[AgentCompletionChoice]
    usage: AgentUsage
    geem: AgentGeemExtension


class AgentModelObject(_StrictModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str


class AgentModelListResponse(_StrictModel):
    object: Literal["list"] = "list"
    data: list[AgentModelObject]


_SCHEMA_TYPES = frozenset(
    {"null", "boolean", "object", "array", "number", "string", "integer"}
)
_SCHEMA_SINGLE = frozenset(
    {
        "additionalProperties",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_SCHEMA_ARRAY = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_MAP = frozenset(
    {"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"}
)
_SCHEMA_NONNEGATIVE_INTEGERS = frozenset(
    {
        "maxContains",
        "maxItems",
        "maxLength",
        "maxProperties",
        "minContains",
        "minItems",
        "minLength",
        "minProperties",
    }
)
_SCHEMA_NUMBERS = frozenset(
    {"exclusiveMaximum", "exclusiveMinimum", "maximum", "minimum"}
)
_SCHEMA_STRINGS = frozenset(
    {
        "$anchor",
        "$comment",
        "$dynamicAnchor",
        "$id",
        "$schema",
        "contentEncoding",
        "contentMediaType",
        "description",
        "format",
        "title",
    }
)


def parse_agent_completion_request(
    payload: Mapping[str, Any],
    *,
    settings: Settings | None = None,
    body_bytes: bytes | None = None,
) -> AgentCompletionRequest:
    """Parse and semantically validate one Agent completion request.

    Routers that need exact Phase 14 errors should accept the JSON object and
    call this function instead of relying solely on FastAPI's generic 422 path.
    Transcript linkage and instruction demotion are performed by
    :func:`app.agent.messages.normalize_agent_messages`.
    """

    cfg = settings or get_settings()
    if not isinstance(payload, Mapping):
        raise AgentProtocolError(
            "Request body must be a JSON object.",
            code="agent_unsupported_parameter",
            param=None,
        )
    if "model" not in payload or payload.get("model") is None or not str(
        payload.get("model")
    ).strip():
        raise AgentProtocolError(
            "model is required.",
            code="agent_model_required",
            param="model",
        )

    max_body = _setting_int(cfg, "agent_max_body_bytes", DEFAULT_AGENT_MAX_BODY_BYTES)
    measured = body_bytes
    if measured is None:
        try:
            measured = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), default=str
            ).encode("utf-8")
        except (TypeError, ValueError):
            measured = b""
    if len(measured) > max_body:
        raise AgentProtocolError(
            "Request body exceeds the Agent API limit.",
            code="agent_unsupported_parameter",
            param=None,
            status_code=413,
        )

    try:
        request = AgentCompletionRequest.model_validate(payload)
    except ValidationError as exc:
        raise _protocol_error_from_validation(exc) from None
    return validate_agent_completion_request(request, settings=cfg)


def validate_agent_completion_request(
    request: AgentCompletionRequest,
    *,
    settings: Settings | None = None,
) -> AgentCompletionRequest:
    """Apply the locked support matrix and return defaults-resolved request."""

    cfg = settings or get_settings()
    if request.model not in PUBLIC_AGENT_MODEL_IDS:
        raise AgentProtocolError(
            f"The model '{request.model}' does not exist or is not available.",
            code="model_not_found",
            param="model",
            status_code=404,
        )

    max_messages = _setting_int(
        cfg, "agent_max_messages", DEFAULT_AGENT_MAX_MESSAGES
    )
    if len(request.messages) > max_messages:
        raise AgentProtocolError(
            f"messages may contain at most {max_messages} items.",
            code="agent_message_limit_exceeded",
            param="messages",
        )

    tools = request.tools or []
    max_tools = _setting_int(cfg, "agent_max_tools", DEFAULT_AGENT_MAX_TOOLS)
    if len(tools) > max_tools:
        raise AgentProtocolError(
            f"tools may contain at most {max_tools} functions.",
            code="agent_tool_limit_exceeded",
            param="tools",
        )
    names: set[str] = set()
    for index, tool in enumerate(tools):
        name = tool.function.name
        if name in names:
            raise AgentProtocolError(
                f"Duplicate tool function name '{name}'.",
                code="agent_unsupported_parameter",
                param=f"tools.{index}.function.name",
            )
        names.add(name)
        if tool.function.strict is True:
            raise AgentProtocolError(
                "strict: true is not supported by the Agent API.",
                code="agent_unsupported_parameter",
                param=f"tools.{index}.function.strict",
            )
        validate_agent_tool_schema(
            tool.function.parameters,
            param=f"tools.{index}.function.parameters",
        )

    schema_bytes = len(
        json.dumps(
            [tool.model_dump(mode="json", exclude_none=True) for tool in tools],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    max_schema_bytes = _setting_int(
        cfg, "agent_tool_schema_max_bytes", DEFAULT_AGENT_TOOL_SCHEMA_MAX_BYTES
    )
    if schema_bytes > max_schema_bytes:
        raise AgentProtocolError(
            f"tools exceed the {max_schema_bytes}-byte schema limit.",
            code="agent_tool_limit_exceeded",
            param="tools",
        )

    choice: AgentToolChoice
    if request.tool_choice is None:
        choice = "auto" if tools else "none"
    else:
        choice = request.tool_choice
    if not tools and choice != "none":
        raise AgentProtocolError(
            "tool_choice requires at least one declared tool.",
            code="agent_unsupported_parameter",
            param="tool_choice",
        )
    if isinstance(choice, AgentNamedToolChoice):
        if choice.function.name not in names:
            raise AgentProtocolError(
                "Named tool_choice must reference a function declared in tools.",
                code="agent_unsupported_parameter",
                param="tool_choice",
            )

    if request.parallel_tool_calls is not None and not tools:
        raise AgentProtocolError(
            "parallel_tool_calls requires at least one declared tool.",
            code="agent_unsupported_parameter",
            param="parallel_tool_calls",
        )
    if request.stream_options is not None and not request.stream:
        raise AgentProtocolError(
            "stream_options is allowed only when stream is true.",
            code="agent_unsupported_parameter",
            param="stream_options",
        )
    if isinstance(request.n, bool) or request.n != 1:
        raise AgentProtocolError(
            "n must be omitted or equal to 1.",
            code="agent_unsupported_parameter",
            param="n",
        )
    if request.temperature is not None and (
        isinstance(request.temperature, bool)
        or not math.isfinite(request.temperature)
        or request.temperature < 0
        or request.temperature > 2
    ):
        raise AgentProtocolError(
            "temperature must be between 0 and 2.",
            code="agent_unsupported_parameter",
            param="temperature",
        )
    if request.top_p is not None and (
        isinstance(request.top_p, bool)
        or not math.isfinite(request.top_p)
        or request.top_p < 0
        or request.top_p > 1
    ):
        raise AgentProtocolError(
            "top_p must be between 0 and 1.",
            code="agent_unsupported_parameter",
            param="top_p",
        )
    max_output = _setting_int(
        cfg, "agent_max_output_tokens", DEFAULT_AGENT_MAX_OUTPUT_TOKENS
    )
    if request.max_tokens is not None and (
        isinstance(request.max_tokens, bool)
        or request.max_tokens < 1
        or request.max_tokens > max_output
    ):
        raise AgentProtocolError(
            f"max_tokens must be between 1 and {max_output}.",
            code="agent_unsupported_parameter",
            param="max_tokens",
        )
    return request.model_copy(update={"tool_choice": choice})


def validate_agent_tool_schema(schema: Any, *, param: str = "tools") -> None:
    """Validate the supported structural Draft 2020-12 JSON Schema subset.

    Unknown annotation/vocabulary keywords remain legal, as required by JSON
    Schema.  Structural schema-bearing keywords are recursively checked and
    remote references are rejected without ever resolving them.
    """

    if not isinstance(schema, dict):
        raise _schema_error("parameters must be a JSON Schema object.", param)
    root_type = schema.get("type")
    root_types = [root_type] if isinstance(root_type, str) else root_type
    if (
        not isinstance(root_types, list)
        or "object" not in root_types
        or any(not isinstance(item, str) for item in root_types)
    ):
        raise _schema_error("parameters root type must include 'object'.", param)

    anchors: set[str] = set()
    _collect_schema_anchors(schema, anchors, path=param)
    local_refs: list[str] = []
    _validate_schema_node(schema, root=schema, path=param, local_refs=local_refs)
    for ref in local_refs:
        if ref == "#":
            continue
        if ref.startswith("#/"):
            if not _json_pointer_exists(schema, unquote(ref[2:])):
                raise _schema_error(f"Local JSON Schema reference '{ref}' does not exist.", param)
            continue
        if ref.startswith("#") and ref[1:] in anchors:
            continue
        raise _schema_error(f"Local JSON Schema reference '{ref}' does not exist.", param)

    # Validate against the official Draft 2020-12 metaschema only after the
    # local traversal.  The traversal produces precise public ``param`` paths
    # and enforces the no-remote-resolution boundary; the metaschema remains
    # the final authority for valid vocabulary shapes we do not special-case.
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        schema_path = ".".join(str(part) for part in exc.path)
        error_param = f"{param}.{schema_path}" if schema_path else param
        raise _schema_error(
            f"parameters must be a valid JSON Schema Draft 2020-12 schema: {exc.message}",
            error_param,
        ) from None


def declared_tool_names(request: AgentCompletionRequest) -> frozenset[str]:
    return frozenset(tool.function.name for tool in (request.tools or []))


def request_tools_payload(request: AgentCompletionRequest) -> list[dict[str, Any]] | None:
    if not request.tools:
        return None
    return [tool.model_dump(mode="json", exclude_none=True) for tool in request.tools]


def request_tool_choice_payload(request: AgentCompletionRequest) -> str | dict[str, Any]:
    choice = request.tool_choice or ("auto" if request.tools else "none")
    if isinstance(choice, str):
        return choice
    return choice.model_dump(mode="json", exclude_none=True)


def request_control_payload(request: AgentCompletionRequest) -> dict[str, Any]:
    """Return only scalar controls accepted by ``complete_for_agent``.

    The sole supported response format is text, which is provider-default
    behavior and is intentionally not forwarded as structured-output config.
    """

    out: dict[str, Any] = {}
    for field in ("temperature", "top_p", "max_tokens", "parallel_tool_calls"):
        value = getattr(request, field)
        if value is not None:
            out[field] = value
    return out


def _protocol_error_from_validation(exc: ValidationError) -> AgentProtocolError:
    first = exc.errors()[0] if exc.errors() else {}
    loc = [str(item) for item in first.get("loc", ())]
    if len(loc) >= 3 and loc[0] == "messages" and loc[2] in {
        "system",
        "developer",
        "user",
        "assistant",
        "tool",
    }:
        loc.pop(2)
    param = ".".join(loc) or None
    message = str(first.get("msg") or "Invalid request.")
    if loc and loc[0] == "model" and first.get("type") == "missing":
        return AgentProtocolError(
            "model is required.", code="agent_model_required", param="model"
        )
    code = (
        "agent_invalid_tool_transcript"
        if loc and loc[0] == "messages"
        else "agent_unsupported_parameter"
    )
    return AgentProtocolError(message, code=code, param=param)


def _validate_schema_node(
    node: Any,
    *,
    root: dict[str, Any],
    path: str,
    local_refs: list[str],
) -> None:
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        raise _schema_error("Schema nodes must be objects or booleans.", path)

    for ref_key in ("$ref", "$dynamicRef"):
        if ref_key in node:
            ref = node[ref_key]
            if not isinstance(ref, str) or not ref.startswith("#"):
                raise _schema_error(
                    "External or remote JSON Schema references are not supported.",
                    f"{path}.{ref_key}",
                )
            local_refs.append(ref)

    for keyword in _SCHEMA_STRINGS:
        if keyword in node and not isinstance(node[keyword], str):
            raise _schema_error(f"{keyword} must be a string.", f"{path}.{keyword}")
    for keyword in ("$anchor", "$dynamicAnchor"):
        if keyword in node and not re.fullmatch(
            r"[A-Za-z_][-A-Za-z0-9._]*", node[keyword]
        ):
            raise _schema_error(f"Invalid {keyword} name.", f"{path}.{keyword}")
    for keyword in _SCHEMA_NUMBERS:
        if keyword in node and not _is_finite_number(node[keyword]):
            raise _schema_error(f"{keyword} must be a number.", f"{path}.{keyword}")
    if "multipleOf" in node and (
        not _is_finite_number(node["multipleOf"]) or node["multipleOf"] <= 0
    ):
        raise _schema_error("multipleOf must be greater than zero.", f"{path}.multipleOf")
    for keyword in _SCHEMA_NONNEGATIVE_INTEGERS:
        value = node.get(keyword)
        if keyword in node and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise _schema_error(
                f"{keyword} must be a non-negative integer.", f"{path}.{keyword}"
            )
    for keyword in ("uniqueItems",):
        if keyword in node and not isinstance(node[keyword], bool):
            raise _schema_error(f"{keyword} must be a boolean.", f"{path}.{keyword}")
    for keyword in ("readOnly", "writeOnly", "deprecated"):
        if keyword in node and not isinstance(node[keyword], bool):
            raise _schema_error(f"{keyword} must be a boolean.", f"{path}.{keyword}")
    if "$vocabulary" in node:
        vocabulary = node["$vocabulary"]
        if not isinstance(vocabulary, dict) or any(
            not isinstance(uri, str) or not isinstance(required, bool)
            for uri, required in vocabulary.items()
        ):
            raise _schema_error(
                "$vocabulary must map URI strings to booleans.", f"{path}.$vocabulary"
            )

    if "type" in node:
        raw_type = node["type"]
        types = [raw_type] if isinstance(raw_type, str) else raw_type
        if (
            not isinstance(types, list)
            or not types
            or any(not isinstance(item, str) or item not in _SCHEMA_TYPES for item in types)
            or len(set(types)) != len(types)
        ):
            raise _schema_error("Invalid JSON Schema type.", f"{path}.type")
    if "required" in node:
        required = node["required"]
        if (
            not isinstance(required, list)
            or any(not isinstance(item, str) for item in required)
            or len(set(required)) != len(required)
        ):
            raise _schema_error(
                "required must be an array of unique strings.", f"{path}.required"
            )
    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        raise _schema_error("enum must be a non-empty array.", f"{path}.enum")
    if "examples" in node and not isinstance(node["examples"], list):
        raise _schema_error("examples must be an array.", f"{path}.examples")
    if "pattern" in node:
        _validate_regex(node["pattern"], f"{path}.pattern")

    for keyword in _SCHEMA_SINGLE:
        if keyword in node:
            _validate_schema_node(
                node[keyword], root=root, path=f"{path}.{keyword}", local_refs=local_refs
            )
    for keyword in _SCHEMA_ARRAY:
        if keyword not in node:
            continue
        values = node[keyword]
        if not isinstance(values, list) or not values:
            raise _schema_error(f"{keyword} must be a non-empty array.", f"{path}.{keyword}")
        for index, value in enumerate(values):
            _validate_schema_node(
                value,
                root=root,
                path=f"{path}.{keyword}.{index}",
                local_refs=local_refs,
            )
    for keyword in _SCHEMA_MAP:
        if keyword not in node:
            continue
        values = node[keyword]
        if not isinstance(values, dict):
            raise _schema_error(f"{keyword} must be an object.", f"{path}.{keyword}")
        for name, value in values.items():
            if keyword == "patternProperties":
                _validate_regex(name, f"{path}.{keyword}")
            _validate_schema_node(
                value,
                root=root,
                path=f"{path}.{keyword}.{name}",
                local_refs=local_refs,
            )
    if "dependentRequired" in node:
        values = node["dependentRequired"]
        if not isinstance(values, dict):
            raise _schema_error(
                "dependentRequired must be an object.", f"{path}.dependentRequired"
            )
        for required in values.values():
            if (
                not isinstance(required, list)
                or any(not isinstance(item, str) for item in required)
                or len(set(required)) != len(required)
            ):
                raise _schema_error(
                    "dependentRequired values must be arrays of unique strings.",
                    f"{path}.dependentRequired",
                )


def _collect_schema_anchors(node: Any, anchors: set[str], *, path: str) -> None:
    if isinstance(node, dict):
        for keyword in ("$anchor", "$dynamicAnchor"):
            anchor = node.get(keyword)
            if isinstance(anchor, str):
                if anchor in anchors:
                    raise _schema_error(
                        f"Duplicate JSON Schema anchor '{anchor}'.", f"{path}.{keyword}"
                    )
                anchors.add(anchor)
        for keyword in _SCHEMA_SINGLE:
            if keyword in node:
                _collect_schema_anchors(
                    node[keyword], anchors, path=f"{path}.{keyword}"
                )
        for keyword in _SCHEMA_ARRAY:
            values = node.get(keyword)
            if isinstance(values, list):
                for index, value in enumerate(values):
                    _collect_schema_anchors(
                        value, anchors, path=f"{path}.{keyword}.{index}"
                    )
        for keyword in _SCHEMA_MAP:
            values = node.get(keyword)
            if isinstance(values, dict):
                for name, value in values.items():
                    _collect_schema_anchors(
                        value, anchors, path=f"{path}.{keyword}.{name}"
                    )


def _json_pointer_exists(root: Any, pointer: str) -> bool:
    current = root
    if not pointer:
        return True
    for raw in pointer.split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                current = current[int(token)]
                continue
            except (ValueError, IndexError):
                return False
        return False
    return True


def _validate_regex(value: Any, path: str) -> None:
    if not isinstance(value, str):
        raise _schema_error("JSON Schema regex must be a string.", path)
    try:
        re.compile(value)
    except re.error as exc:
        raise _schema_error(f"Invalid JSON Schema regex: {exc}.", path) from None


def _schema_error(message: str, param: str) -> AgentProtocolError:
    return AgentProtocolError(
        message,
        code="agent_unsupported_parameter",
        param=param,
    )


def _setting_int(settings: Settings, name: str, fallback: int) -> int:
    try:
        value = int(getattr(settings, name, fallback))
    except (TypeError, ValueError):
        value = fallback
    return value if value > 0 else fallback


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
    )


__all__ = [
    "AgentAssistantMessage",
    "AgentAssistantResponseMessage",
    "AgentCompletionChoice",
    "AgentCompletionRequest",
    "AgentCompletionResponse",
    "AgentFunctionCall",
    "AgentFunctionDefinition",
    "AgentGeemExtension",
    "AgentInstructionMessage",
    "AgentMessage",
    "AgentModelListResponse",
    "AgentModelObject",
    "AgentNamedToolChoice",
    "AgentProtocolError",
    "AgentProviderResult",
    "AgentProviderStreamEvent",
    "AgentProviderToolCallDelta",
    "AgentStreamOptions",
    "AgentTextResponseFormat",
    "AgentToolCall",
    "AgentToolChoice",
    "AgentToolDefinition",
    "AgentToolMessage",
    "AgentUsage",
    "AgentUserMessage",
    "declared_tool_names",
    "parse_agent_completion_request",
    "request_control_payload",
    "request_tool_choice_payload",
    "request_tools_payload",
    "validate_agent_completion_request",
    "validate_agent_tool_schema",
]
