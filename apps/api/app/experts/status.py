"""Derive Expert ``status`` from linked-Document ingestion state (Phase 3B).

``status`` semantics:

* ``disabled`` is sticky — a manual admin action. Never overwritten by
  reconciliation. Callers must skip reconciliation for disabled Experts.
* ``draft``   → no linked (non-deleted) Documents, or all linked Documents are
  still queued and nothing has entered processing yet.
* ``processing`` → any linked Document is currently queued / processing / OCRing
  and no Document has reached ``ready`` yet.
* ``ready``   → at least one linked Document is ``ready``. Coexists with other
  linked Documents that are still processing or failed.
* ``failed``  → all linked Documents are ``failed`` (and there is at least one
  linked Document — otherwise we stay ``draft``).

Callers must invoke ``reconcile(expert_id)`` AFTER commit for link, unlink,
soft-delete, delete, and pipeline-completion events.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.db.models import Document
from app.experts.models import Expert, ExpertDocument, ExpertKnowledgeMode, ExpertStatus

logger = logging.getLogger(__name__)

# Terminal / in-flight buckets for the underlying Document lifecycle.
_READY_STATUSES = frozenset({"ready"})
_FAILED_STATUSES = frozenset({"failed"})
_PROCESSING_STATUSES = frozenset({"queued", "processing", "deleting"})


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Outcome of a status reconciliation pass."""

    expert_id: uuid.UUID
    previous_status: str
    new_status: str
    changed: bool
    linked_count: int
    ready_count: int
    processing_count: int
    failed_count: int


class ExpertStatusReconciler:
    def __init__(self, db: Session) -> None:
        self.db = db

    def reconcile(self, expert_id: uuid.UUID) -> ReconciliationResult | None:
        """Recompute and persist Expert status from linked-Document lifecycle.

        Returns None when the Expert is missing / soft-deleted / disabled
        (nothing to reconcile). Otherwise persists and returns the outcome
        (``changed=False`` when nothing needed to move).
        """
        expert = self.db.get(Expert, expert_id)
        if expert is None or expert.deleted_at is not None:
            return None
        if expert.status == ExpertStatus.DISABLED.value:
            return None

        # Geem General (and any knowledge_mode=general) stays ready without docs.
        if expert.knowledge_mode == ExpertKnowledgeMode.GENERAL.value:
            previous = expert.status
            if previous == ExpertStatus.READY.value:
                return ReconciliationResult(
                    expert_id=expert_id,
                    previous_status=previous,
                    new_status=previous,
                    changed=False,
                    linked_count=0,
                    ready_count=0,
                    processing_count=0,
                    failed_count=0,
                )
            expert.status = ExpertStatus.READY.value
            self.db.commit()
            security_log(
                "expert.status_reconciled",
                expert_id=str(expert_id),
                previous_status=previous,
                new_status=ExpertStatus.READY.value,
                linked_count=0,
                ready_count=0,
                processing_count=0,
                failed_count=0,
                knowledge_mode="general",
            )
            return ReconciliationResult(
                expert_id=expert_id,
                previous_status=previous,
                new_status=ExpertStatus.READY.value,
                changed=True,
                linked_count=0,
                ready_count=0,
                processing_count=0,
                failed_count=0,
            )

        counts = self._count_link_states(expert_id)
        new_status = self._derive_status(counts)
        previous = expert.status
        changed = new_status != previous
        if changed:
            expert.status = new_status
            self.db.commit()
            security_log(
                "expert.status_reconciled",
                expert_id=str(expert_id),
                previous_status=previous,
                new_status=new_status,
                linked_count=counts["linked"],
                ready_count=counts["ready"],
                processing_count=counts["processing"],
                failed_count=counts["failed"],
            )
        return ReconciliationResult(
            expert_id=expert_id,
            previous_status=previous,
            new_status=new_status,
            changed=changed,
            linked_count=counts["linked"],
            ready_count=counts["ready"],
            processing_count=counts["processing"],
            failed_count=counts["failed"],
        )

    def _count_link_states(self, expert_id: uuid.UUID) -> dict[str, int]:
        rows = list(
            self.db.execute(
                select(Document.status)
                .join(ExpertDocument, ExpertDocument.document_id == Document.id)
                .where(
                    ExpertDocument.expert_id == expert_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        linked = len(rows)
        ready = sum(1 for r in rows if r[0] in _READY_STATUSES)
        processing = sum(1 for r in rows if r[0] in _PROCESSING_STATUSES)
        failed = sum(1 for r in rows if r[0] in _FAILED_STATUSES)
        return {
            "linked": linked,
            "ready": ready,
            "processing": processing,
            "failed": failed,
        }

    @staticmethod
    def _derive_status(counts: dict[str, int]) -> str:
        linked = counts["linked"]
        ready = counts["ready"]
        processing = counts["processing"]
        failed = counts["failed"]

        if linked == 0:
            return ExpertStatus.DRAFT.value
        if ready > 0:
            return ExpertStatus.READY.value
        if processing > 0:
            return ExpertStatus.PROCESSING.value
        if failed == linked:
            return ExpertStatus.FAILED.value
        # Any other mix (e.g. all links are in an unexpected status) — keep the
        # safest resolution: nothing ready + nothing processing yet ⇒ draft.
        return ExpertStatus.DRAFT.value


__all__ = ["ExpertStatusReconciler", "ReconciliationResult"]
