"""Chat attachment persistence helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat_attachments.models import ChatAttachment


class ChatAttachmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def sum_byte_size(self, workspace_id: uuid.UUID) -> int:
        """Billable chat attachment storage still present in the Workspace.

        Rows are hard-deleted on dismiss / TTL purge, so this SUM drops once
        attachments are auto-deleted or removed by the user.
        """
        value = self.db.scalar(
            select(func.coalesce(func.sum(ChatAttachment.byte_size), 0)).where(
                ChatAttachment.workspace_id == workspace_id,
            )
        )
        return int(value or 0)
