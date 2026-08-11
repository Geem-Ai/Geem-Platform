"""Keep Qdrant ``expert_ids`` payload in sync with PG ``expert_documents`` (Phase 3B).

Retrieval filters points by ``expert_ids`` (keyword-array contains
``expert_id``). Because ``expert_documents`` and Qdrant are two systems, a link
/ unlink / delete / soft-delete in PG must be projected onto Qdrant payload
before the next query, or an Expert either misses knowledge it should have or
serves knowledge it shouldn't.

Design:

* One synchronizer method — ``sync_document`` — is authoritative for a single
  Document. It grabs a per-Document Redis lock (falls back to a process-local
  lock when Redis is unavailable), then RE-READS PostgreSQL under the lock,
  computes the current list of active Expert IDs, and writes it as a Qdrant
  ``set_payload`` on every point that belongs to that Document.

* Re-reading PG under the lock is the reason we don't diff — one write always
  wins, and it's always the truth PG can see at commit time. Callers must
  invoke ``sync_document`` AFTER ``db.commit()`` so we don't overwrite Qdrant
  with a soon-to-rollback in-flight state.

* Redis outage does NOT block sync. We log and continue best-effort with a
  process-local lock. Cross-process races in that degraded mode are accepted
  because we always re-read PG, so the last writer still writes truth.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import Document
from app.experts.models import Expert, ExpertDocument
from app.storage.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


_LOCK_TIMEOUT_SECONDS = 30
_LOCK_BLOCKING_TIMEOUT_SECONDS = 15

# Process-local fallback locks (per document_id). Only used when Redis is
# unreachable — Redis is the primary lock service.
_local_locks: dict[str, threading.Lock] = {}
_local_locks_guard = threading.Lock()


def _get_local_lock(document_id: uuid.UUID) -> threading.Lock:
    key = str(document_id)
    with _local_locks_guard:
        lock = _local_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _local_locks[key] = lock
        return lock


class ExpertVectorMembershipSynchronizer:
    """Project PG ``expert_documents`` onto Qdrant ``expert_ids`` payload."""

    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        vectors: QdrantVectorStore | None = None,
        redis_factory: Any = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self._redis_factory = redis_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_document(self, document_id: uuid.UUID) -> list[str]:
        """Rewrite ``expert_ids`` for every Qdrant point of ``document_id``.

        Returns the freshly-computed list of Expert IDs (stringified UUIDs)
        that were written. Empty list means the Document is now unlinked from
        every non-deleted Expert (or has no Qdrant points yet).

        Safe to invoke on Documents that no longer exist / are soft-deleted —
        in that case we still re-read PG (finds no active links), then either
        skip Qdrant (Document row missing) or clear ``expert_ids`` on any
        remaining points (best-effort).
        """
        lock_name = self._lock_name(document_id)
        redis_lock = self._acquire_redis_lock(lock_name)
        if redis_lock is not None:
            try:
                return self._sync_under_lock(document_id)
            finally:
                self._release_redis_lock(redis_lock)

        # Redis unavailable — degrade to process-local lock. Cross-process
        # racers still all re-read PG under their own local lock, so the last
        # writer always writes the truth PG can see at that moment.
        local_lock = _get_local_lock(document_id)
        acquired = local_lock.acquire(timeout=_LOCK_BLOCKING_TIMEOUT_SECONDS)
        try:
            return self._sync_under_lock(document_id)
        finally:
            if acquired:
                local_lock.release()

    def list_active_expert_ids_for_document(
        self, document_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Active (non-deleted) Experts currently linking a Document in PG.

        The workspace scope isn't reasserted here because ``expert_documents``
        is authoritative: create paths in ExpertService already enforce the
        Workspace/knowledge-Workspace invariants at link time.
        """
        stmt = (
            select(Expert.id)
            .join(ExpertDocument, ExpertDocument.expert_id == Expert.id)
            .where(
                ExpertDocument.document_id == document_id,
                Expert.deleted_at.is_(None),
            )
            .order_by(Expert.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _sync_under_lock(self, document_id: uuid.UUID) -> list[str]:
        # Re-read PG inside the critical section so late-arriving link/unlink
        # commits made just before the lock was acquired are visible.
        expert_ids = [str(eid) for eid in self.list_active_expert_ids_for_document(document_id)]

        document = self.db.get(Document, document_id)
        try:
            point_ids = self.vectors.scroll_point_ids_for_document(str(document_id))
        except AppError:
            logger.warning(
                "expert_membership_sync.scroll_failed",
                extra={"document_id": str(document_id)},
            )
            raise
        if not point_ids:
            # Document not indexed yet (still processing) or fully purged.
            # PG remains the source of truth; the pipeline will pick up
            # expert_ids from PG on the next upsert.
            return expert_ids

        try:
            self.vectors.set_payload(point_ids, {"expert_ids": expert_ids})
        except AppError:
            logger.exception(
                "expert_membership_sync.set_payload_failed",
                extra={
                    "document_id": str(document_id),
                    "workspace_id": (
                        str(document.workspace_id) if document is not None else None
                    ),
                    "point_count": len(point_ids),
                },
            )
            raise
        return expert_ids

    def _lock_name(self, document_id: uuid.UUID) -> str:
        # Include the knowledge_workspace_id when we can resolve it — the
        # namespace makes Redis key inspection self-documenting and avoids
        # collisions if UUIDs are ever reused. We look up the Document once
        # without a transaction; if it's gone we still hold a per-doc lock.
        doc = self.db.get(Document, document_id)
        ws_prefix = f"ws:{doc.workspace_id}:" if doc is not None else "ws:unknown:"
        return f"{ws_prefix}document:{document_id}:expert-sync"

    def _acquire_redis_lock(self, name: str) -> Any | None:
        try:
            client = self._redis_client()
        except (RedisError, OSError) as exc:
            logger.warning(
                "expert_membership_sync.redis_unavailable",
                extra={"lock": name, "error": str(exc)},
            )
            return None

        try:
            lock = client.lock(
                name,
                timeout=_LOCK_TIMEOUT_SECONDS,
                blocking_timeout=_LOCK_BLOCKING_TIMEOUT_SECONDS,
            )
            acquired = lock.acquire(blocking=True)
        except (RedisError, OSError) as exc:
            logger.warning(
                "expert_membership_sync.redis_lock_failed",
                extra={"lock": name, "error": str(exc)},
            )
            return None
        if not acquired:
            logger.warning(
                "expert_membership_sync.redis_lock_timeout",
                extra={"lock": name},
            )
            return None
        return lock

    def _release_redis_lock(self, lock: Any) -> None:
        try:
            lock.release()
        except (RedisError, OSError) as exc:
            logger.warning(
                "expert_membership_sync.redis_release_failed",
                extra={"error": str(exc)},
            )

    def _redis_client(self) -> Redis:
        if self._redis_factory is not None:
            return self._redis_factory()
        return Redis.from_url(self.settings.redis_url, socket_connect_timeout=1)


__all__ = ["ExpertVectorMembershipSynchronizer"]
