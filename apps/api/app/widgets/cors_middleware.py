"""Short-circuit CORS for public widget endpoints.

Global CORSMiddleware only allows Workspace SPA origins. Customer sites embedding
the widget send Origin headers that would otherwise fail preflight / hide errors.
This middleware:

- Answers OPTIONS for ``/api/public/widgets/{id}/…`` using the widget allowlist
- Adds ACAO on all responses (including AppError / validation failures) when the
  request Origin is allowed (empty allowlist = any Origin)
"""

from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.db.session import SessionLocal
from app.widgets.models import WidgetInstance, WidgetInstanceStatus
from app.widgets.origins import origin_allowed, request_origin

_PREFIX = "/api/public/widgets/"
_WIDGET_RE = re.compile(
    r"^/api/public/widgets/"
    r"(?P<widget_id>"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r")"
    r"/(?P<route>bootstrap|messages/stream|messages|tool-turns/status)/?$"
)

_PRIVATE_ROUTES = frozenset({"messages", "messages/stream", "tool-turns/status"})
_PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}

_ROUTE_RULES: dict[str, tuple[str, frozenset[str]]] = {
    "bootstrap": ("GET", frozenset()),
    "messages": ("POST", frozenset({"content-type"})),
    "messages/stream": ("POST", frozenset({"accept", "content-type"})),
    "tool-turns/status": (
        "POST",
        frozenset({"content-type", "x-geem-widget-session"}),
    ),
}

_CANONICAL_HEADER_NAMES = {
    "accept": "Accept",
    "content-type": "Content-Type",
    "x-geem-widget-session": "X-Geem-Widget-Session",
}


def _cors_headers(
    origin: str | None,
    *,
    method: str,
    allowed_headers: frozenset[str],
) -> dict[str, str]:
    headers = (
        {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": f"{method}, OPTIONS",
            "Access-Control-Max-Age": "86400",
        }
        if not origin
        else {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": f"{method}, OPTIONS",
            "Access-Control-Max-Age": "86400",
            "Vary": "Origin",
        }
    )
    if allowed_headers:
        headers["Access-Control-Allow-Headers"] = ", ".join(
            _CANONICAL_HEADER_NAMES[value] for value in sorted(allowed_headers)
        )
    return headers


def _resolve_cors_origin(
    widget_id: uuid.UUID,
    *,
    origin_header: str | None,
    referer: str | None,
) -> tuple[str | None, str]:
    """Return (acao_origin_or_none, status) where status is ok|deny|missing."""
    db = SessionLocal()
    try:
        row = db.get(WidgetInstance, widget_id)
        if row is None or row.status != WidgetInstanceStatus.ACTIVE.value:
            return None, "missing"
        allowlist = row.allowed_origins if isinstance(row.allowed_origins, list) else None
        req = request_origin(origin_header, referer)
        if not origin_allowed(allowlist, req):
            return None, "deny"
        return (req or origin_header), "ok"
    finally:
        db.close()


class PublicWidgetCorsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(_PREFIX):
            return await call_next(request)

        match = _WIDGET_RE.match(request.url.path)
        if match is None:
            if request.method == "OPTIONS":
                return Response(status_code=404)
            return await call_next(request)

        try:
            widget_id = uuid.UUID(match.group("widget_id"))
        except ValueError:
            # Do not let middleware path parsing turn an ordinary invalid path
            # into an uncaught 500 before FastAPI can return its normal 404/422.
            if request.method == "OPTIONS":
                return Response(status_code=404)
            return await call_next(request)
        route_name = match.group("route")
        route_method, allowed_headers = _ROUTE_RULES[route_name]
        origin_header = request.headers.get("origin")
        referer = request.headers.get("referer")
        acao, status = _resolve_cors_origin(
            widget_id, origin_header=origin_header, referer=referer
        )

        if request.method == "OPTIONS":
            if status == "missing":
                return Response(status_code=404)
            if status == "deny":
                return Response(status_code=403)
            requested_method = request.headers.get("access-control-request-method")
            if requested_method != route_method:
                return Response(status_code=405)
            requested_headers = {
                value.strip().lower()
                for value in request.headers.get(
                    "access-control-request-headers", ""
                ).split(",")
                if value.strip()
            }
            if not requested_headers.issubset(allowed_headers):
                return Response(status_code=403)
            return Response(
                status_code=204,
                headers=_cors_headers(
                    acao or origin_header,
                    method=route_method,
                    allowed_headers=allowed_headers,
                ),
            )

        response = await call_next(request)
        if route_name in _PRIVATE_ROUTES:
            # Apply on success and on validation/AppError responses.  Public
            # turn handles, signed session tokens, and visitor answers must not
            # be retained or replayed by a browser/intermediary cache.
            for key, value in _PRIVATE_NO_STORE_HEADERS.items():
                response.headers[key] = value
        if status == "ok":
            for key, value in _cors_headers(
                acao or origin_header,
                method=route_method,
                allowed_headers=allowed_headers,
            ).items():
                response.headers[key] = value
        return response
