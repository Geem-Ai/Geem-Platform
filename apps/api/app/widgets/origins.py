"""Origin allowlist helpers for Chat Widget public APIs."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.errors import AppError, ErrorCategory

_MAX_ORIGINS = 50


def normalize_origin(value: str) -> str:
    """Return canonical origin (scheme://host[:port]) or raise validation."""
    raw = (value or "").strip()
    if not raw:
        raise AppError(ErrorCategory.VALIDATION, "Origin must not be empty.")
    if "*" in raw:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Wildcard origins are not supported. Use exact https origins.",
        )
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise AppError(
            ErrorCategory.VALIDATION,
            "Origins must use http or https.",
        )
    if not parsed.hostname:
        raise AppError(ErrorCategory.VALIDATION, "Origin must include a host.")
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Origins must not include a path, query, or fragment.",
        )
    host = parsed.hostname.lower()
    if parsed.port:
        return f"{parsed.scheme}://{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def normalize_origins_list(values: list[str] | None) -> list[str] | None:
    """Normalize and dedupe; empty list becomes None (allow all)."""
    if values is None:
        return None
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not str(item).strip():
            continue
        origin = normalize_origin(str(item))
        if origin in seen:
            continue
        seen.add(origin)
        cleaned.append(origin)
        if len(cleaned) > _MAX_ORIGINS:
            raise AppError(
                ErrorCategory.VALIDATION,
                f"At most {_MAX_ORIGINS} allowed origins.",
            )
    return cleaned or None


def request_origin(origin_header: str | None, referer: str | None) -> str | None:
    """Extract origin from Origin header, else Referer."""
    if origin_header and origin_header.strip():
        try:
            return normalize_origin(origin_header.strip())
        except AppError:
            return origin_header.strip().rstrip("/")
    if referer and referer.strip():
        parsed = urlparse(referer.strip())
        if parsed.scheme and parsed.hostname:
            try:
                return normalize_origin(
                    f"{parsed.scheme}://{parsed.hostname}"
                    + (f":{parsed.port}" if parsed.port else "")
                )
            except AppError:
                return None
    return None


def origin_allowed(allowed_origins: list[str] | None, request_origin_value: str | None) -> bool:
    """Empty/null allowlist = allow any. Non-empty requires exact match."""
    if not allowed_origins:
        return True
    if not request_origin_value:
        return False
    try:
        candidate = normalize_origin(request_origin_value)
    except AppError:
        candidate = request_origin_value.rstrip("/")
    return candidate in {normalize_origin(o) for o in allowed_origins if o}
