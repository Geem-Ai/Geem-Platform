"""Phase 11D — Qdrant filter isolation + MinIO authorization isolation."""

from __future__ import annotations

import threading
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pypdf import PdfWriter
import io

from app.storage.qdrant_store import QdrantVectorStore


def _unique_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=120, height=140)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class _Hit:
    def __init__(self, payload: dict, score: float = 0.99, point_id: str = "p") -> None:
        self.payload = payload
        self.score = score
        self.id = point_id


@pytest.mark.isolation
def test_qdrant_search_expert_drops_foreign_payloads_under_concurrency() -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    expert_a = uuid.uuid4()
    expert_b = uuid.uuid4()
    payload_a = {
        "workspace_id": str(ws_a),
        "expert_ids": [str(expert_a)],
        "document_id": str(uuid.uuid4()),
        "chunk_id": "ca",
        "canonical_text": "identical lease clause",
        "search_text": "identical lease clause",
    }
    payload_b = {
        "workspace_id": str(ws_b),
        "expert_ids": [str(expert_b)],
        "document_id": str(uuid.uuid4()),
        "chunk_id": "cb",
        "canonical_text": "identical lease clause",
        "search_text": "identical lease clause",
    }

    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.collection = "test"
    store.client = MagicMock()
    store.client.query_points.return_value = SimpleNamespace(
        points=[_Hit(payload_a), _Hit(payload_b, point_id="pb")]
    )

    errors: list[str] = []

    def _search_a() -> None:
        hits = store.search_expert(
            knowledge_workspace_id=ws_a,
            expert_id=expert_a,
            vector=[0.1, 0.2],
            top_k=8,
        )
        if any(h.get("workspace_id") != str(ws_a) for h in hits):
            errors.append("a-leaked-workspace")
        if any(str(expert_b) in (h.get("expert_ids") or []) for h in hits):
            errors.append("a-leaked-expert")
        if any(h.get("chunk_id") == "cb" for h in hits):
            errors.append("a-got-b-chunk")

    def _search_b() -> None:
        hits = store.search_expert(
            knowledge_workspace_id=ws_b,
            expert_id=expert_b,
            vector=[0.1, 0.2],
            top_k=8,
        )
        if any(h.get("workspace_id") != str(ws_b) for h in hits):
            errors.append("b-leaked-workspace")
        if any(h.get("chunk_id") == "ca" for h in hits):
            errors.append("b-got-a-chunk")

    threads = [threading.Thread(target=_search_a) for _ in range(8)] + [
        threading.Thread(target=_search_b) for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
        assert not t.is_alive()
    assert errors == []

    call_filter = store.client.query_points.call_args.kwargs.get("query_filter")
    assert call_filter is not None


@pytest.mark.isolation
def test_minio_download_is_workspace_authorized(client, register_user) -> None:
    def _auth(token: str, workspace: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": workspace["id"],
        }

    user_a = register_user(email="iso-minio-a@example.com")
    user_b = register_user(email="iso-minio-b@example.com")
    ws_a = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user_a['access_token']}"},
        json={"name": "A", "slug": "iso-minio-a"},
    ).json()
    ws_b = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user_b['access_token']}"},
        json={"name": "B", "slug": "iso-minio-b"},
    ).json()

    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.api.documents.enqueue_ingest", return_value="task-id"),
    ):
        storage = MagicMock()
        storage.get_document_bytes.return_value = (b"%PDF-1.4 secret-b", "workspaces/b/doc.pdf")
        storage.put_document_bytes.side_effect = lambda **kw: SimpleNamespace(
            canonical=f"workspaces/{kw['workspace_id']}/documents/{kw['document_id']}/original.pdf"
        )
        storage_cls.return_value = storage

        from app.storage.document_keys import resolve_document_storage_key

        storage.put_document_bytes.side_effect = lambda **kw: resolve_document_storage_key(
            kw["document_id"], kw.get("workspace_id")
        )

        upload_b = client.post(
            "/api/documents",
            headers=_auth(user_b["access_token"], ws_b),
            files={"file": ("b.pdf", _unique_pdf(), "application/pdf")},
        )
        assert upload_b.status_code in {200, 201}, upload_b.text
        doc_b = upload_b.json()["id"]

        denied = client.get(
            f"/api/documents/{doc_b}/file",
            headers=_auth(user_a["access_token"], ws_a),
        )
        assert denied.status_code in {403, 404}, denied.text
        assert b"secret-b" not in denied.content
        assert "secret-b" not in denied.text

        allowed = client.get(
            f"/api/documents/{doc_b}/file",
            headers=_auth(user_b["access_token"], ws_b),
        )
        assert allowed.status_code == 200, allowed.text
