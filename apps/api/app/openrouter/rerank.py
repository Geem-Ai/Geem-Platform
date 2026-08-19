from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.openrouter.client import OpenRouterClient
from app.observability.tracing import start_span


class OpenRouterRerankProvider:
    def __init__(
        self,
        client: OpenRouterClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(self.settings)
        self.last_meta: dict[str, Any] | None = None

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_n: int,
    ) -> list[dict]:
        if not candidates:
            self.last_meta = None
            return []

        with start_span("rag.rerank"):
            documents = []
            for c in candidates:
                documents.append(
                    {
                        "id": str(c.get("chunk_id") or c.get("id")),
                        "text": c.get("search_text") or c.get("canonical_text") or c.get("text") or "",
                    }
                )

            payload: dict[str, Any] = {
                "model": self.settings.openrouter_rerank_model,
                "query": query,
                "documents": [d["text"] for d in documents],
                "top_n": top_n,
                "provider": self.client.provider_preferences(),
            }
            body, meta, status = self.client.request(
                "POST",
                "/rerank",
                json_body=payload,
                timeout=60.0,
            )
            if status >= 400 or not body:
                self.last_meta = None
                raise AppError(
                    ErrorCategory.RERANK_FAILED,
                    f"Rerank request failed with status {status}",
                    details={"openrouter_id": (meta or {}).get("openrouter_id")},
                    retryable=status in {429, 500, 502, 503, 504, 529},
                )

            self.last_meta = {
                "usage": (meta or {}).get("usage") or (body or {}).get("usage"),
                "request_id": (meta or {}).get("request_id"),
                "model": (meta or {}).get("model")
                or (body or {}).get("model")
                or self.settings.openrouter_rerank_model,
            }

            results = body.get("results") or body.get("data") or []
            ranked: list[dict] = []
            for rank, item in enumerate(results[:top_n], start=1):
                idx = item.get("index")
                if idx is None:
                    continue
                if not (0 <= idx < len(candidates)):
                    continue
                candidate = dict(candidates[idx])
                candidate["rerank_score"] = item.get("relevance_score") or item.get("score")
                candidate["final_rank"] = rank
                ranked.append(candidate)
            return ranked
