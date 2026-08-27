from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from app.agent.constants import SUPPORTED_AGENT_FINISH_REASONS
from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentFunctionCall,
    AgentProviderResult,
    AgentProviderStreamEvent,
    AgentProviderToolCallDelta,
    AgentToolCall,
    AgentUsage,
)
from app.chat_attachments.payload import ChatTurnAttachment, build_user_message_content
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.openrouter.client import OpenRouterClient, OpenRouterStreamCancellation


ANSWER_SCHEMA_HINT = """
Return ONLY valid JSON with this schema:
{
  "answer_markdown": string,
  "citation_chunk_ids": string[],
  "insufficient_context": boolean
}
"""


def parse_answer_json_content(content: str) -> dict[str, Any]:
    """Normalize one model answer object, tolerating a surrounding JSON fence."""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, Mapping):
        raise ValueError("Model answer JSON must be an object.")
    return {
        "answer_markdown": data.get("answer_markdown") or data.get("answer") or "",
        "citation_chunk_ids": data.get("citation_chunk_ids") or [],
        "insufficient_context": bool(data.get("insufficient_context", False)),
    }


def _valid_no_tool_content(content: str | None, *, json_response: bool) -> bool:
    if not isinstance(content, str) or not content.strip():
        return False
    if not json_response:
        return True
    try:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return False
    if not isinstance(parsed, Mapping):
        return False
    answer = parsed.get("answer_markdown") or parsed.get("answer")
    citation_ids = parsed.get("citation_chunk_ids", [])
    insufficient_context = parsed.get("insufficient_context", False)
    return bool(
        isinstance(answer, str)
        and answer.strip()
        and isinstance(citation_ids, list)
        and all(isinstance(item, str) for item in citation_ids)
        and isinstance(insufficient_context, bool)
    )


def extract_partial_json_string(text: str, field: str) -> str | None:
    """Return the (possibly incomplete) JSON string value for `field`, or None."""
    pattern = f'"{field}"'
    idx = text.find(pattern)
    if idx < 0:
        return None
    colon = text.find(":", idx + len(pattern))
    if colon < 0:
        return None
    i = colon + 1
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    if i >= len(text) or text[i] != '"':
        return None
    i += 1
    out: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text):
                break
            nxt = text[i + 1]
            if nxt == "u":
                if i + 5 >= len(text):
                    break
                try:
                    out.append(chr(int(text[i + 2 : i + 6], 16)))
                except ValueError:
                    break
                i += 6
                continue
            escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


class OpenRouterChatProvider:
    def __init__(
        self,
        client: OpenRouterClient | None = None,
        settings: Settings | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(self.settings)
        self.system_prompt = system_prompt or ""

    def answer(
        self,
        question: str,
        context: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> dict:
        try:
            return self._call(
                self.settings.openrouter_chat_model,
                question,
                context,
                history=history,
                attachment=attachment,
            )
        except AppError:
            return self._call(
                self.settings.openrouter_chat_fallback_model,
                question,
                context,
                history=history,
                attachment=attachment,
            )

    def answer_stream(
        self,
        question: str,
        context: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield stream events: {"type":"delta"|"replace"|"done", ...}.

        Falls back to the secondary model if the primary stream fails before a
        completed ``done`` event (including after partial deltas were shown).
        """
        completed = False
        try:
            for event in self._call_stream(
                self.settings.openrouter_chat_model,
                question,
                context,
                history=history,
                attachment=attachment,
            ):
                if event.get("type") == "done":
                    completed = True
                yield event
        except AppError:
            if completed:
                raise
            # Clear any partial primary tokens before streaming the fallback.
            yield {"type": "replace", "text": ""}
            yield from self._call_stream(
                self.settings.openrouter_chat_fallback_model,
                question,
                context,
                history=history,
                attachment=attachment,
            )

    def complete_for_agent(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | Mapping[str, Any] = "none",
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        parallel_tool_calls: bool | None = None,
    ) -> AgentProviderResult:
        """Run one client-owned agent model round with pre-response fallback."""

        payload = self._agent_payload(
            self.settings.openrouter_chat_model,
            messages,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
            stream=False,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        )
        names = _agent_declared_names(tools)
        try:
            return self._call_agent(
                self.settings.openrouter_chat_model,
                payload,
                declared_names=names,
            )
        except AppError:
            fallback = self.settings.openrouter_chat_fallback_model
            payload["model"] = fallback
            return self._call_agent(fallback, payload, declared_names=names)

    def answer_with_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        system_prompt: str,
        tools: Sequence[Mapping[str, Any]],
        json_response: bool = False,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AgentProviderResult:
        """Run one Geem-owned MCP loop round on one preselected model.

        Unlike ``complete_for_agent`` this boundary never attempts a fallback:
        model selection happens before the bounded turn reservation, parallel
        calls are disabled, and a provider failure consumes no hidden N+2 call.
        """

        selected = (model or "").strip()
        if not selected:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "A reviewed tool-capable model is required.",
            )
        payload = self._agent_payload(
            selected,
            messages,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice="auto",
            stream=False,
            temperature=None,
            top_p=None,
            max_tokens=max_tokens,
            parallel_tool_calls=False,
        )
        if json_response:
            payload["response_format"] = {"type": "json_object"}
        return self._call_agent(
            selected,
            payload,
            declared_names=_agent_declared_names(tools),
            timeout_seconds=timeout_seconds,
            max_attempts=1,
        )

    def answer_without_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        system_prompt: str,
        fallback_content: str,
        json_response: bool = False,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AgentProviderResult:
        """Run one fixed-model finalizer that can never return a tool call.

        Some upstream models emit function calls even when no functions are
        declared. This boundary explicitly disables tools and converts calls,
        truncated output, or malformed final content into caller-owned
        deterministic content. The provider's validated usage and identifiers
        remain attached so the rejected generation is still metered accurately.
        """

        selected = (model or "").strip()
        if not selected:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "A reviewed tool-capable model is required.",
            )
        if not isinstance(fallback_content, str) or not fallback_content.strip():
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "The no-tool finalizer requires deterministic fallback content.",
            )
        if json_response and not _valid_no_tool_content(
            fallback_content,
            json_response=True,
        ):
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "The no-tool finalizer fallback must match the answer schema.",
            )
        payload = self._agent_payload(
            selected,
            messages,
            system_prompt=system_prompt,
            tools=None,
            tool_choice="none",
            stream=False,
            temperature=None,
            top_p=None,
            max_tokens=max_tokens,
            parallel_tool_calls=None,
        )
        # `_agent_payload` normally emits a choice only alongside declarations.
        # Keep declarations absent while making the no-tool contract explicit.
        payload["tool_choice"] = "none"
        if json_response:
            payload["response_format"] = {"type": "json_object"}
        result = self._call_agent(
            selected,
            payload,
            declared_names=frozenset(),
            timeout_seconds=timeout_seconds,
            max_attempts=1,
            no_tool_fallback_content=fallback_content,
        )
        if _valid_no_tool_content(result.message.content, json_response=json_response):
            return result
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(
                content=fallback_content,
                tool_calls=None,
            ),
            finish_reason="stop",
            usage=result.usage,
            provider_model=result.provider_model,
            provider_request_id=result.provider_request_id,
            provider_completion_id=result.provider_completion_id,
        )

    def stream_for_agent(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | Mapping[str, Any] = "none",
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        parallel_tool_calls: bool | None = None,
        cancellation: OpenRouterStreamCancellation | None = None,
    ) -> Iterator[AgentProviderStreamEvent]:
        """Yield provider-neutral events; fallback is forbidden after event one."""

        primary = self.settings.openrouter_chat_model
        payload = self._agent_payload(
            primary,
            messages,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
            stream=True,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        )
        names = _agent_declared_names(tools)
        emitted = False
        try:
            for event in self._call_agent_stream(
                primary,
                payload,
                declared_names=names,
                cancellation=cancellation,
            ):
                emitted = True
                yield event
        except AppError:
            if emitted or (cancellation is not None and cancellation.cancelled):
                raise
            fallback = self.settings.openrouter_chat_fallback_model
            payload["model"] = fallback
            yield from self._call_agent_stream(
                fallback,
                payload,
                declared_names=names,
                cancellation=cancellation,
            )

    def complete_for_agent_stream(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> Iterator[AgentProviderStreamEvent]:
        """Compatibility alias for callers that group Agent methods by prefix."""

        yield from self.stream_for_agent(messages, **kwargs)

    def _agent_payload(
        self,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None,
        tools: Sequence[Mapping[str, Any]] | None,
        tool_choice: str | Mapping[str, Any],
        stream: bool,
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
        parallel_tool_calls: bool | None,
    ) -> dict[str, Any]:
        resolved_system = self.system_prompt if system_prompt is None else system_prompt
        if not isinstance(resolved_system, str) or not resolved_system.strip():
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Agent provider requires a non-empty Geem system prompt.",
            )
        if not messages:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Agent provider requires a normalized client transcript.",
            )
        caller_messages: list[dict[str, Any]] = []
        for message in messages:
            copied = dict(message)
            if copied.get("role") not in {"user", "assistant", "tool"}:
                raise AppError(
                    ErrorCategory.GENERATION_FAILED,
                    "Agent provider input contains an invalid or privileged role.",
                )
            caller_messages.append(copied)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": resolved_system,
                },
                *caller_messages,
            ],
            "provider": self.client.provider_preferences(),
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = (
                dict(tool_choice) if isinstance(tool_choice, Mapping) else tool_choice
            )
        for key, value in (
            ("temperature", temperature),
            ("top_p", top_p),
            ("max_tokens", max_tokens),
            ("parallel_tool_calls", parallel_tool_calls),
        ):
            if value is not None:
                payload[key] = value
        return payload

    def _call_agent(
        self,
        model: str,
        payload: dict[str, Any],
        *,
        declared_names: frozenset[str],
        timeout_seconds: float | None = None,
        max_attempts: int = 5,
        no_tool_fallback_content: str | None = None,
    ) -> AgentProviderResult:
        body, meta, status = self.client.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=max(0.001, float(timeout_seconds or 120.0)),
            max_attempts=max(1, int(max_attempts)),
        )
        if status >= 400 or not isinstance(body, dict):
            raise _agent_provider_error(
                f"Agent generation failed with status {status}.",
                model=model,
                meta=meta,
                retryable=status in {429, 500, 502, 503, 504, 529},
            )
        return validate_agent_provider_response(
            body,
            declared_names=declared_names,
            meta=meta,
            fallback_model=model,
            no_tool_fallback_content=no_tool_fallback_content,
        )

    def _call_agent_stream(
        self,
        model: str,
        payload: dict[str, Any],
        *,
        declared_names: frozenset[str],
        cancellation: OpenRouterStreamCancellation | None = None,
    ) -> Iterator[AgentProviderStreamEvent]:
        content_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        ids: set[str] = set()
        mode: str | None = None
        finish_reason: str | None = None
        usage_raw: Any = None
        provider_model: str | None = None
        provider_request_id: str | None = None
        provider_completion_id: str | None = None
        started = False

        stream_kwargs: dict[str, Any] = {
            "json_body": payload,
            "timeout": 180.0,
        }
        if cancellation is not None and getattr(
            self.client, "supports_stream_cancellation", False
        ):
            stream_kwargs["cancellation"] = cancellation
        for chunk in self.client.stream(
            "POST",
            "/chat/completions",
            **stream_kwargs,
        ):
            if not isinstance(chunk, Mapping):
                raise _agent_provider_error("Invalid Agent stream chunk.", model=model)
            if isinstance(chunk.get("model"), str):
                provider_model = chunk["model"]
            if isinstance(chunk.get("_request_id"), str):
                provider_request_id = chunk["_request_id"]
            if isinstance(chunk.get("id"), str):
                provider_completion_id = chunk["id"]
            if chunk.get("usage") is not None:
                usage_raw = chunk.get("usage")

            choices = chunk.get("choices")
            if choices is None:
                choices = []
            if not isinstance(choices, list) or len(choices) > 1:
                raise _agent_provider_error("Invalid Agent stream choices.", model=model)
            if not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, Mapping):
                raise _agent_provider_error("Invalid Agent stream choice.", model=model)
            if finish_reason is not None:
                raise _agent_provider_error(
                    "Agent provider emitted choices after the terminal choice.", model=model
                )
            if choice.get("index") not in {None, 0}:
                raise _agent_provider_error("Invalid Agent stream choice index.", model=model)
            delta = choice.get("delta")
            if delta is None:
                delta = {}
            if not isinstance(delta, Mapping):
                raise _agent_provider_error("Invalid Agent stream delta.", model=model)
            if delta.get("role") not in {None, "assistant"}:
                raise _agent_provider_error("Invalid Agent stream role.", model=model)

            buffered: list[AgentProviderStreamEvent] = []
            content = delta.get("content")
            if content is not None:
                if not isinstance(content, str):
                    raise _agent_provider_error("Agent content delta must be text.", model=model)
                if content:
                    if mode == "tool":
                        raise _agent_provider_error(
                            "Agent provider mixed text and tool-call output.", model=model
                        )
                    mode = "text"
                    content_parts.append(content)
                    buffered.append(
                        AgentProviderStreamEvent(type="content_delta", content=content)
                    )

            raw_tool_deltas = delta.get("tool_calls")
            if raw_tool_deltas is not None:
                if not isinstance(raw_tool_deltas, list):
                    raise _agent_provider_error("Invalid tool-call delta list.", model=model)
                for raw_delta in raw_tool_deltas:
                    event = _consume_agent_tool_delta(
                        raw_delta,
                        calls=calls,
                        ids=ids,
                        declared_names=declared_names,
                        model=model,
                    )
                    if mode == "text":
                        raise _agent_provider_error(
                            "Agent provider mixed text and tool-call output.", model=model
                        )
                    mode = "tool"
                    if event is not None:
                        buffered.append(event)

            raw_finish = choice.get("finish_reason")
            if raw_finish is not None:
                if raw_finish not in SUPPORTED_AGENT_FINISH_REASONS:
                    raise _agent_provider_error("Unsupported Agent finish reason.", model=model)
                if finish_reason is not None and raw_finish != finish_reason:
                    raise _agent_provider_error("Agent finish reason changed.", model=model)
                finish_reason = raw_finish

            if not started:
                started = True
                yield AgentProviderStreamEvent(type="start")
            yield from buffered

        if not started or finish_reason is None:
            raise _agent_provider_error("Incomplete Agent stream.", model=model)

        if mode == "tool":
            if finish_reason != "tool_calls" or set(calls) != set(range(len(calls))):
                raise _agent_provider_error("Invalid completed Agent tool stream.", model=model)
            tool_calls = [
                AgentToolCall(
                    id=calls[index]["id"],
                    type="function",
                    function=AgentFunctionCall(
                        name=calls[index]["name"],
                        arguments=calls[index]["arguments"],
                    ),
                )
                for index in range(len(calls))
            ]
            message = AgentAssistantResponseMessage(
                content=None,
                tool_calls=tool_calls,
            )
        else:
            if finish_reason == "tool_calls":
                raise _agent_provider_error("Tool finish without tool calls.", model=model)
            message = AgentAssistantResponseMessage(
                content="".join(content_parts),
                tool_calls=None,
            )
        result = AgentProviderResult(
            message=message,
            finish_reason=finish_reason,
            usage=_validated_agent_usage(usage_raw, model=model),
            provider_model=provider_model or model,
            provider_request_id=provider_request_id,
            provider_completion_id=provider_completion_id,
        )
        yield AgentProviderStreamEvent(type="done", result=result)

    def answer_general(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> dict:
        """Non-RAG general-knowledge answer (plain markdown)."""
        primary = self._general_model()
        try:
            return self._call_text(primary, question, history=history, attachment=attachment)
        except AppError:
            return self._call_text(
                self.settings.openrouter_chat_fallback_model,
                question,
                history=history,
                attachment=attachment,
            )

    def answer_general_stream(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream a plain-markdown general-knowledge answer."""
        primary = self._general_model()
        completed = False
        try:
            for event in self._call_text_stream(
                primary, question, history=history, attachment=attachment
            ):
                if event.get("type") == "done":
                    completed = True
                yield event
        except AppError:
            if completed:
                raise
            yield {"type": "replace", "text": ""}
            yield from self._call_text_stream(
                self.settings.openrouter_chat_fallback_model,
                question,
                history=history,
                attachment=attachment,
            )

    def _general_model(self) -> str:
        return (self.settings.openrouter_general_model or "").strip() or self.settings.openrouter_chat_model

    def _payload(
        self,
        model: str,
        question: str,
        context: str,
        *,
        stream: bool,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        for turn in history or []:
            role = (turn.get("role") or "").strip()
            content = turn.get("content") or ""
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        prompt_text = (
            f"{ANSWER_SCHEMA_HINT}\n\n"
            f"SOURCES:\n{context}\n\n"
            f"QUESTION:\n{question}"
        )
        messages.append(
            {
                "role": "user",
                "content": build_user_message_content(prompt_text, attachment),
            }
        )
        return {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "stream": stream,
            "provider": self.client.provider_preferences(),
            **({"stream_options": {"include_usage": True}} if stream else {}),
        }

    def _text_payload(
        self,
        model: str,
        question: str,
        *,
        stream: bool,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        for turn in history or []:
            role = (turn.get("role") or "").strip()
            content = turn.get("content") or ""
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": build_user_message_content(question, attachment),
            }
        )
        return {
            "model": model,
            "messages": messages,
            "stream": stream,
            "provider": self.client.provider_preferences(),
            **({"stream_options": {"include_usage": True}} if stream else {}),
        }

    def _call_text(
        self,
        model: str,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> dict:
        payload = self._text_payload(
            model, question, stream=False, history=history, attachment=attachment
        )
        payload.pop("stream", None)
        body, meta, status = self.client.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=120.0,
        )
        if status >= 400 or not body:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                f"General chat generation failed with status {status}",
                details={"model": model, "openrouter_id": (meta or {}).get("openrouter_id")},
                retryable=status in {429, 500, 502, 503, 504, 529},
            )
        choices = body.get("choices") or []
        if not choices:
            raise AppError(ErrorCategory.GENERATION_FAILED, "No choices in general chat response")
        content = (choices[0].get("message", {}) or {}).get("content") or ""
        return {
            "answer_markdown": content.strip(),
            "model": body.get("model") or model,
            "prompt_version": self.settings.general_prompt_version,
            "_meta": {
                "openrouter_id": meta.get("openrouter_id"),
                "usage": meta.get("usage"),
                "request_id": meta.get("request_id"),
            },
        }

    def _call_text_stream(
        self,
        model: str,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> Iterator[dict[str, Any]]:
        payload = self._text_payload(
            model, question, stream=True, history=history, attachment=attachment
        )
        buffer = ""
        resolved_model = model
        request_id: str | None = None
        openrouter_id: str | None = None
        usage: Any = None
        for chunk in self.client.stream(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=180.0,
        ):
            request_id = chunk.get("_request_id") or request_id
            if chunk.get("model"):
                resolved_model = chunk["model"]
            if chunk.get("id"):
                openrouter_id = chunk["id"]
            if chunk.get("usage"):
                usage = chunk["usage"]

            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content") or ""
            if not piece and not buffer:
                message = choices[0].get("message") or {}
                piece = message.get("content") or ""
            if not piece:
                continue
            buffer += piece
            yield {"type": "delta", "text": piece}

        if not buffer.strip():
            raise AppError(ErrorCategory.GENERATION_FAILED, "Empty streamed general chat response")

        yield {
            "type": "done",
            "result": {
                "answer_markdown": buffer.strip(),
                "model": resolved_model,
                "prompt_version": self.settings.general_prompt_version,
                "_meta": {
                    "openrouter_id": openrouter_id,
                    "usage": usage,
                    "request_id": request_id,
                },
            },
        }

    def _call(
        self,
        model: str,
        question: str,
        context: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> dict:
        payload = self._payload(
            model, question, context, stream=False, history=history, attachment=attachment
        )
        # Non-stream OpenRouter rejects stream=false being explicit on some providers; omit key
        payload.pop("stream", None)
        body, meta, status = self.client.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=120.0,
        )
        if status >= 400 or not body:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                f"Chat generation failed with status {status}",
                details={"model": model, "openrouter_id": (meta or {}).get("openrouter_id")},
                retryable=status in {429, 500, 502, 503, 504, 529},
            )
        choices = body.get("choices") or []
        if not choices:
            raise AppError(ErrorCategory.GENERATION_FAILED, "No choices in chat response")
        content = choices[0].get("message", {}).get("content") or ""
        parsed = self._parse_json_content(content)
        parsed["model"] = body.get("model") or model
        parsed["prompt_version"] = self.settings.prompt_version
        parsed["_meta"] = {
            "openrouter_id": meta.get("openrouter_id"),
            "usage": meta.get("usage"),
            "request_id": meta.get("request_id"),
        }
        return parsed

    def _call_stream(
        self,
        model: str,
        question: str,
        context: str,
        *,
        history: list[dict[str, str]] | None = None,
        attachment: ChatTurnAttachment | None = None,
    ) -> Iterator[dict[str, Any]]:
        payload = self._payload(
            model, question, context, stream=True, history=history, attachment=attachment
        )
        buffer = ""
        emitted = ""
        resolved_model = model
        request_id: str | None = None
        openrouter_id: str | None = None
        usage: Any = None
        for chunk in self.client.stream(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=180.0,
        ):
            request_id = chunk.get("_request_id") or request_id
            if chunk.get("model"):
                resolved_model = chunk["model"]
            if chunk.get("id"):
                openrouter_id = chunk["id"]
            if chunk.get("usage"):
                usage = chunk["usage"]

            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content") or ""
            # Only accept non-delta message.content when we have not streamed yet.
            # Appending a full message after deltas doubles the buffer and breaks JSON.
            if not piece and not buffer:
                message = choices[0].get("message") or {}
                piece = message.get("content") or ""
            if not piece:
                continue
            buffer += piece
            partial = extract_partial_json_string(buffer, "answer_markdown")
            if partial is None:
                continue
            if len(partial) > len(emitted):
                delta_text = partial[len(emitted) :]
                emitted = partial
                yield {"type": "delta", "text": delta_text}

        if not buffer.strip():
            raise AppError(ErrorCategory.GENERATION_FAILED, "Empty streamed chat response")

        parsed = self._parse_json_content(buffer)
        parsed["model"] = resolved_model
        parsed["prompt_version"] = self.settings.prompt_version
        parsed["_meta"] = {
            "openrouter_id": openrouter_id,
            "usage": usage,
            "request_id": request_id,
        }
        # Ensure UI has the full answer if partial extraction missed escapes/edge cases
        final_answer = parsed.get("answer_markdown") or ""
        if final_answer.startswith(emitted) and len(final_answer) > len(emitted):
            yield {"type": "delta", "text": final_answer[len(emitted) :]}
        elif final_answer != emitted and final_answer:
            yield {"type": "replace", "text": final_answer}
        yield {"type": "done", "result": parsed}

    def _parse_json_content(self, content: str) -> dict:
        try:
            return parse_answer_json_content(content)
        except (TypeError, ValueError) as exc:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Model did not return valid JSON",
            ) from exc


def validate_agent_provider_response(
    body: Mapping[str, Any],
    *,
    declared_names: frozenset[str],
    meta: Mapping[str, Any] | None = None,
    fallback_model: str | None = None,
    no_tool_fallback_content: str | None = None,
) -> AgentProviderResult:
    """Reject malformed provider output before it reaches the public protocol."""

    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise _agent_provider_error(
            "Agent provider must return exactly one choice.", model=fallback_model
        )
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise _agent_provider_error("Invalid Agent provider choice.", model=fallback_model)
    if choice.get("index") not in {None, 0}:
        raise _agent_provider_error("Invalid Agent provider choice index.", model=fallback_model)
    message = choice.get("message")
    finish_reason = choice.get("finish_reason")
    if not isinstance(message, Mapping) or message.get("role") != "assistant":
        raise _agent_provider_error("Invalid Agent assistant message.", model=fallback_model)
    if finish_reason not in SUPPORTED_AGENT_FINISH_REASONS:
        raise _agent_provider_error("Unsupported Agent finish reason.", model=fallback_model)

    metadata = meta or {}
    raw_usage = body.get("usage")
    if raw_usage is None:
        raw_usage = metadata.get("usage")
    usage = _validated_agent_usage(raw_usage, model=fallback_model)
    provider_model = body.get("model")
    provider_completion_id = body.get("id")
    resolved_provider_model = (
        provider_model if isinstance(provider_model, str) else fallback_model
    )
    provider_request_id = (
        metadata.get("request_id")
        if isinstance(metadata.get("request_id"), str)
        else None
    )
    resolved_completion_id = (
        provider_completion_id
        if isinstance(provider_completion_id, str)
        else metadata.get("openrouter_id")
        if isinstance(metadata.get("openrouter_id"), str)
        else None
    )

    raw_calls = message.get("tool_calls")
    legacy_function_call = message.get("function_call")
    invalid_no_tool_output = bool(
        no_tool_fallback_content is not None
        and not declared_names
        and (
            raw_calls is not None
            or legacy_function_call is not None
            or finish_reason != "stop"
            or not isinstance(message.get("content"), str)
        )
    )
    if invalid_no_tool_output:
        parsed_message = AgentAssistantResponseMessage(
            content=no_tool_fallback_content,
            tool_calls=None,
        )
        finish_reason = "stop"
    elif raw_calls is not None:
        if not isinstance(raw_calls, list) or not raw_calls:
            raise _agent_provider_error("Agent tool_calls must be non-empty.", model=fallback_model)
        if message.get("content") is not None or finish_reason != "tool_calls":
            raise _agent_provider_error(
                "Agent tool output has inconsistent content or finish reason.",
                model=fallback_model,
            )
        calls: list[AgentToolCall] = []
        ids: set[str] = set()
        for raw in raw_calls:
            if not isinstance(raw, Mapping):
                raise _agent_provider_error("Invalid Agent tool call.", model=fallback_model)
            function = raw.get("function")
            call_id = raw.get("id")
            if (
                not isinstance(call_id, str)
                or not call_id
                or call_id in ids
                or raw.get("type") != "function"
                or not isinstance(function, Mapping)
            ):
                raise _agent_provider_error(
                    "Invalid Agent tool call metadata.", model=fallback_model
                )
            name = function.get("name")
            arguments = function.get("arguments")
            if name not in declared_names or not isinstance(arguments, str):
                raise _agent_provider_error(
                    "Agent provider returned an undeclared or malformed function call.",
                    model=fallback_model,
                )
            ids.add(call_id)
            try:
                calls.append(
                    AgentToolCall(
                        id=call_id,
                        type="function",
                        function=AgentFunctionCall(name=name, arguments=arguments),
                    )
                )
            except Exception as exc:
                raise _agent_provider_error(
                    "Agent provider returned invalid tool-call data.", model=fallback_model
                ) from exc
        parsed_message = AgentAssistantResponseMessage(
            content=None,
            tool_calls=calls,
        )
    else:
        content = message.get("content")
        if not isinstance(content, str) or finish_reason == "tool_calls":
            raise _agent_provider_error(
                "Agent text output has inconsistent content or finish reason.",
                model=fallback_model,
            )
        parsed_message = AgentAssistantResponseMessage(content=content, tool_calls=None)

    return AgentProviderResult(
        message=parsed_message,
        finish_reason=finish_reason,
        usage=usage,
        provider_model=resolved_provider_model,
        provider_request_id=provider_request_id,
        provider_completion_id=resolved_completion_id,
    )


def _consume_agent_tool_delta(
    raw_delta: Any,
    *,
    calls: dict[int, dict[str, str]],
    ids: set[str],
    declared_names: frozenset[str],
    model: str,
) -> AgentProviderStreamEvent | None:
    if not isinstance(raw_delta, Mapping):
        raise _agent_provider_error("Invalid Agent tool-call delta.", model=model)
    index = raw_delta.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise _agent_provider_error("Invalid Agent tool-call index.", model=model)
    function = raw_delta.get("function")
    if function is None:
        function = {}
    if not isinstance(function, Mapping):
        raise _agent_provider_error("Invalid Agent function delta.", model=model)

    call_id = raw_delta.get("id")
    call_type = raw_delta.get("type")
    name = function.get("name")
    arguments = function.get("arguments")
    if arguments is not None and not isinstance(arguments, str):
        raise _agent_provider_error("Agent argument delta must be text.", model=model)

    first = index not in calls
    if first:
        if (
            not isinstance(call_id, str)
            or not call_id
            or call_id in ids
            or call_type != "function"
            or not isinstance(name, str)
            or name not in declared_names
        ):
            raise _agent_provider_error(
                "The first Agent tool delta lacks valid function metadata.", model=model
            )
        calls[index] = {
            "id": call_id,
            "name": name,
            "arguments": arguments or "",
        }
        ids.add(call_id)
        parsed = AgentProviderToolCallDelta(
            index=index,
            id=call_id,
            type="function",
            name=name,
            arguments=arguments,
        )
    else:
        current = calls[index]
        if call_id is not None and call_id != current["id"]:
            raise _agent_provider_error("Agent tool-call id changed.", model=model)
        if call_type is not None and call_type != "function":
            raise _agent_provider_error("Agent tool-call type changed.", model=model)
        if name is not None and name != current["name"]:
            raise _agent_provider_error("Agent function name changed.", model=model)
        if arguments is not None:
            current["arguments"] += arguments
        else:
            return None
        parsed = AgentProviderToolCallDelta(index=index, arguments=arguments)
    return AgentProviderStreamEvent(type="tool_call_delta", tool_call=parsed)


def _agent_declared_names(
    tools: Sequence[Mapping[str, Any]] | None,
) -> frozenset[str]:
    names: set[str] = set()
    for tool in tools or ():
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if isinstance(function, Mapping) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return frozenset(names)


def _validated_agent_usage(raw: Any, *, model: str | None) -> AgentUsage:
    if not isinstance(raw, Mapping):
        raise _agent_provider_error("Agent provider omitted token usage.", model=model)
    values: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _agent_provider_error("Agent provider returned invalid token usage.", model=model)
        values[key] = value
    if values["total_tokens"] != values["prompt_tokens"] + values["completion_tokens"]:
        raise _agent_provider_error(
            "Agent provider returned inconsistent token usage.", model=model
        )
    return AgentUsage(**values)


def _agent_provider_error(
    message: str,
    *,
    model: str | None = None,
    meta: Mapping[str, Any] | None = None,
    retryable: bool = False,
) -> AppError:
    details: dict[str, Any] = {}
    if model:
        details["model"] = model
    if meta and isinstance(meta.get("openrouter_id"), str):
        details["openrouter_id"] = meta["openrouter_id"]
    return AppError(
        ErrorCategory.GENERATION_FAILED,
        message,
        details=details or None,
        retryable=retryable,
    )


__all__ = [
    "OpenRouterChatProvider",
    "extract_partial_json_string",
    "validate_agent_provider_response",
]
