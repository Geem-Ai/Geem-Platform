from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, health, query
from app.api.v1.router import router as public_v1_router
from app.common.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.errors import HTTP_STATUS_BY_CATEGORY, AppError
from app.core.logging import setup_logging
from app.conversations.router import router as conversations_router
from app.experts.router import router as experts_router
from app.identity.router import router as auth_router
from app.platform_admin.router import router as platform_router
from app.billing.router import router as subscription_router
from app.billing.checkout_router import router as billing_router
from app.entitlements.router import router as entitlements_router
from app.usage.router import router as usage_router
from app.workspaces.router import router as workspaces_router
from app.api_keys.router import router as api_keys_router

setup_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Geem — Arabic-first AI workspace API",
)


_cors_kwargs: dict = {
    "allow_origins": settings.cors_origin_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
_regex = settings.local_spa_origin_regex()
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
app.include_router(subscription_router)
app.include_router(billing_router)
app.include_router(entitlements_router)
app.include_router(usage_router)
app.include_router(api_keys_router)
app.include_router(public_v1_router)
app.include_router(platform_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    code = HTTP_STATUS_BY_CATEGORY.get(exc.category.value, 500)
    if code == 500 and (
        exc.category.value.endswith("_failed") or "rate" in exc.category.value
    ):
        code = 502
    payload: dict = {
        "error": exc.category.value,
        "code": exc.category.value,
        "message": exc.message,
        "details": exc.details,
    }
    if isinstance(exc.details, dict):
        for key in ("metric", "limit", "used", "remaining", "retry_after"):
            if key in exc.details:
                payload[key] = exc.details[key]
    return JSONResponse(status_code=code, content=payload, headers=exc.headers or None)


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "auth_required": settings.auth_required,
    }
