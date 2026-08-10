from __future__ import annotations

import base64
import hashlib
import logging
import re
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.core.types import ParsedPage
from app.openrouter.client import OpenRouterClient

logger = logging.getLogger(__name__)


class OpenRouterDocumentParser:
    def __init__(
        self,
        client: OpenRouterClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(self.settings)

    def parse_page(
        self,
        page_pdf_bytes: bytes,
        filename: str,
        page_number: int,
    ) -> ParsedPage:
        b64 = base64.b64encode(page_pdf_bytes).decode("ascii")
        data_url = f"data:application/pdf;base64,{b64}"
        payload = {
            "model": self.settings.openrouter_pdf_trigger_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Parse the attached document page. No summary is required.",
                        },
                        {
                            "type": "file",
                            "file": {
                                "filename": filename,
                                "file_data": data_url,
                            },
                        },
                    ],
                }
            ],
            "plugins": [
                {
                    "id": "file-parser",
                    "pdf": {"engine": self.settings.openrouter_pdf_engine},
                }
            ],
            "provider": self.client.provider_preferences(),
        }

        body, meta, status = self.client.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=180.0,
        )

        annotations = self._extract_annotations(body)
        if not annotations and status >= 400:
            # Try error metadata for successful parse + failed generation
            annotations = self._extract_annotations_from_error(body)

        if not annotations:
            category = ErrorCategory.PARSER_RATE_LIMITED if status == 429 else ErrorCategory.PARSER_FAILED
            raise AppError(
                category,
                f"No file annotations returned for page {page_number}",
                details={"status": status, "openrouter_id": meta.get("openrouter_id")},
                retryable=status in {429, 500, 502, 503, 504, 529},
            )

        raw_markdown = self._annotations_to_markdown(annotations)
        plain_text = self._markdown_to_plain(raw_markdown)
        parser = f"openrouter:{self.settings.openrouter_pdf_engine}"
        parser_hash = hashlib.sha256(raw_markdown.encode("utf-8")).hexdigest()

        return ParsedPage(
            page_number=page_number,
            raw_markdown=raw_markdown,
            plain_text=plain_text,
            parser=parser,
            parser_hash=parser_hash,
            metadata={
                "openrouter_id": meta.get("openrouter_id"),
                "model": meta.get("model"),
                "usage": meta.get("usage"),
                "request_id": meta.get("request_id"),
                "latency_ms": meta.get("latency_ms"),
            },
        )

    def _extract_annotations(self, body: dict[str, Any] | None) -> list[Any]:
        if not body:
            return []
        choices = body.get("choices") or []
        annotations: list[Any] = []
        for choice in choices:
            message = choice.get("message") or {}
            anns = message.get("annotations") or []
            annotations.extend(anns)
            # Some responses nest file annotations under content parts
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("annotations"):
                        annotations.extend(part["annotations"])
        if not annotations and "file_annotations" in body:
            annotations = body["file_annotations"] or []
        return annotations

    def _extract_annotations_from_error(self, body: dict[str, Any] | None) -> list[Any]:
        if not body:
            return []
        error = body.get("error") or {}
        meta = error.get("metadata") or {}
        if "file_annotations" in meta:
            return meta["file_annotations"] or []
        if "file_annotations" in error:
            return error["file_annotations"] or []
        if "file_annotations" in body:
            return body["file_annotations"] or []
        return self._extract_annotations(body)

    def _annotations_to_markdown(self, annotations: list[Any]) -> str:
        parts: list[str] = []
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            # OpenRouter file-parser annotation shapes vary
            if ann.get("type") in {"file", "file_citation", "file_content"} or "file" in ann:
                file_obj = ann.get("file") or ann
                content = (
                    file_obj.get("content")
                    or file_obj.get("text")
                    or file_obj.get("markdown")
                    or ann.get("content")
                    or ann.get("text")
                    or ""
                )
                text = self._content_to_text(content)
                if text:
                    parts.append(text)
            elif "content" in ann:
                text = self._content_to_text(ann["content"])
                if text:
                    parts.append(text)
            elif "text" in ann:
                text = self._content_to_text(ann["text"])
                if text:
                    parts.append(text)
        return "\n\n".join(parts).strip()

    def _content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    chunks.append(
                        str(
                            item.get("text")
                            or item.get("content")
                            or item.get("markdown")
                            or ""
                        )
                    )
            return "\n".join(c for c in chunks if c).strip()
        if isinstance(content, dict):
            return self._content_to_text(
                content.get("text") or content.get("content") or content.get("markdown") or ""
            )
        return str(content).strip()

    def _markdown_to_plain(self, markdown: str) -> str:
        text = re.sub(r"</?file\b[^>]*>", " ", markdown, flags=re.IGNORECASE)
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"[#*_>`\[\]()]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
