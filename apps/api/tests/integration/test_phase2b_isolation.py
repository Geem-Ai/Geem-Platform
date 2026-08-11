"""Phase 2B — Celery/MinIO/Qdrant/RAG tenant isolation + invalid Bearer fail-closed."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.common.request_context import clear_request_context, get_request_context
from app.common.tenant_context import tenant_context
from app.core.errors import AppError, ErrorCategory
from app.db.models import Chunk, Document
from app.rag.service import RagService
from app.storage.document_keys import resolve_document_storage_key, workspace_document_key
from app.storage.scopes import WorkspaceRagScope
from app.worker.tasks import ingest_document
from sqlalchemy import select


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


@pytest.fixture()
def mock_storage_and_ingest():
    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.api.documents.enqueue_ingest", return_value="task-id") as enqueue,
    ):
        storage = MagicMock()
        storage.get_document_bytes.return_value = (b"%PDF-1.4 mock", "documents/x/original.pdf")
        storage.put_document_bytes.side_effect = lambda **kw: resolve_document_storage_key(
            kw["document_id"], kw.get("workspace_id")
        )
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


# ---------------------------------------------------------------------------
# Auth mode: invalid Bearer must NEVER fall back to legacy
# ---------------------------------------------------------------------------


def test_invalid_bearer_never_falls_back_to_documents(client, mock_storage_and_ingest) -> None:
    mock_storage_and_ingest
    for headers in (
        {"Authorization": "Bearer totally-invalid"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "not-a-scheme token"},
    ):
        res = client.get("/api/documents", headers=headers)
        assert res.status_code == 401, headers
        assert res.json()["code"] in {"unauthorized", "session_expired", "session_revoked"}

    assert client.get("/api/documents").status_code == 401
    assert _upload(client, {}, _unique_pdf("LEG")).status_code == 401


def test_invalid_bearer_never_falls_back_to_legacy_query(client) -> None:
    # Phase 3B: /api/query requires expert_id, but auth failure MUST NOT be
    # short-circuited by body-schema validation. Send a well-formed body so
    # any 401/422 mixup would surface immediately.
    body = {"question": "hello", "expert_id": str(uuid.uuid4())}
    res = client.post(
        "/api/query",
        headers={"Authorization": "Bearer garbage-token"},
        json=body,
    )
    assert res.status_code == 401
    assert res.json()["code"] in {"unauthorized", "session_expired", "session_revoked"}
    assert client.post("/api/query", json=body).status_code == 401


def test_expired_session_does_not_become_legacy(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    from datetime import datetime, timedelta, timezone

    from app.identity.repository import SessionRepository
    from app.identity.security import hash_refresh_token

    mock_storage_and_ingest
    body = register_user(email="expire-q@example.com")
    refresh = body["_refresh"]
    session = SessionRepository(db).get_by_token_hash(hash_refresh_token(refresh))
    assert session is not None
    session.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.flush()

    # Access token may still decode; session check should fail → 401.
    res = client.get("/api/documents", headers=_auth(body["access_token"]))
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Storage keys
# ---------------------------------------------------------------------------


def test_workspace_upload_uses_prefixed_minio_key(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    storage, enqueue = mock_storage_and_ingest
    user = register_user(email="key-a@example.com")
    ws = _create_workspace(client, user["access_token"], "Key A", "key-a")
    pdf = _unique_pdf("KEYA")
    res = _upload(client, _ws_headers(user["access_token"], ws), pdf)
    assert res.status_code == 200
    doc = db.get(Document, uuid.UUID(res.json()["id"]))
    assert doc is not None
    expected = workspace_document_key(ws["id"], doc.id)
    assert doc.storage_key == expected
    assert doc.workspace_id == uuid.UUID(ws["id"])
    # Celery enqueue carries workspace_id
    assert enqueue.called
    kwargs = enqueue.call_args.kwargs
    assert kwargs.get("workspace_id") == ws["id"]


def test_same_hash_different_workspace_keys(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="sha-a@example.com")
    user_b = register_user(email="sha-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "SHA A", "sha-a2")
    ws_b = _create_workspace(client, user_b["access_token"], "SHA B", "sha-b2")
    same = _unique_pdf("SAMEHASH")
    a = _upload(client, _ws_headers(user_a["access_token"], ws_a), same)
    b = _upload(client, _ws_headers(user_b["access_token"], ws_b), same)
    assert a.status_code == 200 and b.status_code == 200
    doc_a = db.get(Document, uuid.UUID(a.json()["id"]))
    doc_b = db.get(Document, uuid.UUID(b.json()["id"]))
    assert doc_a is not None and doc_b is not None
    assert doc_a.sha256 == doc_b.sha256
    assert doc_a.storage_key != doc_b.storage_key
    assert str(ws_a["id"]) in doc_a.storage_key
    assert str(ws_b["id"]) in doc_b.storage_key


# ---------------------------------------------------------------------------
# Celery tenant contract
# ---------------------------------------------------------------------------


def test_ingest_task_workspace_mismatch_fail_closed(db) -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    # Minimal Document row owned by A
    from app.workspaces.models import Workspace

    db.add(Workspace(id=ws_a, name="A", slug=f"a-{ws_a.hex[:8]}", status="active"))
    db.add(Workspace(id=ws_b, name="B", slug=f"b-{ws_b.hex[:8]}", status="active"))
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_a,
        title="t",
        original_filename="t.pdf",
        storage_key=workspace_document_key(ws_a, uuid.uuid4()),
        sha256="b" * 64,
        mime_type="application/pdf",
        byte_size=1,
        page_count=1,
        status="queued",
    )
    # Fix storage_key to use real doc id
    doc.storage_key = workspace_document_key(ws_a, doc.id)
    db.add(doc)
    db.commit()

    with patch("app.worker.tasks.IngestionPipeline") as pipe_cls:
        pipe = MagicMock()
        pipe_cls.return_value = pipe
        result = ingest_document.run(
            str(doc.id),
            mode="full",
            workspace_id=str(ws_b),
            actor_id=None,
        )
        assert result["status"] == "failed"
        pipe.run.assert_not_called()


def test_ingest_task_matching_workspace_runs(db) -> None:
    from app.workspaces.models import Workspace

    ws = uuid.uuid4()
    db.add(Workspace(id=ws, name="W", slug=f"w-{ws.hex[:8]}", status="active"))
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws,
        title="t",
        original_filename="t.pdf",
        storage_key="x",
        sha256="c" * 64,
        mime_type="application/pdf",
        byte_size=1,
        page_count=1,
        status="queued",
    )
    doc.storage_key = workspace_document_key(ws, doc.id)
    db.add(doc)
    db.commit()

    with patch("app.worker.tasks.IngestionPipeline") as pipe_cls:
        pipe = MagicMock()
        pipe_cls.return_value = pipe
        result = ingest_document.run(str(doc.id), mode="full", workspace_id=str(ws))
        assert result["status"] == "ready"
        pipe.run.assert_called_once()


def test_tenant_context_cleared_between_tasks() -> None:
    clear_request_context()
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    with tenant_context(workspace_id=ws_a, document_id=uuid.uuid4()):
        assert get_request_context().workspace_id == ws_a
    assert get_request_context().workspace_id is None
    with tenant_context(workspace_id=ws_b, document_id=uuid.uuid4()):
        assert get_request_context().workspace_id == ws_b
    assert get_request_context().workspace_id is None


# ---------------------------------------------------------------------------
# RAG isolation (mocked vector store)
# ---------------------------------------------------------------------------


def _seed_ready_doc(db, *, workspace_id, title: str, secret: str) -> Document:
    from app.workspaces.models import Workspace

    assert workspace_id is not None
    existing = db.get(Workspace, workspace_id)
    if existing is None:
        db.add(
            Workspace(
                id=workspace_id,
                name=f"WS-{workspace_id.hex[:6]}",
                slug=f"s-{workspace_id.hex[:10]}",
                status="active",
            )
        )
        db.flush()
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        title=title,
        original_filename=f"{title}.pdf",
        storage_key=workspace_document_key(workspace_id, uuid.uuid4()),
        sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        mime_type="application/pdf",
        byte_size=10,
        page_count=1,
        status="ready",
    )
    doc.storage_key = workspace_document_key(workspace_id, doc.id)
    db.add(doc)
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        document_page_id=None,  # type: ignore[arg-type]
        page_number=1,
        ordinal=0,
        canonical_text=secret,
        search_text=secret,
        token_count=5,
        content_hash=uuid.uuid4().hex,
        qdrant_point_id=uuid.uuid4(),
        embedding_model="test",
        embedding_version="v1",
    )
    # Chunk requires document_page_id FK — create a page
    from app.db.models import DocumentPage

    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=1,
        status="parsed",
        canonical_text=secret,
        search_text=secret,
        text_length=len(secret),
    )
    db.add(page)
    db.flush()
    chunk.document_page_id = page.id
    db.add(chunk)
    db.commit()
    return doc


def test_rag_workspace_isolation_adversarial(db) -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    doc_a = _seed_ready_doc(db, workspace_id=ws_a, title="A", secret="ALPHA_SECRET_123")
    doc_b = _seed_ready_doc(db, workspace_id=ws_b, title="B", secret="BETA_SECRET_456")

    vectors = MagicMock()
    # If somehow B's chunk is returned, enrichment must drop it; also assert filter.
    chunk_b = db.scalar(select(Chunk).where(Chunk.document_id == doc_b.id))
    assert chunk_b is not None
    vectors.search_workspace.return_value = [
        {
            "chunk_id": str(chunk_b.id),
            "document_id": str(doc_b.id),
            "workspace_id": str(ws_b),
            "canonical_text": "BETA_SECRET_456",
            "search_text": "BETA_SECRET_456",
            "page": 1,
            "ordinal": 0,
            "vector_score": 0.99,
        }
    ]

    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda q, cands, top_n: cands[:top_n]
    chat = MagicMock()
    chat.answer.return_value = {
        "answer": "none",
        "insufficient_context": True,
        "citation_chunk_ids": [],
        "model": "test",
        "_meta": {},
    }

    svc = RagService(
        db,
        embedder=embedder,
        reranker=reranker,
        chat=chat,
        vectors=vectors,
    )
    # Disable general fallback noise
    svc.settings.general_fallback_enabled = False

    prepared = svc._prepare_context(
        "BETA_SECRET_456",
        scope=WorkspaceRagScope(workspace_id=ws_a),
    )
    # Must call workspace search with A's id
    assert vectors.search_workspace.called
    assert str(vectors.search_workspace.call_args.kwargs["workspace_id"]) == str(ws_a)
    # B's chunk must not enter context (DB ownership check)
    joined = prepared["context"]
    assert "BETA_SECRET_456" not in joined
    assert str(doc_a.id) in str(vectors.search_workspace.call_args.kwargs["document_ids"])
    assert str(doc_b.id) not in vectors.search_workspace.call_args.kwargs["document_ids"]


def test_rag_cross_workspace_document_filter(db) -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    owned = _seed_ready_doc(db, workspace_id=ws_a, title="WS", secret="WORKSPACE_SECRET")
    foreign = _seed_ready_doc(db, workspace_id=ws_b, title="OTHER", secret="FOREIGN_SECRET")

    vectors = MagicMock()
    vectors.search_workspace.return_value = []
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda q, cands, top_n: cands[:top_n]

    svc = RagService(db, embedder=embedder, reranker=reranker, vectors=vectors)
    svc.settings.general_fallback_enabled = False

    ws_prep = svc._prepare_context(
        "WORKSPACE_SECRET", scope=WorkspaceRagScope(workspace_id=ws_a)
    )
    assert vectors.search_workspace.called
    ws_ids = vectors.search_workspace.call_args.kwargs["document_ids"]
    assert str(owned.id) in ws_ids
    assert str(foreign.id) not in ws_ids
    assert "FOREIGN_SECRET" not in ws_prep["context"]


def test_query_forged_workspace_denied(client, register_user, mock_storage_and_ingest) -> None:
    user_a = register_user(email="q-a@example.com")
    user_b = register_user(email="q-b@example.com")
    ws_b = _create_workspace(client, user_b["access_token"], "QB", "q-b")
    # A forges B's workspace. Body includes a valid-shape expert_id so
    # authorization runs before body semantics.
    res = client.post(
        "/api/query",
        headers=_auth(user_a["access_token"], **{"X-Workspace-Id": ws_b["id"]}),
        json={"question": "secret?", "expert_id": str(uuid.uuid4())},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "workspace_access_denied"


def test_soft_deleted_excluded_from_rag(db) -> None:
    ws = uuid.uuid4()
    doc = _seed_ready_doc(db, workspace_id=ws, title="DEL", secret="GONE_SECRET")
    doc.soft_delete()
    db.commit()

    vectors = MagicMock()
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    svc = RagService(db, embedder=embedder, vectors=vectors)
    with pytest.raises(AppError) as exc:
        svc._prepare_context("GONE", scope=WorkspaceRagScope(workspace_id=ws))
    assert exc.value.category == ErrorCategory.VALIDATION


def test_unscoped_vector_search_rejected() -> None:
    from app.storage.qdrant_store import QdrantVectorStore

    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.settings = MagicMock()
    store.collection = "test"
    store.client = MagicMock()
    with pytest.raises(AppError) as exc:
        QdrantVectorStore.search(store, [0.1], top_k=5)
    assert exc.value.category == ErrorCategory.VALIDATION
