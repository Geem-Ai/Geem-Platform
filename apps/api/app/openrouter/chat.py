from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.openrouter.client import OpenRouterClient


ANSWER_SCHEMA_HINT = """
Return ONLY valid JSON with this schema:
{
  "answer_markdown": string,
  "citation_chunk_ids": string[],
  "insufficient_context": boolean
}
"""


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
    ) -> dict:
        try:
            return self._call(
                self.settings.openrouter_chat_model,
                question,
                context,
                history=history,
            )
        except AppError:
            return self._call(
                self.settings.openrouter_chat_fallback_model,
                question,
                context,
                history=history,
            )

    def answer_stream(
        self,
        question: str,
        context: str,
        *,
        history: list[dict[str, str]] | None = None,
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
            )

    def answer_general(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict:
        """Non-RAG general-knowledge answer (plain markdown)."""
        primary = self._general_model()
        try:
            return self._call_text(primary, question, history=history)
        except AppError:
            return self._call_text(
                self.settings.openrouter_chat_fallback_model,
                question,
                history=history,
            )

    def answer_general_stream(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream a plain-markdown general-knowledge answer."""
        primary = self._general_model()
        completed = False
        try:
            for event in self._call_text_stream(primary, question, history=history):
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
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        for turn in history or []:
            role = (turn.get("role") or "").strip()
            content = turn.get("content") or ""
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{ANSWER_SCHEMA_HINT}\n\n"
                    f"SOURCES:\n{context}\n\n"
                    f"QUESTION:\n{question}"
                ),
            }
        )
        return {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "stream": stream,
            "provider": self.client.provider_preferences(),
        }

    def _text_payload(
        self,
        model: str,
        question: str,
        *,
        stream: bool,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        for turn in history or []:
            role = (turn.get("role") or "").strip()
            content = turn.get("content") or ""
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        return {
            "model": model,
            "messages": messages,
            "stream": stream,
            "provider": self.client.provider_preferences(),
        }

    def _call_text(
        self,
        model: str,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict:
        payload = self._text_payload(model, question, stream=False, history=history)
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
    ) -> Iterator[dict[str, Any]]:
        payload = self._text_payload(model, question, stream=True, history=history)
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
    ) -> dict:
        payload = self._payload(model, question, context, stream=False, history=history)
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
    ) -> Iterator[dict[str, Any]]:
        payload = self._payload(model, question, context, stream=True, history=history)
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
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Model did not return valid JSON",
            ) from exc
        return {
            "answer_markdown": data.get("answer_markdown") or data.get("answer") or "",
            "citation_chunk_ids": data.get("citation_chunk_ids") or [],
            "insufficient_context": bool(data.get("insufficient_context", False)),
        }
