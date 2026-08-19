"""HTTP request spans that work with Starlette TestClient and BaseHTTPMiddleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.observability.attributes import attach_request_context, set_safe_attributes
from app.observability.setup import tracing_active
from app.observability.tracing import start_span
from opentelemetry.trace import Status, StatusCode


class ObservabilityHttpMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not tracing_active():
            return await call_next(request)
        with start_span("http.request") as span:
            set_safe_attributes(span, {"http.method": request.method})
            response = await call_next(request)
            route = request.scope.get("route")
            template = getattr(route, "path", None)
            if template:
                set_safe_attributes(span, {"http.route": template})
            set_safe_attributes(span, {"http.status_code": response.status_code})
            attach_request_context(span)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            return response
