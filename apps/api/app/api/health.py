from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.storage.minio_storage import MinioObjectStorage

router = APIRouter(prefix="/api/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {}
    ok = True

    # PostgreSQL
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        finally:
            db.close()
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"
        ok = False

    # Redis
    try:
        r = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        ok = False

    # Qdrant
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=5, check_compatibility=False)
        client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as exc:
        checks["qdrant"] = f"error: {exc}"
        ok = False

    # MinIO
    try:
        storage = MinioObjectStorage(settings)
        storage.ensure_bucket()
        checks["minio"] = "ok"
    except Exception as exc:
        checks["minio"] = f"error: {exc}"
        ok = False

    # OpenRouter status is informational only
    checks["openrouter"] = "configured" if settings.openrouter_api_key else "missing_key"

    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if ok else "degraded", "checks": checks},
    )
