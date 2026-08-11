"""Phase 3B — Expert-scoped RAG isolation, grants, stale payload, shared docs."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, DocumentPage
from app.experts.access import AuthorizedExpert
from app.experts.knowledge import ExpertKnowledgeResolver, ResolvedExpertKnowledge
from app.experts.membership_sync import ExpertVectorMembershipSynchronizer
from app.experts.models import Expert, ExpertDocument, ExpertStatus, ExpertVisibility
from app.experts.policy import ExpertAction
from app.experts.prompt import compose_expert_system_prompt
from app.experts.rag_config import EffectiveRagConfig
from app.experts.service import ExpertService
from app.identity.models import PlatformRole
from app.identity.repository import UserRepository
from app.rag.service import RagService
from app.storage.scopes import ExpertRagScope
from app.workspaces.models import Workspace
from app.workspaces.repository import MembershipRepository
from app.workspaces.service import WorkspaceService


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
        patch("app.api.documents.enqueue_ingest", return_value="task-id"),
        patch("app.experts.service._enqueue_ingest", return_value="task-id"),
        patch("app.platform_admin.router.enqueue_ingest", return_value="task-id"),
    ):
        storage = MagicMock()
        storage.get_document_bytes.return_value = (
            b"%PDF-1.4 mock",
            "workspaces/x/documents/y/original.pdf",
        )

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage_cls.return_value = storage
        yield storage


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


def _promote_platform_admin(db: Session, user_id: str):
    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _seed_ready_document(db: Session, *, workspace_id: uuid.UUID, title: str, secret: str) -> Document:
    doc_id = uuid.uuid4()
    page_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        title=title,
        original_filename=f"{title}.pdf",
        storage_key=f"workspaces/{workspace_id}/documents/{doc_id}/original.pdf",
        sha256=(uuid.uuid4().hex + uuid.uuid4().hex)[:64],
        mime_type="application/pdf",
        byte_size=10,
        page_count=1,
        status="ready",
    )
    page = DocumentPage(
        id=page_id,
        document_id=doc_id,
        page_number=1,
        status="parsed",
        raw_markdown=secret,
        canonical_text=secret,
        search_text=secret,
        text_length=len(secret),
    )
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        document_page_id=page_id,
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
    db.add(doc)
    db.add(page)
    db.add(chunk)
    db.commit()
    return doc


def test_query_rejects_document_ids_field(client, register_user, mock_storage_and_ingest) -> None:
    user = register_user(email="q-contract@example.com")
    ws = _create_workspace(client, user["access_token"], "QC", "q-contract-ws")
    res = client.post(
        "/api/query",
        headers=_ws_headers(user["access_token"], ws),
        json={
            "question": "hi",
            "expert_id": str(uuid.uuid4()),
            "document_ids": [str(uuid.uuid4())],
        },
    )
    assert res.status_code == 422


def test_query_requires_expert_id(client, register_user, mock_storage_and_ingest) -> None:
    user = register_user(email="q-req@example.com")
    ws = _create_workspace(client, user["access_token"], "QR", "q-req-ws")
    res = client.post(
        "/api/query",
        headers=_ws_headers(user["access_token"], ws),
        json={"question": "hi"},
    )
    assert res.status_code == 422


def test_cross_workspace_expert_query_denied(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="rag-a@example.com")
    user_b = register_user(email="rag-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "RA", "rag-ws-a")
    ws_b = _create_workspace(client, user_b["access_token"], "RB", "rag-ws-b")

    ea = client.post(
        "/api/experts",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"name": "Expert A"},
    ).json()
    eb = client.post(
        "/api/experts",
        headers=_ws_headers(user_b["access_token"], ws_b),
        json={"name": "Expert B"},
    ).json()

    for eid in (ea["id"], eb["id"]):
        expert = db.get(Expert, uuid.UUID(eid))
        expert.status = ExpertStatus.READY.value
    db.commit()

    denied = client.post(
        "/api/query",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"question": "secret?", "expert_id": eb["id"]},
    )
    assert denied.status_code == 404


def test_same_workspace_expert_isolation_in_prepare(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="same-ws@example.com")
    ws = _create_workspace(client, user["access_token"], "SW", "same-ws-experts")
    headers = _ws_headers(user["access_token"], ws)

    legal = client.post("/api/experts", headers=headers, json={"name": "Legal"}).json()
    hr = client.post("/api/experts", headers=headers, json={"name": "HR"}).json()

    doc_legal = _seed_ready_document(
        db, workspace_id=uuid.UUID(ws["id"]), title="Legal Doc", secret="LEGAL_ONLY_123"
    )
    doc_hr = _seed_ready_document(
        db, workspace_id=uuid.UUID(ws["id"]), title="HR Doc", secret="HR_ONLY_456"
    )

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    svc = ExpertService(db)

    with patch.object(ExpertVectorMembershipSynchronizer, "sync_document", return_value=[]):
        svc.link_document(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=uuid.UUID(legal["id"]),
            document_id=doc_legal.id,
        )
        svc.link_document(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=uuid.UUID(hr["id"]),
            document_id=doc_hr.id,
        )

    for eid in (legal["id"], hr["id"]):
        e = db.get(Expert, uuid.UUID(eid))
        e.status = ExpertStatus.READY.value
    db.commit()

    legal_chunk = db.query(Chunk).filter(Chunk.document_id == doc_legal.id).one()
    hr_chunk = db.query(Chunk).filter(Chunk.document_id == doc_hr.id).one()

    vectors = MagicMock()
    vectors.search_expert.return_value = [
        {
            "chunk_id": str(legal_chunk.id),
            "document_id": str(doc_legal.id),
            "workspace_id": ws["id"],
            "vector_score": 0.9,
            "canonical_text": "LEGAL_ONLY_123",
        },
        {
            "chunk_id": str(hr_chunk.id),
            "document_id": str(doc_hr.id),
            "workspace_id": ws["id"],
            "vector_score": 0.95,
            "canonical_text": "HR_ONLY_456",
        },
    ]
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 8
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda q, items, top_n=6: items[:top_n]

    rag = RagService(db, embedder=embedder, reranker=reranker, vectors=vectors)
    knowledge = ExpertKnowledgeResolver(db).resolve(
        AuthorizedExpert(
            expert=db.get(Expert, uuid.UUID(legal["id"])),
            ownership="workspace",
            workspace=workspace,
            membership=membership,
            action=ExpertAction.USE,
        )
    )
    prepared = rag._prepare_expert_context("Where is HR_ONLY_456?", knowledge, top_k=None)
    texts = " ".join(c.get("canonical_text") or "" for c in prepared["context_chunks"])
    assert "HR_ONLY_456" not in texts
    assert vectors.search_expert.call_args.kwargs["expert_id"] == uuid.UUID(legal["id"])


def test_shared_document_multi_expert_unlink(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="share@example.com")
    ws = _create_workspace(client, user["access_token"], "SH", "share-ws")
    headers = _ws_headers(user["access_token"], ws)
    ea = client.post("/api/experts", headers=headers, json={"name": "EA"}).json()
    eb = client.post("/api/experts", headers=headers, json={"name": "EB"}).json()

    doc = _seed_ready_document(
        db, workspace_id=uuid.UUID(ws["id"]), title="Common", secret="COMMON_SHARED"
    )
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    svc = ExpertService(db)

    synced: list[list[str]] = []

    def _fake_sync(document_id):
        ids = ExpertVectorMembershipSynchronizer(db).list_active_expert_ids_for_document(
            document_id
        )
        synced.append([str(i) for i in ids])
        return [str(i) for i in ids]

    with patch.object(ExpertVectorMembershipSynchronizer, "sync_document", side_effect=_fake_sync):
        svc.link_document(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=uuid.UUID(ea["id"]),
            document_id=doc.id,
        )
        svc.link_document(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=uuid.UUID(eb["id"]),
            document_id=doc.id,
        )
        both = set(synced[-1])
        assert ea["id"] in both and eb["id"] in both

        svc.unlink_document(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=uuid.UUID(ea["id"]),
            document_id=doc.id,
        )
        after = set(synced[-1])
        assert ea["id"] not in after
        assert eb["id"] in after


def test_stale_expert_ids_rejected_before_rerank(
    db, register_user, client, mock_storage_and_ingest
) -> None:
    user = register_user(email="stale@example.com")
    ws = _create_workspace(client, user["access_token"], "ST", "stale-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "StaleE"}).json()

    doc = _seed_ready_document(
        db, workspace_id=uuid.UUID(ws["id"]), title="StaleDoc", secret="STALE_SECRET"
    )
    e = db.get(Expert, uuid.UUID(expert["id"]))
    e.status = ExpertStatus.READY.value
    db.commit()

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    chunk = db.query(Chunk).filter(Chunk.document_id == doc.id).one()

    vectors = MagicMock()
    vectors.search_expert.return_value = [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(doc.id),
            "workspace_id": ws["id"],
            "vector_score": 0.99,
            "canonical_text": "STALE_SECRET",
        }
    ]
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 8
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda q, items, top_n=6: items

    knowledge = ResolvedExpertKnowledge(
        authorized=AuthorizedExpert(
            expert=e,
            ownership="workspace",
            workspace=workspace,
            membership=membership,
            action=ExpertAction.USE,
        ),
        scope=ExpertRagScope(
            consumer_workspace_id=workspace.id,
            knowledge_workspace_id=workspace.id,
            expert_id=e.id,
            expert_type="workspace",
        ),
        system_instructions="test",
        rag_config=EffectiveRagConfig(top_k=10, rerank_top_n=5),
        knowledge_workspace=workspace,
        ready_document_ids=(doc.id,),
        all_linked_document_ids=(doc.id,),
    )

    rag = RagService(db, embedder=embedder, reranker=reranker, vectors=vectors)
    prepared = rag._prepare_expert_context("STALE_SECRET?", knowledge, top_k=None)
    assert all(
        "STALE_SECRET" not in (c.get("canonical_text") or "")
        for c in prepared["context_chunks"]
    )


def test_platform_expert_grant_query_and_revoke(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    admin_body = register_user(email="plat-rag-admin@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    user_a = register_user(email="plat-rag-a@example.com")
    user_b = register_user(email="plat-rag-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "PRA", "plat-rag-a")
    ws_b = _create_workspace(client, user_b["access_token"], "PRB", "plat-rag-b")

    created = client.post(
        "/api/platform/experts",
        headers=_auth(admin_body["access_token"]),
        json={
            "name": "Platform RAG",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
            "system_instructions": "Platform brain",
        },
    )
    assert created.status_code == 201, created.text
    expert_p = created.json()["id"]

    assert (
        client.post(
            "/api/query",
            headers=_ws_headers(user_a["access_token"], ws_a),
            json={"question": "x", "expert_id": expert_p},
        ).status_code
        == 404
    )

    grant = client.post(
        f"/api/platform/experts/{expert_p}/grants",
        headers=_auth(admin_body["access_token"]),
        json={"workspace_id": ws_a["id"]},
    )
    assert grant.status_code == 201

    no_know = client.post(
        "/api/query",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"question": "x", "expert_id": expert_p},
    )
    assert no_know.status_code in {422, 409}
    assert no_know.json()["code"] in {
        "expert_has_no_knowledge",
        "expert_not_ready",
        "expert_knowledge_unavailable",
    }

    assert (
        client.post(
            "/api/query",
            headers=_ws_headers(user_b["access_token"], ws_b),
            json={"question": "x", "expert_id": expert_p},
        ).status_code
        == 404
    )

    admin = UserRepository(db).get_by_id(uuid.UUID(admin_body["user"]["id"]))
    svc = ExpertService(db)
    with patch.object(ExpertVectorMembershipSynchronizer, "sync_document", return_value=[]):
        doc = svc.upload_platform_knowledge_document(
            actor=admin,
            file_bytes=_unique_pdf(b"PLAT"),
            filename="plat.pdf",
        )
        doc.status = "ready"
        db.commit()
        svc.link_platform_document(actor=admin, expert_id=uuid.UUID(expert_p), document_id=doc.id)
        e = db.get(Expert, uuid.UUID(expert_p))
        e.status = ExpertStatus.READY.value
        db.commit()

    assert (
        client.get(
            f"/api/documents/{doc.id}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )

    client.delete(
        f"/api/platform/experts/{expert_p}/grants/{ws_a['id']}",
        headers=_auth(admin_body["access_token"]),
    )
    assert (
        client.post(
            "/api/query",
            headers=_ws_headers(user_a["access_token"], ws_a),
            json={"question": "x", "expert_id": expert_p},
        ).status_code
        == 404
    )


def test_wrong_knowledge_workspace_rejected(
    db, register_user, client, mock_storage_and_ingest
) -> None:
    user = register_user(email="wrong-kw@example.com")
    ws = _create_workspace(client, user["access_token"], "WK", "wrong-kw-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "WKE"}).json()

    pk = WorkspaceService(db).ensure_platform_knowledge_workspace()
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    e = db.get(Expert, uuid.UUID(expert["id"]))

    auth = AuthorizedExpert(
        expert=e,
        ownership="workspace",
        workspace=workspace,
        membership=membership,
        action=ExpertAction.USE,
    )
    knowledge = ExpertKnowledgeResolver(db).resolve(auth)
    assert knowledge.knowledge_workspace_id == workspace.id
    assert knowledge.knowledge_workspace_id != pk.id


def test_expert_instructions_do_not_leak_across_experts() -> None:
    a = compose_expert_system_prompt("BASE", "Instructions for Expert A ONLY")
    b = compose_expert_system_prompt("BASE", "Instructions for Expert B ONLY")
    assert "Expert A ONLY" in a and "Expert A ONLY" not in b
    assert "Expert B ONLY" in b and "Expert B ONLY" not in a


def test_membership_sync_rereads_under_lock(
    db, register_user, client, mock_storage_and_ingest
) -> None:
    user = register_user(email="sync-lock@example.com")
    ws = _create_workspace(client, user["access_token"], "SL", "sync-lock-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "SyncE"}).json()
    doc = _seed_ready_document(
        db, workspace_id=uuid.UUID(ws["id"]), title="SyncDoc", secret="SYNC"
    )
    db.add(ExpertDocument(expert_id=uuid.UUID(expert["id"]), document_id=doc.id))
    db.commit()

    vectors = MagicMock()
    vectors.scroll_point_ids_for_document.return_value = [str(uuid.uuid4())]
    vectors.set_payload = MagicMock()

    sync = ExpertVectorMembershipSynchronizer(db, vectors=vectors)
    result = sync.sync_document(doc.id)
    assert expert["id"] in result
    vectors.set_payload.assert_called()
    payload = vectors.set_payload.call_args.args[1]
    assert expert["id"] in payload["expert_ids"]


def test_deleted_expert_query_not_found(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="del-q@example.com")
    ws = _create_workspace(client, user["access_token"], "DQ", "del-q-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "TempQ"}).json()
    e = db.get(Expert, uuid.UUID(expert["id"]))
    e.status = ExpertStatus.READY.value
    db.commit()
    assert client.delete(f"/api/experts/{expert['id']}", headers=headers).status_code == 204
    assert (
        client.post(
            "/api/query",
            headers=headers,
            json={"question": "x", "expert_id": expert["id"]},
        ).status_code
        == 404
    )


def test_expert_txt_upload_accepted(client, register_user, mock_storage_and_ingest) -> None:
    user = register_user(email="txt-up@example.com")
    ws = _create_workspace(client, user["access_token"], "TU", "txt-up-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "TxtE"}).json()
    res = client.post(
        f"/api/experts/{expert['id']}/upload",
        headers=headers,
        files={"file": ("note.txt", "hello arabic مرحبا".encode("utf-8"), "text/plain")},
    )
    assert res.status_code in {200, 201}, res.text
    body = res.json()
    assert body["document_id"]
