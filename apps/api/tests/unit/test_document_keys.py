from __future__ import annotations

import uuid

from app.storage.document_keys import (
    document_storage_key,
    legacy_document_key,
    resolve_document_storage_key,
    workspace_document_key,
)


def test_legacy_and_workspace_keys_differ() -> None:
    doc = uuid.uuid4()
    ws = uuid.uuid4()
    assert legacy_document_key(doc) == f"documents/{doc}/original.pdf"
    assert workspace_document_key(ws, doc) == f"workspaces/{ws}/documents/{doc}/original.pdf"
    assert document_storage_key(str(doc)) == legacy_document_key(doc)
    assert document_storage_key(str(doc), str(ws)) == workspace_document_key(ws, doc)


def test_candidate_read_keys_production_excludes_legacy_flat() -> None:
    doc = uuid.uuid4()
    ws = uuid.uuid4()
    resolved = resolve_document_storage_key(doc, ws)
    keys = resolved.candidate_read_keys(stored_key=resolved.canonical)
    assert keys == [resolved.canonical]
    assert resolved.legacy_flat not in keys


def test_candidate_read_keys_maintenance_dual_read() -> None:
    doc = uuid.uuid4()
    ws = uuid.uuid4()
    resolved = resolve_document_storage_key(doc, ws)
    keys = resolved.candidate_read_keys(
        stored_key=legacy_document_key(doc),
        include_legacy_flat=True,
    )
    assert keys[0] == legacy_document_key(doc)
    assert resolved.canonical in keys
    assert resolved.legacy_flat in keys
