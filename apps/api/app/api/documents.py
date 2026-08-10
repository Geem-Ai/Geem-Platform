from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DocumentCreateResponse,
    DocumentDetail,
    DocumentSummary,
    FailedPageInfo,
    JobResponse,
    ReprocessRequest,
)
from app.core.errors import AppError, ErrorCategory
from app.db.models import DocumentPage, IngestionJob
from app.db.session import get_db
from app.documents.service import DocumentService
from app.worker.tasks import enqueue_ingest

router = APIRouter(prefix="/api/documents", tags=["documents"])


def content_disposition_inline(filename: str) -> str:
    """Build a latin-1-safe Content-Disposition header for inline PDF viewing.

    Starlette encodes header values as latin-1; Arabic/other Unicode filenames
    must use RFC 5987 ``filename*`` with an ASCII ``filename`` fallback.
    """
    raw = (filename or "document.pdf").replace("\r", "").replace("\n", "")
    ascii_name = raw.encode("ascii", "ignore").decode("ascii").strip().strip(".")
    if not ascii_name or ascii_name in {'"', "'"}:
        ascii_name = "document.pdf"
    ascii_name = ascii_name.replace("\\", "_").replace('"', "'")
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(raw)}"


def _summary(svc: DocumentService, doc) -> DocumentSummary:
    prog = svc.progress(doc)
    return DocumentSummary(
        id=doc.id,
        title=doc.title,
        original_filename=doc.original_filename,
        status=doc.status,
        page_count=doc.page_count,
        processed_pages=prog["processed_pages"],
        failed_pages=prog["failed_pages"],
        current_stage=prog["current_stage"],
        progress=prog["progress"],
        failure_reason=doc.failure_reason,
        created_at=doc.created_at,
        completed_at=doc.completed_at,
    )


@router.post("", response_model=DocumentCreateResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentCreateResponse:
    if file.content_type and file.content_type not in {
        "application/pdf",
        "application/x-pdf",
        "binary/octet-stream",
        "application/octet-stream",
    }:
        # Still allow if magic validates
        pass
    data = await file.read()
    svc = DocumentService(db)
    try:
        doc = svc.upload(data, file.filename or "document.pdf", title=title)
    except AppError as exc:
        if exc.category == ErrorCategory.CONFLICT:
            raise
        raise
    enqueue_ingest(str(doc.id), mode="full")
    return DocumentCreateResponse(id=doc.id, status=doc.status, page_count=doc.page_count)


@router.get("", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    svc = DocumentService(db)
    return [_summary(svc, d) for d in svc.list_documents()]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    debug: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    svc = DocumentService(db)
    doc = svc.get(document_id)
    prog = svc.progress(doc)
    failed = [
        FailedPageInfo(
            page_number=p.page_number,
            last_error=p.last_error,
            attempt_count=p.attempt_count,
        )
        for p in svc.failed_pages(document_id)
    ]
    debug_pages = None
    if debug:
        pages = list(
            db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
        )
        debug_pages = [
            {
                "page_number": p.page_number,
                "status": p.status,
                "text_length": p.text_length,
                "arabic_ratio": p.arabic_ratio,
                "canonical_text": p.canonical_text,
                "last_error": p.last_error,
            }
            for p in pages
        ]
    base = _summary(svc, doc)
    return DocumentDetail(
        **base.model_dump(),
        sha256=doc.sha256,
        mime_type=doc.mime_type,
        job_id=prog.get("job_id"),
        failed_page_details=failed,
        debug_pages=debug_pages,
    )


@router.get("/{document_id}/file")
def download_file(document_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    svc = DocumentService(db)
    data, filename = svc.get_file(document_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_inline(filename)},
    )


@router.post("/{document_id}/reprocess", response_model=JobResponse)
def reprocess_document(
    document_id: uuid.UUID,
    body: ReprocessRequest,
    db: Session = Depends(get_db),
) -> JobResponse:
    svc = DocumentService(db)
    job = svc.reprocess(document_id, mode=body.mode)
    enqueue_ingest(str(document_id), mode=body.mode)
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


@router.delete("/{document_id}")
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    svc = DocumentService(db)
    svc.delete(document_id)
    return {"status": "deleted", "id": str(document_id)}
