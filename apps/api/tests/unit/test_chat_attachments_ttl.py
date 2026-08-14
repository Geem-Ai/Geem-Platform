"""Unit tests for chat attachment TTL purge + storage credit-back."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.chat_attachments.models import ChatAttachment
from app.chat_attachments.service import ChatAttachmentService


def _row(*, expires_at: datetime) -> ChatAttachment:
    return ChatAttachment(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        original_filename="note.txt",
        mime_type="text/plain",
        byte_size=4,
        sha256="a" * 64,
        storage_key="workspaces/w/chat-attachments/a/original.txt",
        created_at=expires_at - timedelta(hours=12),
        expires_at=expires_at,
    )


def test_purge_by_id_skips_unexpired() -> None:
    now = datetime.now(timezone.utc)
    row = _row(expires_at=now + timedelta(hours=1))
    db = MagicMock()
    db.get.return_value = row
    storage = MagicMock()
    svc = ChatAttachmentService(db, storage=storage)

    assert svc.purge_by_id_if_expired(row.id, now=now) is False
    db.delete.assert_not_called()
    storage.delete.assert_not_called()


def test_purge_by_id_deletes_expired_and_credits_storage() -> None:
    now = datetime.now(timezone.utc)
    row = _row(expires_at=now - timedelta(minutes=1))
    db = MagicMock()
    db.get.return_value = row
    storage = MagicMock()
    svc = ChatAttachmentService(db, storage=storage)

    with patch("app.chat_attachments.service.StorageQuotaService") as quota_cls:
        quota = quota_cls.return_value
        assert svc.purge_by_id_if_expired(row.id, now=now) is True
        quota.record_logical_delete.assert_called_once()
        kwargs = quota.record_logical_delete.call_args.kwargs
        assert kwargs["chat_attachment_id"] == row.id
        assert kwargs["byte_size"] == 4

    db.delete.assert_called_once_with(row)
    db.commit.assert_called()
    storage.delete.assert_called_once_with(row.storage_key)


def test_billable_used_includes_chat_attachments() -> None:
    from app.usage.storage import StorageQuotaService

    db = MagicMock()
    docs = MagicMock()
    docs.sum_active_byte_size.return_value = 100
    atts = MagicMock()
    atts.sum_byte_size.return_value = 25

    with (
        patch("app.usage.storage.DocumentRepository", return_value=docs),
        patch("app.usage.storage.ChatAttachmentRepository", return_value=atts),
        patch("app.usage.storage.QuotaService"),
        patch("app.usage.storage.StorageUsageService"),
        patch("app.usage.storage.WorkspaceResourceUsageRepository"),
        patch("app.usage.storage.StorageReservationRepository"),
    ):
        svc = StorageQuotaService(db)
        assert svc.billable_used_bytes(uuid.uuid4()) == 125
