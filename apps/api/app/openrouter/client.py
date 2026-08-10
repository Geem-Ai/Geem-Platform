from __future__ import annotations

import logging
import random
import time
import uuid
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}
BACKOFF_SECONDS = [2.0, 5.0, 15.0, 45.0]


class OpenRouterClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.openrouter_base_url.rstrip("/")
        self.api_key = self.settings.openrouter_api_key

    def _headers(self, request_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.app_url,
            "X-Title": "ArabicRag",
            "X-Request-ID": request_id,
        }

    def provider_preferences(self) -> dict[str, Any]:
        return {
            "allow_fallbacks": self.settings.openrouter_allow_fallbacks,
            "data_collection": self.settings.openrouter_data_collection,
        }

    def request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        timeout: float = 120.0,
        max_attempts: int = 5,
    ) -> tuple[dict[str, Any] | None, dict[str, Any], int]:
        """Return (json_body_or_none, meta, status_code).

        On HTTP error with a JSON body, returns that body with the error status
        so callers can recover annotations from error metadata.
        """
        if not self.api_key:
            raise AppError(ErrorCategory.VALIDATION, "OPENROUTER_API_KEY is not configured")

        request_id = str(uuid.uuid4())
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        last_status = 0
        last_body: dict[str, Any] | None = None

        for attempt in range(max_attempts):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.request(
                        method,
                        url,
                        headers=self._headers(request_id),
                        json=json_body,
                    )
                latency_ms = int((time.perf_counter() - started) * 1000)
                last_status = response.status_code
                try:
                    body = response.json()
                except Exception:
                    body = None

                meta = {
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "status_code": response.status_code,
                    "openrouter_id": None,
                    "model": None,
                    "usage": None,
                }
                if isinstance(body, dict):
                    meta["openrouter_id"] = body.get("id")
                    meta["model"] = body.get("model")
                    meta["usage"] = body.get("usage")

                logger.info(
                    "openrouter_request",
                    extra={
                        "request_id": request_id,
                        "provider": "openrouter",
                        "model": meta.get("model"),
                        "latency_ms": latency_ms,
                        "attempt": attempt + 1,
                        "status": response.status_code,
                        "openrouter_id": meta.get("openrouter_id"),
                        "usage": meta.get("usage"),
                        "stage": path,
                    },
                )

                if response.status_code < 400:
                    return body if isinstance(body, dict) else {}, meta, response.status_code

                last_body = body if isinstance(body, dict) else None
                if response.status_code in RETRYABLE_STATUS and attempt < max_attempts - 1:
                    delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    delay *= 0.5 + random.random()
                    time.sleep(delay)
                    continue

                # Non-retryable or exhausted: return body for annotation recovery
                return last_body, meta, response.status_code

            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    delay *= 0.5 + random.random()
                    time.sleep(delay)
                    continue
                raise AppError(
                    ErrorCategory.PARSER_TIMEOUT,
                    "OpenRouter request timed out",
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    delay *= 0.5 + random.random()
                    time.sleep(delay)
                    continue
                raise AppError(
                    ErrorCategory.PARSER_FAILED,
                    f"OpenRouter HTTP error: {exc}",
                    retryable=True,
                ) from exc

        raise AppError(
            ErrorCategory.PARSER_FAILED,
            f"OpenRouter request failed after retries: {last_error}",
            details={"status": last_status},
            retryable=True,
        )
