from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.openrouter.client import OpenRouterClient
from app.usage.accounting import merge_token_usage, parse_provider_usage

logger = logging.getLogger(__name__)


class OpenRouterEmbeddingProvider:
    def __init__(
        self,
        client: OpenRouterClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(self.settings)
        self.last_meta: dict[str, Any] | None = None

    @property
    def model_id(self) -> str:
        return self.settings.openrouter_embedding_model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            self.last_meta = None
            return []
        batch_size = self.settings.embedding_batch_size
        vectors: list[list[float]] = []
        merged_usage: dict[str, Any] | None = None
        last_request_id: str | None = None
        i = 0
        current_batch_size = batch_size
        while i < len(texts):
            batch = texts[i : i + current_batch_size]
            try:
                vectors.extend(self._embed_batch(batch))
                parsed = parse_provider_usage((self.last_meta or {}).get("usage"))
                if parsed is not None:
                    merged_usage = merge_token_usage(merged_usage, parsed)
                last_request_id = (self.last_meta or {}).get("request_id") or last_request_id
                i += current_batch_size
                current_batch_size = batch_size
            except AppError as exc:
                if "token" in exc.message.lower() or "too large" in exc.message.lower():
                    if current_batch_size <= 1:
                        raise
                    current_batch_size = max(1, current_batch_size // 2)
                    continue
                raise
        self.last_meta = {
            "usage": merged_usage,
            "request_id": last_request_id,
            "model": self.model_id,
        }
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": texts,
            "provider": self.client.provider_preferences(),
        }
        body, meta, status = self.client.request(
            "POST",
            "/embeddings",
            json_body=payload,
            timeout=120.0,
        )
        if status >= 400 or not body:
            self.last_meta = None
            raise AppError(
                ErrorCategory.EMBEDDING_FAILED,
                f"Embedding request failed with status {status}",
                details={"openrouter_id": (meta or {}).get("openrouter_id")},
                retryable=status in {429, 500, 502, 503, 504, 529},
            )
        data = body.get("data") or []
        # Ensure order by index
        data = sorted(data, key=lambda d: d.get("index", 0))
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts):
            self.last_meta = None
            raise AppError(
                ErrorCategory.EMBEDDING_FAILED,
                f"Expected {len(texts)} embeddings, got {len(vectors)}",
            )
        self.last_meta = {
            "usage": (meta or {}).get("usage") or (body or {}).get("usage"),
            "request_id": (meta or {}).get("request_id"),
            "model": (meta or {}).get("model") or (body or {}).get("model") or self.model_id,
        }
        return vectors
