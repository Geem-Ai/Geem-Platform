"""Phase 2C — migrate legacy documents (workspace_id IS NULL) into DEFAULT_WORKSPACE_SLUG.

Usage (from apps/api):

  python -m app.maintenance.phase2c_migrate_legacy --dry-run
  python -m app.maintenance.phase2c_migrate_legacy --apply
  python -m app.maintenance.phase2c_migrate_legacy --verify

Idempotent / resumable. Never deletes legacy MinIO source objects.
Never guesses ownership — PostgreSQL Document rows are the inventory source of truth.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document  # noqa: F401 — register metadata
from app.db.session import SessionLocal
from app.storage.document_keys import resolve_document_storage_key
from app.storage.minio_storage import MinioObjectStorage
from app.storage.qdrant_store import QdrantVectorStore
from app.workspaces.models import Workspace, WorkspaceStatus
from app.workspaces.service import WorkspaceService

# Ensure identity models are registered for Workspace relationships.
import app.identity.models  # noqa: F401
import app.db.models  # noqa: F401

logger = logging.getLogger("geem.maintenance.phase2c")


@dataclass
class LegacyItem:
    document_id: str
    sha256: str
    status: str
    storage_key: str
    byte_size: int | None
    created_at: str | None
    minio_source_exists: bool | None = None
    qdrant_point_count: int | None = None
    qdrant_workspace_ids: list[str] = field(default_factory=list)


@dataclass
class MigrationStats:
    migration_run_id: str
    target_workspace_id: str | None
    target_workspace_slug: str | None
    mode: str
    legacy_documents: int = 0
    completed: int = 0
    skipped_already_correct: int = 0
    would_migrate: int = 0
    failed: int = 0
    conflicts: int = 0
    missing_minio: int = 0
    zero_vectors: int = 0
    conflict_details: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    orphan_report: list[dict[str, Any]] = field(default_factory=list)
    legacy_minio_sources_retained: int = 0


def classify_orphan(kind: str) -> str:
    if kind in {
        "qdrant_wrong_workspace",
        "null_workspace_remaining",
        "canonical_missing_while_owned",
    }:
        return "security_blocker"
    if kind in {"db_without_minio", "db_without_qdrant_payload", "storage_key_stale"}:
        return "availability_data_integrity"
    return "cleanup_candidate"


def build_orphan_report(
    db,
    *,
    target: Workspace,
    storage: MinioObjectStorage,
    vectors: QdrantVectorStore,
) -> tuple[list[dict[str, Any]], int]:
    """Classify store/DB inconsistencies after migration (no content logged)."""
    report: list[dict[str, Any]] = []
    retained_legacy = 0
    docs = list(db.scalars(select(Document).where(Document.deleted_at.is_(None))))
    for doc in docs:
        resolved = resolve_document_storage_key(doc.id, doc.workspace_id)
        canonical_ok = False
        try:
            canonical_ok = storage.object_exists(resolved.canonical)
        except Exception:  # noqa: BLE001
            canonical_ok = False
        legacy_ok = False
        try:
            legacy_ok = storage.object_exists(resolved.legacy_flat)
        except Exception:  # noqa: BLE001
            legacy_ok = False
        if legacy_ok and doc.workspace_id is not None:
            retained_legacy += 1
            report.append(
                {
                    "document_id": str(doc.id),
                    "kind": "legacy_flat_minio_remains",
                    "class": classify_orphan("legacy_flat_minio_remains"),
                }
            )
        if doc.workspace_id is None:
            report.append(
                {
                    "document_id": str(doc.id),
                    "kind": "null_workspace_remaining",
                    "class": classify_orphan("null_workspace_remaining"),
                }
            )
            continue
        if not canonical_ok:
            report.append(
                {
                    "document_id": str(doc.id),
                    "kind": "canonical_missing_while_owned",
                    "class": classify_orphan("canonical_missing_while_owned"),
                }
            )
        if doc.storage_key != resolved.canonical:
            report.append(
                {
                    "document_id": str(doc.id),
                    "kind": "storage_key_stale",
                    "class": classify_orphan("storage_key_stale"),
                }
            )
        try:
            point_ids = vectors.scroll_point_ids_for_document(str(doc.id))
        except Exception:  # noqa: BLE001
            point_ids = []
        if doc.status == "ready" and not point_ids:
            report.append(
                {
                    "document_id": str(doc.id),
                    "kind": "db_without_qdrant_payload",
                    "class": classify_orphan("db_without_qdrant_payload"),
                }
            )
        elif point_ids and vectors.client.collection_exists(vectors.collection):
            from qdrant_client.http import models as qm

            pts, _ = vectors.client.scroll(
                collection_name=vectors.collection,
                scroll_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="document_id",
                            match=qm.MatchValue(value=str(doc.id)),
                        )
                    ]
                ),
                limit=max(len(point_ids), 256),
                with_payload=True,
                with_vectors=False,
            )
            for p in pts:
                ws = (p.payload or {}).get("workspace_id")
                if str(ws or "") != str(doc.workspace_id):
                    report.append(
                        {
                            "document_id": str(doc.id),
                            "kind": "qdrant_wrong_workspace",
                            "class": classify_orphan("qdrant_wrong_workspace"),
                        }
                    )
                    break
    return report, retained_legacy


def resolve_target_workspace(db) -> Workspace:
    settings = get_settings()
    svc = WorkspaceService(db, settings=settings)
    # Prefer existing configured slug; create only via ensure_migration_workspace.
    workspace = svc.ensure_migration_workspace()
    if workspace.deleted_at is not None:
        raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Migration workspace is soft-deleted.")
    if workspace.status != WorkspaceStatus.ACTIVE.value:
        raise AppError(
            ErrorCategory.WORKSPACE_ACCESS_DENIED,
            "Migration workspace is not active.",
            details={"status": workspace.status, "slug": workspace.slug},
        )
    if workspace.slug != settings.default_workspace_slug:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Resolved migration workspace slug mismatch.",
            details={"expected": settings.default_workspace_slug, "actual": workspace.slug},
        )
    from app.workspaces.models import WorkspaceMembership, WorkspaceRole
    from sqlalchemy import select

    owners = list(
        db.scalars(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace.id,
                WorkspaceMembership.role == WorkspaceRole.OWNER.value,
            )
        )
    )
    if not owners:
        raise AppError(
            ErrorCategory.VALIDATION,
            "ABORT MIGRATION: default Workspace has no owner membership. "
            "Run `python -m app.identity.bootstrap` with BOOTSTRAP_ADMIN_* first.",
            details={"workspace_id": str(workspace.id), "slug": workspace.slug},
        )
    return workspace


def inventory_legacy(db, storage: MinioObjectStorage, vectors: QdrantVectorStore) -> list[LegacyItem]:
    rows = list(
        db.scalars(
            select(Document)
            .where(Document.workspace_id.is_(None))
            .order_by(Document.created_at.asc())
        )
    )
    items: list[LegacyItem] = []
    for doc in rows:
        source_exists = None
        try:
            source_exists = storage.object_exists(doc.storage_key) or storage.object_exists(
                resolve_document_storage_key(doc.id, None).legacy_flat
            )
        except Exception:  # noqa: BLE001
            source_exists = None
        point_ids: list[str] = []
        workspace_ids: set[str] = set()
        try:
            point_ids = vectors.scroll_point_ids_for_document(str(doc.id))
            # Inspect payloads for any accidental workspace tags
            from qdrant_client.http import models as qm

            if vectors.client.collection_exists(vectors.collection):
                pts, _ = vectors.client.scroll(
                    collection_name=vectors.collection,
                    scroll_filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="document_id",
                                match=qm.MatchValue(value=str(doc.id)),
                            )
                        ]
                    ),
                    limit=256,
                    with_payload=True,
                    with_vectors=False,
                )
                for p in pts:
                    ws = (p.payload or {}).get("workspace_id")
                    if ws is not None:
                        workspace_ids.add(str(ws))
        except Exception:  # noqa: BLE001
            point_ids = []
        items.append(
            LegacyItem(
                document_id=str(doc.id),
                sha256=doc.sha256,
                status=doc.status,
                storage_key=doc.storage_key,
                byte_size=doc.byte_size,
                created_at=doc.created_at.isoformat() if doc.created_at else None,
                minio_source_exists=source_exists,
                qdrant_point_count=len(point_ids),
                qdrant_workspace_ids=sorted(workspace_ids),
            )
        )
    return items


def detect_conflicts(db, target: Workspace, legacy_items: list[LegacyItem]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for item in legacy_items:
        existing = db.scalar(
            select(Document).where(
                Document.workspace_id == target.id,
                Document.sha256 == item.sha256,
                Document.deleted_at.is_(None),
            )
        )
        if existing is not None:
            conflicts.append(
                {
                    "legacy_document_id": item.document_id,
                    "workspace_document_id": str(existing.id),
                    "sha256": item.sha256,
                }
            )
    return conflicts


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def migrate_one(
    db,
    *,
    document: Document,
    target: Workspace,
    storage: MinioObjectStorage,
    vectors: QdrantVectorStore,
    dry_run: bool,
    run_id: str,
) -> str:
    """Returns status: completed|skipped_already_correct|would_migrate|failed|missing_minio."""
    assert document.workspace_id is None or document.workspace_id == target.id
    resolved = resolve_document_storage_key(document.id, target.id)
    canonical = resolved.canonical

    already_owned = document.workspace_id == target.id
    minio_ok = False
    try:
        minio_ok = storage.object_exists(canonical)
    except Exception:  # noqa: BLE001
        minio_ok = False

    point_ids = []
    try:
        point_ids = vectors.scroll_point_ids_for_document(str(document.id))
        if not point_ids:
            point_ids = [
                str(c.qdrant_point_id)
                for c in db.scalars(select(Chunk).where(Chunk.document_id == document.id))
            ]
    except Exception:  # noqa: BLE001
        point_ids = []

    qdrant_ok = True
    if point_ids and vectors.client.collection_exists(vectors.collection):
        from qdrant_client.http import models as qm

        pts, _ = vectors.client.scroll(
            collection_name=vectors.collection,
            scroll_filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="document_id",
                        match=qm.MatchValue(value=str(document.id)),
                    )
                ]
            ),
            limit=max(len(point_ids), 256),
            with_payload=True,
            with_vectors=False,
        )
        tagged = [
            p
            for p in pts
            if str((p.payload or {}).get("workspace_id") or "") == str(target.id)
        ]
        qdrant_ok = len(pts) == 0 or len(tagged) == len(pts)
    elif not point_ids:
        qdrant_ok = True  # zero-vector documents are valid

    if already_owned and minio_ok and document.storage_key == canonical and qdrant_ok:
        return "skipped_already_correct"

    if dry_run:
        logger.info(
            "phase2c_dry_run_item",
            extra={
                "migration_run_id": run_id,
                "document_id": str(document.id),
                "target_workspace_id": str(target.id),
                "step": "dry_run",
                "status": "would_migrate",
                "source_key": document.storage_key,
                "destination_key": canonical,
                "qdrant_point_count": len(point_ids),
            },
        )
        return "would_migrate"

    # 1) Copy MinIO source → canonical (no source delete)
    source_key = None
    for key in resolve_document_storage_key(document.id, None).candidate_read_keys(
        document.storage_key,
        include_legacy_flat=True,
    ):
        if storage.object_exists(key):
            source_key = key
            break
    if source_key is None and not minio_ok:
        logger.error(
            "phase2c_missing_minio",
            extra={
                "migration_run_id": run_id,
                "document_id": str(document.id),
                "step": "minio_copy",
                "status": "missing_minio",
            },
        )
        return "missing_minio"

    if not minio_ok and source_key is not None:
        data = storage.get_bytes(source_key)
        storage.put_bytes(canonical, data, "application/pdf")
        if not storage.object_exists(canonical):
            raise AppError(ErrorCategory.STORAGE_ERROR, "Canonical MinIO object missing after copy")
        # Prefer verifying length; hash when byte_size known
        if document.byte_size is not None and len(data) != document.byte_size:
            # Update byte_size from trusted object
            document.byte_size = len(data)
        elif document.byte_size is None:
            document.byte_size = len(data)
        # Optional content hash check against Document.sha256 when source is original upload
        digest = _sha256_bytes(data)
        if document.sha256 and digest != document.sha256:
            # Still allow — derived objects / re-encoded pages shouldn't block; log only.
            logger.warning(
                "phase2c_sha_mismatch_on_copy",
                extra={
                    "migration_run_id": run_id,
                    "document_id": str(document.id),
                    "step": "minio_copy",
                    "status": "sha_mismatch",
                },
            )

    # 2) PostgreSQL ownership + storage_key BEFORE exposing as workspace RAG
    document.workspace_id = target.id
    document.storage_key = canonical
    if document.byte_size is None and minio_ok:
        # Best-effort size from re-read
        try:
            document.byte_size = len(storage.get_bytes(canonical))
        except Exception:  # noqa: BLE001
            pass
    db.commit()

    # 3) Qdrant payload update
    if point_ids:
        if vectors.client.collection_exists(vectors.collection):
            vectors._ensure_payload_indexes()
            vectors.set_payload(point_ids, {"workspace_id": str(target.id)})

    logger.info(
        "phase2c_migrated_item",
        extra={
            "migration_run_id": run_id,
            "document_id": str(document.id),
            "target_workspace_id": str(target.id),
            "step": "complete",
            "status": "completed",
            "source_key": source_key,
            "destination_key": canonical,
            "qdrant_point_count": len(point_ids),
        },
    )
    return "completed"


def run(*, dry_run: bool, verify_only: bool = False) -> MigrationStats:
    settings = get_settings()
    run_id = str(uuid.uuid4())
    db = SessionLocal()
    storage = MinioObjectStorage(settings)
    vectors = QdrantVectorStore(settings)
    stats = MigrationStats(
        migration_run_id=run_id,
        target_workspace_id=None,
        target_workspace_slug=settings.default_workspace_slug,
        mode="verify" if verify_only else ("dry_run" if dry_run else "apply"),
    )
    try:
        target = resolve_target_workspace(db)
        stats.target_workspace_id = str(target.id)
        stats.target_workspace_slug = target.slug

        items = inventory_legacy(db, storage, vectors)
        stats.legacy_documents = len(items)
        stats.zero_vectors = sum(1 for i in items if (i.qdrant_point_count or 0) == 0)
        stats.missing_minio = sum(1 for i in items if i.minio_source_exists is False)

        conflicts = detect_conflicts(db, target, items)
        stats.conflicts = len(conflicts)
        stats.conflict_details = conflicts
        if conflicts and not verify_only:
            logger.error(
                "phase2c_conflicts_abort",
                extra={"migration_run_id": run_id, "conflicts": len(conflicts)},
            )
            return stats

        if verify_only:
            # Report remaining NULL + partially migrated owned rows with incomplete stores
            null_count = db.scalar(
                select(func.count()).select_from(Document).where(Document.workspace_id.is_(None))
            )
            stats.legacy_documents = int(null_count or 0)
            orphans, retained = build_orphan_report(
                db, target=target, storage=storage, vectors=vectors
            )
            stats.orphan_report = orphans
            stats.legacy_minio_sources_retained = retained
            return stats

        for item in items:
            doc = db.get(Document, uuid.UUID(item.document_id))
            if doc is None:
                continue
            try:
                status = migrate_one(
                    db,
                    document=doc,
                    target=target,
                    storage=storage,
                    vectors=vectors,
                    dry_run=dry_run,
                    run_id=run_id,
                )
                if status == "completed":
                    stats.completed += 1
                elif status == "skipped_already_correct":
                    stats.skipped_already_correct += 1
                elif status == "would_migrate":
                    stats.would_migrate += 1
                elif status == "missing_minio":
                    stats.missing_minio += 1
                    stats.failed += 1
                    stats.failures.append({"document_id": item.document_id, "error": status})
                else:
                    stats.failed += 1
                    stats.failures.append({"document_id": item.document_id, "error": status})
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                stats.failed += 1
                stats.failures.append({"document_id": item.document_id, "error": str(exc)})
                logger.exception(
                    "phase2c_item_failed",
                    extra={
                        "migration_run_id": run_id,
                        "document_id": item.document_id,
                        "step": "migrate_one",
                        "status": "failed",
                    },
                )
        return stats
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Phase 2C legacy document migration")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)

    stats = run(dry_run=args.dry_run, verify_only=args.verify)
    print(asdict(stats))
    if stats.conflicts > 0 and not args.verify:
        return 2
    if stats.failed > 0:
        return 1
    if args.verify and stats.legacy_documents > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
