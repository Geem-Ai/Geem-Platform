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
    r"(?P<widget_id>[0-9a-fA-F-]{36})"
    r"/(bootstrap|messages)/?$"
)


def _cors_headers(origin: str | None) -> dict[str, str]:
    if not origin:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        }
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
    }


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

        widget_id = uuid.UUID(match.group("widget_id"))
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
            return Response(status_code=204, headers=_cors_headers(acao or origin_header))

        response = await call_next(request)
        if status == "ok":
            for key, value in _cors_headers(acao or origin_header).items():
                response.headers[key] = value
        return response
