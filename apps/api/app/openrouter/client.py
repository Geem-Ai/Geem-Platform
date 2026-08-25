from __future__ import annotations

import json
import logging
import random
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.observability.tracing import start_span

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}
BACKOFF_SECONDS = [2.0, 5.0, 15.0, 45.0]


class OpenRouterStreamCancellation:
    """Thread-safe ownership handle for one active streaming response.

    Agent SSE iteration runs in a worker thread.  The ASGI task keeps this
    handle so a downstream disconnect can close the active httpx response and
    unblock a worker that is waiting for the next provider frame.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._closer: Callable[[], None] | None = None

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def bind(self, closer: Callable[[], None]) -> bool:
        """Bind the current response closer, or close it if already cancelled."""

        with self._lock:
            if self._cancelled:
                close_now = True
            else:
                self._closer = closer
                close_now = False
        if close_now:
            self._close(closer)
            return False
        return True

    def unbind(self, closer: Callable[[], None]) -> None:
        with self._lock:
            if self._closer is closer:
                self._closer = None

    def cancel(self) -> None:
        """Idempotently close the currently bound provider response."""

        with self._lock:
            self._cancelled = True
            closer = self._closer
            self._closer = None
        if closer is not None:
            self._close(closer)

    @staticmethod
    def _close(closer: Callable[[], None]) -> None:
        try:
            closer()
        except Exception:
            logger.exception("openrouter_stream_cancel_close_failed")


def _openrouter_span_name(path: str) -> str:
    lowered = (path or "").lower()
    if "embed" in lowered:
        return "openrouter.embed"
    if "rerank" in lowered:
        return "openrouter.rerank"
    if "ocr" in lowered or "pdf" in lowered:
        return "openrouter.ocr"
    if "audio" in lowered or "transcription" in lowered:
        return "openrouter.stt"
    return "openrouter.chat"


class OpenRouterClient:
    supports_stream_cancellation = True

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.openrouter_base_url.rstrip("/")
        self.api_key = self.settings.openrouter_api_key

    def _headers(self, request_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.app_url,
            "X-Title": "Geem",
            "X-Request-ID": request_id,
        }

    def provider_preferences(self) -> dict[str, Any]:
        return {
            "allow_fallbacks": self.settings.openrouter_allow_fallbacks,
            "data_collection": self.settings.openrouter_data_collection,
        }

    def stream(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        timeout: float = 180.0,
        cancellation: OpenRouterStreamCancellation | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield parsed OpenRouter SSE chunk objects from a streaming chat request."""
        if not self.api_key:
            raise AppError(ErrorCategory.VALIDATION, "OPENROUTER_API_KEY is not configured")

        request_id = str(uuid.uuid4())
        url = f"{self.base_url}{path}"
        started = time.perf_counter()
        try:
            with start_span(_openrouter_span_name(path)):
                with httpx.Client(timeout=timeout) as client:
                    with client.stream(
                        method,
                        url,
                        headers=self._headers(request_id),
                        json=json_body,
                    ) as response:
                        closer: Callable[[], None] | None = None
                        bound = True
                        if cancellation is not None:
                            closer = response.close
                            bound = cancellation.bind(closer)
                        try:
                            if not bound:
                                return
                            if response.status_code >= 400:
                                raise AppError(
                                    ErrorCategory.GENERATION_FAILED,
                                    f"OpenRouter stream failed with status {response.status_code}",
                                    details={
                                        "status": response.status_code,
                                        "request_id": request_id,
                                    },
                                    retryable=response.status_code in RETRYABLE_STATUS,
                                )

                            for line in response.iter_lines():
                                if not line:
                                    continue
                                if line.startswith(":"):
                                    continue
                                if not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if not data or data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                except json.JSONDecodeError as exc:
                                    raise AppError(
                                        ErrorCategory.GENERATION_FAILED,
                                        "OpenRouter returned malformed stream data.",
                                        details={"request_id": request_id},
                                        retryable=True,
                                    ) from exc
                                if not isinstance(chunk, dict):
                                    raise AppError(
                                        ErrorCategory.GENERATION_FAILED,
                                        "OpenRouter returned malformed stream data.",
                                        details={"request_id": request_id},
                                        retryable=True,
                                    )
                                chunk["_request_id"] = request_id
                                yield chunk
                        finally:
                            if cancellation is not None and closer is not None:
                                cancellation.unbind(closer)
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "OpenRouter stream timed out.",
                details={"request_id": request_id},
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "OpenRouter streaming transport failed.",
                details={"request_id": request_id},
                retryable=True,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "openrouter_stream",
            extra={
                "request_id": request_id,
                "provider": "openrouter",
                "latency_ms": latency_ms,
                "stage": path,
            },
        )

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
        last_status = 0
        last_body: dict[str, Any] | None = None

        for attempt in range(max_attempts):
            started = time.perf_counter()
            try:
                with start_span(_openrouter_span_name(path)):
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
                if attempt < max_attempts - 1:
                    delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    delay *= 0.5 + random.random()
                    time.sleep(delay)
                    continue
                raise AppError(
                    ErrorCategory.PARSER_FAILED,
                    "OpenRouter HTTP error",
                    retryable=True,
                ) from exc

        raise AppError(
            ErrorCategory.PARSER_FAILED,
            "OpenRouter request failed after retries",
            details={"status": last_status},
            retryable=True,
        )
