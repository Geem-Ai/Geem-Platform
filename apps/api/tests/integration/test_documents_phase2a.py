"""Phase 2A — cross-tenant document isolation, hash uniqueness, legacy vs workspace boundary."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.db.models import Document
from app.documents.service import DocumentService


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _unique_pdf(marker: bytes | str | None = None) -> bytes:
    """Vary page geometry so sha256 differs across fixtures when needed."""
    raw = marker.encode() if isinstance(marker, str) else (marker or uuid.uuid4().bytes)
    seed = int.from_bytes(raw[:4].ljust(4, b"\0"), "big")
    writer = PdfWriter()
    writer.add_blank_page(width=100 + (seed % 80), height=100 + ((seed // 80) % 80))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture()
def mock_storage_and_ingest():
    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.api.documents.enqueue_ingest", return_value="task-id") as enqueue,
    ):
        storage = MagicMock()
        storage.get_bytes.return_value = b"%PDF-1.4 mock"
        storage.get_document_bytes.return_value = (b"%PDF-1.4 mock", "documents/x/original.pdf")

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage_cls.return_value = storage
        yield storage, enqueue


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


def test_cross_tenant_document_isolation(client, register_user, mock_storage_and_ingest) -> None:
    storage, _ = mock_storage_and_ingest
    user_a = register_user(email="doc-a@example.com")
    user_b = register_user(email="doc-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "Doc A", "doc-a")
    ws_b = _create_workspace(client, user_b["access_token"], "Doc B", "doc-b")

    pdf_a = _unique_pdf(b"A")
    pdf_b = _unique_pdf(b"B")

    up_a = _upload(client, _ws_headers(user_a["access_token"], ws_a), pdf_a, "a.pdf")
    up_b = _upload(client, _ws_headers(user_b["access_token"], ws_b), pdf_b, "b.pdf")
    assert up_a.status_code == 200, up_a.text
    assert up_b.status_code == 200, up_b.text
    doc_a = up_a.json()["id"]
    doc_b = up_b.json()["id"]

    # Listing
    list_a = client.get("/api/documents", headers=_ws_headers(user_a["access_token"], ws_a))
    list_b = client.get("/api/documents", headers=_ws_headers(user_b["access_token"], ws_b))
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    ids_a = {d["id"] for d in list_a.json()["items"]}
    ids_b = {d["id"] for d in list_b.json()["items"]}
    assert doc_a in ids_a and doc_b not in ids_a
    assert doc_b in ids_b and doc_a not in ids_b

    # Get
    assert (
        client.get(
            f"/api/documents/{doc_a}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 200
    )
    denied_get = client.get(
        f"/api/documents/{doc_b}",
        headers=_ws_headers(user_a["access_token"], ws_a),
    )
    assert denied_get.status_code == 404
    assert denied_get.json()["code"] == "document_not_found"

    denied_get_b = client.get(
        f"/api/documents/{doc_a}",
        headers=_ws_headers(user_b["access_token"], ws_b),
    )
    assert denied_get_b.status_code == 404

    # Download
    assert (
        client.get(
            f"/api/documents/{doc_a}/file",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/documents/{doc_b}/file",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/documents/{doc_a}/file",
            headers=_ws_headers(user_b["access_token"], ws_b),
        ).status_code
        == 404
    )

    # Reprocess
    assert (
        client.post(
            f"/api/documents/{doc_b}/reprocess",
            headers=_ws_headers(user_a["access_token"], ws_a),
            json={"mode": "full"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/documents/{doc_a}/reprocess",
            headers=_ws_headers(user_b["access_token"], ws_b),
            json={"mode": "full"},
        ).status_code
        == 404
    )

    # Delete
    assert (
        client.delete(
            f"/api/documents/{doc_b}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/documents/{doc_a}",
            headers=_ws_headers(user_b["access_token"], ws_b),
        ).status_code
        == 404
    )

    # Own delete succeeds (soft)
    assert (
        client.delete(
            f"/api/documents/{doc_a}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/documents/{doc_a}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )
    # Phase 8: logical delete also purges MinIO objects
    assert storage.delete.called


def test_forged_workspace_header_and_host_denied_for_documents(
    client, register_user, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="forge-a@example.com")
    user_b = register_user(email="forge-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "Forge A", "forge-a")
    ws_b = _create_workspace(client, user_b["access_token"], "Forge B", "forge-b")

    up = _upload(
        client,
        _ws_headers(user_b["access_token"], ws_b),
        _unique_pdf(b"F"),
        "secret.pdf",
    )
    assert up.status_code == 200
    doc_b = up.json()["id"]

    forged = client.get(
        f"/api/documents/{doc_b}",
        headers=_auth(user_a["access_token"], **{"X-Workspace-Id": ws_b["id"]}),
    )
    assert forged.status_code == 403
    assert forged.json()["code"] == "workspace_access_denied"

    host = client.get(
        "/api/documents",
        headers={
            **_auth(user_a["access_token"]),
            "Host": "forge-b.localhost",
        },
    )
    assert host.status_code == 403

    # A with own workspace still cannot see B's document
    assert (
        client.get(
            f"/api/documents/{doc_b}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )


def test_same_hash_across_workspaces_and_duplicate_within(
    client, register_user, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="hash-a@example.com")
    user_b = register_user(email="hash-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "Hash A", "hash-a")
    ws_b = _create_workspace(client, user_b["access_token"], "Hash B", "hash-b")

    same_pdf = _unique_pdf(b"SAME")

    up_a = _upload(client, _ws_headers(user_a["access_token"], ws_a), same_pdf)
    up_b = _upload(client, _ws_headers(user_b["access_token"], ws_b), same_pdf)
    assert up_a.status_code == 200, up_a.text
    assert up_b.status_code == 200, up_b.text
    assert up_a.json()["id"] != up_b.json()["id"]

    dup = _upload(client, _ws_headers(user_a["access_token"], ws_a), same_pdf)
    assert dup.status_code == 409
    assert dup.json()["code"] == "document_already_exists"


def test_unauthenticated_document_routes_denied(
    client, register_user, mock_storage_and_ingest
) -> None:
    """Phase 2C: no Authorization → 401 (legacy population removed)."""
    user = register_user(email="bound-a@example.com")
    ws = _create_workspace(client, user["access_token"], "Bound A", "bound-a")
    up = _upload(
        client,
        _ws_headers(user["access_token"], ws),
        _unique_pdf(b"WS"),
        "ws.pdf",
    )
    assert up.status_code == 200, up.text
    doc_id = up.json()["id"]

    assert client.get("/api/documents").status_code == 401
    assert client.get(f"/api/documents/{doc_id}").status_code == 401
    assert client.get(f"/api/documents/{doc_id}/file").status_code == 401
    assert client.post(f"/api/documents/{doc_id}/reprocess", json={"mode": "full"}).status_code == 401
    assert client.delete(f"/api/documents/{doc_id}").status_code == 401
    assert _upload(client, {}, _unique_pdf(b"LEG"), "legacy.pdf").status_code == 401

    detail = client.get(
        f"/api/documents/{doc_id}",
        headers=_ws_headers(user["access_token"], ws),
    )
    assert detail.status_code == 200
    job_id = detail.json().get("job_id")
    if job_id:
        assert client.get(f"/api/jobs/{job_id}").status_code == 401
        assert (
            client.get(
                f"/api/jobs/{job_id}",
                headers=_ws_headers(user["access_token"], ws),
            ).status_code
            == 200
        )


def test_new_user_workspace_does_not_see_other_workspace_docs(
    client, register_user, mock_storage_and_ingest
) -> None:
    owner = register_user(email="owner-seed@example.com")
    owner_ws = _create_workspace(client, owner["access_token"], "Owner", "owner-seed")
    seeded = _upload(
        client,
        _ws_headers(owner["access_token"], owner_ws),
        _unique_pdf(b"SEED"),
        "seed.pdf",
    )
    assert seeded.status_code == 200
    seed_id = seeded.json()["id"]

    newbie = register_user(email="newbie@example.com")
    ws = _create_workspace(client, newbie["access_token"], "Newbie", "newbie-ws")
    listed = client.get("/api/documents", headers=_ws_headers(newbie["access_token"], ws))
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert listed.json()["total"] == 0
    assert (
        client.get(
            f"/api/documents/{seed_id}",
            headers=_ws_headers(newbie["access_token"], ws),
        ).status_code
        == 404
    )


def test_workspace_upload_sets_byte_size_and_workspace_id(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="bytes@example.com")
    ws = _create_workspace(client, user["access_token"], "Bytes", "bytes-ws")
    pdf = _unique_pdf(b"BY")
    res = _upload(client, _ws_headers(user["access_token"], ws), pdf)
    assert res.status_code == 200
    body = res.json()
    assert body["byte_size"] == len(pdf)
    row = db.get(Document, uuid.UUID(body["id"]))
    assert row is not None
    assert row.workspace_id == uuid.UUID(ws["id"])
    assert row.byte_size == len(pdf)


def test_soft_delete_releases_hash_for_reupload(
    client, register_user, mock_storage_and_ingest
) -> None:
    user = register_user(email="reup@example.com")
    ws = _create_workspace(client, user["access_token"], "Reup", "reup-ws")
    pdf = _unique_pdf(b"RE")
    headers = _ws_headers(user["access_token"], ws)
    first = _upload(client, headers, pdf)
    assert first.status_code == 200
    doc_id = first.json()["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 200
    second = _upload(client, headers, pdf)
    assert second.status_code == 200
    assert second.json()["id"] != doc_id


def test_legacy_service_paths_retired(db, mock_storage_and_ingest) -> None:
    from app.core.errors import AppError, ErrorCategory
    from app.documents.service import DocumentService

    mock_storage_and_ingest
    svc = DocumentService(db)
    with pytest.raises(AppError) as exc:
        svc.upload(_unique_pdf(b"ALIAS"), "alias.pdf")
    assert exc.value.category == ErrorCategory.UNAUTHORIZED
