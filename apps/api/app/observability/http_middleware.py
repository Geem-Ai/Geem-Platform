"""HTTP request spans via a pass-through ASGI wrapper (not BaseHTTPMiddleware)."""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.observability.attributes import attach_request_context, set_safe_attributes
from app.observability.setup import tracing_active
from app.observability.tracing import start_span
from opentelemetry.trace import Status, StatusCode


class ObservabilityHttpMiddleware:
    """Light ASGI wrapper. When tracing is inactive this is a direct pass-through."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not tracing_active():
            await self.app(scope, receive, send)
            return

        status_code = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status") or 0)
            await send(message)

        with start_span("http.request") as span:
            set_safe_attributes(span, {"http.method": scope.get("method", "")})
            await self.app(scope, receive, send_wrapper)
            route = scope.get("route")
            template = getattr(route, "path", None)
            if template:
                set_safe_attributes(span, {"http.route": template})
            if status_code:
                set_safe_attributes(span, {"http.status_code": status_code})
            attach_request_context(span)
            if status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
