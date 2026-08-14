from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.api.schemas import Citation, JobResponse, QueryRequest, QueryResponse
from app.common.public_model import public_model_id, public_model_or_none, redact_public_models
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document, IngestionJob
from app.db.session import SessionLocal, get_db
from app.documents.dependencies import DocumentAccess, get_document_access
from app.experts.query_service import ExpertQueryService
from app.usage.metered import MeteredWorkspaceGeneration
from app.workspaces.policy import WorkspaceAction

router = APIRouter(prefix="/api", tags=["query"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _require_read(access: DocumentAccess) -> None:
    # Reading knowledge — including through an Expert — requires the same
    # Workspace read grant tenants need to view Documents.
    access.require_action(WorkspaceAction.READ_DOCUMENT)


@router.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> QueryResponse:
    _require_read(access)
    meter = MeteredWorkspaceGeneration(
        db,
        workspace_id=access.workspace.id,
        user_id=access.user.id,
        expert_id=body.expert_id,
    )
    usage_context = meter.reserve()
    try:
        svc = ExpertQueryService(db)
        result = svc.query(
            workspace=access.workspace,
            membership=access.membership,
            actor=access.user,
            expert_id=body.expert_id,
            question=body.question,
            top_k=body.top_k,
            usage_context=usage_context,
        )
        meter.settle(result)
    except Exception:
        meter.release()
        raise
    return QueryResponse(
        answer=result["answer"],
        insufficient_context=result["insufficient_context"],
        citations=[Citation(**c) for c in result["citations"]],
        model=public_model_id(result.get("model")),
        general_answer=result.get("general_answer"),
        used_general_knowledge=bool(result.get("used_general_knowledge")),
        general_model=public_model_or_none(result.get("general_model")),
    )


@router.post("/query/stream")
async def query_stream(
    body: QueryRequest,
    access: DocumentAccess = Depends(get_document_access),
) -> StreamingResponse:
    _require_read(access)
    workspace = access.workspace
    membership = access.membership
    actor = access.user
    expert_id = body.expert_id
    question = body.question
    top_k = body.top_k

    def generate() -> Iterator[str]:
        db = SessionLocal()
        meter = MeteredWorkspaceGeneration(
            db,
            workspace_id=workspace.id,
            user_id=actor.id,
            expert_id=expert_id,
        )
        try:
            usage_context = meter.reserve()
            svc = ExpertQueryService(db)
            for item in svc.query_stream(
                workspace=workspace,
                membership=membership,
                actor=actor,
                expert_id=expert_id,
                question=question,
                top_k=top_k,
                usage_context=usage_context,
            ):
                payload = item.get("data") or {}
                if item.get("event") == "final":
                    meter.settle(payload)
                    payload = redact_public_models(payload)
                yield _sse(item["event"], payload)
            if not meter.closed:
                meter.release()
        except AppError as exc:
            meter.release()
            yield _sse(
                "error",
                {
                    "error": exc.category.value,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except GeneratorExit:
            meter.release()
            raise
        except Exception as exc:  # noqa: BLE001 — surface to client SSE
            meter.release()
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
def get_job(
    job_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> JobResponse:
    """Job status — Workspace-owned documents only (Phase 2C)."""
    job = db.get(IngestionJob, job_id)
    if not job:
        raise AppError(ErrorCategory.NOT_FOUND, "Job not found")

    document = db.get(Document, job.document_id)
    if document is None or document.deleted_at is not None:
        raise AppError(ErrorCategory.NOT_FOUND, "Job not found")

    if document.workspace_id != access.workspace.id:
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
