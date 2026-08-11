"""Expert domain services (Phase 3A + 3B wiring).

Phase 3B additions:

* Every mutation that changes the ``expert_documents`` set for a Document
  (link, unlink, hard/soft-delete Expert) triggers Qdrant payload
  reconciliation via ``ExpertVectorMembershipSynchronizer.sync_document`` and
  Expert status reconciliation via ``ExpertStatusReconciler.reconcile``.
* Sync runs AFTER the DB commit so we never overwrite Qdrant with a state PG
  is about to roll back.
* Sync failures are logged and do NOT undo the DB mutation — retrieval will
  still filter by workspace_id (safe by default) and a background
  reconciliation job will catch up.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.documents.repository import DocumentRepository
from app.documents.service import DocumentService, WorkspaceUploadResult
from app.experts.access import AuthorizedExpert, ExpertAccessService
from app.experts.membership_sync import ExpertVectorMembershipSynchronizer
from app.experts.models import (
    DEFAULT_RAG_CONFIG,
    MAX_EXPERT_DESCRIPTION_LENGTH,
    MAX_EXPERT_NAME_LENGTH,
    MAX_SYSTEM_INSTRUCTIONS_LENGTH,
    SUPPORTED_RAG_CONFIG_KEYS,
    Expert,
    ExpertAvailabilityMode,
    ExpertDocument,
    ExpertSource,
    ExpertSourceStatus,
    ExpertSourceType,
    ExpertStatus,
    ExpertType,
    ExpertVisibility,
    WorkspaceExpertGrant,
)
from app.experts.policy import ExpertAction, ExpertPolicy
from app.experts.repository import ExpertRepository
from app.experts.status import ExpertStatusReconciler
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceKind, WorkspaceMembership
from app.workspaces.repository import WorkspaceRepository
from app.workspaces.service import WorkspaceService

logger = logging.getLogger(__name__)


def normalize_system_instructions(raw: str | None) -> str:
    text = (raw or "").strip()
    if len(text) > MAX_SYSTEM_INSTRUCTIONS_LENGTH:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"system_instructions max length is {MAX_SYSTEM_INSTRUCTIONS_LENGTH}.",
        )
    return text


def normalize_rag_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Expert rag_config. Only known knobs; Phase 3B applies them."""
    if raw is None:
        return dict(DEFAULT_RAG_CONFIG)
    if not isinstance(raw, dict):
        raise AppError(ErrorCategory.VALIDATION, "rag_config must be an object.")
    unknown = set(raw.keys()) - SUPPORTED_RAG_CONFIG_KEYS
    if unknown:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"Unsupported rag_config keys: {sorted(unknown)}",
            details={"supported": sorted(SUPPORTED_RAG_CONFIG_KEYS)},
        )
    out: dict[str, Any] = {}
    if "top_k" in raw:
        top_k = raw["top_k"]
        if not isinstance(top_k, int) or top_k < 1 or top_k > 100:
            raise AppError(ErrorCategory.VALIDATION, "rag_config.top_k must be 1–100.")
        out["top_k"] = top_k
    if "rerank_top_n" in raw:
        n = raw["rerank_top_n"]
        if not isinstance(n, int) or n < 1 or n > 50:
            raise AppError(ErrorCategory.VALIDATION, "rag_config.rerank_top_n must be 1–50.")
        out["rerank_top_n"] = n
    if "similarity_threshold" in raw:
        thr = raw["similarity_threshold"]
        if not isinstance(thr, (int, float)) or thr < 0 or thr > 1:
            raise AppError(
                ErrorCategory.VALIDATION,
                "rag_config.similarity_threshold must be between 0 and 1.",
            )
        out["similarity_threshold"] = float(thr)
    return out


def _normalize_name(name: str) -> str:
    clean = name.strip()
    if not clean or len(clean) > MAX_EXPERT_NAME_LENGTH:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"Expert name is required (max {MAX_EXPERT_NAME_LENGTH} chars).",
        )
    return clean


@dataclass(frozen=True, slots=True)
class ExpertUploadResult:
    """Result of ``ExpertService.upload_document_for_*_expert`` (Phase 3B)."""

    expert_id: uuid.UUID
    source_id: uuid.UUID
    document: Document
    reused: bool


def _enqueue_ingest(*, document_id: str, workspace_id: str, actor_id: str) -> str:
    """Lazy import to avoid pulling Celery / Redis at module import time.

    ``app.worker.tasks`` transitively depends on the pipeline module which
    imports back into ``app.experts`` — importing it eagerly at
    module scope creates an import cycle during test collection.
    """
    from app.worker.tasks import enqueue_ingest as _enqueue

    return _enqueue(
        document_id,
        mode="full",
        workspace_id=workspace_id,
        actor_id=actor_id,
    )


def _normalize_description(description: str | None) -> str | None:
    if description is None:
        return None
    clean = description.strip()
    if len(clean) > MAX_EXPERT_DESCRIPTION_LENGTH:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"description max length is {MAX_EXPERT_DESCRIPTION_LENGTH}.",
        )
    return clean or None


class ExpertService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        membership_sync: ExpertVectorMembershipSynchronizer | None = None,
        status_reconciler: ExpertStatusReconciler | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = ExpertRepository(db)
        self.access = ExpertAccessService(db)
        self.documents = DocumentRepository(db)
        self.workspaces = WorkspaceRepository(db)
        self._membership_sync = membership_sync
        self._status_reconciler = status_reconciler or ExpertStatusReconciler(db)

    @property
    def membership_sync(self) -> ExpertVectorMembershipSynchronizer:
        # Lazy so tests can swap the Qdrant/Redis-touching path without paying
        # its construction cost on every read-only ExpertService call.
        if self._membership_sync is None:
            self._membership_sync = ExpertVectorMembershipSynchronizer(
                self.db, self.settings
            )
        return self._membership_sync

    # ------------------------------------------------------------------
    # Post-commit sync helpers (Phase 3B)
    # ------------------------------------------------------------------

    def _sync_document_membership(self, document_id: uuid.UUID) -> None:
        """Best-effort Qdrant ``expert_ids`` sync for one Document.

        MUST be called after ``self.db.commit()`` for any mutation that changes
        which Experts link to this Document. Failures are logged but never
        raised — retrieval is still safe (filtered by workspace_id) and a
        background reconciliation job will catch up.
        """
        try:
            self.membership_sync.sync_document(document_id)
        except Exception as exc:  # noqa: BLE001 — best-effort background sync
            logger.warning(
                "expert_membership_sync.deferred",
                extra={"document_id": str(document_id), "error": str(exc)},
            )

    def _reconcile_status(self, expert_id: uuid.UUID) -> None:
        """Best-effort Expert-status reconciliation. Never raises."""
        try:
            self._status_reconciler.reconcile(expert_id)
        except Exception as exc:  # noqa: BLE001 — status derived from PG state
            logger.warning(
                "expert.status_reconcile_failed",
                extra={"expert_id": str(expert_id), "error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Workspace-facing
    # ------------------------------------------------------------------

    def list_for_workspace(self, workspace: Workspace) -> list[tuple[Expert, str]]:
        """Return (expert, ownership) pairs: owned Workspace + available Platform."""
        owned = [(e, "workspace") for e in self.repo.list_workspace_experts(workspace.id)]
        platform = [
            (e, "platform") for e in self.repo.list_available_platform_for_workspace(workspace.id)
        ]
        return owned + platform

    def create_workspace_expert(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        name: str,
        description: str | None = None,
        system_instructions: str | None = None,
        rag_config: dict[str, Any] | None = None,
        visibility: str | None = None,
        status: str | None = None,
        icon_url: str | None = None,
    ) -> Expert:
        # Ownership always from trusted RequestContext — never client-submitted workspace_id.
        ExpertPolicy.require(membership.role, ExpertAction.CREATE)
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(ErrorCategory.VALIDATION, "Experts require a tenant Workspace.")

        vis = visibility or ExpertVisibility.WORKSPACE.value
        if vis not in {ExpertVisibility.PRIVATE.value, ExpertVisibility.WORKSPACE.value}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid visibility for Workspace Expert.")
        st = status or ExpertStatus.DRAFT.value
        if st not in {s.value for s in ExpertStatus}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid Expert status.")

        expert = Expert(
            workspace_id=workspace.id,
            type=ExpertType.WORKSPACE.value,
            name=_normalize_name(name),
            description=_normalize_description(description),
            icon_url=(icon_url.strip() if icon_url else None),
            system_instructions=normalize_system_instructions(system_instructions),
            rag_config=normalize_rag_config(rag_config),
            status=st,
            visibility=vis,
            availability_mode=ExpertAvailabilityMode.SELECTED_WORKSPACES.value,
            created_by=actor.id,
        )
        self.repo.create(expert)
        self.db.commit()
        security_log(
            "expert.created",
            expert_id=str(expert.id),
            workspace_id=str(workspace.id),
            actor_id=str(actor.id),
            action="create",
            type=ExpertType.WORKSPACE.value,
        )
        return expert

    def get_for_workspace(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        expert_id: uuid.UUID,
        actor: User,
        action: ExpertAction = ExpertAction.VIEW,
    ) -> AuthorizedExpert:
        return self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=action,
            actor_id=actor.id,
        )

    def update_workspace_expert(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        system_instructions: str | None = None,
        rag_config: dict[str, Any] | None = None,
        visibility: str | None = None,
        status: str | None = None,
        icon_url: str | None = None,
    ) -> Expert:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.UPDATE,
            actor_id=actor.id,
        )
        expert = auth.expert
        if name is not None:
            expert.name = _normalize_name(name)
        if description is not None:
            expert.description = _normalize_description(description)
        if system_instructions is not None:
            expert.system_instructions = normalize_system_instructions(system_instructions)
        if rag_config is not None:
            expert.rag_config = normalize_rag_config(rag_config)
        if visibility is not None:
            if visibility not in {ExpertVisibility.PRIVATE.value, ExpertVisibility.WORKSPACE.value}:
                raise AppError(ErrorCategory.VALIDATION, "Invalid visibility for Workspace Expert.")
            expert.visibility = visibility
        if status is not None:
            if status not in {s.value for s in ExpertStatus}:
                raise AppError(ErrorCategory.VALIDATION, "Invalid Expert status.")
            expert.status = status
        if icon_url is not None:
            expert.icon_url = icon_url.strip() or None
        self.db.commit()
        security_log(
            "expert.updated",
            expert_id=str(expert.id),
            workspace_id=str(workspace.id),
            actor_id=str(actor.id),
            action="update",
        )
        return expert

    def delete_workspace_expert(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
    ) -> None:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.DELETE,
            actor_id=actor.id,
        )
        expert = auth.expert
        # Capture linked document IDs BEFORE soft-delete: after the commit the
        # ExpertVectorMembershipSynchronizer re-reads PG and will exclude this
        # Expert (deleted_at set), which is exactly the payload we want to
        # write to Qdrant on each affected Document.
        linked_doc_ids = [link.document_id for link in self.repo.list_document_links(expert.id)]
        # Soft-delete Expert; do NOT delete underlying Documents (may be shared).
        expert.soft_delete()
        self.db.commit()
        security_log(
            "expert.deleted",
            expert_id=str(expert.id),
            workspace_id=str(workspace.id),
            actor_id=str(actor.id),
            action="delete",
        )
        for doc_id in linked_doc_ids:
            self._sync_document_membership(doc_id)

    def link_document(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        document_id: uuid.UUID,
        source_id: uuid.UUID | None = None,
    ) -> ExpertDocument:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        return self._link_document_scoped(
            expert=auth.expert,
            expected_document_workspace_id=workspace.id,
            document_id=document_id,
            source_id=source_id,
            actor_id=actor.id,
        )

    def unlink_document(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        link = self.repo.get_document_link(auth.expert.id, document_id)
        if link is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Expert document link not found.")
        self.repo.delete_document_link(link)
        self.db.commit()
        security_log(
            "expert.document_unlinked",
            expert_id=str(expert_id),
            document_id=str(document_id),
            workspace_id=str(workspace.id),
            actor_id=str(actor.id),
            action="unlink",
        )
        self._sync_document_membership(document_id)
        self._reconcile_status(auth.expert.id)

    def list_linked_documents(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
    ) -> list[ExpertDocument]:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.VIEW,
            actor_id=actor.id,
        )
        # Platform Expert knowledge is not exposed on the Workspace product API
        # (Phase 3C) — raw Document bytes remain inaccessible via /api/documents.
        if auth.ownership == "platform" or auth.expert.type == ExpertType.PLATFORM.value:
            return []
        return self.repo.list_document_links(auth.expert.id)

    def list_knowledge_items(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
    ) -> list[tuple[ExpertDocument, Document]]:
        """Return (link, document) pairs for Workspace Expert knowledge UI."""
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.VIEW,
            actor_id=actor.id,
        )
        if auth.ownership == "platform" or auth.expert.type == ExpertType.PLATFORM.value:
            return []

        links = self.repo.list_document_links(auth.expert.id)
        if not links:
            return []
        doc_ids = [link.document_id for link in links]
        docs = {
            d.id: d
            for d in self.db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
        }
        return [(link, docs[link.document_id]) for link in links if link.document_id in docs]

    def count_linked_documents(self, expert_id: uuid.UUID) -> int:
        return self.repo.count_document_links(expert_id)

    def create_upload_source(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        name: str | None = None,
    ) -> ExpertSource:
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        # Phase 3B: newly-created upload sources start PENDING; the source
        # only becomes PROCESSING once an actual upload has been attached
        # and dispatched to the ingest pipeline.
        source = ExpertSource(
            expert_id=auth.expert.id,
            type=ExpertSourceType.UPLOAD.value,
            name=(name.strip() if name else None),
            status=ExpertSourceStatus.PENDING.value,
            config={},
            created_by=actor.id,
        )
        self.repo.create_source(source)
        self.db.commit()
        security_log(
            "expert.source_created",
            expert_id=str(expert_id),
            source_id=str(source.id),
            workspace_id=str(workspace.id),
            actor_id=str(actor.id),
            action="create_source",
        )
        return source

    def soft_delete_source(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> None:
        """Soft-delete a source. Does not hard-delete Documents (may be linked elsewhere)."""
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        source = self.repo.get_source(auth.expert.id, source_id)
        if source is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Expert source not found.")
        source.soft_delete()
        self.db.commit()
        security_log(
            "expert.source_deleted",
            expert_id=str(expert_id),
            source_id=str(source_id),
            workspace_id=str(workspace.id),
            actor_id=str(actor.id),
            action="delete_source",
        )

    def _link_document_scoped(
        self,
        *,
        expert: Expert,
        expected_document_workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        source_id: uuid.UUID | None,
        actor_id: uuid.UUID,
    ) -> ExpertDocument:
        # Scoped lookup — never Document.get globally then compare loosely.
        document = self.documents.get_for_workspace(expected_document_workspace_id, document_id)
        if document is None:
            security_log(
                "expert.document_link_denied",
                expert_id=str(expert.id),
                document_id=str(document_id),
                actor_id=str(actor_id),
                reason="document_scope_mismatch",
            )
            raise AppError(ErrorCategory.DOCUMENT_NOT_FOUND, "Document not found.")

        if expert.is_workspace_expert:
            if expert.workspace_id != expected_document_workspace_id:
                raise AppError(ErrorCategory.VALIDATION, "Cross-scope Expert/Document link denied.")
        elif expert.is_platform_expert:
            pk = WorkspaceService(self.db, self.settings).get_platform_knowledge_workspace()
            if expected_document_workspace_id != pk.id:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Platform Experts may only link Platform Knowledge Documents.",
                )
        else:
            raise AppError(ErrorCategory.VALIDATION, "Unknown Expert type.")

        if source_id is not None:
            source = self.repo.get_source(expert.id, source_id)
            if source is None:
                raise AppError(ErrorCategory.NOT_FOUND, "Expert source not found.")

        existing = self.repo.get_document_link(expert.id, document_id)
        if existing is not None:
            raise AppError(ErrorCategory.CONFLICT, "Document already linked to this Expert.")

        link = ExpertDocument(
            expert_id=expert.id,
            document_id=document_id,
            source_id=source_id,
        )
        try:
            self.repo.create_document_link(link)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(ErrorCategory.CONFLICT, "Document already linked to this Expert.") from exc

        security_log(
            "expert.document_linked",
            expert_id=str(expert.id),
            document_id=str(document_id),
            actor_id=str(actor_id),
            action="link",
            expert_type=expert.type,
        )
        self._sync_document_membership(document_id)
        self._reconcile_status(expert.id)
        return link

    # ------------------------------------------------------------------
    # Expert-scoped upload (Phase 3B)
    # ------------------------------------------------------------------

    def upload_document_for_workspace_expert(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        declared_mime_type: str | None = None,
    ) -> "ExpertUploadResult":
        """Upload a Document via a Workspace Expert.

        Behavior:
        * Authorizes MANAGE_KNOWLEDGE on the target Expert.
        * Uploads to the Expert's Workspace (dedupe by sha256; reuse on hit).
        * Creates or reuses the ``expert_documents`` link.
        * Creates an ``ExpertSource`` (upload) in PENDING; flips to PROCESSING
          when a new Document is ingested, or READY when reusing a doc that
          is already ready.
        * Enqueues ingest only when a genuinely new Document was created; a
          reused Document that is still processing keeps its existing job.
        """
        auth = self.access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.MANAGE_KNOWLEDGE,
            actor_id=actor.id,
        )
        if auth.expert.type != ExpertType.WORKSPACE.value:
            raise AppError(
                ErrorCategory.EXPERT_IMMUTABLE,
                "Platform Experts cannot be modified through Workspace APIs.",
            )
        return self._upload_document_for_expert(
            expert=auth.expert,
            knowledge_workspace=workspace,
            actor=actor,
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            declared_mime_type=declared_mime_type,
        )

    def upload_document_for_platform_expert(
        self,
        *,
        actor: User,
        expert_id: uuid.UUID,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
        declared_mime_type: str | None = None,
    ) -> "ExpertUploadResult":
        """Privileged Platform-Expert upload (Platform Knowledge Workspace)."""
        expert = self.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        pk = WorkspaceService(self.db, self.settings).get_platform_knowledge_workspace()
        return self._upload_document_for_expert(
            expert=expert,
            knowledge_workspace=pk,
            actor=actor,
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            declared_mime_type=declared_mime_type,
            audit_event="expert.platform_document_uploaded",
        )

    def _upload_document_for_expert(
        self,
        *,
        expert: Expert,
        knowledge_workspace: Workspace,
        actor: User,
        file_bytes: bytes,
        filename: str,
        title: str | None,
        declared_mime_type: str | None,
        audit_event: str = "expert.document_uploaded",
    ) -> "ExpertUploadResult":
        # 1. Upload (or reuse) the Document in the knowledge Workspace.
        docs = DocumentService(self.db, self.settings)
        upload: WorkspaceUploadResult = docs.upload_for_workspace_or_link_existing(
            knowledge_workspace,
            file_bytes,
            filename,
            title=title,
            declared_mime_type=declared_mime_type,
        )
        document = upload.document

        # 2. Create the upload source in PENDING (post-upload so we don't
        #    orphan a source if validation failed).
        source = ExpertSource(
            expert_id=expert.id,
            type=ExpertSourceType.UPLOAD.value,
            name=(document.original_filename or None),
            status=ExpertSourceStatus.PENDING.value,
            config={},
            created_by=actor.id,
        )
        self.repo.create_source(source)
        self.db.commit()

        # 3. Ensure link exists (reuse if it does — same Document may already
        #    be linked to another Expert in this Workspace).
        link = self.repo.get_document_link(expert.id, document.id)
        if link is None:
            link = self._link_document_scoped(
                expert=expert,
                expected_document_workspace_id=knowledge_workspace.id,
                document_id=document.id,
                source_id=source.id,
                actor_id=actor.id,
            )
        else:
            # Attach the new source_id to the existing link so audits trace
            # back to whoever uploaded most recently.
            link.source_id = source.id
            self.db.commit()
            self._sync_document_membership(document.id)
            self._reconcile_status(expert.id)

        # 4. Enqueue ingest only for genuinely new Documents. A reused
        #    Document that is ready keeps its indexed chunks; one that is
        #    still processing already has an ingest job in-flight.
        if not upload.reused:
            enqueued_id = _enqueue_ingest(
                document_id=str(document.id),
                workspace_id=str(knowledge_workspace.id),
                actor_id=str(actor.id),
            )
            source.status = ExpertSourceStatus.PROCESSING.value
            source.config = {**(source.config or {}), "task_id": enqueued_id}
            self.db.commit()
        else:
            # Sync source status to the reused Document's ingestion state so
            # UIs can render an accurate "attached / processing / ready" pill.
            if document.status == "ready":
                source.status = ExpertSourceStatus.READY.value
            elif document.status == "failed":
                source.status = ExpertSourceStatus.FAILED.value
            else:
                source.status = ExpertSourceStatus.PROCESSING.value
            self.db.commit()

        security_log(
            audit_event,
            expert_id=str(expert.id),
            source_id=str(source.id),
            document_id=str(document.id),
            workspace_id=str(knowledge_workspace.id),
            actor_id=str(actor.id),
            action="expert_upload",
            reused=upload.reused,
            expert_type=expert.type,
        )
        return ExpertUploadResult(
            expert_id=expert.id,
            source_id=source.id,
            document=document,
            reused=upload.reused,
        )

    # ------------------------------------------------------------------
    # Platform admin (privileged)
    # ------------------------------------------------------------------

    def create_platform_expert(
        self,
        *,
        actor: User,
        name: str,
        description: str | None = None,
        system_instructions: str | None = None,
        rag_config: dict[str, Any] | None = None,
        visibility: str | None = None,
        status: str | None = None,
        availability_mode: str | None = None,
        icon_url: str | None = None,
    ) -> Expert:
        ExpertPolicy.require_platform_admin(actor.platform_role)
        vis = visibility or ExpertVisibility.PLATFORM_DRAFT.value
        if vis not in {
            ExpertVisibility.PLATFORM_DRAFT.value,
            ExpertVisibility.PLATFORM_PUBLISHED.value,
        }:
            raise AppError(ErrorCategory.VALIDATION, "Invalid visibility for Platform Expert.")
        st = status or ExpertStatus.DRAFT.value
        if st not in {s.value for s in ExpertStatus}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid Expert status.")
        mode = availability_mode or ExpertAvailabilityMode.SELECTED_WORKSPACES.value
        if mode not in {m.value for m in ExpertAvailabilityMode}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid availability_mode.")

        expert = Expert(
            workspace_id=None,
            type=ExpertType.PLATFORM.value,
            name=_normalize_name(name),
            description=_normalize_description(description),
            icon_url=(icon_url.strip() if icon_url else None),
            system_instructions=normalize_system_instructions(system_instructions),
            rag_config=normalize_rag_config(rag_config),
            status=st,
            visibility=vis,
            availability_mode=mode,
            created_by=actor.id,
        )
        self.repo.create(expert)
        self.db.commit()
        security_log(
            "expert.platform_created",
            expert_id=str(expert.id),
            actor_id=str(actor.id),
            action="create",
            visibility=vis,
        )
        return expert

    def update_platform_expert(
        self,
        *,
        actor: User,
        expert_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        system_instructions: str | None = None,
        rag_config: dict[str, Any] | None = None,
        visibility: str | None = None,
        status: str | None = None,
        availability_mode: str | None = None,
        icon_url: str | None = None,
    ) -> Expert:
        expert = self.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        prev_vis = expert.visibility
        if name is not None:
            expert.name = _normalize_name(name)
        if description is not None:
            expert.description = _normalize_description(description)
        if system_instructions is not None:
            expert.system_instructions = normalize_system_instructions(system_instructions)
        if rag_config is not None:
            expert.rag_config = normalize_rag_config(rag_config)
        if visibility is not None:
            if visibility not in {
                ExpertVisibility.PLATFORM_DRAFT.value,
                ExpertVisibility.PLATFORM_PUBLISHED.value,
            }:
                raise AppError(ErrorCategory.VALIDATION, "Invalid visibility for Platform Expert.")
            expert.visibility = visibility
        if status is not None:
            if status not in {s.value for s in ExpertStatus}:
                raise AppError(ErrorCategory.VALIDATION, "Invalid Expert status.")
            expert.status = status
        if availability_mode is not None:
            if availability_mode not in {m.value for m in ExpertAvailabilityMode}:
                raise AppError(ErrorCategory.VALIDATION, "Invalid availability_mode.")
            expert.availability_mode = availability_mode
        if icon_url is not None:
            expert.icon_url = icon_url.strip() or None
        self.db.commit()
        event = "expert.platform_updated"
        if prev_vis != expert.visibility:
            event = (
                "expert.platform_published"
                if expert.visibility == ExpertVisibility.PLATFORM_PUBLISHED.value
                else "expert.platform_unpublished"
            )
        security_log(
            event,
            expert_id=str(expert.id),
            actor_id=str(actor.id),
            action="update",
            visibility=expert.visibility,
        )
        return expert

    def delete_platform_expert(self, *, actor: User, expert_id: uuid.UUID) -> None:
        expert = self.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        linked_doc_ids = [link.document_id for link in self.repo.list_document_links(expert.id)]
        expert.soft_delete()
        self.db.commit()
        security_log(
            "expert.platform_deleted",
            expert_id=str(expert.id),
            actor_id=str(actor.id),
            action="delete",
        )
        for doc_id in linked_doc_ids:
            self._sync_document_membership(doc_id)

    def list_platform_experts(self, *, actor: User) -> list[Expert]:
        ExpertPolicy.require_platform_admin(actor.platform_role)
        return self.repo.list_platform_experts(include_drafts=True)

    def grant_platform_expert(
        self,
        *,
        actor: User,
        expert_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> WorkspaceExpertGrant:
        expert = self.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        if expert.type != ExpertType.PLATFORM.value:
            raise AppError(ErrorCategory.VALIDATION, "Only Platform Experts may be granted.")

        workspace = self.workspaces.get_by_id(workspace_id)
        if workspace is None or workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")

        existing = self.repo.get_grant(workspace_id, expert_id)
        if existing is not None:
            return existing

        grant = WorkspaceExpertGrant(
            workspace_id=workspace_id,
            expert_id=expert_id,
            created_by=actor.id,
        )
        self.repo.create_grant(grant)
        self.db.commit()
        security_log(
            "expert.grant_created",
            expert_id=str(expert_id),
            workspace_id=str(workspace_id),
            actor_id=str(actor.id),
            action="grant",
        )
        return grant

    def revoke_platform_expert(
        self,
        *,
        actor: User,
        expert_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        self.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        grant = self.repo.get_grant(workspace_id, expert_id)
        if grant is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Grant not found.")
        self.repo.delete_grant(grant)
        self.db.commit()
        security_log(
            "expert.grant_revoked",
            expert_id=str(expert_id),
            workspace_id=str(workspace_id),
            actor_id=str(actor.id),
            action="revoke",
        )

    def link_platform_document(
        self,
        *,
        actor: User,
        expert_id: uuid.UUID,
        document_id: uuid.UUID,
        source_id: uuid.UUID | None = None,
    ) -> ExpertDocument:
        expert = self.access.require_platform_admin_expert(
            expert_id=expert_id,
            platform_role=actor.platform_role,
            actor_id=actor.id,
        )
        pk = WorkspaceService(self.db, self.settings).get_platform_knowledge_workspace()
        return self._link_document_scoped(
            expert=expert,
            expected_document_workspace_id=pk.id,
            document_id=document_id,
            source_id=source_id,
            actor_id=actor.id,
        )

    def upload_platform_knowledge_document(
        self,
        *,
        actor: User,
        file_bytes: bytes,
        filename: str,
        title: str | None = None,
    ):
        """Privileged upload into Platform Knowledge Workspace (not tenant Document APIs)."""
        ExpertPolicy.require_platform_admin(actor.platform_role)
        pk = WorkspaceService(self.db, self.settings).get_platform_knowledge_workspace()
        doc = DocumentService(self.db, self.settings).upload_for_workspace(
            pk, file_bytes, filename, title=title
        )
        security_log(
            "platform_knowledge.document_uploaded",
            workspace_id=str(pk.id),
            document_id=str(doc.id),
            actor_id=str(actor.id),
            action="platform_upload",
        )
        return doc
