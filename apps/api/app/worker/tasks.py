from __future__ import annotations

import logging
import uuid

from app.db.session import SessionLocal
from app.ingestion.pipeline import IngestionPipeline
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ingest_document", bind=True, max_retries=3)
def ingest_document(self, document_id: str, mode: str = "full") -> dict:
    from app.core.errors import AppError

    db = SessionLocal()
    try:
        pipeline = IngestionPipeline(db)
        pipeline.run(uuid.UUID(document_id), mode=mode)
        return {"document_id": document_id, "status": "ready"}
    except AppError as exc:
        logger.exception("ingest_task_failed", extra={"document_id": document_id})
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30) from exc
        return {"document_id": document_id, "status": "failed", "error": str(exc)}
    except Exception as exc:
        logger.exception("ingest_task_failed", extra={"document_id": document_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30) from exc
        return {"document_id": document_id, "status": "failed", "error": str(exc)}
    finally:
        db.close()


def enqueue_ingest(document_id: str, mode: str = "full") -> str:
    result = ingest_document.delay(document_id, mode=mode)
    return result.id
