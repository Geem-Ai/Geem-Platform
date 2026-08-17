from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access
from app.experts.models import Expert, ExpertType
from app.experts.policy import ExpertAction
from app.experts.schemas import (
    AddConnectorSourcesRequest,
    AddConnectorSourcesResponse,
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
        knowledge_mode=getattr(expert, "knowledge_mode", None) or "rag",
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
    from app.documents.repository import DocumentRepository
    from app.documents.service import compute_document_progress
    from app.experts.models import ExpertSource, ExpertSourceType

    svc = ExpertService(db)
    items = svc.list_knowledge_items(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
    )
    jobs_by_doc = DocumentRepository(db).latest_jobs_by_document_ids(
        [document.id for _, document in items]
    )
    out: list[ExpertKnowledgeItemOut] = []
    linked_source_ids: set[uuid.UUID] = set()
    for link, document in items:
        prog = compute_document_progress(document, jobs_by_doc.get(document.id))
        source_type = "upload"
        if link.source_id is not None:
            source = db.get(ExpertSource, link.source_id)
            if source is not None and source.type:
                source_type = source.type
                linked_source_ids.add(source.id)
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
                source_type=source_type,
                processed_pages=int(prog["processed_pages"] or 0),
                failed_pages=int(prog["failed_pages"] or 0),
                current_stage=prog["current_stage"],
                progress=float(prog["progress"] or 0.0),
            )
        )

    # Connector sources appear as soon as they are added — before sync creates
    # a Document — so the Knowledge panel is not empty after a successful pick.
    pending_sources = [
        s
        for s in ExpertService(db).repo.list_sources(expert_id)
        if s.type == ExpertSourceType.CONNECTOR.value and s.id not in linked_source_ids
    ]
    # Auth already enforced via list_knowledge_items; re-check workspace ownership
    # for sources by ensuring list_knowledge_items succeeded for this expert.
    for source in pending_sources:
        name = (source.name or "").strip() or "Google Drive file"
        cfg = source.config if isinstance(source.config, dict) else {}
        failure_reason = None
        if isinstance(cfg.get("last_error_message"), str):
            failure_reason = cfg["last_error_message"]
        elif isinstance(cfg.get("last_error_code"), str):
            failure_reason = cfg["last_error_code"]
        out.append(
            ExpertKnowledgeItemOut(
                id=source.id,
                expert_id=source.expert_id,
                document_id=None,
                source_id=source.id,
                created_at=source.created_at,
                title=name,
                original_filename=name,
                status=source.status,
                mime_type=None,
                byte_size=None,
                page_count=0,
                failure_reason=failure_reason,
                source_type=ExpertSourceType.CONNECTOR.value,
                processed_pages=0,
                failed_pages=0,
                current_stage=None,
                progress=0.0,
            )
        )

    out.sort(key=lambda row: row.created_at, reverse=True)
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
    from app.experts.connector_sources import ExpertConnectorSourceService
    from app.experts.models import ExpertSource, ExpertSourceType

    source = db.get(ExpertSource, source_id)
    if (
        source is not None
        and source.expert_id == expert_id
        and source.type == ExpertSourceType.CONNECTOR.value
        and source.deleted_at is None
    ):
        ExpertConnectorSourceService(db).remove_connector_source(
            workspace=access.workspace,
            membership=access.membership,
            actor=access.user,
            expert_id=expert_id,
            source_id=source_id,
        )
        db.commit()
        return

    ExpertService(db).soft_delete_source(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        source_id=source_id,
    )


@router.post(
    "/{expert_id}/connector-sources",
    response_model=AddConnectorSourcesResponse,
    status_code=201,
)
def add_expert_connector_sources(
    expert_id: uuid.UUID,
    body: AddConnectorSourcesRequest,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> AddConnectorSourcesResponse:
    from app.experts.connector_sources import (
        ConnectorSourceSelection,
        ExpertConnectorSourceService,
    )

    result = ExpertConnectorSourceService(db).add_connector_sources(
        workspace=access.workspace,
        membership=access.membership,
        actor=access.user,
        expert_id=expert_id,
        connection_id=body.connection_id,
        items=[
            ConnectorSourceSelection(
                external_id=item.external_id,
                resource_key=item.resource_key,
            )
            for item in body.items
        ],
    )
    db.commit()
    return AddConnectorSourcesResponse(
        sources=[ExpertSourceOut.model_validate(s) for s in result.sources],
        sync_run_id=result.sync_run_id,
        status=result.status,
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
