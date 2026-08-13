"""Workspace Expert allowance — count + lock, never plan-name branching."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ErrorCategory, raise_resource_quota
from app.entitlements.keys import EntitlementKey
from app.entitlements.quota import QuotaService
from app.experts.models import Expert, ExpertType
from app.usage.locks import LockNamespace, workspace_advisory_lock


@dataclass(frozen=True, slots=True)
class ExpertSlotSnapshot:
    limit: int
    used: int
    remaining: int


class ExpertQuotaService:
    """Enforce ``experts_limit`` for Workspace-owned Experts.

    Counted: active (not soft-deleted) Experts with ``type=workspace`` owned by
    this Workspace. Not counted: Platform Experts, Geem General, grants, or
    soft-deleted Workspace Experts. Editing an existing Expert does not call
    this service.
    """

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.quota = QuotaService(db, self.settings)

    def snapshot(self, workspace_id: uuid.UUID) -> ExpertSlotSnapshot:
        limit = self.quota.get_expert_limit(workspace_id)
        used = self.count_active_workspace_experts(workspace_id)
        return ExpertSlotSnapshot(
            limit=limit,
            used=used,
            remaining=max(0, int(limit) - int(used)),
        )

    def acquire_slot(self, workspace_id: uuid.UUID) -> ExpertSlotSnapshot:
        """Lock the Workspace expert namespace, then require one free slot.

        Caller must insert/restore the Expert in the same transaction.
        """
        workspace_advisory_lock(self.db, workspace_id, LockNamespace.EXPERTS)
        snap = self.snapshot(workspace_id)
        if snap.remaining < 1:
            raise_resource_quota(
                ErrorCategory.EXPERT_LIMIT_REACHED,
                "Workspace Expert allowance has been reached.",
                metric=EntitlementKey.EXPERTS_LIMIT.value,
                limit=snap.limit,
                used=snap.used,
                remaining=0,
            )
        return snap

    def count_active_workspace_experts(self, workspace_id: uuid.UUID) -> int:
        value = self.db.scalar(
            select(func.count())
            .select_from(Expert)
            .where(
                Expert.workspace_id == workspace_id,
                Expert.type == ExpertType.WORKSPACE.value,
                Expert.deleted_at.is_(None),
            )
        )
        return int(value or 0)
