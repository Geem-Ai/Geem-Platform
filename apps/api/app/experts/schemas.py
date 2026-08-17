from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ExpertCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    system_instructions: str | None = Field(default=None, max_length=32000)
    rag_config: dict[str, Any] | None = None
    visibility: str | None = None
    status: str | None = None
    icon_url: str | None = Field(default=None, max_length=1024)
    # Client-submitted workspace_id is ignored — ownership from RequestContext.


class ExpertUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    system_instructions: str | None = Field(default=None, max_length=32000)
    rag_config: dict[str, Any] | None = None
    visibility: str | None = None
    status: str | None = None
    icon_url: str | None = Field(default=None, max_length=1024)
    availability_mode: str | None = None


class GenerateExpertInstructionsRequest(BaseModel):
    """Draft system instructions from a brief + optional structured fields."""

    brief: str = Field(min_length=1, max_length=4000)
    persona: str | None = Field(default=None, max_length=2000)
    audience: str | None = Field(default=None, max_length=2000)
    tone: str | None = Field(default=None, max_length=2000)
    constraints: str | None = Field(default=None, max_length=2000)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class GenerateExpertInstructionsResponse(BaseModel):
    system_instructions: str


class ExpertOut(BaseModel):
    id: uuid.UUID
    type: str
    ownership: str
    workspace_id: uuid.UUID | None
    name: str
    description: str | None
    icon_url: str | None
    # Workspace-facing Platform Experts omit instructions/config (Phase 3C privacy).
    # Platform admin APIs continue to return full values.
    system_instructions: str | None = None
    rag_config: dict[str, Any] | None = None
    status: str
    visibility: str
    availability_mode: str
    knowledge_mode: str = "rag"
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    knowledge_document_count: int = 0

    model_config = {"from_attributes": True}


class ExpertDocumentLinkRequest(BaseModel):
    document_id: uuid.UUID
    source_id: uuid.UUID | None = None


class ExpertDocumentLinkOut(BaseModel):
    id: uuid.UUID
    expert_id: uuid.UUID
    document_id: uuid.UUID
    source_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExpertKnowledgeItemOut(BaseModel):
    """Workspace Expert knowledge row (upload Document link or connector source)."""

    id: uuid.UUID
    expert_id: uuid.UUID
    # Null while a connector source is queued/syncing and no Document exists yet.
    document_id: uuid.UUID | None = None
    source_id: uuid.UUID | None
    created_at: datetime
    title: str
    original_filename: str
    status: str
    mime_type: str | None = None
    byte_size: int | None = None
    page_count: int = 0
    failure_reason: str | None = None
    source_type: str = "upload"
    # Ingestion progress (from latest IngestionJob) — for Expert knowledge UX.
    processed_pages: int = 0
    failed_pages: int = 0
    current_stage: str | None = None
    progress: float = 0.0


class ExpertSourceCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    type: str = "upload"


class ExpertSourceOut(BaseModel):
    id: uuid.UUID
    expert_id: uuid.UUID
    type: str
    name: str | None
    status: str
    config: dict[str, Any]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectorSourceItemIn(BaseModel):
    external_id: str | None = Field(default=None, max_length=1024)
    resource_key: str | None = Field(default=None, max_length=512)
    provider_locator: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_identity(self) -> ConnectorSourceItemIn:
        has_external = bool((self.external_id or "").strip())
        locator = self.provider_locator or {}
        has_locator = bool(
            isinstance(locator, dict)
            and (locator.get("drive_id") or locator.get("item_id"))
        )
        if not has_external and not has_locator:
            raise ValueError("external_id or provider_locator is required")
        return self


class AddConnectorSourcesRequest(BaseModel):
    connection_id: uuid.UUID
    items: list[ConnectorSourceItemIn] = Field(min_length=1, max_length=100)


class AddConnectorSourcesResponse(BaseModel):
    sources: list[ExpertSourceOut]
    sync_run_id: uuid.UUID | None = None
    status: str


class ExpertUploadResponse(BaseModel):
    """Response shape for ``POST /api/experts/{expert_id}/upload`` (Phase 3B)."""

    expert_id: uuid.UUID
    source_id: uuid.UUID
    document_id: uuid.UUID
    status: str
    mime_type: str
    page_count: int
    reused: bool


class PlatformExpertCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    system_instructions: str | None = Field(default=None, max_length=32000)
    rag_config: dict[str, Any] | None = None
    visibility: str | None = None
    status: str | None = None
    availability_mode: str | None = None
    icon_url: str | None = Field(default=None, max_length=1024)


class PlatformExpertGrantRequest(BaseModel):
    workspace_id: uuid.UUID


class WorkspaceExpertGrantOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    expert_id: uuid.UUID
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
