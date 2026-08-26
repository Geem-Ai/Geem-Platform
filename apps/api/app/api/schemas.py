from __future__ import annotations

import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator


class DocumentCreateResponse(BaseModel):
    id: uuid.UUID
    status: str
    page_count: int
    byte_size: int | None = None


class DocumentExpertRef(BaseModel):
    id: uuid.UUID
    name: str


class DocumentSummary(BaseModel):
    id: uuid.UUID
    title: str
    original_filename: str
    status: str
    page_count: int
    byte_size: int | None = None
    mime_type: str | None = None
    processed_pages: int = 0
    failed_pages: int = 0
    current_stage: str | None = None
    progress: float = 0.0
    failure_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    experts: list[DocumentExpertRef] = Field(default_factory=list)


class DocumentListOut(BaseModel):
    items: list[DocumentSummary]
    total: int = 0
    limit: int = 25
    offset: int = 0


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


class DocumentUpdateRequest(BaseModel):
    """Rename a Workspace document (display title)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=512)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Title is required.")
        return cleaned


class ReprocessRequest(BaseModel):
    mode: str = "failed_pages"


class QueryRequest(BaseModel):
    """RAG query request (Phase 3B).

    ``expert_id`` is required — every query targets a specific Expert whose
    linked knowledge determines the retrieval set. ``document_ids`` is
    intentionally rejected: filtering by Documents is a legacy per-request
    concern; Expert scope is now the single source of truth.
    """

    model_config = ConfigDict(extra="forbid")

    question: str
    expert_id: uuid.UUID
    top_k: int | None = None


class Citation(BaseModel):
    """Metadata-safe chunk/tool citation contract.

    The default chunk discriminator is intentionally omitted on serialization
    so pre-MCP Conversation/API/SSE payloads stay byte-compatible.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["chunk", "tool"] = "chunk"
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    document_title: str | None = None
    page: int | None = None
    snippet: str | None = None
    connection_display_name: str | None = None
    tool_name: str | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "Citation":
        if self.kind == "chunk":
            if (
                self.chunk_id is None
                or self.document_id is None
                or not (self.document_title or "").strip()
                or self.page is None
                or self.snippet is None
            ):
                raise ValueError("Chunk citations require complete document metadata.")
            if self.connection_display_name is not None or self.tool_name is not None:
                raise ValueError("Chunk citations cannot contain tool metadata.")
        else:
            if not (self.connection_display_name or "").strip() or not (
                self.tool_name or ""
            ).strip():
                raise ValueError("Tool citations require a connection display name and tool name.")
            if any(
                value is not None
                for value in (
                    self.chunk_id,
                    self.document_id,
                    self.document_title,
                    self.page,
                    self.snippet,
                )
            ):
                raise ValueError("Tool citations cannot contain chunk metadata.")
        return self

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        payload = handler(self)
        if self.kind == "chunk":
            payload.pop("kind", None)
            payload.pop("connection_display_name", None)
            payload.pop("tool_name", None)
        else:
            for key in ("chunk_id", "document_id", "document_title", "page", "snippet"):
                payload.pop(key, None)
        return {key: value for key, value in payload.items() if value is not None}


class QueryResponse(BaseModel):
    answer: str
    insufficient_context: bool
    citations: list[Citation]
    model: str
    general_answer: str | None = None
    used_general_knowledge: bool = False
    general_model: str | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    total_pages: int
    processed_pages: int
    failed_pages: int
    current_stage: str | None
    last_error: str | None
