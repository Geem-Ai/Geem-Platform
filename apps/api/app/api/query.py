from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import JobResponse, QueryRequest, QueryResponse, Citation
from app.core.errors import AppError, ErrorCategory
from app.db.models import IngestionJob
from app.db.session import get_db
from app.rag.service import RagService

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(body: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    svc = RagService(db)
    result = svc.query(body.question, document_ids=body.document_ids, top_k=body.top_k)
    return QueryResponse(
        answer=result["answer"],
        insufficient_context=result["insufficient_context"],
        citations=[Citation(**c) for c in result["citations"]],
        model=result["model"],
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
