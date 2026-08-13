"""Workspace storage quota — reserve / finalize / release (Phase 5C).

Billable used = SUM(byte_size) of active (not soft-deleted) Documents in the
Workspace. ``storage_usage_events`` remain the append-only audit trail.
``workspace_resource_usage.reserved_bytes`` holds in-flight chargeable uploads.

Platform Knowledge (SYSTEM workspaces) never consume tenant storage quota.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory, raise_resource_quota
from app.documents.repository import DocumentRepository
from app.entitlements.keys import EntitlementKey
from app.entitlements.quota import QuotaService
from app.usage.locks import LockNamespace, workspace_advisory_lock
from app.usage.meters import StorageUsageService
from app.usage.metrics import StorageReservationStatus, StorageUsageReason, UsageMetric
from app.usage.models import StorageReservation, WorkspaceResourceUsage
from app.usage.repository import StorageReservationRepository, WorkspaceResourceUsageRepository
from app.workspaces.models import Workspace


@dataclass(frozen=True, slots=True)
class StorageHold:
    workspace_id: uuid.UUID
    request_id: str
    byte_size: int
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    limit_bytes: int
    used_bytes: int
    reserved_bytes: int

    @property
    def remaining_bytes(self) -> int:
        return max(0, int(self.limit_bytes) - int(self.used_bytes) - int(self.reserved_bytes))

    @property
    def percentage(self) -> float:
        if self.limit_bytes <= 0:
            return 100.0 if (self.used_bytes > 0 or self.reserved_bytes > 0) else 0.0
        return min(
            100.0,
            round(100.0 * float(self.used_bytes + self.reserved_bytes) / float(self.limit_bytes), 4),
        )


class StorageQuotaService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.quota = QuotaService(db, self.settings)
        self.events = StorageUsageService(db, self.settings)
        self.counters = WorkspaceResourceUsageRepository(db)
        self.reservations = StorageReservationRepository(db)
        self.documents = DocumentRepository(db)

    def snapshot(self, workspace_id: uuid.UUID) -> StorageSnapshot:
        counter = self.counters.get(workspace_id, UsageMetric.STORAGE_BYTES.value)
        return StorageSnapshot(
            limit_bytes=self.quota.get_storage_limit(workspace_id),
            used_bytes=self.documents.sum_active_byte_size(workspace_id),
            reserved_bytes=int(counter.reserved_bytes) if counter is not None else 0,
        )

    def lock(self, workspace_id: uuid.UUID) -> None:
        workspace_advisory_lock(self.db, workspace_id, LockNamespace.STORAGE)

    def heal_stale_committed(self, workspace_id: uuid.UUID) -> None:
        """Release expired holds in a dedicated transaction.

        Must run *before* the caller's storage lock. A later quota failure in
        the request session must not roll back this heal.
        """
        from app.db.session import SessionLocal

        session = SessionLocal()
        try:
            other = StorageQuotaService(session, self.settings)
            other.lock(workspace_id)
            other._heal_stale_locked(workspace_id)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def reserve(
        self,
        workspace: Workspace,
        byte_size: int,
        *,
        request_id: str | None = None,
    ) -> StorageHold:
        """Check quota and hold ``byte_size`` until finalize or release.

        SYSTEM workspaces skip enforcement (Platform Knowledge is not tenant
        storage). Caller should already hold the storage advisory lock when
        combining this with a reuse-on-hash check.
        """
        rid = (request_id or "").strip() or f"upload:{uuid.uuid4()}"
        size = int(byte_size)
        if size < 0:
            raise AppError(ErrorCategory.VALIDATION, "byte_size must be >= 0.")
        if workspace.is_system or size == 0:
            return StorageHold(
                workspace_id=workspace.id,
                request_id=rid,
                byte_size=size,
                skipped=True,
            )

        self.lock(workspace.id)
        self._heal_stale_locked(workspace.id)
        existing = self.reservations.get_by_request_id_for_update(workspace.id, rid)
        if existing is not None:
            if existing.status == StorageReservationStatus.RESERVED.value:
                return StorageHold(
                    workspace_id=workspace.id,
                    request_id=rid,
                    byte_size=int(existing.byte_size),
                    skipped=False,
                )
            raise AppError(
                ErrorCategory.CONFLICT,
                "Storage reservation is no longer open.",
                details={"request_id": rid, "status": existing.status},
            )

        counter = self._lock_counter(workspace.id)
        used = self.documents.sum_active_byte_size(workspace.id)
        reserved = int(counter.reserved_bytes)
        limit = self.quota.get_storage_limit(workspace.id)
        remaining = max(0, limit - used - reserved)
        if size > remaining:
            raise_resource_quota(
                ErrorCategory.STORAGE_QUOTA_EXCEEDED,
                "Workspace storage quota would be exceeded.",
                metric=EntitlementKey.STORAGE_BYTES.value,
                limit=limit,
                used=used,
                remaining=remaining,
            )
        counter.reserved_bytes = reserved + size
        self.reservations.create(
            StorageReservation(
                workspace_id=workspace.id,
                request_id=rid,
                byte_size=size,
                status=StorageReservationStatus.RESERVED.value,
            )
        )
        self.events.record_delta(
            workspace.id,
            delta_bytes=0,
            reason=StorageUsageReason.RESERVE,
            request_id=rid,
            extra={"reserved_bytes": size},
        )
        return StorageHold(
            workspace_id=workspace.id, request_id=rid, byte_size=size, skipped=False
        )

    def finalize(
        self,
        hold: StorageHold,
        *,
        document_id: uuid.UUID,
        reason: StorageUsageReason | str = StorageUsageReason.UPLOAD,
    ) -> None:
        if hold.skipped or hold.byte_size == 0:
            return
        self.lock(hold.workspace_id)
        row = self.reservations.get_by_request_id_for_update(
            hold.workspace_id, hold.request_id
        )
        if row is None:
            raise AppError(
                ErrorCategory.NOT_FOUND,
                "Storage reservation not found.",
                details={"request_id": hold.request_id},
            )
        if row.status != StorageReservationStatus.RESERVED.value:
            return
        parsed = reason if isinstance(reason, StorageUsageReason) else StorageUsageReason(reason)
        counter = self._lock_counter(hold.workspace_id)
        counter.reserved_bytes = max(0, int(counter.reserved_bytes) - int(row.byte_size))
        row.status = StorageReservationStatus.FINALIZED.value
        row.document_id = document_id
        self.events.record_delta(
            hold.workspace_id,
            delta_bytes=int(row.byte_size),
            reason=parsed,
            document_id=document_id,
            request_id=hold.request_id,
        )

    def release(self, hold: StorageHold) -> None:
        if hold.skipped or hold.byte_size == 0:
            return
        self.lock(hold.workspace_id)
        row = self.reservations.get_by_request_id_for_update(
            hold.workspace_id, hold.request_id
        )
        if row is None or row.status != StorageReservationStatus.RESERVED.value:
            return
        counter = self._lock_counter(hold.workspace_id)
        counter.reserved_bytes = max(0, int(counter.reserved_bytes) - int(row.byte_size))
        row.status = StorageReservationStatus.RELEASED.value
        self.events.record_delta(
            hold.workspace_id,
            delta_bytes=0,
            reason=StorageUsageReason.RELEASE,
            request_id=hold.request_id,
            extra={"released_bytes": int(row.byte_size)},
        )

    def record_logical_delete(
        self,
        workspace_id: uuid.UUID,
        *,
        document_id: uuid.UUID,
        byte_size: int,
        request_id: str | None = None,
    ) -> None:
        """Soft-delete has already set ``deleted_at``; billable used drops via SUM."""
        size = int(byte_size or 0)
        if size == 0:
            return
        self.lock(workspace_id)
        self.events.record_delta(
            workspace_id,
            delta_bytes=-size,
            reason=StorageUsageReason.DELETE,
            document_id=document_id,
            request_id=request_id,
        )

    def consume_restore(
        self,
        workspace: Workspace,
        *,
        document_id: uuid.UUID,
        byte_size: int,
        request_id: str | None = None,
    ) -> StorageHold:
        """Reserve + finalize restore in the current transaction (no new blob)."""
        hold = self.reserve(
            workspace,
            int(byte_size or 0),
            request_id=request_id or f"restore:{document_id}:{uuid.uuid4()}",
        )
        self.finalize(hold, document_id=document_id, reason=StorageUsageReason.RESTORE)
        return hold

    def _lock_counter(self, workspace_id: uuid.UUID) -> WorkspaceResourceUsage:
        metric = UsageMetric.STORAGE_BYTES.value
        existing = self.counters.get_for_update(workspace_id, metric)
        if existing is not None:
            return existing
        try:
            with self.db.begin_nested():
                return self.counters.create(
                    WorkspaceResourceUsage(
                        workspace_id=workspace_id,
                        metric=metric,
                        reserved_bytes=0,
                    )
                )
        except IntegrityError:
            found = self.counters.get_for_update(workspace_id, metric)
            if found is None:
                raise
            return found

    def _heal_stale_locked(self, workspace_id: uuid.UUID) -> None:
        ttl = int(getattr(self.settings, "storage_reservation_ttl_seconds", 900) or 900)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, ttl))
        for row in self.reservations.list_stale_reserved(workspace_id, older_than=cutoff):
            hold = StorageHold(
                workspace_id=workspace_id,
                request_id=row.request_id,
                byte_size=int(row.byte_size),
                skipped=False,
            )
            self.release(hold)
