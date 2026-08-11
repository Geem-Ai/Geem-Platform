from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, health, query
from app.common.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging

setup_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Geem — Arabic-first AI workspace API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    status_map = {
        "not_found": 404,
        "conflict": 409,
        "validation": 422,
        "unauthorized": 401,
        "forbidden": 403,
        "quota_exceeded": 429,
        "billing_required": 402,
        "invalid_pdf": 400,
        "encrypted_pdf": 400,
    }
    code = status_map.get(exc.category.value, 500)
    if exc.category.value.endswith("_failed") or "rate" in exc.category.value:
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
