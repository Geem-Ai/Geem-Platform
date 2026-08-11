from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.common.request_context import RequestContext, reset_request_context, set_request_context
from app.core.config import get_settings


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a RequestContext for every HTTP request.

    Phase 0: populates request_id + AUTH_REQUIRED flag only.
    Phase 1+: resolve user/session and workspace from Host / headers / membership.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        ctx = RequestContext(
            request_id=request_id,
            auth_required=settings.auth_required,
        )
        token = set_request_context(ctx)
        request.state.request_id = request_id
        request.state.request_context = ctx
        try:
            response = await call_next(request)
            response.headers.setdefault("X-Request-Id", request_id)
            return response
        finally:
            reset_request_context(token)
