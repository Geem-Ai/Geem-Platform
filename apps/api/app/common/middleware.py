from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.common.request_context import RequestContext, reset_request_context, set_request_context
from app.common.workspace_resolver import resolve_workspace_hint
from app.core.config import get_settings
from app.observability.request_id import sanitize_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a RequestContext for every HTTP request.

    Phase 1A: request_id + AUTH_REQUIRED + candidate workspace hint from Host /
    local X-Workspace-Slug. User/session and membership authorization are applied
    in FastAPI dependencies (trusted DB checks), not from hostname alone.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        request_id = sanitize_request_id(request.headers.get("X-Request-Id"))
        hint = resolve_workspace_hint(request, settings)
        ctx = RequestContext(
            request_id=request_id,
            auth_required=settings.auth_required,
            workspace_slug=hint.slug,
            workspace_id=hint.workspace_id,
            workspace_resolution=hint.source if hint.source != "none" else None,
        )
        token = set_request_context(ctx)
        request.state.request_id = request_id
        request.state.request_context = ctx
        request.state.workspace_hint = hint
        try:
            response = await call_next(request)
            response.headers.setdefault("X-Request-Id", request_id)
            return response
        finally:
            reset_request_context(token)
