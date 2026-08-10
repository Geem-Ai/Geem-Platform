from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.api.schemas import JobResponse, QueryRequest, QueryResponse, Citation
from app.core.errors import AppError, ErrorCategory
from app.db.models import IngestionJob
from app.db.session import SessionLocal, get_db
from app.rag.service import RagService

router = APIRouter(prefix="/api", tags=["query"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/query", response_model=QueryResponse)
def query(body: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    svc = RagService(db)
    result = svc.query(body.question, document_ids=body.document_ids, top_k=body.top_k)
    return QueryResponse(
        answer=result["answer"],
        insufficient_context=result["insufficient_context"],
        citations=[Citation(**c) for c in result["citations"]],
        model=result["model"],
        general_answer=result.get("general_answer"),
        used_general_knowledge=bool(result.get("used_general_knowledge")),
        general_model=result.get("general_model"),
    )


@router.post("/query/stream")
async def query_stream(body: QueryRequest) -> StreamingResponse:
    def generate() -> Iterator[str]:
        db = SessionLocal()
        try:
            svc = RagService(db)
            for item in svc.query_stream(
                body.question,
                document_ids=body.document_ids,
                top_k=body.top_k,
            ):
                yield _sse(item["event"], item["data"])
        except AppError as exc:
            yield _sse(
                "error",
                {
                    "error": exc.category.value,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except Exception as exc:  # noqa: BLE001 — surface to client SSE
            yield _sse("error", {"error": "generation_failed", "message": str(exc)})
        finally:
            db.close()

    return StreamingResponse(
        iterate_in_threadpool(generate()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(IngestionJob, job_id)
    if not job:
        raise AppError(ErrorCategory.NOT_FOUND, "Job not found")
    return JobResponse(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        total_pages=job.total_pages,
        processed_pages=job.processed_pages,
        failed_pages=job.failed_pages,
        current_stage=job.current_stage,
        last_error=job.last_error,
    )
