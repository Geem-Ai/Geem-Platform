from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreateResponse(BaseModel):
    id: uuid.UUID
    status: str
    page_count: int


class DocumentSummary(BaseModel):
    id: uuid.UUID
    title: str
    original_filename: str
    status: str
    page_count: int
    processed_pages: int = 0
    failed_pages: int = 0
    current_stage: str | None = None
    progress: float = 0.0
    failure_reason: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class FailedPageInfo(BaseModel):
    page_number: int
    last_error: str | None = None
    attempt_count: int = 0


class DocumentDetail(DocumentSummary):
    sha256: str
    mime_type: str
    job_id: str | None = None
    failed_page_details: list[FailedPageInfo] = Field(default_factory=list)
    debug_pages: list[dict] | None = None


class ReprocessRequest(BaseModel):
    mode: str = "failed_pages"


class QueryRequest(BaseModel):
    question: str
    document_ids: list[uuid.UUID] | None = None
    top_k: int | None = None


class Citation(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page: int
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    insufficient_context: bool
    citations: list[Citation]
    model: str


class JobResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    total_pages: int
    processed_pages: int
    failed_pages: int
    current_stage: str | None
    last_error: str | None
