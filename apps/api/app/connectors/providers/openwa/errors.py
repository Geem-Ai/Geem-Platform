"""OpenWA HTTP errors — never expose API keys or raw provider dumps to clients."""

from __future__ import annotations

from typing import Any

from app.connectors.sanitize import sanitize_error_message
from app.core.errors import AppError, ErrorCategory


class OpenWAClientError(AppError):
    """Mapped OpenWA HTTP failure."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        status_code: int | None = None,
        provider_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        safe_details: dict[str, Any] = dict(details or {})
        if status_code is not None:
            safe_details["status_code"] = status_code
        if provider_code:
            safe_details["provider_code"] = provider_code
        super().__init__(category, sanitize_error_message(message) or message, details=safe_details)


def map_openwa_http_error(
    *,
    status_code: int,
    body: Any,
    operation: str,
) -> OpenWAClientError:
    """Map OpenWA status/body to a safe Geem AppError."""
    provider_code: str | None = None
    message = f"OpenWA {operation} failed."
    if isinstance(body, dict):
        raw_code = body.get("code") or body.get("error") or body.get("errorCode")
        if isinstance(raw_code, str) and raw_code.strip():
            provider_code = raw_code.strip()[:128]
        for key in ("message", "error", "detail", "title"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                message = sanitize_error_message(val.strip()) or message
                break

    if status_code in {401, 403}:
        return OpenWAClientError(
            ErrorCategory.OPENWA_UNAUTHORIZED,
            "OpenWA rejected the configured API key.",
            status_code=status_code,
            provider_code=provider_code,
        )
    if status_code == 404:
        return OpenWAClientError(
            ErrorCategory.OPENWA_SESSION_NOT_FOUND,
            "OpenWA session was not found.",
            status_code=status_code,
            provider_code=provider_code,
        )
    if status_code == 409:
        if provider_code == "SESSION_NAME_TEARDOWN_PENDING":
            return OpenWAClientError(
                ErrorCategory.OPENWA_SESSION_CONFLICT,
                "OpenWA session teardown is still in progress. Retry shortly.",
                status_code=status_code,
                provider_code=provider_code,
            )
        return OpenWAClientError(
            ErrorCategory.OPENWA_SESSION_CONFLICT,
            message or "OpenWA session conflict.",
            status_code=status_code,
            provider_code=provider_code,
        )
    if status_code == 400:
        return OpenWAClientError(
            ErrorCategory.OPENWA_REQUEST_INVALID,
            message or "OpenWA rejected the request.",
            status_code=status_code,
            provider_code=provider_code,
        )
    if status_code == 504:
        return OpenWAClientError(
            ErrorCategory.OPENWA_TIMEOUT,
            "OpenWA request timed out.",
            status_code=status_code,
            provider_code=provider_code,
        )
    if status_code >= 500:
        return OpenWAClientError(
            ErrorCategory.OPENWA_UNAVAILABLE,
            "OpenWA is temporarily unavailable.",
            status_code=status_code,
            provider_code=provider_code,
        )
    return OpenWAClientError(
        ErrorCategory.OPENWA_REQUEST_INVALID,
        message,
        status_code=status_code,
        provider_code=provider_code,
    )
