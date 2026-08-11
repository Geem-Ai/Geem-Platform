"""Minimal Platform Expert admin APIs (Phase 3A scaffolding for Phase 8).

Protected by ``platform_role=admin``. Not the full Platform Admin product surface.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.schemas import DocumentCreateResponse
from app.db.session import get_db
from app.experts.models import Expert
from app.experts.schemas import (
    ExpertDocumentLinkOut,
    ExpertDocumentLinkRequest,
    ExpertOut,
    ExpertUpdateRequest,
    ExpertUploadResponse,
    PlatformExpertCreateRequest,
    PlatformExpertGrantRequest,
    WorkspaceExpertGrantOut,
)
from app.experts.service import ExpertService
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.worker.tasks import enqueue_ingest

router = APIRouter(prefix="/api/platform", tags=["platform"])


def _platform_out(expert: Expert) -> ExpertOut:
    return ExpertOut(
        id=expert.id,
        type=expert.type,
        ownership="platform",
        workspace_id=expert.workspace_id,
        name=expert.name,
        description=expert.description,
        icon_url=expert.icon_url,
        system_instructions=expert.system_instructions,
        rag_config=expert.rag_config or {},
        status=expert.status,
        visibility=expert.visibility,
        availability_mode=expert.availability_mode,
        knowledge_mode=getattr(expert, "knowledge_mode", None) or "rag",
        created_by=expert.created_by,
        created_at=expert.created_at,
        updated_at=expert.updated_at,
        knowledge_document_count=0,
    )


@router.get("/experts", response_model=list[ExpertOut])
def list_platform_experts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExpertOut]:
    experts = ExpertService(db).list_platform_experts(actor=user)
    return [_platform_out(e) for e in experts]


@router.post("/experts", response_model=ExpertOut, status_code=201)
def create_platform_expert(
    body: PlatformExpertCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpertOut:
    expert = ExpertService(db).create_platform_expert(
        actor=user,
        name=body.name,
        description=body.description,
        system_instructions=body.system_instructions,
        rag_config=body.rag_config,
        visibility=body.visibility,
        status=body.status,
        availability_mode=body.availability_mode,
        icon_url=body.icon_url,
    )
    return _platform_out(expert)


@router.patch("/experts/{expert_id}", response_model=ExpertOut)
def update_platform_expert(
    expert_id: uuid.UUID,
    body: ExpertUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpertOut:
    expert = ExpertService(db).update_platform_expert(
        actor=user,
        expert_id=expert_id,
        name=body.name,
        description=body.description,
        system_instructions=body.system_instructions,
        rag_config=body.rag_config,
        visibility=body.visibility,
        status=body.status,
        availability_mode=body.availability_mode,
        icon_url=body.icon_url,
    )
    return _platform_out(expert)


@router.delete("/experts/{expert_id}", status_code=204)
def delete_platform_expert(
    expert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).delete_platform_expert(actor=user, expert_id=expert_id)


@router.post(
    "/experts/{expert_id}/grants",
    response_model=WorkspaceExpertGrantOut,
    status_code=201,
)
def grant_platform_expert(
    expert_id: uuid.UUID,
    body: PlatformExpertGrantRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceExpertGrantOut:
    grant = ExpertService(db).grant_platform_expert(
        actor=user,
        expert_id=expert_id,
        workspace_id=body.workspace_id,
    )
    return WorkspaceExpertGrantOut.model_validate(grant)


@router.delete("/experts/{expert_id}/grants/{workspace_id}", status_code=204)
def revoke_platform_expert(
    expert_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).revoke_platform_expert(
        actor=user,
        expert_id=expert_id,
        workspace_id=workspace_id,
    )


@router.post(
    "/experts/{expert_id}/documents",
    response_model=ExpertDocumentLinkOut,
    status_code=201,
)
def link_platform_expert_document(
    expert_id: uuid.UUID,
    body: ExpertDocumentLinkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpertDocumentLinkOut:
    link = ExpertService(db).link_platform_document(
        actor=user,
        expert_id=expert_id,
        document_id=body.document_id,
        source_id=body.source_id,
    )
    return ExpertDocumentLinkOut.model_validate(link)


@router.post("/knowledge/documents", response_model=DocumentCreateResponse, status_code=201)
async def upload_platform_knowledge_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentCreateResponse:
    """Upload a Document into the Platform Knowledge system Workspace."""
    data = await file.read()
    svc = ExpertService(db)
    doc = svc.upload_platform_knowledge_document(
        actor=user,
        file_bytes=data,
        filename=file.filename or "document.pdf",
        title=title,
    )
    from app.workspaces.service import WorkspaceService

    pk = WorkspaceService(db).get_platform_knowledge_workspace()
    enqueue_ingest(
        str(doc.id),
        mode="full",
        workspace_id=str(pk.id),
        actor_id=str(user.id),
    )
    return DocumentCreateResponse(
        id=doc.id,
        status=doc.status,
        page_count=doc.page_count,
        byte_size=doc.byte_size,
    )


@router.post(
    "/experts/{expert_id}/upload",
    response_model=ExpertUploadResponse,
    status_code=201,
)
async def upload_platform_expert_document(
    expert_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpertUploadResponse:
    """Privileged upload for a Platform Expert (Phase 3B).

    Requires platform admin. Uploads into the Platform Knowledge Workspace,
    dedupes on sha256, and links the (new or reused) Document to the Expert.
    """
    data = await file.read()
    result = ExpertService(db).upload_document_for_platform_expert(
        actor=user,
        expert_id=expert_id,
        file_bytes=data,
        filename=file.filename or "document",
        title=title,
        declared_mime_type=file.content_type,
    )
    return ExpertUploadResponse(
        expert_id=result.expert_id,
        source_id=result.source_id,
        document_id=result.document.id,
        status=result.document.status,
        mime_type=result.document.mime_type,
        page_count=result.document.page_count,
        reused=result.reused,
    )
