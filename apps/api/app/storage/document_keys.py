"""Centralized MinIO object key layout for documents (Phase 2C).

Canonical Workspace keys:
  workspaces/{workspace_id}/documents/{document_id}/original.pdf

Legacy flat keys (``documents/{id}/original.pdf``) are retained only as:
  - migration/rollback source copies
  - explicit maintenance dual-read when ``include_legacy_flat=True``

Production HTTP Document reads use stored_key → canonical only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


ORIGINAL_SUFFIX = "original.pdf"


@dataclass(frozen=True, slots=True)
class DocumentStorageKey:
    """Resolved object keys for a Document. Prefer ``canonical`` for writes."""

    canonical: str
    legacy_flat: str
    workspace_id: uuid.UUID | None

    @property
    def is_workspace(self) -> bool:
        return self.workspace_id is not None

    def candidate_read_keys(
        self,
        stored_key: str | None = None,
        *,
        include_legacy_flat: bool = False,
    ) -> list[str]:
        """Ordered keys to try for reads (authorized Document only).

        Production path (default): stored key → canonical workspace key.
        Maintenance / rekey may set ``include_legacy_flat=True`` to also try
        the pre-2B flat key (orphaned rollback copy).
        """
        keys: list[str] = []
        candidates = [stored_key, self.canonical]
        if include_legacy_flat or self.workspace_id is None:
            candidates.append(self.legacy_flat)
        for key in candidates:
            if key and key not in keys:
                keys.append(key)
        return keys


def legacy_document_key(document_id: uuid.UUID | str) -> str:
    return f"documents/{document_id}/{ORIGINAL_SUFFIX}"


def workspace_document_key(workspace_id: uuid.UUID | str, document_id: uuid.UUID | str) -> str:
    return f"workspaces/{workspace_id}/documents/{document_id}/{ORIGINAL_SUFFIX}"


def resolve_document_storage_key(
    document_id: uuid.UUID | str,
    workspace_id: uuid.UUID | str | None,
) -> DocumentStorageKey:
    flat = legacy_document_key(document_id)
    if workspace_id is None:
        return DocumentStorageKey(canonical=flat, legacy_flat=flat, workspace_id=None)
    ws = uuid.UUID(str(workspace_id))
    return DocumentStorageKey(
        canonical=workspace_document_key(ws, document_id),
        legacy_flat=flat,
        workspace_id=ws,
    )


# Backward-compatible alias used by older call sites.
def document_storage_key(document_id: str, workspace_id: str | None = None) -> str:
    return resolve_document_storage_key(document_id, workspace_id).canonical
