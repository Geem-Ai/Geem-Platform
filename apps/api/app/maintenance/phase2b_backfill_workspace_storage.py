"""Phase 2B maintenance — rekey MinIO + backfill Qdrant workspace_id payloads.

Source of truth: PostgreSQL Document.workspace_id (must be non-NULL).

Usage (from apps/api):

  python -m app.maintenance.phase2b_backfill_workspace_storage --dry-run
  python -m app.maintenance.phase2b_backfill_workspace_storage
  python -m app.maintenance.phase2b_backfill_workspace_storage --limit 50

Idempotent and resumable: already-canonical MinIO keys and already-tagged
Qdrant payloads are skipped. Never assigns ownership by guessing.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Chunk, Document
from app.db.session import SessionLocal
from app.storage.minio_storage import MinioObjectStorage
from app.storage.qdrant_store import QdrantVectorStore

logger = logging.getLogger("geem.maintenance.phase2b")


def backfill(
    *,
    dry_run: bool = False,
    limit: int | None = None,
    document_id: uuid.UUID | None = None,
) -> dict:
    settings = get_settings()
    db = SessionLocal()
    storage = MinioObjectStorage(settings)
    vectors = QdrantVectorStore(settings)
    stats = {
        "documents_seen": 0,
        "minio_rekeyed": 0,
        "minio_already_canonical": 0,
        "minio_missing": 0,
        "qdrant_updated": 0,
        "qdrant_skipped_empty": 0,
        "errors": 0,
        "dry_run": dry_run,
    }
    try:
        stmt = select(Document).where(
            Document.workspace_id.is_not(None),
            Document.deleted_at.is_(None),
        )
        if document_id is not None:
            stmt = stmt.where(Document.id == document_id)
        stmt = stmt.order_by(Document.created_at.asc())
        if limit is not None:
            stmt = stmt.limit(limit)

        documents = list(db.scalars(stmt))
        for document in documents:
            stats["documents_seen"] += 1
            assert document.workspace_id is not None
            try:
                minio_result = storage.rekey_workspace_document(
                    document_id=document.id,
                    workspace_id=document.workspace_id,
                    stored_key=document.storage_key,
                    dry_run=dry_run,
                )
                status = minio_result["status"]
                if status == "rekeyed":
                    stats["minio_rekeyed"] += 1
                    if not dry_run:
                        document.storage_key = minio_result["to"]
                        db.commit()
                elif status == "already_canonical":
                    stats["minio_already_canonical"] += 1
                    # Ensure DB storage_key matches canonical even if object already moved.
                    from app.storage.document_keys import resolve_document_storage_key

                    canonical = resolve_document_storage_key(
                        document.id, document.workspace_id
                    ).canonical
                    if document.storage_key != canonical and not dry_run:
                        document.storage_key = canonical
                        db.commit()
                elif status == "would_rekey":
                    stats["minio_rekeyed"] += 1
                elif status == "source_missing":
                    stats["minio_missing"] += 1

                logger.info(
                    "phase2b_minio",
                    extra={
                        "document_id": str(document.id),
                        "workspace_id": str(document.workspace_id),
                        "operation": "minio_rekey",
                        **minio_result,
                    },
                )

                # Qdrant payload backfill without re-embed.
                point_ids = vectors.scroll_point_ids_for_document(str(document.id))
                if not point_ids:
                    # Fallback: known chunk point IDs from Postgres.
                    point_ids = [
                        str(c.qdrant_point_id)
                        for c in db.scalars(
                            select(Chunk).where(Chunk.document_id == document.id)
                        )
                    ]
                if not point_ids:
                    stats["qdrant_skipped_empty"] += 1
                    continue

                if dry_run:
                    stats["qdrant_updated"] += 1
                    logger.info(
                        "phase2b_qdrant_dry_run",
                        extra={
                            "document_id": str(document.id),
                            "workspace_id": str(document.workspace_id),
                            "point_count": len(point_ids),
                            "operation": "qdrant_payload_backfill",
                        },
                    )
                    continue

                if vectors.client.collection_exists(vectors.collection):
                    vectors._ensure_payload_indexes()
                    vectors.set_payload(
                        point_ids,
                        {"workspace_id": str(document.workspace_id)},
                    )
                    stats["qdrant_updated"] += 1
                    logger.info(
                        "phase2b_qdrant",
                        extra={
                            "document_id": str(document.id),
                            "workspace_id": str(document.workspace_id),
                            "point_count": len(point_ids),
                            "operation": "qdrant_payload_backfill",
                        },
                    )
                else:
                    stats["qdrant_skipped_empty"] += 1
            except Exception:  # noqa: BLE001
                stats["errors"] += 1
                logger.exception(
                    "phase2b_backfill_failed",
                    extra={
                        "document_id": str(document.id),
                        "workspace_id": str(document.workspace_id),
                    },
                )
                db.rollback()
        return stats
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Phase 2B workspace storage/vector backfill")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--document-id", type=str, default=None)
    args = parser.parse_args(argv)
    doc_id = uuid.UUID(args.document_id) if args.document_id else None
    stats = backfill(dry_run=args.dry_run, limit=args.limit, document_id=doc_id)
    print(stats)
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
