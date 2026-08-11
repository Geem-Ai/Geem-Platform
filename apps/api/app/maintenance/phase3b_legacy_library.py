"""Phase 3B — create Legacy Library Expert for the default Workspace.

Idempotent:

* Resolves DEFAULT_WORKSPACE_SLUG (tenant migration Workspace only)
* Creates (or reuses) a Workspace Expert named ``Legacy Library``
* Links every active Document in that Workspace to the Expert
* Synchronizes Qdrant ``expert_ids`` without re-embedding
* Reconciles Expert status

Does NOT create Legacy Library for other Workspaces.
Does NOT move Documents into Platform Knowledge.
Does NOT change MinIO keys.

Usage (from apps/api):

    python -m app.maintenance.phase3b_legacy_library --dry-run
    python -m app.maintenance.phase3b_legacy_library --apply
    python -m app.maintenance.phase3b_legacy_library --verify
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
from app.experts.models import (
    Expert,
    ExpertDocument,
    ExpertStatus,
    ExpertType,
    ExpertVisibility,
)
from app.experts.status import ExpertStatusReconciler
from app.workspaces.models import WorkspaceKind

logger = logging.getLogger(__name__)

LEGACY_LIBRARY_NAME = "Legacy Library"
LEGACY_LIBRARY_INSTRUCTIONS = (
    "You answer questions using the Workspace's migrated document library. "
    "Prefer citing the supplied sources. Match the user's language."
)


@dataclass
class LegacyLibraryStats:
    workspace_id: str | None = None
    expert_id: str | None = None
    expert_created: bool = False
    documents_considered: int = 0
    links_created: int = 0
    links_already: int = 0
    synced: int = 0
    errors: list[str] = field(default_factory=list)


def run(*, apply: bool, verify_only: bool) -> LegacyLibraryStats:
    settings = get_settings()
    stats = LegacyLibraryStats()
    db = SessionLocal()
    try:
        from app.workspaces.service import WorkspaceService

        ws_svc = WorkspaceService(db, settings)
        workspace = ws_svc.workspaces.get_by_slug(settings.default_workspace_slug)
        if workspace is None:
            stats.errors.append(
                f"Default Workspace slug={settings.default_workspace_slug!r} not found."
            )
            return stats
        if workspace.kind != WorkspaceKind.TENANT.value:
            stats.errors.append("Default Workspace is not a tenant Workspace.")
            return stats

        stats.workspace_id = str(workspace.id)

        expert = db.scalar(
            select(Expert).where(
                Expert.workspace_id == workspace.id,
                Expert.type == ExpertType.WORKSPACE.value,
                Expert.name == LEGACY_LIBRARY_NAME,
                Expert.deleted_at.is_(None),
            )
        )

        if verify_only:
            if expert is None:
                stats.errors.append("Legacy Library Expert missing.")
                return stats
            stats.expert_id = str(expert.id)
            docs = list(
                db.scalars(
                    select(Document).where(
                        Document.workspace_id == workspace.id,
                        Document.deleted_at.is_(None),
                    )
                )
            )
            stats.documents_considered = len(docs)
            linked = {
                row
                for row in db.scalars(
                    select(ExpertDocument.document_id).where(
                        ExpertDocument.expert_id == expert.id
                    )
                )
            }
            missing = [d.id for d in docs if d.id not in linked]
            if missing:
                stats.errors.append(f"{len(missing)} default-Workspace Document(s) not linked.")
            sync = ExpertVectorMembershipSynchronizer(db, settings)
            for doc in docs:
                expected = {str(x) for x in sync.list_active_expert_ids_for_document(doc.id)}
                actual = set(sync.vectors.get_payload_expert_ids_for_document(str(doc.id)) or [])
                # Only compare when points exist
                point_ids = sync.vectors.scroll_point_ids_for_document(str(doc.id))
                if point_ids and expected != actual:
                    stats.errors.append(
                        f"Qdrant mismatch for document {doc.id}: expected={sorted(expected)} actual={sorted(actual)}"
                    )
            return stats

        if expert is None:
            if not apply:
                stats.expert_created = True
                stats.expert_id = "(would-create)"
            else:
                expert = Expert(
                    workspace_id=workspace.id,
                    type=ExpertType.WORKSPACE.value,
                    name=LEGACY_LIBRARY_NAME,
                    description="Migrated MVP documents for this Workspace.",
                    system_instructions=LEGACY_LIBRARY_INSTRUCTIONS,
                    rag_config={},
                    status=ExpertStatus.DRAFT.value,
                    visibility=ExpertVisibility.WORKSPACE.value,
                    created_by=workspace.created_by,
                )
                db.add(expert)
                db.flush()
                stats.expert_created = True
                stats.expert_id = str(expert.id)
        else:
            stats.expert_id = str(expert.id)

        docs = list(
            db.scalars(
                select(Document).where(
                    Document.workspace_id == workspace.id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        stats.documents_considered = len(docs)

        if expert is None and not apply:
            # dry-run without expert — assume all would be linked
            stats.links_created = len(docs)
            return stats

        assert expert is not None or not apply

        existing_links = set()
        if expert is not None:
            existing_links = {
                row
                for row in db.scalars(
                    select(ExpertDocument.document_id).where(
                        ExpertDocument.expert_id == expert.id
                    )
                )
            }

        for doc in docs:
            if doc.id in existing_links:
                stats.links_already += 1
                continue
            if not apply:
                stats.links_created += 1
                continue
            db.add(
                ExpertDocument(
                    expert_id=expert.id,
                    document_id=doc.id,
                    source_id=None,
                )
            )
            stats.links_created += 1

        if apply:
            db.commit()
            sync = ExpertVectorMembershipSynchronizer(db, settings)
            for doc in docs:
                try:
                    sync.sync_document(doc.id)
                    stats.synced += 1
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"sync {doc.id}: {exc}")
            if expert is not None:
                ExpertStatusReconciler(db).reconcile(expert.id)
                db.commit()

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
    print(stats)
    if stats.errors:
        for err in stats.errors:
            print("ERROR:", err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
