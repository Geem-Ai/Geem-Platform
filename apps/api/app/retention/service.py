"""Soft-delete retention + retry-safe permanent purge (Phase 11A).

Postgres mutations for one entity are transactional. MinIO/Qdrant cleanup is
best-effort and retried on the next run — never a fake distributed TX.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey
from app.apps_catalog.models import (
    AppInstallation,
    AppInstallationStatus,
    AppLicense,
    AppLicenseStatus,
    AppSubscription,
    AppSubscriptionStatus,
)
from app.audit import AuditAction, AuditEntityType, record_audit
from app.billing.models import Subscription, SubscriptionStatus
from app.chat_attachments.models import ChatAttachment
from app.common.security_log import security_log
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import (
    AppConnection,
    ChannelBinding,
    ChannelConversationBinding,
    ConnectorItem,
    ConnectorSyncRun,
    ConnectorWebhookEvent,
)
from app.connectors.repository import ConnectorRepository
from app.connectors.types import ConnectionHealth, ConnectionStatus
from app.conversations.models import Conversation, Message
from app.core.config import Settings, get_settings
from app.observability.tracing import start_span
from app.db.models import Document, IngestionJob
from app.documents.service import DocumentService
from app.experts.membership_sync import ExpertVectorMembershipSynchronizer
from app.experts.models import (
    Expert,
    ExpertDocument,
    ExpertSource,
    ExpertType,
    WorkspaceExpertGrant,
)
from app.usage.models import AiUsageReservation, StorageReservation
from app.widgets.models import WidgetConversationBinding, WidgetInstance, WidgetInstanceStatus
from app.workspaces.models import (
    Workspace,
    WorkspaceInvitation,
    WorkspaceKind,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceRolePermission,
    WorkspaceStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class PurgeBatchResult:
    scanned: int = 0
    purged: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "purged": self.purged,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors[:20],
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class RetentionPurgeService:
    """Permanent cleanup of soft-deleted Workspace / Expert / Conversation rows."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.batch_size = max(1, int(self.settings.purge_batch_size))
        self.retention_days = max(0, int(self.settings.soft_delete_retention_days))

    def cutoff(self, *, now: datetime | None = None) -> datetime:
        when = _aware(now) or _now()
        return when - timedelta(days=self.retention_days)

    # ------------------------------------------------------------------
    # Sweep entry points (idempotent, bounded)
    # ------------------------------------------------------------------

    def purge_deleted_conversations(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> PurgeBatchResult:
        cutoff = self.cutoff(now=now)
        batch = limit or self.batch_size
        ids = list(
            self.db.scalars(
                select(Conversation.id)
                .where(
                    Conversation.deleted_at.is_not(None),
                    Conversation.deleted_at <= cutoff,
                )
                .order_by(Conversation.deleted_at.asc())
                .limit(batch)
            )
        )
        result = PurgeBatchResult(scanned=len(ids))
        for conversation_id in ids:
            try:
                if self.purge_conversation(conversation_id, now=now):
                    result.purged += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                self.db.rollback()
                result.failed += 1
                result.errors.append(f"conversation:{conversation_id}:{exc}")
                logger.exception(
                    "retention.conversation_purge_failed",
                    extra={"conversation_id": str(conversation_id)},
                )
        logger.info("retention.conversations_purged", extra=result.as_dict())
        return result

    def purge_deleted_experts(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> PurgeBatchResult:
        cutoff = self.cutoff(now=now)
        batch = limit or self.batch_size
        ids = list(
            self.db.scalars(
                select(Expert.id)
                .where(
                    Expert.deleted_at.is_not(None),
                    Expert.deleted_at <= cutoff,
                    Expert.type == ExpertType.WORKSPACE.value,
                )
                .order_by(Expert.deleted_at.asc())
                .limit(batch)
            )
        )
        result = PurgeBatchResult(scanned=len(ids))
        for expert_id in ids:
            try:
                if self.purge_expert(expert_id, now=now):
                    result.purged += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                self.db.rollback()
                result.failed += 1
                result.errors.append(f"expert:{expert_id}:{exc}")
                logger.exception(
                    "retention.expert_purge_failed", extra={"expert_id": str(expert_id)}
                )
        logger.info("retention.experts_purged", extra=result.as_dict())
        return result

    def purge_deleted_workspaces(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> PurgeBatchResult:
        cutoff = self.cutoff(now=now)
        batch = limit or self.batch_size
        ids = list(
            self.db.scalars(
                select(Workspace.id)
                .where(
                    Workspace.deleted_at.is_not(None),
                    Workspace.deleted_at <= cutoff,
                    Workspace.purged_at.is_(None),
                    Workspace.kind == WorkspaceKind.TENANT.value,
                )
                .order_by(Workspace.deleted_at.asc())
                .limit(batch)
            )
        )
        result = PurgeBatchResult(scanned=len(ids))
        for workspace_id in ids:
            try:
                if self.purge_workspace(workspace_id, now=now):
                    result.purged += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                self.db.rollback()
                result.failed += 1
                result.errors.append(f"workspace:{workspace_id}:{exc}")
                logger.exception(
                    "retention.workspace_purge_failed",
                    extra={"workspace_id": str(workspace_id)},
                )
        logger.info("retention.workspaces_purged", extra=result.as_dict())
        return result

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def purge_conversation(
        self, conversation_id: uuid.UUID, *, now: datetime | None = None
    ) -> bool:
        """Hard-delete a conversation after retention. Missing row = success."""
        conversation = self.db.get(Conversation, conversation_id)
        if conversation is None:
            return True
        deleted_at = _aware(conversation.deleted_at)
        if deleted_at is None:
            return False
        if deleted_at > self.cutoff(now=now):
            return False

        workspace_id = conversation.workspace_id
        self.db.execute(
            delete(Message).where(Message.conversation_id == conversation_id)
        )
        self.db.execute(
            delete(ChannelConversationBinding).where(
                ChannelConversationBinding.conversation_id == conversation_id,
                ChannelConversationBinding.workspace_id == workspace_id,
            )
        )
        self.db.execute(
            delete(WidgetConversationBinding).where(
                WidgetConversationBinding.conversation_id == conversation_id,
                WidgetConversationBinding.workspace_id == workspace_id,
            )
        )
        self.db.delete(conversation)
        record_audit(
            self.db,
            action=AuditAction.CONVERSATION_PURGED,
            entity_type=AuditEntityType.CONVERSATION,
            entity_id=conversation_id,
            workspace_id=workspace_id,
            metadata={"retention_days": self.retention_days},
            required=False,
        )
        self.db.commit()
        security_log(
            "conversation.purged",
            conversation_id=str(conversation_id),
            workspace_id=str(workspace_id),
        )
        return True

    # ------------------------------------------------------------------
    # Expert
    # ------------------------------------------------------------------

    def purge_expert(self, expert_id: uuid.UUID, *, now: datetime | None = None) -> bool:
        expert = self.db.get(Expert, expert_id)
        if expert is None:
            return True
        deleted_at = _aware(expert.deleted_at)
        if deleted_at is None:
            return False
        if deleted_at > self.cutoff(now=now):
            return False
        if expert.type != ExpertType.WORKSPACE.value:
            return False

        workspace_id = expert.workspace_id
        if workspace_id is None:
            return False

        linked_doc_ids = list(
            self.db.scalars(
                select(ExpertDocument.document_id).where(ExpertDocument.expert_id == expert_id)
            )
        )

        conv_ids = list(
            self.db.scalars(
                select(Conversation.id).where(
                    Conversation.expert_id == expert_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
        )
        for conv_id in conv_ids:
            row = self.db.get(Conversation, conv_id)
            if row is None:
                continue
            if row.deleted_at is None:
                row.soft_delete(when=_now())
            self.db.flush()
            # Force eligibility for this expert's conversation graph.
            row.deleted_at = self.cutoff(now=now) - timedelta(seconds=1)
            self.purge_conversation(conv_id, now=now)
            # purge_conversation commits; reload session state
            expert = self.db.get(Expert, expert_id)
            if expert is None:
                return False

        self.db.execute(
            update(WidgetInstance)
            .where(
                WidgetInstance.expert_id == expert_id,
                WidgetInstance.workspace_id == workspace_id,
            )
            .values(expert_id=None)
        )
        self.db.execute(
            update(ChannelBinding)
            .where(
                ChannelBinding.expert_id == expert_id,
                ChannelBinding.workspace_id == workspace_id,
            )
            .values(expert_id=None, enabled=False)
        )
        self.db.execute(delete(WorkspaceExpertGrant).where(WorkspaceExpertGrant.expert_id == expert_id))
        self.db.execute(delete(ExpertDocument).where(ExpertDocument.expert_id == expert_id))
        self.db.execute(delete(ExpertSource).where(ExpertSource.expert_id == expert_id))
        self.db.delete(expert)
        record_audit(
            self.db,
            action=AuditAction.EXPERT_PURGED,
            entity_type=AuditEntityType.EXPERT,
            entity_id=expert_id,
            workspace_id=workspace_id,
            metadata={"document_links_removed": len(linked_doc_ids)},
            required=False,
        )
        self.db.commit()

        sync = ExpertVectorMembershipSynchronizer(self.db)
        for doc_id in linked_doc_ids:
            try:
                sync.sync_document(doc_id)
            except Exception as exc:  # noqa: BLE001 — Qdrant retry on next sweep
                logger.warning(
                    "retention.expert_vector_sync_failed",
                    extra={"document_id": str(doc_id), "error": str(exc)},
                )

        security_log(
            "expert.purged",
            expert_id=str(expert_id),
            workspace_id=str(workspace_id),
        )
        return True

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def purge_workspace(
        self, workspace_id: uuid.UUID, *, now: datetime | None = None
    ) -> bool:
        """Retire tenant-owned resources; keep a billing/audit tombstone row.

        Authority is the stored ``deleted_at`` + retention cutoff — never a
        caller-supplied workspace id alone.
        """
        workspace = self.db.get(Workspace, workspace_id)
        if workspace is None:
            return True
        if workspace.kind != WorkspaceKind.TENANT.value:
            return False
        if workspace.purged_at is not None:
            return True
        deleted_at = _aware(workspace.deleted_at)
        if deleted_at is None or deleted_at > self.cutoff(now=now):
            return False

        with start_span("workspace.purge", workspace_id=str(workspace_id)):
            self._retire_access(workspace_id)
            self._retire_connectors(workspace_id)
            self._retire_widgets_and_attachments(workspace_id)
            self._purge_workspace_conversations(workspace_id, now=now)
            self._purge_workspace_experts(workspace_id, now=now)
            self._purge_workspace_documents(workspace_id)
            self._cancel_commercial_access(workspace_id)
            self._delete_operational_rows(workspace_id)
            leftover = self._remaining_tenant_graph(workspace_id)
            if leftover:
                logger.error(
                    "retention.workspace_purge_incomplete",
                    extra={"workspace_id": str(workspace_id), "leftover": leftover},
                )
                self.db.commit()
                return False
            workspace = self.db.get(Workspace, workspace_id)
            if workspace is None:
                return True
            self._anonymize_tombstone(workspace, now=now)
            record_audit(
                self.db,
                action=AuditAction.WORKSPACE_PURGED,
                entity_type=AuditEntityType.WORKSPACE,
                entity_id=workspace_id,
                workspace_id=workspace_id,
                metadata={"tombstone": True},
                required=False,
            )
            self.db.commit()
            security_log("workspace.purged", workspace_id=str(workspace_id))
            return True

    def _retire_access(self, workspace_id: uuid.UUID) -> None:
        stamp = _now()
        self.db.execute(
            update(ApiKey)
            .where(ApiKey.workspace_id == workspace_id, ApiKey.revoked_at.is_(None))
            .values(revoked_at=stamp)
        )
        self.db.execute(
            update(WorkspaceInvitation)
            .where(
                WorkspaceInvitation.workspace_id == workspace_id,
                WorkspaceInvitation.revoked_at.is_(None),
                WorkspaceInvitation.accepted_at.is_(None),
            )
            .values(revoked_at=stamp)
        )
        self.db.flush()

    def _retire_connectors(self, workspace_id: uuid.UUID) -> None:
        creds = ConnectorCredentialService(self.db, settings=self.settings)
        repo = ConnectorRepository(self.db)
        rows = list(
            self.db.scalars(
                select(AppConnection).where(AppConnection.workspace_id == workspace_id)
            )
        )
        for row in rows:
            creds.clear_all_secrets(row)
            row.status = ConnectionStatus.REVOKED.value
            row.disconnected_at = row.disconnected_at or _now()
            row.health = ConnectionHealth.UNKNOWN.value
            self.db.flush()
            repo.purge_connection(row)

    def _retire_widgets_and_attachments(self, workspace_id: uuid.UUID) -> None:
        from app.storage.minio_storage import MinioObjectStorage

        storage = MinioObjectStorage()
        attachments = list(
            self.db.scalars(
                select(ChatAttachment).where(ChatAttachment.workspace_id == workspace_id)
            )
        )
        for row in attachments:
            try:
                storage.delete(row.storage_key)
            except Exception as exc:  # noqa: BLE001 — retry-safe external cleanup
                logger.warning(
                    "retention.chat_attachment_minio_failed",
                    extra={"attachment_id": str(row.id), "error": str(exc)},
                )
            self.db.delete(row)
        self.db.execute(
            update(WidgetInstance)
            .where(WidgetInstance.workspace_id == workspace_id)
            .values(status=WidgetInstanceStatus.DISABLED.value, expert_id=None)
        )
        self.db.flush()

    def _purge_workspace_conversations(
        self, workspace_id: uuid.UUID, *, now: datetime | None
    ) -> None:
        stamp = self.cutoff(now=now) - timedelta(seconds=1)
        self.db.execute(
            update(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .values(deleted_at=stamp)
        )
        self.db.commit()
        while True:
            ids = list(
                self.db.scalars(
                    select(Conversation.id)
                    .where(Conversation.workspace_id == workspace_id)
                    .limit(self.batch_size)
                )
            )
            if not ids:
                break
            progressed = False
            for conv_id in ids:
                row = self.db.get(Conversation, conv_id)
                if row is None:
                    continue
                if row.deleted_at is None:
                    row.deleted_at = stamp
                if self.purge_conversation(conv_id, now=now):
                    progressed = True
            if not progressed:
                logger.error(
                    "retention.workspace_conversations_stuck",
                    extra={"workspace_id": str(workspace_id), "ids": [str(i) for i in ids]},
                )
                break

    def _purge_workspace_experts(
        self, workspace_id: uuid.UUID, *, now: datetime | None
    ) -> None:
        stamp = self.cutoff(now=now) - timedelta(seconds=1)
        self.db.execute(
            update(Expert)
            .where(
                Expert.workspace_id == workspace_id,
                Expert.type == ExpertType.WORKSPACE.value,
            )
            .values(deleted_at=stamp)
        )
        self.db.commit()
        while True:
            ids = list(
                self.db.scalars(
                    select(Expert.id).where(
                        Expert.workspace_id == workspace_id,
                        Expert.type == ExpertType.WORKSPACE.value,
                    ).limit(self.batch_size)
                )
            )
            if not ids:
                break
            progressed = False
            for expert_id in ids:
                row = self.db.get(Expert, expert_id)
                if row is None:
                    continue
                if row.deleted_at is None:
                    row.deleted_at = stamp
                if self.purge_expert(expert_id, now=now):
                    progressed = True
            if not progressed:
                logger.error(
                    "retention.workspace_experts_stuck",
                    extra={"workspace_id": str(workspace_id), "ids": [str(i) for i in ids]},
                )
                break

        self.db.execute(
            delete(WorkspaceExpertGrant).where(WorkspaceExpertGrant.workspace_id == workspace_id)
        )
        self.db.flush()

    def _purge_workspace_documents(self, workspace_id: uuid.UUID) -> None:
        workspace = self.db.get(Workspace, workspace_id)
        if workspace is None:
            return
        docs = DocumentService(self.db, self.settings)
        while True:
            ids = list(
                self.db.scalars(
                    select(Document.id)
                    .where(Document.workspace_id == workspace_id)
                    .limit(self.batch_size)
                )
            )
            if not ids:
                break
            remaining_before = set(ids)
            for document_id in ids:
                docs.purge_document_lifecycle(workspace_id, document_id)
            leftover = set(
                self.db.scalars(
                    select(Document.id).where(Document.id.in_(remaining_before))
                )
            )
            if leftover == remaining_before:
                logger.error(
                    "retention.workspace_documents_stuck",
                    extra={
                        "workspace_id": str(workspace_id),
                        "ids": [str(i) for i in leftover],
                    },
                )
                break

    def _cancel_commercial_access(self, workspace_id: uuid.UUID) -> None:
        stamp = _now()
        self.db.execute(
            update(Subscription)
            .where(
                Subscription.workspace_id == workspace_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .values(status=SubscriptionStatus.CANCELED.value, ends_at=stamp)
        )
        self.db.execute(
            update(AppLicense)
            .where(
                AppLicense.workspace_id == workspace_id,
                AppLicense.status == AppLicenseStatus.ACTIVE.value,
            )
            .values(status=AppLicenseStatus.REVOKED.value, revoked_at=stamp)
        )
        self.db.execute(
            update(AppSubscription)
            .where(
                AppSubscription.workspace_id == workspace_id,
                AppSubscription.status == AppSubscriptionStatus.ACTIVE.value,
            )
            .values(status=AppSubscriptionStatus.CANCELLED.value)
        )
        self.db.execute(
            update(AppInstallation)
            .where(
                AppInstallation.workspace_id == workspace_id,
                AppInstallation.status == AppInstallationStatus.ACTIVE.value,
            )
            .values(
                status=AppInstallationStatus.UNINSTALLED.value,
                uninstalled_at=stamp,
                config_encrypted=None,
            )
        )
        self.db.execute(
            update(AppInstallation)
            .where(AppInstallation.workspace_id == workspace_id)
            .values(config_encrypted=None)
        )
        self.db.flush()

    def _delete_operational_rows(self, workspace_id: uuid.UUID) -> None:
        self.db.execute(
            delete(AiUsageReservation).where(AiUsageReservation.workspace_id == workspace_id)
        )
        self.db.execute(
            delete(StorageReservation).where(StorageReservation.workspace_id == workspace_id)
        )
        self.db.execute(
            delete(IngestionJob).where(
                IngestionJob.document_id.in_(
                    select(Document.id).where(Document.workspace_id == workspace_id)
                )
            )
        )
        self.db.execute(
            delete(WidgetConversationBinding).where(
                WidgetConversationBinding.workspace_id == workspace_id
            )
        )
        self.db.execute(delete(WidgetInstance).where(WidgetInstance.workspace_id == workspace_id))
        self.db.execute(
            delete(ChannelConversationBinding).where(
                ChannelConversationBinding.workspace_id == workspace_id
            )
        )
        self.db.execute(delete(ChannelBinding).where(ChannelBinding.workspace_id == workspace_id))
        self.db.execute(
            delete(ConnectorWebhookEvent).where(ConnectorWebhookEvent.workspace_id == workspace_id)
        )
        self.db.execute(delete(ConnectorItem).where(ConnectorItem.workspace_id == workspace_id))
        self.db.execute(
            delete(ConnectorSyncRun).where(ConnectorSyncRun.workspace_id == workspace_id)
        )
        self.db.execute(
            delete(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id)
        )
        self.db.execute(
            delete(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id)
        )
        role_ids = select(WorkspaceRoleDef.id).where(WorkspaceRoleDef.workspace_id == workspace_id)
        self.db.execute(delete(WorkspaceRolePermission).where(WorkspaceRolePermission.role_id.in_(role_ids)))
        self.db.execute(delete(WorkspaceRoleDef).where(WorkspaceRoleDef.workspace_id == workspace_id))
        self.db.flush()

    def _remaining_tenant_graph(self, workspace_id: uuid.UUID) -> list[str]:
        leftover: list[str] = []
        if self.db.scalar(
            select(Conversation.id).where(Conversation.workspace_id == workspace_id).limit(1)
        ):
            leftover.append("conversations")
        if self.db.scalar(
            select(Expert.id).where(
                Expert.workspace_id == workspace_id,
                Expert.type == ExpertType.WORKSPACE.value,
            ).limit(1)
        ):
            leftover.append("experts")
        if self.db.scalar(
            select(Document.id).where(Document.workspace_id == workspace_id).limit(1)
        ):
            leftover.append("documents")
        return leftover

    def _anonymize_tombstone(self, workspace: Workspace, *, now: datetime | None) -> None:
        when = _aware(now) or _now()
        workspace.name = "Deleted workspace"
        workspace.slug = f"deleted-{workspace.id.hex[:12]}"
        workspace.created_by = None
        workspace.settings = {"purged": True}
        workspace.status = WorkspaceStatus.ARCHIVED.value
        if workspace.deleted_at is None:
            workspace.deleted_at = when
        workspace.purged_at = when
        self.db.flush()
