from __future__ import annotations

import json
import re
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

    def answer(self, question: str, context: str) -> dict:
        try:
            return self._call(self.settings.openrouter_chat_model, question, context)
        except AppError:
            return self._call(self.settings.openrouter_chat_fallback_model, question, context)

    def _call(self, model: str, question: str, context: str) -> dict:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{ANSWER_SCHEMA_HINT}\n\n"
                        f"SOURCES:\n{context}\n\n"
                        f"QUESTION:\n{question}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "provider": self.client.provider_preferences(),
        }
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
