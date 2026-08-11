from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, health, query
from app.common.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.errors import HTTP_STATUS_BY_CATEGORY, AppError
from app.core.logging import setup_logging
from app.conversations.router import router as conversations_router
from app.experts.router import router as experts_router
from app.identity.router import router as auth_router
from app.platform_admin.router import router as platform_router
from app.workspaces.router import router as workspaces_router

setup_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Geem — Arabic-first AI workspace API",
)


def _local_cors_origin_regex() -> str | None:
    """Allow http(s)://{optional-subdomain.}{APP_ROOT_DOMAIN}{:port} in local/dev only.

    Never enabled in production — production must use an explicit CORS_ORIGINS allowlist
    (or same-origin reverse proxy). Regex is anchored to APP_ROOT_DOMAIN, not a bare suffix.
    """
    if not settings.is_local:
        return None
    root = settings.app_root_domain.strip().lower().lstrip(".")
    if not root or root in {"localhost", "127.0.0.1"}:
        return None
    escaped = re.escape(root)
    return rf"^https?://([a-z0-9-]+\.)?{escaped}(:\d+)?$"


_cors_kwargs: dict = {
    "allow_origins": settings.cors_origin_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
_regex = _local_cors_origin_regex()
if _regex:
    _cors_kwargs["allow_origin_regex"] = _regex

app.add_middleware(CORSMiddleware, **_cors_kwargs)
app.add_middleware(RequestContextMiddleware)

app.include_router(health.router)
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(experts_router)
app.include_router(conversations_router)
app.include_router(platform_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    code = HTTP_STATUS_BY_CATEGORY.get(exc.category.value, 500)
    if code == 500 and (
        exc.category.value.endswith("_failed") or "rate" in exc.category.value
    ):
        code = 502
    return JSONResponse(
        status_code=code,
        content={
            "error": exc.category.value,
            "code": exc.category.value,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "auth_required": settings.auth_required,
    }
