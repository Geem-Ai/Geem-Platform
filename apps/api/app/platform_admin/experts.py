"""Platform Admin Platform Expert orchestration (Phase 12D)."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, record_audit
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.documents.repository import DocumentRepository
from app.documents.service import compute_document_progress
from app.experts.models import (
    Expert,
    ExpertAvailabilityMode,
    ExpertKnowledgeMode,
    ExpertSource,
    ExpertVisibility,
)
from app.experts.repository import ExpertRepository
from app.experts.schemas import (
    ExpertDocumentLinkRequest,
    ExpertUpdateRequest,
    PlatformExpertCreateRequest,
    PlatformExpertGrantRequest,
)
from app.experts.service import ExpertService
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.repository import PlatformAdminRepository
from app.platform_admin.schemas import (
    PlatformExpertDetailOut,
    PlatformExpertGrantListResponse,
    PlatformExpertKnowledgeItemOut,
    PlatformExpertKnowledgeListResponse,
    PlatformExpertListItem,
    PlatformExpertListResponse,
    PlatformExpertWorkspaceGrantOut,
)

class PlatformAdminExpertsService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = ExpertRepository(db)
        self.admin_repo = PlatformAdminRepository(db)
        self.experts = ExpertService(db, self.settings)

    def _audit_and_commit(
        self,
        *,
        action: AuditAction,
        entity_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        metadata: dict[str, Any],
        allowlist: frozenset[str],
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        record_audit(
            self.db,
            action=action,
            entity_type=AuditEntityType.EXPERT,
            entity_id=entity_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            metadata=metadata,
            allowlist=allowlist,
        )
        self.db.commit()

    def list_experts(
        self,
        actor: User,
        *,
        limit: int = 25,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        knowledge_mode: str | None = None,
        availability_mode: str | None = None,
        published: bool | None = None,
    ) -> PlatformExpertListResponse:
        require_platform_admin_user(actor)
        total = self.repo.count_platform_experts(
            search=search,
            status=status,
            visibility=visibility,
            knowledge_mode=knowledge_mode,
            availability_mode=availability_mode,
            published=published,
        )
        rows = self.repo.list_platform_experts_paginated(
            limit=limit,
            offset=offset,
            search=search,
            status=status,
            visibility=visibility,
            knowledge_mode=knowledge_mode,
            availability_mode=availability_mode,
            published=published,
        )
        expert_ids = [e.id for e in rows]
        doc_counts = self.repo.count_document_links_for_experts(expert_ids)
        grant_counts = self.repo.count_grants_for_experts(expert_ids)
        items = [
            self._list_item(
                expert,
                knowledge_document_count=doc_counts.get(expert.id, 0),
                explicit_workspace_grant_count=grant_counts.get(expert.id, 0),
            )
            for expert in rows
        ]
        return PlatformExpertListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def get_expert(self, actor: User, expert_id: uuid.UUID) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        expert = self.experts.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        return self._detail_out(expert)

    def create_expert(
        self, actor: User, body: PlatformExpertCreateRequest
    ) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        expert = self.experts.create_platform_expert(
            actor=actor,
            name=body.name,
            description=body.description,
            system_instructions=body.system_instructions,
            rag_config=body.rag_config,
            visibility=body.visibility,
            status=body.status,
            availability_mode=body.availability_mode,
            icon_url=body.icon_url,
        )
        record_audit(
            self.db,
            action=AuditAction.PLATFORM_EXPERT_CREATED,
            entity_type=AuditEntityType.EXPERT,
            entity_id=expert.id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert.id),
                "name": expert.name,
                "visibility": expert.visibility,
                "availability_mode": expert.availability_mode,
                "knowledge_mode": expert.knowledge_mode,
            },
            allowlist=frozenset(
                {
                    "expert_id",
                    "name",
                    "visibility",
                    "availability_mode",
                    "knowledge_mode",
                }
            ),
        )
        self.db.commit()
        return self._detail_out(expert)

    def update_expert(
        self,
        actor: User,
        expert_id: uuid.UUID,
        body: ExpertUpdateRequest,
    ) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        before = self.get_expert(actor, expert_id)
        self.experts.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )

        if body.visibility is not None and body.visibility != before.visibility:
            if body.visibility == ExpertVisibility.PLATFORM_PUBLISHED.value:
                expert = self.experts.publish_platform_expert(actor=actor, expert_id=expert_id)
                self._audit_and_commit(
                    action=AuditAction.PLATFORM_EXPERT_PUBLISHED,
                    entity_id=expert.id,
                    actor_user_id=actor.id,
                    metadata={
                        "expert_id": str(expert.id),
                        "old_visibility": before.visibility,
                        "new_visibility": expert.visibility,
                        "via": "patch",
                    },
                    allowlist=frozenset(
                        {"expert_id", "old_visibility", "new_visibility", "via"}
                    ),
                )
            elif body.visibility == ExpertVisibility.PLATFORM_DRAFT.value:
                expert = self.experts.unpublish_platform_expert(actor=actor, expert_id=expert_id)
                self._audit_and_commit(
                    action=AuditAction.PLATFORM_EXPERT_UNPUBLISHED,
                    entity_id=expert.id,
                    actor_user_id=actor.id,
                    metadata={
                        "expert_id": str(expert.id),
                        "old_visibility": before.visibility,
                        "new_visibility": expert.visibility,
                        "via": "patch",
                    },
                    allowlist=frozenset(
                        {"expert_id", "old_visibility", "new_visibility", "via"}
                    ),
                )
            else:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Invalid visibility for Platform Expert.",
                )
            before = self.get_expert(actor, expert_id)

        if (
            body.availability_mode is not None
            and body.availability_mode != before.availability_mode
        ):
            if body.availability_mode == ExpertAvailabilityMode.ALL_WORKSPACES.value:
                expert = self.experts.enable_all_workspaces_access(
                    actor=actor, expert_id=expert_id
                )
                self._audit_and_commit(
                    action=AuditAction.PLATFORM_EXPERT_ACCESS_ALL_ENABLE,
                    entity_id=expert.id,
                    actor_user_id=actor.id,
                    metadata={
                        "expert_id": str(expert.id),
                        "old_access_mode": before.availability_mode,
                        "new_access_mode": expert.availability_mode,
                        "via": "patch",
                    },
                    allowlist=frozenset(
                        {"expert_id", "old_access_mode", "new_access_mode", "via"}
                    ),
                )
            elif body.availability_mode == ExpertAvailabilityMode.SELECTED_WORKSPACES.value:
                expert = self.experts.disable_all_workspaces_access(
                    actor=actor, expert_id=expert_id
                )
                self._audit_and_commit(
                    action=AuditAction.PLATFORM_EXPERT_ACCESS_ALL_DISABLE,
                    entity_id=expert.id,
                    actor_user_id=actor.id,
                    metadata={
                        "expert_id": str(expert.id),
                        "old_access_mode": before.availability_mode,
                        "new_access_mode": expert.availability_mode,
                        "via": "patch",
                    },
                    allowlist=frozenset(
                        {"expert_id", "old_access_mode", "new_access_mode", "via"}
                    ),
                )
            else:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Invalid availability_mode.",
                )
            before = self.get_expert(actor, expert_id)

        has_other_updates = any(
            value is not None
            for value in (
                body.name,
                body.description,
                body.system_instructions,
                body.rag_config,
                body.status,
                body.icon_url,
            )
        )
        if has_other_updates:
            expert = self.experts.update_platform_expert(
                actor=actor,
                expert_id=expert_id,
                name=body.name,
                description=body.description,
                system_instructions=body.system_instructions,
                rag_config=body.rag_config,
                visibility=None,
                status=body.status,
                availability_mode=None,
                icon_url=body.icon_url,
            )
            metadata: dict[str, Any] = {
                "expert_id": str(expert.id),
                "visibility": expert.visibility,
                "availability_mode": expert.availability_mode,
            }
            if body.system_instructions is not None:
                old_hash = hashlib.sha256(
                    (before.system_instructions or "").encode()
                ).hexdigest()[:16]
                new_hash = hashlib.sha256(
                    (expert.system_instructions or "").encode()
                ).hexdigest()[:16]
                metadata["instructions_changed"] = old_hash != new_hash
                metadata["instructions_hash"] = new_hash
            self._audit_and_commit(
                action=AuditAction.PLATFORM_EXPERT_UPDATED,
                entity_id=expert.id,
                actor_user_id=actor.id,
                metadata=metadata,
                allowlist=frozenset(metadata.keys()),
            )

        return self.get_expert(actor, expert_id)

    def delete_expert(self, actor: User, expert_id: uuid.UUID) -> None:
        require_platform_admin_user(actor)
        expert = self.experts.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        self.experts.delete_platform_expert(actor=actor, expert_id=expert_id)
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_SOFT_DELETED,
            entity_id=expert.id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert.id),
                "name": expert.name,
                "knowledge_mode": expert.knowledge_mode,
            },
            allowlist=frozenset({"expert_id", "name", "knowledge_mode"}),
        )

    def publish_expert(self, actor: User, expert_id: uuid.UUID) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        before = self.get_expert(actor, expert_id)
        expert = self.experts.publish_platform_expert(actor=actor, expert_id=expert_id)
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_PUBLISHED,
            entity_id=expert.id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert.id),
                "old_visibility": before.visibility,
                "new_visibility": expert.visibility,
            },
            allowlist=frozenset({"expert_id", "old_visibility", "new_visibility"}),
        )
        return self.get_expert(actor, expert_id)

    def unpublish_expert(self, actor: User, expert_id: uuid.UUID) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        before = self.get_expert(actor, expert_id)
        expert = self.experts.unpublish_platform_expert(actor=actor, expert_id=expert_id)
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_UNPUBLISHED,
            entity_id=expert.id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert.id),
                "old_visibility": before.visibility,
                "new_visibility": expert.visibility,
            },
            allowlist=frozenset({"expert_id", "old_visibility", "new_visibility"}),
        )
        return self.get_expert(actor, expert_id)

    def enable_all_workspaces(
        self, actor: User, expert_id: uuid.UUID
    ) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        before = self.get_expert(actor, expert_id)
        expert = self.experts.enable_all_workspaces_access(actor=actor, expert_id=expert_id)
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_ACCESS_ALL_ENABLE,
            entity_id=expert.id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert.id),
                "old_access_mode": before.availability_mode,
                "new_access_mode": expert.availability_mode,
            },
            allowlist=frozenset(
                {"expert_id", "old_access_mode", "new_access_mode"}
            ),
        )
        return self.get_expert(actor, expert_id)

    def disable_all_workspaces(
        self, actor: User, expert_id: uuid.UUID
    ) -> PlatformExpertDetailOut:
        require_platform_admin_user(actor)
        before = self.get_expert(actor, expert_id)
        expert = self.experts.disable_all_workspaces_access(actor=actor, expert_id=expert_id)
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_ACCESS_ALL_DISABLE,
            entity_id=expert.id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert.id),
                "old_access_mode": before.availability_mode,
                "new_access_mode": expert.availability_mode,
            },
            allowlist=frozenset(
                {"expert_id", "old_access_mode", "new_access_mode"}
            ),
        )
        return self.get_expert(actor, expert_id)

    def list_workspace_grants(
        self,
        actor: User,
        expert_id: uuid.UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        search: str | None = None,
    ) -> PlatformExpertGrantListResponse:
        require_platform_admin_user(actor)
        self.experts.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        total = self.repo.count_workspace_grants_for_expert(expert_id, search=search)
        rows = self.repo.list_workspace_grants_for_expert(
            expert_id, limit=limit, offset=offset, search=search
        )
        items = [
            PlatformExpertWorkspaceGrantOut(
                id=grant.id,
                workspace_id=grant.workspace_id,
                workspace_name=ws.name,
                workspace_slug=ws.slug,
                workspace_status=ws.status,
                expert_id=grant.expert_id,
                created_by=grant.created_by,
                created_at=grant.created_at,
            )
            for grant, ws in rows
        ]
        return PlatformExpertGrantListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def grant_workspace(
        self, actor: User, expert_id: uuid.UUID, body: PlatformExpertGrantRequest
    ) -> PlatformExpertWorkspaceGrantOut:
        require_platform_admin_user(actor)
        grant = self.experts.grant_platform_expert(
            actor=actor,
            expert_id=expert_id,
            workspace_id=body.workspace_id,
        )
        ws = self.admin_repo.get_workspace(body.workspace_id)
        if ws is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_WORKSPACE_GRANT,
            entity_id=expert_id,
            actor_user_id=actor.id,
            workspace_id=body.workspace_id,
            metadata={
                "expert_id": str(expert_id),
                "workspace_id": str(body.workspace_id),
                "workspace_slug": ws.slug,
            },
            allowlist=frozenset({"expert_id", "workspace_id", "workspace_slug"}),
        )
        return PlatformExpertWorkspaceGrantOut(
            id=grant.id,
            workspace_id=grant.workspace_id,
            workspace_name=ws.name,
            workspace_slug=ws.slug,
            workspace_status=ws.status,
            expert_id=grant.expert_id,
            created_by=grant.created_by,
            created_at=grant.created_at,
        )

    def revoke_workspace(
        self, actor: User, expert_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        require_platform_admin_user(actor)
        ws = self.admin_repo.get_workspace(workspace_id)
        self.experts.revoke_platform_expert(
            actor=actor, expert_id=expert_id, workspace_id=workspace_id
        )
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_WORKSPACE_REVOKE,
            entity_id=expert_id,
            actor_user_id=actor.id,
            workspace_id=workspace_id,
            metadata={
                "expert_id": str(expert_id),
                "workspace_id": str(workspace_id),
                "workspace_slug": ws.slug if ws else None,
            },
            allowlist=frozenset({"expert_id", "workspace_id", "workspace_slug"}),
        )

    def list_knowledge(
        self,
        actor: User,
        expert_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> PlatformExpertKnowledgeListResponse:
        require_platform_admin_user(actor)
        pairs = self.experts.list_platform_knowledge_pairs(actor=actor, expert_id=expert_id)
        doc_ids = [document.id for _, document in pairs]
        jobs_by_doc = DocumentRepository(self.db).latest_jobs_by_document_ids(doc_ids)
        items: list[PlatformExpertKnowledgeItemOut] = []
        for link, document in pairs:
            prog = compute_document_progress(document, jobs_by_doc.get(document.id))
            source_type = "upload"
            if link.source_id is not None:
                source = self.db.get(ExpertSource, link.source_id)
                if source is not None and source.type:
                    source_type = source.type
            items.append(
                PlatformExpertKnowledgeItemOut(
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
        items.sort(key=lambda row: row.created_at, reverse=True)
        total = len(items)
        page = items[offset : offset + limit]
        return PlatformExpertKnowledgeListResponse(
            items=page, total=total, limit=limit, offset=offset
        )

    def link_document(
        self,
        actor: User,
        expert_id: uuid.UUID,
        body: ExpertDocumentLinkRequest,
    ):
        require_platform_admin_user(actor)
        link = self.experts.link_platform_document(
            actor=actor,
            expert_id=expert_id,
            document_id=body.document_id,
            source_id=body.source_id,
        )
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_KNOWLEDGE_UPLOAD,
            entity_id=expert_id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert_id),
                "document_id": str(body.document_id),
                "action": "link",
            },
            allowlist=frozenset({"expert_id", "document_id", "action"}),
        )
        return link

    def upload_knowledge(
        self,
        actor: User,
        expert_id: uuid.UUID,
        *,
        file_bytes: bytes,
        filename: str,
        title: str | None,
        declared_mime_type: str | None,
    ):
        require_platform_admin_user(actor)
        result = self.experts.upload_document_for_platform_expert(
            actor=actor,
            expert_id=expert_id,
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            declared_mime_type=declared_mime_type,
        )
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_KNOWLEDGE_UPLOAD,
            entity_id=expert_id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert_id),
                "document_id": str(result.document.id),
                "reused": result.reused,
            },
            allowlist=frozenset({"expert_id", "document_id", "reused"}),
        )
        return result

    def reprocess_knowledge(
        self,
        actor: User,
        expert_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        mode: str = "full",
    ):
        require_platform_admin_user(actor)
        job = self.experts.reprocess_platform_document(
            actor=actor,
            expert_id=expert_id,
            document_id=document_id,
            mode=mode,
        )
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_KNOWLEDGE_REPROCESS,
            entity_id=expert_id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert_id),
                "document_id": str(document_id),
                "mode": mode,
                "job_id": str(job.id),
            },
            allowlist=frozenset({"expert_id", "document_id", "mode", "job_id"}),
        )
        return job

    def remove_knowledge(
        self, actor: User, expert_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        require_platform_admin_user(actor)
        self.experts.unlink_platform_document(
            actor=actor, expert_id=expert_id, document_id=document_id
        )
        self._audit_and_commit(
            action=AuditAction.PLATFORM_EXPERT_KNOWLEDGE_REMOVE,
            entity_id=expert_id,
            actor_user_id=actor.id,
            metadata={
                "expert_id": str(expert_id),
                "document_id": str(document_id),
            },
            allowlist=frozenset({"expert_id", "document_id"}),
        )

    def _list_item(
        self,
        expert: Expert,
        *,
        knowledge_document_count: int,
        explicit_workspace_grant_count: int,
    ) -> PlatformExpertListItem:
        return PlatformExpertListItem(
            id=expert.id,
            type=expert.type,
            ownership="platform",
            workspace_id=expert.workspace_id,
            name=expert.name,
            description=expert.description,
            icon_url=expert.icon_url,
            status=expert.status,
            visibility=expert.visibility,
            availability_mode=expert.availability_mode,
            knowledge_mode=expert.knowledge_mode or ExpertKnowledgeMode.RAG.value,
            created_by=expert.created_by,
            created_at=expert.created_at,
            updated_at=expert.updated_at,
            knowledge_document_count=knowledge_document_count,
            explicit_workspace_grant_count=explicit_workspace_grant_count,
            is_protected=expert.knowledge_mode == ExpertKnowledgeMode.GENERAL.value,
        )

    def _detail_out(self, expert: Expert) -> PlatformExpertDetailOut:
        doc_count = self.repo.count_document_links(expert.id)
        grant_count = self.repo.count_workspace_grants_for_expert(expert.id)
        base = self._list_item(
            expert,
            knowledge_document_count=doc_count,
            explicit_workspace_grant_count=grant_count,
        )
        return PlatformExpertDetailOut(
            **base.model_dump(),
            system_instructions=expert.system_instructions,
            rag_config=expert.rag_config or {},
        )
