from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access
from app.experts.models import Expert, ExpertType
from app.experts.policy import ExpertAction
from app.experts.schemas import (
    ExpertCreateRequest,
    ExpertDocumentLinkOut,
    ExpertDocumentLinkRequest,
    ExpertKnowledgeItemOut,
    ExpertOut,
    ExpertSourceCreateRequest,
    ExpertSourceOut,
    ExpertUpdateRequest,
    ExpertUploadResponse,
)
from app.experts.service import ExpertService

router = APIRouter(prefix="/api/experts", tags=["experts"])


def _expert_out(
    expert: Expert,
    ownership: str,
    *,
    knowledge_document_count: int = 0,
) -> ExpertOut:
    """Serialize Expert for the Workspace product API.

    Platform Experts redact ``system_instructions`` and ``rag_config`` so
    tenants cannot inspect internal platform prompts/tuning (Phase 3C).
    Platform admin routes keep a separate serializer with full fields.
    """
    is_platform = ownership == "platform" or expert.type == ExpertType.PLATFORM.value
    return ExpertOut(
        id=expert.id,
        type=expert.type,
        ownership=ownership,
        workspace_id=expert.workspace_id,
        name=expert.name,
        description=expert.description,
        icon_url=expert.icon_url,
        system_instructions=None if is_platform else expert.system_instructions,
        rag_config=None if is_platform else (expert.rag_config or {}),
        status=expert.status,
        visibility=expert.visibility,
        availability_mode=expert.availability_mode,
        created_by=expert.created_by,
        created_at=expert.created_at,
        updated_at=expert.updated_at,
        knowledge_document_count=knowledge_document_count,
    )


@router.get("", response_model=list[ExpertOut])
def list_experts(
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> list[ExpertOut]:
    """Workspace Experts owned by current Workspace + granted/published Platform Experts."""
    svc = ExpertService(db)
    rows = svc.list_for_workspace(access.workspace)
    return [
        _expert_out(
            e,
            ownership,
            knowledge_document_count=svc.count_linked_documents(e.id),
        )
        for e, ownership in rows
    ]


@router.post("", response_model=ExpertOut, status_code=201)
def create_expert(
    body: ExpertCreateRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ExpertOut:
    expert = ExpertService(db).create_workspace_expert(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        name=body.name,
        description=body.description,
        system_instructions=body.system_instructions,
        rag_config=body.rag_config,
        visibility=body.visibility,
        status=body.status,
        icon_url=body.icon_url,
    )
    return _expert_out(expert, "workspace", knowledge_document_count=0)


@router.get("/{expert_id}", response_model=ExpertOut)
def get_expert(
    expert_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ExpertOut:
    svc = ExpertService(db)
    auth = svc.get_for_workspace(
        workspace=access.workspace,
        membership=access.membership,
        expert_id=expert_id,
        actor=access.user,
        action=ExpertAction.VIEW,
    )
    return _expert_out(
        auth.expert,
        auth.ownership,
        knowledge_document_count=svc.count_linked_documents(auth.expert.id),
    )


@router.patch("/{expert_id}", response_model=ExpertOut)
def update_expert(
    expert_id: uuid.UUID,
    body: ExpertUpdateRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ExpertOut:
    svc = ExpertService(db)
    expert = svc.update_workspace_expert(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        name=body.name,
        description=body.description,
        system_instructions=body.system_instructions,
        rag_config=body.rag_config,
        visibility=body.visibility,
        status=body.status,
        icon_url=body.icon_url,
    )
    return _expert_out(
        expert,
        "workspace",
        knowledge_document_count=svc.count_linked_documents(expert.id),
    )


@router.delete("/{expert_id}", status_code=204)
def delete_expert(
    expert_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).delete_workspace_expert(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
    )


@router.get("/{expert_id}/documents", response_model=list[ExpertKnowledgeItemOut])
def list_expert_documents(
    expert_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> list[ExpertKnowledgeItemOut]:
    from app.documents.service import DocumentService

    svc = ExpertService(db)
    doc_svc = DocumentService(db)
    items = svc.list_knowledge_items(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
    )
    out: list[ExpertKnowledgeItemOut] = []
    for link, document in items:
        prog = doc_svc.progress(document)
        out.append(
            ExpertKnowledgeItemOut(
                id=link.id,
                expert_id=link.expert_id,
                document_id=link.document_id,
                source_id=link.source_id,
                created_at=link.created_at,
                title=document.title,
                original_filename=document.original_filename,
                status=document.status,
                mime_type=document.mime_type,
                byte_size=document.byte_size,
                page_count=document.page_count,
                failure_reason=document.failure_reason,
                source_type="upload",
                processed_pages=int(prog["processed_pages"] or 0),
                failed_pages=int(prog["failed_pages"] or 0),
                current_stage=prog["current_stage"],
                progress=float(prog["progress"] or 0.0),
            )
        )
    return out


@router.post("/{expert_id}/documents", response_model=ExpertDocumentLinkOut, status_code=201)
def link_expert_document(
    expert_id: uuid.UUID,
    body: ExpertDocumentLinkRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ExpertDocumentLinkOut:
    link = ExpertService(db).link_document(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        document_id=body.document_id,
        source_id=body.source_id,
    )
    return ExpertDocumentLinkOut.model_validate(link)


@router.delete("/{expert_id}/documents/{document_id}", status_code=204)
def unlink_expert_document(
    expert_id: uuid.UUID,
    document_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).unlink_document(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        document_id=document_id,
    )


@router.post("/{expert_id}/sources", response_model=ExpertSourceOut, status_code=201)
def create_expert_source(
    expert_id: uuid.UUID,
    body: ExpertSourceCreateRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ExpertSourceOut:
    if body.type != "upload":
        from app.core.errors import AppError, ErrorCategory

        raise AppError(ErrorCategory.VALIDATION, "Only source type 'upload' is supported.")
    source = ExpertService(db).create_upload_source(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        name=body.name,
    )
    return ExpertSourceOut.model_validate(source)


@router.delete("/{expert_id}/sources/{source_id}", status_code=204)
def delete_expert_source(
    expert_id: uuid.UUID,
    source_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> None:
    ExpertService(db).soft_delete_source(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        source_id=source_id,
    )


@router.post(
    "/{expert_id}/upload",
    response_model=ExpertUploadResponse,
    status_code=201,
)
async def upload_expert_document(
    expert_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> ExpertUploadResponse:
    """Upload a Document directly to a Workspace Expert (Phase 3B).

    Idempotent on sha256 within the Workspace — re-uploading the same file
    returns ``reused=true`` and links the existing Document instead of
    raising ``document_already_exists``.
    """
    data = await file.read()
    result = ExpertService(db).upload_document_for_workspace_expert(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
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
