"""Phase 2C — legacy migration tooling + post-cutover auth isolation."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter
from sqlalchemy import text

from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.maintenance.phase2c_migrate_legacy import detect_conflicts, migrate_one
from app.storage.document_keys import legacy_document_key, workspace_document_key
from app.workspaces.models import Workspace


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _unique_pdf(marker: bytes | str | None = None) -> bytes:
    raw = marker.encode() if isinstance(marker, str) else (marker or uuid.uuid4().bytes)
    seed = int.from_bytes(raw[:4].ljust(4, b"\0"), "big")
    writer = PdfWriter()
    writer.add_blank_page(width=100 + (seed % 80), height=100 + ((seed // 80) % 80))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _create_workspace(client, token: str, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _ws_headers(token: str, workspace: dict) -> dict[str, str]:
    return _auth(token, **{"X-Workspace-Id": workspace["id"]})


def _upload(client, headers: dict[str, str], data: bytes, filename: str = "doc.pdf"):
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (filename, data, "application/pdf")},
    )


@pytest.fixture()
def mock_storage_and_ingest():
    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.api.documents.enqueue_ingest", return_value="task-id") as enqueue,
    ):
        storage = MagicMock()
        storage.get_document_bytes.return_value = (b"%PDF-1.4 mock", "workspaces/x/documents/y/original.pdf")

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage_cls.return_value = storage
        yield storage, enqueue


@pytest.fixture()
def allow_nullable_workspace_id(db):
    """Temporarily allow NULL workspace_id so migration unit paths can be exercised."""
    db.execute(text("ALTER TABLE documents ALTER COLUMN workspace_id DROP NOT NULL"))
    db.commit()
    yield


def _target_workspace(db) -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        name="Default Workspace",
        slug="default",
        status="active",
    )
    db.add(ws)
    db.commit()
    return ws


def _insert_legacy_document(db, *, sha256: str | None = None, status: str = "ready") -> Document:
    doc_id = uuid.uuid4()
    digest = sha256 or (uuid.uuid4().hex + uuid.uuid4().hex[:32])
    doc = Document(
        id=doc_id,
        workspace_id=None,  # type: ignore[arg-type]
        title="legacy",
        original_filename="legacy.pdf",
        storage_key=legacy_document_key(doc_id),
        sha256=digest,
        mime_type="application/pdf",
        byte_size=12,
        page_count=1,
        status=status,
    )
    db.add(doc)
    db.commit()
    return doc


def test_unauthenticated_cutover_401(client, mock_storage_and_ingest) -> None:
    mock_storage_and_ingest
    assert client.get("/api/documents").status_code == 401
    assert (
        client.post(
            "/api/query",
            json={"question": "x", "expert_id": str(uuid.uuid4())},
        ).status_code
        == 401
    )
    assert client.get(f"/api/jobs/{uuid.uuid4()}").status_code == 401
    assert _upload(client, {}, _unique_pdf("x")).status_code == 401


def test_cross_workspace_and_new_user_isolation(
    client, register_user, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="p2c-a@example.com")
    user_b = register_user(email="p2c-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p2c-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p2c-b")
    up = _upload(client, _ws_headers(user_a["access_token"], ws_a), _unique_pdf("A"))
    assert up.status_code == 200
    doc_a = up.json()["id"]

    assert (
        client.get(
            f"/api/documents/{doc_a}",
            headers=_ws_headers(user_b["access_token"], ws_b),
        ).status_code
        == 404
    )

    newbie = register_user(email="p2c-new@example.com")
    ws_n = _create_workspace(client, newbie["access_token"], "N", "p2c-new")
    assert (
        client.get(
            f"/api/documents/{doc_a}",
            headers=_ws_headers(newbie["access_token"], ws_n),
        ).status_code
        == 404
    )


def test_migrate_dry_run_mutates_nothing(db, allow_nullable_workspace_id) -> None:
    allow_nullable_workspace_id
    target = _target_workspace(db)
    doc = _insert_legacy_document(db)
    storage = MagicMock()
    storage.object_exists.return_value = True
    storage.get_bytes.return_value = b"%PDF-legacy"
    vectors = MagicMock()
    vectors.scroll_point_ids_for_document.return_value = []
    vectors.client.collection_exists.return_value = False

    status = migrate_one(
        db,
        document=doc,
        target=target,
        storage=storage,
        vectors=vectors,
        dry_run=True,
        run_id="dry",
    )
    assert status == "would_migrate"
    db.refresh(doc)
    assert doc.workspace_id is None
    storage.put_bytes.assert_not_called()
    vectors.set_payload.assert_not_called()


def test_migrate_apply_idempotent(db, allow_nullable_workspace_id) -> None:
    allow_nullable_workspace_id
    target = _target_workspace(db)
    doc = _insert_legacy_document(db)
    source = doc.storage_key
    data = b"%PDF-legacy-bytes"
    storage = MagicMock()

    def _exists(key: str) -> bool:
        if key == source:
            return True
        if key == workspace_document_key(target.id, doc.id):
            return bool(getattr(storage, "_canonical", False))
        return False

    storage.object_exists.side_effect = _exists
    storage.get_bytes.return_value = data

    def _put(key, payload, _ct):
        storage._canonical = True

    storage.put_bytes.side_effect = _put
    vectors = MagicMock()
    vectors.scroll_point_ids_for_document.return_value = ["p1"]
    vectors.client.collection_exists.return_value = True
    vectors.client.scroll.return_value = ([], None)

    first = migrate_one(
        db,
        document=doc,
        target=target,
        storage=storage,
        vectors=vectors,
        dry_run=False,
        run_id="apply1",
    )
    assert first == "completed"
    db.refresh(doc)
    assert doc.workspace_id == target.id
    assert doc.storage_key == workspace_document_key(target.id, doc.id)
    # Source must not be deleted (copy-then-cutover)
    storage.delete.assert_not_called()
    assert source == legacy_document_key(doc.id)
    # Second apply: already correct after we report qdrant tagged
    class _Pt:
        def __init__(self):
            self.payload = {"workspace_id": str(target.id), "document_id": str(doc.id)}

    vectors.client.scroll.return_value = ([_Pt()], None)
    second = migrate_one(
        db,
        document=doc,
        target=target,
        storage=storage,
        vectors=vectors,
        dry_run=False,
        run_id="apply2",
    )
    assert second == "skipped_already_correct"


def test_migrate_sha_conflict_detected(db, allow_nullable_workspace_id) -> None:
    allow_nullable_workspace_id
    target = _target_workspace(db)
    digest = "a" * 64
    owned = Document(
        id=uuid.uuid4(),
        workspace_id=target.id,
        title="owned",
        original_filename="o.pdf",
        storage_key=workspace_document_key(target.id, uuid.uuid4()),
        sha256=digest,
        mime_type="application/pdf",
        byte_size=1,
        page_count=1,
        status="ready",
    )
    owned.storage_key = workspace_document_key(target.id, owned.id)
    db.add(owned)
    db.commit()
    legacy = _insert_legacy_document(db, sha256=digest)
    from app.maintenance.phase2c_migrate_legacy import LegacyItem

    conflicts = detect_conflicts(
        db,
        target,
        [
            LegacyItem(
                document_id=str(legacy.id),
                sha256=digest,
                status="ready",
                storage_key=legacy.storage_key,
                byte_size=1,
                created_at=None,
            )
        ],
    )
    assert len(conflicts) == 1
    assert conflicts[0]["sha256"] == digest


def test_migrate_missing_minio(db, allow_nullable_workspace_id) -> None:
    allow_nullable_workspace_id
    target = _target_workspace(db)
    doc = _insert_legacy_document(db)
    storage = MagicMock()
    storage.object_exists.return_value = False
    vectors = MagicMock()
    vectors.scroll_point_ids_for_document.return_value = []
    vectors.client.collection_exists.return_value = False
    status = migrate_one(
        db,
        document=doc,
        target=target,
        storage=storage,
        vectors=vectors,
        dry_run=False,
        run_id="miss",
    )
    assert status == "missing_minio"
    db.refresh(doc)
    assert doc.workspace_id is None


def test_migrate_zero_vector_document(db, allow_nullable_workspace_id) -> None:
    allow_nullable_workspace_id
    target = _target_workspace(db)
    doc = _insert_legacy_document(db, status="failed")
    source = doc.storage_key
    storage = MagicMock()
    storage.object_exists.side_effect = lambda key: key == source or key == workspace_document_key(
        target.id, doc.id
    )
    # First calls: source exists, canonical may not until put
    storage.object_exists.side_effect = None

    exists = {source: True}

    def _exists(key: str) -> bool:
        return exists.get(key, False)

    storage.object_exists.side_effect = _exists
    storage.get_bytes.return_value = b"%PDF-z"

    def _put(key, payload, _ct):
        exists[key] = True

    storage.put_bytes.side_effect = _put
    vectors = MagicMock()
    vectors.scroll_point_ids_for_document.return_value = []
    vectors.client.collection_exists.return_value = False
    status = migrate_one(
        db,
        document=doc,
        target=target,
        storage=storage,
        vectors=vectors,
        dry_run=False,
        run_id="zero",
    )
    assert status == "completed"
    vectors.set_payload.assert_not_called()


def test_legacy_mvp_writes_flag_default_false() -> None:
    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.legacy_mvp_writes_enabled is False
    assert settings.auth_required is True
