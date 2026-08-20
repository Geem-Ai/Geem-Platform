"""Chat attachment persistence + secure MinIO lifecycle."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.chat_attachments.models import ChatAttachment
from app.chat_attachments.storage_keys import chat_attachment_storage_key
from app.chat_attachments.validation import inspect_chat_attachment
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.storage.minio_storage import MinioObjectStorage
from app.usage.storage import StorageHold, StorageQuotaService
from app.workspaces.lifecycle import require_active_workspace
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)


class ChatAttachmentService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        storage: MinioObjectStorage | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage or MinioObjectStorage(self.settings)

    def upload(
        self,
        *,
        workspace: Workspace,
        actor: User,
        file_bytes: bytes,
        filename: str,
        declared_mime_type: str | None = None,
    ) -> ChatAttachment:
        self._require_active_workspace(workspace)
        inspection = inspect_chat_attachment(
            file_bytes,
            filename,
            settings=self.settings,
            declared_mime_type=declared_mime_type,
        )

        attachment_id = uuid.uuid4()
        key = chat_attachment_storage_key(
            workspace.id,
            attachment_id,
            extension=inspection.extension,
        )
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.settings.chat_attachment_ttl_seconds)

        quota = StorageQuotaService(self.db, self.settings)
        if not workspace.is_system:
            quota.heal_stale_committed(workspace.id)

        hold: StorageHold | None = None
        try:
            hold = quota.reserve(
                workspace,
                inspection.byte_size,
                request_id=f"chat-attach:{attachment_id}",
            )
            self.storage.put_bytes(key, file_bytes, inspection.mime_type)
            row = ChatAttachment(
                id=attachment_id,
                workspace_id=workspace.id,
                uploaded_by=actor.id,
                original_filename=inspection.safe_name,
                mime_type=inspection.mime_type,
                byte_size=inspection.byte_size,
                sha256=inspection.sha256,
                storage_key=key,
                created_at=now,
                expires_at=expires_at,
            )
            self.db.add(row)
            self.db.flush()
            quota.finalize(hold, chat_attachment_id=row.id)
            self.db.commit()
            self.db.refresh(row)
        except AppError:
            self.db.rollback()
            if hold is not None and not hold.skipped:
                try:
                    quota.release(hold)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            try:
                self.storage.delete(key)
            except Exception:
                logger.exception("Failed to clean up chat attachment blob after AppError")
            raise
        except Exception:
            self.db.rollback()
            if hold is not None and not hold.skipped:
                try:
                    quota.release(hold)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            try:
                self.storage.delete(key)
            except Exception:
                logger.exception("Failed to clean up chat attachment blob after DB error")
            raise

        security_log(
            "chat_attachment.uploaded",
            workspace_id=str(workspace.id),
            user_id=str(actor.id),
            attachment_id=str(row.id),
            action="upload",
            byte_size=row.byte_size,
            mime_type=row.mime_type,
            expires_at=row.expires_at.isoformat() if row.expires_at else None,
        )
        return row

    def delete_for_actor(
        self,
        *,
        workspace: Workspace,
        actor: User,
        attachment_id: uuid.UUID,
    ) -> None:
        self._require_active_workspace(workspace)
        row = (
            self.db.query(ChatAttachment)
            .filter(
                ChatAttachment.id == attachment_id,
                ChatAttachment.workspace_id == workspace.id,
                ChatAttachment.uploaded_by == actor.id,
            )
            .one_or_none()
        )
        if row is None:
            # Cross-tenant / cross-user → same 404 (no existence oracle).
            raise AppError(
                ErrorCategory.CHAT_ATTACHMENT_NOT_FOUND,
                "Chat attachment not found.",
            )

        self._delete_row(row, reason="user_dismiss")

    def load_for_turn(
        self,
        *,
        workspace: Workspace,
        actor: User,
        attachment_id: uuid.UUID,
    ):
        """Load an actor-owned, non-expired attachment for a chat turn (no ingest)."""
        from app.chat_attachments.payload import ChatTurnAttachment

        self._require_active_workspace(workspace)
        now = datetime.now(timezone.utc)
        row = (
            self.db.query(ChatAttachment)
            .filter(
                ChatAttachment.id == attachment_id,
                ChatAttachment.workspace_id == workspace.id,
                ChatAttachment.uploaded_by == actor.id,
            )
            .one_or_none()
        )
        if row is None or row.expires_at <= now:
            raise AppError(
                ErrorCategory.CHAT_ATTACHMENT_NOT_FOUND,
                "Chat attachment not found.",
            )
        data = self.storage.get_bytes(row.storage_key)
        return ChatTurnAttachment(
            id=row.id,
            filename=row.original_filename,
            mime_type=row.mime_type,
            byte_size=int(row.byte_size),
            data=data,
        )

    def purge_expired(self, *, now: datetime | None = None, limit: int = 200) -> int:
        """Delete attachments past ``expires_at``. Returns number purged."""
        cutoff = now or datetime.now(timezone.utc)
        rows = (
            self.db.query(ChatAttachment)
            .filter(ChatAttachment.expires_at <= cutoff)
            .order_by(ChatAttachment.expires_at.asc())
            .limit(max(1, min(limit, 1000)))
            .all()
        )
        purged = 0
        for row in rows:
            self._delete_row(row, reason="ttl_expired")
            purged += 1
        return purged

    def purge_by_id_if_expired(
        self,
        attachment_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> bool:
        """ETA task helper — delete one attachment only if its TTL has elapsed."""
        cutoff = now or datetime.now(timezone.utc)
        row = self.db.get(ChatAttachment, attachment_id)
        if row is None:
            return False
        if row.expires_at > cutoff:
            return False
        self._delete_row(row, reason="ttl_expired")
        return True

    def _delete_row(self, row: ChatAttachment, *, reason: str) -> None:
        attachment_id = row.id
        workspace_id = row.workspace_id
        byte_size = int(row.byte_size or 0)
        key = row.storage_key

        quota = StorageQuotaService(self.db, self.settings)
        # Audit credit-back first; billable used drops when the row is removed.
        if byte_size > 0:
            quota.record_logical_delete(
                workspace_id,
                chat_attachment_id=attachment_id,
                byte_size=byte_size,
                request_id=f"chat-attach-delete:{attachment_id}:{reason}",
            )
        self.db.delete(row)
        self.db.commit()
        try:
            self.storage.delete(key)
        except Exception:
            logger.exception(
                "Failed to delete chat attachment blob",
                extra={"attachment_id": str(attachment_id), "storage_key": key},
            )

        security_log(
            "chat_attachment.deleted",
            workspace_id=str(workspace_id),
            attachment_id=str(attachment_id),
            action="delete",
            reason=reason,
            byte_size=byte_size,
        )

    @staticmethod
    def _require_active_workspace(workspace: Workspace) -> None:
        require_active_workspace(workspace)
