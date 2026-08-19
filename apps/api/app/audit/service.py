"""Audit writer — same Postgres transaction as the business mutation."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.audit.actions import AuditAction, AuditEntityType
from app.audit.models import AuditLog
from app.audit.sanitize import sanitize_audit_metadata
from app.common.request_context import get_request_context

logger = logging.getLogger(__name__)


class AuditPersistenceError(RuntimeError):
    """Raised when a required audit row cannot be flushed (fail-closed)."""


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        action: AuditAction | str,
        entity_type: AuditEntityType | str,
        entity_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_api_key_id: uuid.UUID | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        allowlist: frozenset[str] | None = None,
        required: bool = True,
    ) -> AuditLog | None:
        """Insert an audit row and flush (does not commit).

        Required persistence failures raise ``AuditPersistenceError`` so the
        caller can roll back the domain transaction. Sanitizer issues never
        fail the mutation — metadata is dropped instead.
        """
        ctx = get_request_context()
        action_value = action.value if isinstance(action, AuditAction) else str(action)
        entity_value = (
            entity_type.value if isinstance(entity_type, AuditEntityType) else str(entity_type)
        )
        extra = sanitize_audit_metadata(metadata, allowlist=allowlist)
        row = AuditLog(
            workspace_id=workspace_id or ctx.workspace_id,
            actor_user_id=actor_user_id if actor_user_id is not None else ctx.user_id,
            actor_api_key_id=(
                actor_api_key_id if actor_api_key_id is not None else ctx.api_key_id
            ),
            action=action_value,
            entity_type=entity_value,
            entity_id=entity_id,
            request_id=request_id if request_id is not None else ctx.request_id,
            extra=extra,
        )
        try:
            # SAVEPOINT so a failed flush cannot poison the outer session.
            with self.db.begin_nested():
                self.db.add(row)
                self.db.flush()
            return row
        except Exception as exc:
            logger.exception(
                "audit.persist_failed",
                extra={"action": action_value, "entity_type": entity_value, "required": required},
            )
            if required:
                self.db.rollback()
                raise AuditPersistenceError("Failed to persist required audit event.") from exc
            return None


def record_audit(
    db: Session,
    *,
    action: AuditAction | str,
    entity_type: AuditEntityType | str,
    entity_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_api_key_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    allowlist: frozenset[str] | None = None,
    required: bool = True,
) -> AuditLog | None:
    return AuditService(db).record(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        actor_api_key_id=actor_api_key_id,
        metadata=metadata,
        allowlist=allowlist,
        required=required,
    )
