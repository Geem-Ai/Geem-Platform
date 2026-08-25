"""Message normalization and tool-transcript validation for client-owned agents."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.agent.constants import (
    CLIENT_INSTRUCTIONS_TAG,
    CLIENT_TOOL_RESULT_TAG,
    DEFAULT_AGENT_CLIENT_INSTRUCTIONS_MAX_CHARS,
    DEFAULT_AGENT_TOOL_RESULT_MAX_CHARS,
)
from app.agent.schemas import (
    AgentAssistantMessage,
    AgentCompletionRequest,
    AgentInstructionMessage,
    AgentProtocolError,
    AgentToolMessage,
    AgentUserMessage,
    declared_tool_names,
)
from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class ClientInstructionAudit:
    """Safe-to-log instruction metadata; caller text is intentionally absent."""

    normalized_length: int
    digest: str | None


@dataclass(frozen=True, slots=True)
class NormalizedAgentMessages:
    """Validated model transcript plus retrieval and audit metadata."""

    transcript: tuple[dict[str, Any], ...]
    client_instruction_message: dict[str, str] | None
    retrieval_question: str
    is_tool_continuation: bool
    instruction_audit: ClientInstructionAudit

    def provider_messages(self) -> list[dict[str, Any]]:
        """Return only unprivileged messages for ``complete_for_agent``."""

        messages: list[dict[str, Any]] = []
        if self.client_instruction_message is not None:
            messages.append(dict(self.client_instruction_message))
        messages.extend(dict(message) for message in self.transcript)
        return messages

    def upstream_messages(self, system_prompt: str) -> list[dict[str, Any]]:
        """Build the provider transcript with exactly one privileged message."""

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": str(system_prompt)}
        ]
        if self.client_instruction_message is not None:
            messages.append(dict(self.client_instruction_message))
        for message in self.transcript:
            if message.get("role") in {"system", "developer"}:
                raise AssertionError("normalized transcript contains a privileged client role")
            messages.append(dict(message))
        return messages


def normalize_agent_messages(
    request: AgentCompletionRequest,
    *,
    settings: Settings | None = None,
    digest_key: str | bytes | None = None,
) -> NormalizedAgentMessages:
    """Demote instructions, validate linkage, and sanitize only tool-result text."""

    cfg = settings or get_settings()
    instruction_parts: list[str] = []
    ordinary: list[
        AgentUserMessage | AgentAssistantMessage | AgentToolMessage
    ] = []
    prefix_open = True

    for index, message in enumerate(request.messages):
        if isinstance(message, AgentInstructionMessage):
            if not prefix_open:
                raise _transcript_error(
                    "Client system/developer messages must form one leading prefix.",
                    f"messages.{index}.role",
                )
            instruction_parts.append(_normalize_instruction_text(message.content))
            continue
        prefix_open = False
        ordinary.append(message)

    normalized_instructions = "\n\n".join(instruction_parts)
    max_instructions = _positive_setting(
        cfg,
        "agent_client_instructions_max_chars",
        DEFAULT_AGENT_CLIENT_INSTRUCTIONS_MAX_CHARS,
    )
    if len(normalized_instructions) > max_instructions:
        raise AgentProtocolError(
            f"Client instructions exceed the {max_instructions}-character limit.",
            code="agent_client_instruction_limit_exceeded",
            param="messages",
        )

    instruction_message: dict[str, str] | None = None
    digest: str | None = None
    if instruction_parts:
        instruction_message = {
            "role": "user",
            "content": serialize_client_instructions(normalized_instructions),
        }
        key = _digest_key(cfg, digest_key)
        digest = hmac.new(
            key,
            normalized_instructions.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    allowed_names = declared_tool_names(request)
    seen_call_ids: set[str] = set()
    resolved_call_ids: set[str] = set()
    pending: dict[str, str] = {}
    transcript: list[dict[str, Any]] = []
    last_user: str | None = None

    for index, message in enumerate(ordinary):
        original_index = index + len(instruction_parts)
        if pending and not isinstance(message, AgentToolMessage):
            raise _transcript_error(
                "Every pending tool call must be resolved before another message.",
                f"messages.{original_index}",
            )

        if isinstance(message, AgentUserMessage):
            last_user = message.content
            transcript.append(message.model_dump(mode="json"))
            continue

        if isinstance(message, AgentAssistantMessage):
            tool_calls = message.tool_calls or []
            for call_index, call in enumerate(tool_calls):
                if call.id in seen_call_ids:
                    raise _transcript_error(
                        f"Duplicate tool call id '{call.id}'.",
                        f"messages.{original_index}.tool_calls.{call_index}.id",
                    )
                if call.function.name not in allowed_names:
                    raise _transcript_error(
                        f"Tool call references undeclared function '{call.function.name}'.",
                        f"messages.{original_index}.tool_calls.{call_index}.function.name",
                    )
                seen_call_ids.add(call.id)
                pending[call.id] = call.function.name
            transcript.append(message.model_dump(mode="json", exclude_none=True))
            continue

        if not isinstance(message, AgentToolMessage):
            raise _transcript_error("Unsupported message role.", f"messages.{original_index}.role")
        call_id = message.tool_call_id
        if call_id in resolved_call_ids:
            raise _transcript_error(
                f"Duplicate tool result for '{call_id}'.",
                f"messages.{original_index}.tool_call_id",
            )
        if call_id not in pending:
            raise _transcript_error(
                f"Tool result '{call_id}' does not match a pending tool call.",
                f"messages.{original_index}.tool_call_id",
            )
        pending.pop(call_id)
        resolved_call_ids.add(call_id)
        max_result = _positive_setting(
            cfg,
            "agent_tool_result_max_chars",
            DEFAULT_AGENT_TOOL_RESULT_MAX_CHARS,
        )
        bounded_content = message.content[:max_result]
        transcript.append(
            {
                "role": "tool",
                "content": serialize_tool_result(bounded_content),
                "tool_call_id": call_id,
            }
        )

    if pending:
        raise _transcript_error(
            "The transcript ends with unresolved tool calls.",
            "messages",
        )
    if not ordinary or isinstance(ordinary[-1], AgentAssistantMessage):
        raise _transcript_error(
            "A completion request must end with user input or completed tool results.",
            "messages",
        )
    if last_user is None or not last_user.strip():
        raise AgentProtocolError(
            "At least one non-empty real user message is required.",
            code="agent_user_message_required",
            param="messages",
        )

    return NormalizedAgentMessages(
        transcript=tuple(transcript),
        client_instruction_message=instruction_message,
        retrieval_question=last_user.strip(),
        is_tool_continuation=isinstance(ordinary[-1], AgentToolMessage),
        instruction_audit=ClientInstructionAudit(
            normalized_length=len(normalized_instructions),
            digest=digest,
        ),
    )


def serialize_client_instructions(content: str) -> str:
    return _xml_envelope(CLIENT_INSTRUCTIONS_TAG, content)


def serialize_tool_result(content: str) -> str:
    return _xml_envelope(CLIENT_TOOL_RESULT_TAG, content)


@lru_cache(maxsize=1)
def load_agent_context_prompt() -> str:
    path = Path(__file__).with_name("prompts") / "agent_context_v1.txt"
    return path.read_text(encoding="utf-8").strip()


def compose_agent_system_prompt(
    expert_prompt: str,
    *,
    source_context: str = "",
) -> str:
    """Compose the sole provider system message in locked precedence order."""

    sections = [str(expert_prompt).strip(), load_agent_context_prompt()]
    if source_context.strip():
        sections.append(_trusted_source_envelope(source_context.strip()))
    return "\n\n".join(section for section in sections if section)


def _xml_envelope(tag: str, content: str) -> str:
    element = ElementTree.Element(tag, {"trust": "untrusted"})
    element.text = _xml_safe_text(content)
    return ElementTree.tostring(
        element,
        encoding="unicode",
        short_empty_elements=False,
    )


def _trusted_source_envelope(source_xml: str) -> str:
    """Preserve server-built SOURCE markup while validating its exact shape."""

    try:
        parsed = ElementTree.fromstring(f"<ROOT>{source_xml}</ROOT>")
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid trusted Agent source XML.") from exc
    if parsed.text and parsed.text.strip():
        raise ValueError("Trusted Agent source XML contains text outside SOURCE blocks.")
    outer = ElementTree.Element("GEEM_RAG_CONTEXT", {"trust": "untrusted"})
    for source in list(parsed):
        if source.tag != "SOURCE" or list(source):
            raise ValueError("Trusted Agent context may contain only flat SOURCE blocks.")
        if source.tail and source.tail.strip():
            raise ValueError("Trusted Agent source XML contains trailing text.")
        outer.append(source)
    if not list(outer):
        raise ValueError("Trusted Agent context contains no SOURCE blocks.")
    return ElementTree.tostring(
        outer,
        encoding="unicode",
        short_empty_elements=False,
    )


def _xml_safe_text(value: str) -> str:
    return "".join(
        character if _valid_xml_character(ord(character)) else "\N{REPLACEMENT CHARACTER}"
        for character in value
    )


def _valid_xml_character(codepoint: int) -> bool:
    return (
        codepoint in {0x09, 0x0A, 0x0D}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _normalize_instruction_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _digest_key(settings: Settings, supplied: str | bytes | None) -> bytes:
    raw: str | bytes
    if supplied is not None:
        raw = supplied
    else:
        effective = getattr(settings, "effective_api_key_hash_pepper", "")
        raw = effective() if callable(effective) else effective
    if isinstance(raw, bytes):
        return raw
    return str(raw).encode("utf-8")


def _positive_setting(settings: Settings, name: str, fallback: int) -> int:
    try:
        value = int(getattr(settings, name, fallback))
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _transcript_error(message: str, param: str) -> AgentProtocolError:
    return AgentProtocolError(
        message,
        code="agent_invalid_tool_transcript",
        param=param,
    )


__all__ = [
    "ClientInstructionAudit",
    "NormalizedAgentMessages",
    "compose_agent_system_prompt",
    "load_agent_context_prompt",
    "normalize_agent_messages",
    "serialize_client_instructions",
    "serialize_tool_result",
]
