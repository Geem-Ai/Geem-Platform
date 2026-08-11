"""Phase 3B — reconcile PostgreSQL expert_documents vs Qdrant expert_ids.

PostgreSQL is authoritative. This command repairs Qdrant payload arrays without
re-embedding.

Usage (from apps/api):

    python -m app.maintenance.sync_expert_vector_memberships --dry-run
    python -m app.maintenance.sync_expert_vector_memberships --apply
    python -m app.maintenance.sync_expert_vector_memberships --verify
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.experts.membership_sync import ExpertVectorMembershipSynchronizer

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    documents_scanned: int = 0
    matched: int = 0
    mismatched: int = 0
    repaired: int = 0
    skipped_no_points: int = 0
    errors: list[str] = field(default_factory=list)
    mismatches: list[dict] = field(default_factory=list)


def run(*, apply: bool, verify_only: bool) -> SyncStats:
    settings = get_settings()
    stats = SyncStats()
    db = SessionLocal()
    try:
        sync = ExpertVectorMembershipSynchronizer(db, settings)
        docs = list(
            db.scalars(
                select(Document).where(Document.deleted_at.is_(None)).order_by(Document.created_at)
            )
        )
        for doc in docs:
            stats.documents_scanned += 1
            expected = sorted(str(x) for x in sync.list_active_expert_ids_for_document(doc.id))
            point_ids = sync.vectors.scroll_point_ids_for_document(str(doc.id))
            if not point_ids:
                # Soft-deleted vectors / not yet ingested — nothing to compare.
                stats.skipped_no_points += 1
                continue
            actual = sorted(sync.vectors.get_payload_expert_ids_for_document(str(doc.id)) or [])
            if expected == actual:
                stats.matched += 1
                continue
            stats.mismatched += 1
            stats.mismatches.append(
                {
                    "document_id": str(doc.id),
                    "workspace_id": str(doc.workspace_id),
                    "expected": expected,
                    "actual": actual,
                }
            )
            if apply and not verify_only:
                try:
                    sync.sync_document(doc.id)
                    stats.repaired += 1
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"{doc.id}: {exc}")
        return stats
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    stats = run(apply=args.apply, verify_only=args.verify)
    print(
        f"scanned={stats.documents_scanned} matched={stats.matched} "
        f"mismatched={stats.mismatched} repaired={stats.repaired} "
        f"skipped_no_points={stats.skipped_no_points}"
    )
    for m in stats.mismatches[:50]:
        print("MISMATCH", m)
    if stats.errors:
        for err in stats.errors:
            print("ERROR:", err, file=sys.stderr)
        return 1
    if args.verify and stats.mismatched:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
