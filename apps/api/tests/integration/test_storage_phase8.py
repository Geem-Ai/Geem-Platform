"""Phase 8 — Workspace Storage inventory, pagination, download, full purge."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document, DocumentPage
from app.documents.service import DocumentService
from app.experts.models import ExpertDocument
from app.usage.metrics import StorageUsageReason
from app.usage.repository import StorageUsageRepository
from app.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from app.worker.tasks import ingest_document


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _unique_pdf(marker: bytes | str | None = None, *, pages: int = 1) -> bytes:
    raw = marker.encode() if isinstance(marker, str) else (marker or uuid.uuid4().bytes)
    seed = int.from_bytes(raw[:4].ljust(4, b"\0"), "big")
    writer = PdfWriter()
    for i in range(max(1, pages)):
        writer.add_blank_page(
            width=100 + (seed % 80) + i,
            height=100 + ((seed // 80) % 80) + i,
        )
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture()
def mock_stores():
    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.documents.service.QdrantVectorStore") as vectors_cls,
        patch("app.api.documents.enqueue_ingest", return_value="task-id"),
        patch("app.experts.service._enqueue_ingest", return_value="task-id"),
    ):
        storage = MagicMock()
        vectors = MagicMock()
        storage.get_document_bytes.return_value = (
            b"%PDF-1.4 mock",
            "workspaces/x/documents/y/original.pdf",
        )

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage_cls.return_value = storage
        vectors_cls.return_value = vectors
        yield storage, vectors


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


def _add_member(db, workspace_id: str, user_id: str, role: WorkspaceRole) -> None:
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id),
            role=role.value,
        )
    )
    db.commit()


def test_list_is_paginated_and_workspace_isolated(client, register_user, mock_stores) -> None:
    user_a = register_user(email="p8-list-a@example.com")
    user_b = register_user(email="p8-list-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p8-list-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p8-list-b")
    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)

    ids_a = []
    for i, marker in enumerate((b"aa", b"bb", b"cc")):
        up = _upload(client, ha, _unique_pdf(marker, pages=i + 1), f"a{i}.pdf")
        assert up.status_code == 200, up.text
        ids_a.append(up.json()["id"])
    up_b = _upload(client, hb, _unique_pdf(b"zz"), "secret.pdf")
    assert up_b.status_code == 200
    id_b = up_b.json()["id"]

    page = client.get("/api/documents", headers=ha, params={"limit": 2, "offset": 0})
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert id_b not in {row["id"] for row in body["items"]}
    assert all(row["experts"] == [] for row in body["items"])

    page2 = client.get("/api/documents", headers=ha, params={"limit": 2, "offset": 2})
    assert page2.json()["total"] == 3
    assert len(page2.json()["items"]) == 1

    other = client.get("/api/documents", headers=hb)
    assert other.json()["total"] == 1
    assert other.json()["items"][0]["id"] == id_b


def test_list_search_and_expert_names(client, register_user, mock_stores) -> None:
    user = register_user(email="p8-q@example.com")
    ws = _create_workspace(client, user["access_token"], "Q", "p8-q")
    headers = _ws_headers(user["access_token"], ws)
    contract = _upload(client, headers, _unique_pdf(b"contract"), "contract.pdf")
    other = _upload(client, headers, _unique_pdf(b"other"), "notes.pdf")
    assert contract.status_code == 200
    assert other.status_code == 200
    doc_id = contract.json()["id"]

    expert = client.post("/api/experts", headers=headers, json={"name": "Legal"}).json()
    link = client.post(
        f"/api/experts/{expert['id']}/documents",
        headers=headers,
        json={"document_id": doc_id},
    )
    assert link.status_code in {200, 201}, link.text

    found = client.get("/api/documents", headers=headers, params={"q": "contract"})
    assert found.status_code == 200
    assert found.json()["total"] == 1
    item = found.json()["items"][0]
    assert item["id"] == doc_id
    assert item["experts"] == [{"id": expert["id"], "name": "Legal"}]

    missed = client.get("/api/documents", headers=headers, params={"q": "nope"})
    assert missed.json()["items"] == []
    assert missed.json()["total"] == 0


def test_download_uses_mime_and_attachment(
    client, register_user, mock_stores
) -> None:
    storage, _vectors = mock_stores
    user = register_user(email="p8-dl@example.com")
    ws = _create_workspace(client, user["access_token"], "DL", "p8-dl")
    headers = _ws_headers(user["access_token"], ws)
    up = _upload(client, headers, _unique_pdf(b"dl"), "policy.pdf")
    doc_id = up.json()["id"]

    res = client.get(f"/api/documents/{doc_id}/file", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert res.headers["content-disposition"].startswith("attachment;")
    assert "policy.pdf" in res.headers["content-disposition"]
    storage.get_document_bytes.assert_called()

    txt = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("notes.txt", b"hello storage", "text/plain")},
    )
    assert txt.status_code == 200, txt.text
    txt_id = txt.json()["id"]
    txt_res = client.get(f"/api/documents/{txt_id}/file", headers=headers)
    assert txt_res.status_code == 200
    assert txt_res.headers["content-type"].startswith("text/plain")
    assert txt_res.headers["content-disposition"].startswith("attachment;")

    other = register_user(email="p8-dl-b@example.com")
    ws_b = _create_workspace(client, other["access_token"], "DLB", "p8-dl-b")
    denied = client.get(
        f"/api/documents/{doc_id}/file",
        headers=_ws_headers(other["access_token"], ws_b),
    )
    assert denied.status_code == 404


def test_member_can_download(client, register_user, db, mock_stores) -> None:
    owner = register_user(email="p8-mem-o@example.com")
    member = register_user(email="p8-mem-m@example.com")
    ws = _create_workspace(client, owner["access_token"], "Mem", "p8-mem")
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
    headers = _ws_headers(owner["access_token"], ws)
    up = _upload(client, headers, _unique_pdf(b"mem"), "m.pdf")
    doc_id = up.json()["id"]
    res = client.get(
        f"/api/documents/{doc_id}/file",
        headers=_ws_headers(member["access_token"], ws),
    )
    assert res.status_code == 200


def test_purge_removes_blob_vectors_links_and_derived(
    client, register_user, db, mock_stores
) -> None:
    storage, vectors = mock_stores
    user = register_user(email="p8-purge@example.com")
    ws = _create_workspace(client, user["access_token"], "Purge", "p8-purge")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"purge")
    up = _upload(client, headers, pdf, "gone.pdf")
    doc_id = uuid.UUID(up.json()["id"])

    expert = client.post("/api/experts", headers=headers, json={"name": "Ops"}).json()
    assert (
        client.post(
            f"/api/experts/{expert['id']}/documents",
            headers=headers,
            json={"document_id": str(doc_id)},
        ).status_code
        in {200, 201}
    )

    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc_id,
        page_number=1,
        status="parsed",
        canonical_text="secret",
        search_text="secret",
        text_length=6,
    )
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        document_page_id=page.id,
        page_number=1,
        ordinal=0,
        canonical_text="secret",
        search_text="secret",
        token_count=1,
        content_hash=uuid.uuid4().hex,
        qdrant_point_id=uuid.uuid4(),
        embedding_model="test",
        embedding_version="v1",
    )
    db.add(page)
    db.add(chunk)
    db.commit()

    deleted = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    usage = client.get("/api/usage/summary", headers=headers)
    assert usage.status_code == 200, usage.text
    assert usage.json()["storage"]["used_bytes"] == 0

    listed = client.get("/api/documents", headers=headers)
    assert listed.json()["items"] == []
    assert listed.json()["total"] == 0
    assert client.get(f"/api/documents/{doc_id}", headers=headers).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/file", headers=headers).status_code == 404

    knowledge = client.get(f"/api/experts/{expert['id']}/documents", headers=headers)
    assert knowledge.status_code == 200
    assert knowledge.json() == []

    db.expire_all()
    row = db.get(Document, doc_id)
    assert row is not None
    assert row.deleted_at is not None
    assert db.query(Chunk).filter_by(document_id=doc_id).count() == 0
    assert db.query(DocumentPage).filter_by(document_id=doc_id).count() == 0
    assert db.query(ExpertDocument).filter_by(document_id=doc_id).count() == 0

    events = StorageUsageRepository(db).list_for_workspace(uuid.UUID(ws["id"]))
    assert any(e.reason == StorageUsageReason.DELETE.value for e in events)

    assert storage.delete.called
    vectors.delete_by_document.assert_called()
    args, kwargs = vectors.delete_by_document.call_args
    assert args[0] == str(doc_id)
    assert kwargs["workspace_id"] == uuid.UUID(ws["id"])

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    with pytest.raises(AppError) as exc:
        DocumentService(db).restore_for_workspace(workspace, doc_id)
    assert exc.value.category == ErrorCategory.DOCUMENT_DELETED

    again = client.post(
        f"/api/experts/{expert['id']}/upload",
        headers=headers,
        files={"file": ("gone.pdf", pdf, "application/pdf")},
    )
    assert again.status_code == 201, again.text
    assert again.json()["document_id"] != str(doc_id)
    assert again.json()["reused"] is False


def test_ingest_skips_deleted_document(client, register_user, db, mock_stores) -> None:
    user = register_user(email="p8-ingest@example.com")
    ws = _create_workspace(client, user["access_token"], "Ingest", "p8-ingest")
    headers = _ws_headers(user["access_token"], ws)
    up = _upload(client, headers, _unique_pdf(b"ing"), "ing.pdf")
    doc_id = up.json()["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 200

    with patch("app.worker.tasks.IngestionPipeline") as pipeline_cls:
        pipeline_cls.return_value.run.side_effect = AssertionError("must not ingest")
        result = ingest_document.apply(
            args=[str(doc_id)],
            kwargs={"mode": "full", "workspace_id": ws["id"]},
        ).get()
    assert result["status"] == "deleted"
    pipeline_cls.return_value.run.assert_not_called()


def test_pipeline_aborts_when_document_deleted_mid_ingest(
    client, register_user, db, mock_stores
) -> None:
    """Storage purge during ingest must not mark the document ready or re-index."""
    from app.ingestion.pipeline import IngestionPipeline

    user = register_user(email="p8-mid@example.com")
    ws = _create_workspace(client, user["access_token"], "Mid", "p8-mid")
    headers = _ws_headers(user["access_token"], ws)
    up = _upload(client, headers, _unique_pdf(b"mid"), "mid.pdf")
    doc_id = uuid.UUID(up.json()["id"])

    pipeline = IngestionPipeline(db)
    # Soft-delete as Storage would, then attempt ingest on the same session.
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 200
    db.expire_all()

    with pytest.raises(AppError) as exc:
        pipeline.run(doc_id, mode="full")
    assert exc.value.category == ErrorCategory.DOCUMENT_DELETED

    db.expire_all()
    row = db.get(Document, doc_id)
    assert row is not None
    assert row.deleted_at is not None
    assert row.status != "ready"
    assert db.query(Chunk).filter_by(document_id=doc_id).count() == 0


def test_search_treats_percent_as_literal(client, register_user, mock_stores) -> None:
    user = register_user(email="p8-pct@example.com")
    ws = _create_workspace(client, user["access_token"], "Pct", "p8-pct")
    headers = _ws_headers(user["access_token"], ws)
    _upload(client, headers, _unique_pdf(b"plain"), "notes.pdf")
    tagged = client.post(
        "/api/documents",
        headers=headers,
        data={"title": "Growth 100%"},
        files={"file": ("growth.pdf", _unique_pdf(b"pct"), "application/pdf")},
    )
    assert tagged.status_code == 200, tagged.text

    wild = client.get("/api/documents", headers=headers, params={"q": "%"})
    assert wild.status_code == 200
    assert wild.json()["total"] == 1
    assert wild.json()["items"][0]["id"] == tagged.json()["id"]

    unders = client.get("/api/documents", headers=headers, params={"q": "100%"})
    assert unders.json()["total"] == 1
    assert unders.json()["items"][0]["id"] == tagged.json()["id"]

    none = client.get("/api/documents", headers=headers, params={"q": "nope%"})
    assert none.json()["total"] == 0
    assert none.json()["items"] == []


def test_q_does_not_leak_other_workspace(client, register_user, mock_stores) -> None:
    user_a = register_user(email="p8-leak-a@example.com")
    user_b = register_user(email="p8-leak-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "LA", "p8-leak-a")
    ws_b = _create_workspace(client, user_b["access_token"], "LB", "p8-leak-b")
    _upload(
        client,
        _ws_headers(user_b["access_token"], ws_b),
        _unique_pdf(b"secret-name"),
        "unique-secret.pdf",
    )
    found = client.get(
        "/api/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
        params={"q": "unique-secret"},
    )
    assert found.json()["total"] == 0
    assert found.json()["items"] == []
