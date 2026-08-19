"""Phase 11A — Workspace / Expert / Conversation soft-delete + retention purge."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey
from app.api_keys.service import ApiKeyService
from app.apps_catalog.models import AppCategory, AppInstallation, AppInstallationStatus, CatalogApp
from app.audit import AuditAction, AuditLog
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.types import ConnectionHealth, ConnectionStatus, ConnectorAuthMode
from app.conversations.models import Conversation, MessageRole
from app.conversations.service import ConversationService
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.documents.service import DocumentService
from app.experts.models import Expert
from app.identity.models import User
from app.retention.service import RetentionPurgeService
from app.storage.document_keys import resolve_document_storage_key
from app.storage.minio_storage import MinioObjectStorage
from app.storage.qdrant_store import QdrantVectorStore
from app.workspaces.models import Workspace, WorkspaceStatus
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import has_permission
from tests.support.rbac import add_workspace_member, get_membership


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client: TestClient, token: str, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _ws_headers(token: str, workspace: dict) -> dict[str, str]:
    return _auth(token, **{"X-Workspace-Id": workspace["id"]})


def _backdate_deleted(db: Session, row, *, days: int = 31) -> None:
    row.deleted_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.commit()
    db.refresh(row)


def _host_object_store_settings() -> Settings:
    """MinIO/Qdrant settings from the repo `.env`, rewritten for host-side pytest."""
    env_file = Path(__file__).resolve().parents[3] / ".env"
    kwargs: dict[str, object] = {}
    if env_file.is_file():
        kwargs["_env_file"] = env_file
        kwargs["_env_file_encoding"] = "utf-8"
    settings = Settings(**kwargs)
    minio_endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
    if minio_endpoint.startswith("minio:") or minio_endpoint.endswith(":9000"):
        # infra/docker-compose.yml publishes MinIO S3 on host 9100.
        minio_endpoint = "localhost:9100"
    qdrant_url = settings.qdrant_url.replace("qdrant:", "localhost:")
    return settings.model_copy(
        update={
            "minio_endpoint": minio_endpoint,
            "qdrant_url": qdrant_url,
            "qdrant_collection": "geem_test_purge_11a",
        }
    )


def _live_object_stores() -> tuple[Settings, MinioObjectStorage, QdrantVectorStore, int] | None:
    """Return real MinIO + Qdrant clients, or None when infra is down."""
    try:
        settings = _host_object_store_settings()
        storage = MinioObjectStorage(settings=settings)
        storage.ensure_bucket()
        vectors = QdrantVectorStore(settings=settings)
        if not vectors.client.collection_exists(vectors.collection):
            vectors.ensure_collection(8)
        info = vectors.client.get_collection(vectors.collection)
        size = int(info.config.params.vectors.size)  # type: ignore[union-attr]
        return settings, storage, vectors, size
    except Exception:
        return None


def _qdrant_has_document(vectors: QdrantVectorStore, document_id: uuid.UUID) -> bool:
    from qdrant_client.http import models as qm

    if not vectors.client.collection_exists(vectors.collection):
        return False
    records, _ = vectors.client.scroll(
        collection_name=vectors.collection,
        scroll_filter=qm.Filter(
            must=[
                qm.FieldCondition(
                    key="document_id",
                    match=qm.MatchValue(value=str(document_id)),
                )
            ]
        ),
        limit=1,
        with_payload=False,
        with_vectors=False,
    )
    return bool(records)


def test_soft_deleted_workspace_cannot_resolve(client, register_user, db: Session) -> None:
    user = register_user(email="p11a-ws-del@example.com")
    ws = _create_workspace(client, user["access_token"], "Gone", "p11a-ws-gone")
    headers = _auth(user["access_token"])
    deleted = client.delete(f"/api/workspaces/{ws['id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    listed = client.get("/api/workspaces", headers=headers)
    assert listed.status_code == 200
    assert all(item["id"] != ws["id"] for item in listed.json())

    fetched = client.get(f"/api/workspaces/{ws['id']}", headers=headers)
    assert fetched.status_code == 404

    row = db.get(Workspace, uuid.UUID(ws["id"]))
    assert row is not None
    assert row.deleted_at is not None
    assert row.status == WorkspaceStatus.ARCHIVED.value


def test_workspace_delete_rbac_member_forbidden(client, register_user, db: Session) -> None:
    owner = register_user(email="p11a-owner@example.com")
    member = register_user(email="p11a-member@example.com")
    ws = _create_workspace(client, owner["access_token"], "RBAC", "p11a-ws-rbac")
    add_workspace_member(db, ws["id"], member["user"]["id"], "member")
    membership = get_membership(db, ws["id"], member["user"]["id"])
    assert has_permission(membership, WorkspacePermission.WORKSPACE_DELETE) is False

    res = client.delete(
        f"/api/workspaces/{ws['id']}",
        headers=_auth(member["access_token"]),
    )
    assert res.status_code == 403
    still = db.get(Workspace, uuid.UUID(ws["id"]))
    assert still is not None and still.deleted_at is None


def test_api_keys_from_deleted_workspace_cannot_auth(client, register_user, db: Session) -> None:
    user = register_user(email="p11a-key@example.com")
    ws = _create_workspace(client, user["access_token"], "Keys", "p11a-ws-keys")
    headers = _ws_headers(user["access_token"], ws)
    created = client.post("/api/api-keys", headers=headers, json={"name": "bot"})
    assert created.status_code == 201, created.text
    secret = created.json()["key"]

    client.delete(f"/api/workspaces/{ws['id']}", headers=_auth(user["access_token"]))
    key_row = db.scalar(select(ApiKey).where(ApiKey.workspace_id == uuid.UUID(ws["id"])))
    assert key_row is not None and key_row.revoked_at is not None

    with pytest.raises(AppError) as exc:
        ApiKeyService(db).authenticate(secret)
    assert exc.value.category in {
        ErrorCategory.UNAUTHORIZED,
        ErrorCategory.WORKSPACE_ACCESS_DENIED,
    }


def test_soft_deleted_expert_hidden_and_isolated(client, register_user) -> None:
    user = register_user(email="p11a-ex@example.com")
    ws = _create_workspace(client, user["access_token"], "Exp", "p11a-ex-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "Alpha"}).json()
    gone = client.delete(f"/api/experts/{expert['id']}", headers=headers)
    assert gone.status_code == 204, gone.text

    listed = client.get("/api/experts", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    items = payload if isinstance(payload, list) else payload.get("items") or payload.get("experts") or []
    assert all(item["id"] != expert["id"] for item in items)
    assert client.get(f"/api/experts/{expert['id']}", headers=headers).status_code == 404
    conv = client.post("/api/conversations", headers=headers, json={"expert_id": expert["id"]})
    assert conv.status_code in {403, 404}


def test_soft_deleted_conversation_cannot_continue(client, register_user, db: Session) -> None:
    user = register_user(email="p11a-cv@example.com")
    ws = _create_workspace(client, user["access_token"], "Chat", "p11a-cv-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "C"}).json()
    conv = client.post("/api/conversations", headers=headers, json={"expert_id": expert["id"]})
    assert conv.status_code == 201, conv.text
    cid = conv.json()["id"]
    assert client.delete(f"/api/conversations/{cid}", headers=headers).status_code == 204

    listed = client.get("/api/conversations", headers=headers)
    assert all(item["id"] != cid for item in listed.json())
    assert client.get(f"/api/conversations/{cid}", headers=headers).status_code == 404

    actor_id = uuid.UUID(user["user"]["id"])
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = get_membership(db, ws["id"], actor_id)
    actor = db.get(User, actor_id)
    with pytest.raises(AppError) as exc:
        ConversationService(db).append_message(
            workspace=workspace,
            membership=membership,
            actor=actor,
            conversation_id=uuid.UUID(cid),
            role=MessageRole.USER.value,
            content="nope",
        )
    assert exc.value.category == ErrorCategory.CONVERSATION_NOT_FOUND


def test_conversation_purge_retention_and_idempotent(client, register_user, db: Session) -> None:
    user = register_user(email="p11a-cv-purge@example.com")
    other = register_user(email="p11a-cv-other@example.com")
    ws_a = _create_workspace(client, user["access_token"], "A", "p11a-cv-a")
    ws_b = _create_workspace(client, other["access_token"], "B", "p11a-cv-b")
    ha = _ws_headers(user["access_token"], ws_a)
    hb = _ws_headers(other["access_token"], ws_b)
    ea = client.post("/api/experts", headers=ha, json={"name": "EA"}).json()
    eb = client.post("/api/experts", headers=hb, json={"name": "EB"}).json()
    ca = client.post("/api/conversations", headers=ha, json={"expert_id": ea["id"]}).json()
    cb = client.post("/api/conversations", headers=hb, json={"expert_id": eb["id"]}).json()
    client.delete(f"/api/conversations/{ca['id']}", headers=ha)

    conv_a = db.get(Conversation, uuid.UUID(ca["id"]))
    assert RetentionPurgeService(db).purge_conversation(conv_a.id) is False
    assert db.get(Conversation, conv_a.id) is not None

    _backdate_deleted(db, conv_a)
    svc = RetentionPurgeService(db)
    assert svc.purge_conversation(conv_a.id) is True
    assert db.get(Conversation, conv_a.id) is None
    assert svc.purge_conversation(uuid.UUID(ca["id"])) is True
    assert db.get(Conversation, uuid.UUID(cb["id"])) is not None


def test_expert_purge_does_not_touch_other_workspace(client, register_user, db: Session) -> None:
    user_a = register_user(email="p11a-ex-a@example.com")
    user_b = register_user(email="p11a-ex-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p11a-exa")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p11a-exb")
    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)
    ea = client.post("/api/experts", headers=ha, json={"name": "EA"}).json()
    eb = client.post("/api/experts", headers=hb, json={"name": "EB"}).json()
    client.delete(f"/api/experts/{ea['id']}", headers=ha)
    expert_a = db.get(Expert, uuid.UUID(ea["id"]))
    _backdate_deleted(db, expert_a)

    with patch("app.retention.service.ExpertVectorMembershipSynchronizer") as sync_cls:
        sync_cls.return_value.sync_document = MagicMock()
        result = RetentionPurgeService(db).purge_expert(expert_a.id)
    assert result is True
    assert db.get(Expert, uuid.UUID(ea["id"])) is None
    kept = db.get(Expert, uuid.UUID(eb["id"]))
    assert kept is not None and kept.deleted_at is None
    assert kept.workspace_id == uuid.UUID(ws_b["id"])


def _seed_connection(db: Session, workspace_id: uuid.UUID) -> AppConnection:
    category = AppCategory(slug=f"cat-{uuid.uuid4().hex[:8]}", name_key="t")
    db.add(category)
    db.flush()
    app = CatalogApp(
        slug=f"app-{uuid.uuid4().hex[:8]}",
        name="Drive",
        short_description="d",
        category_id=category.id,
        status="published",
        connector_key="google_drive",
    )
    db.add(app)
    db.flush()
    installation = AppInstallation(
        workspace_id=workspace_id,
        app_id=app.id,
        status=AppInstallationStatus.ACTIVE.value,
    )
    db.add(installation)
    db.flush()
    conn = AppConnection(
        workspace_id=workspace_id,
        app_installation_id=installation.id,
        connector_key="google_drive",
        auth_mode=ConnectorAuthMode.OAUTH2.value,
        status=ConnectionStatus.ACTIVE.value,
        health=ConnectionHealth.HEALTHY.value,
    )
    db.add(conn)
    db.flush()
    ConnectorCredentialService(db).set_credentials(
        conn, {"refresh_token": "rt-secret", "access_token": "at-secret"}
    )
    db.commit()
    db.refresh(conn)
    return conn


def test_workspace_purge_isolates_and_clears_connectors(
    client, register_user, db: Session
) -> None:
    user_a = register_user(email="p11a-wsa@example.com")
    user_b = register_user(email="p11a-wsb@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "p11a-wsa")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "p11a-wsb")
    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)
    client.post("/api/experts", headers=ha, json={"name": "EA"})
    client.post("/api/experts", headers=hb, json={"name": "EB"})
    conn = _seed_connection(db, uuid.UUID(ws_a["id"]))
    assert conn.credentials_encrypted

    client.delete(f"/api/workspaces/{ws_a['id']}", headers=_auth(user_a["access_token"]))
    db.refresh(conn)
    assert conn.credentials_encrypted is None
    assert conn.status == ConnectionStatus.REVOKED.value

    row = db.get(Workspace, uuid.UUID(ws_a["id"]))
    _backdate_deleted(db, row)

    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.documents.service.QdrantVectorStore") as vectors_cls,
        patch("app.storage.minio_storage.MinioObjectStorage") as attach_cls,
        patch("app.retention.service.ExpertVectorMembershipSynchronizer") as sync_cls,
        patch("app.retention.service.DocumentService") as doc_svc_cls,
    ):
        storage_cls.return_value = MagicMock()
        vectors_cls.return_value = MagicMock()
        attach_cls.return_value = MagicMock()
        sync_cls.return_value.sync_document = MagicMock()
        doc_svc_cls.return_value.purge_document_lifecycle = MagicMock()
        purged = RetentionPurgeService(db).purge_workspace(row.id)
    assert purged is True
    tomb = db.get(Workspace, uuid.UUID(ws_a["id"]))
    assert tomb is not None
    assert tomb.purged_at is not None
    assert tomb.slug.startswith("deleted-")
    assert db.get(AppConnection, conn.id) is None
    assert db.get(Workspace, uuid.UUID(ws_b["id"])) is not None
    experts_b = list(
        db.scalars(select(Expert).where(Expert.workspace_id == uuid.UUID(ws_b["id"])))
    )
    assert experts_b
    assert RetentionPurgeService(db).purge_workspace(row.id) is True


def test_workspace_purge_does_not_tombstone_when_documents_remain(
    client, register_user, db: Session
) -> None:
    user = register_user(email="p11a-ws-stuck@example.com")
    ws = _create_workspace(client, user["access_token"], "Stuck", "p11a-ws-stuck")
    headers = _auth(user["access_token"])
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    doc = Document(
        workspace_id=workspace.id,
        title="keep",
        original_filename="keep.pdf",
        storage_key="workspaces/x/documents/y/original.pdf",
        sha256="b" * 64,
        mime_type="application/pdf",
        byte_size=10,
        status="ready",
    )
    db.add(doc)
    db.commit()
    client.delete(f"/api/workspaces/{ws['id']}", headers=headers)
    row = db.get(Workspace, uuid.UUID(ws["id"]))
    _backdate_deleted(db, row)

    with (
        patch("app.storage.minio_storage.MinioObjectStorage") as attach_cls,
        patch("app.retention.service.ExpertVectorMembershipSynchronizer") as sync_cls,
        patch("app.retention.service.DocumentService") as doc_svc_cls,
    ):
        attach_cls.return_value = MagicMock()
        sync_cls.return_value.sync_document = MagicMock()
        doc_svc_cls.return_value.purge_document_lifecycle = MagicMock()
        purged = RetentionPurgeService(db).purge_workspace(row.id)
    assert purged is False
    leftover = db.get(Workspace, uuid.UUID(ws["id"]))
    assert leftover is not None
    assert leftover.purged_at is None
    assert db.get(Document, doc.id) is not None


def test_workspace_document_purge_retries_real_minio_and_qdrant(
    client, register_user, db: Session
) -> None:
    stores = _live_object_stores()
    if stores is None:
        pytest.skip("MinIO/Qdrant not reachable")
    live_settings, storage, vectors, vector_size = stores

    user = register_user(email="p11a-ws-live-doc@example.com")
    ws = _create_workspace(client, user["access_token"], "Live", "p11a-ws-live-doc")
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    doc = Document(
        workspace_id=workspace.id,
        title="live",
        original_filename="live.pdf",
        storage_key="pending",
        sha256="c" * 64,
        mime_type="application/pdf",
        byte_size=12,
        status="ready",
    )
    db.add(doc)
    db.flush()
    keys = resolve_document_storage_key(doc.id, workspace.id)
    doc.storage_key = keys.canonical
    db.commit()
    db.refresh(doc)

    storage.put_bytes(keys.canonical, b"%PDF-1.4 live", "application/pdf")
    point_id = str(uuid.uuid4())
    vectors.upsert(
        [
            {
                "id": point_id,
                "vector": [0.01] * vector_size,
                "payload": {
                    "document_id": str(doc.id),
                    "workspace_id": str(workspace.id),
                },
            }
        ]
    )
    assert storage.object_exists(keys.canonical)
    assert _qdrant_has_document(vectors, doc.id)

    client.delete(f"/api/workspaces/{ws['id']}", headers=_auth(user["access_token"]))
    row = db.get(Workspace, uuid.UUID(ws["id"]))
    _backdate_deleted(db, row)

    def _fail_minio(_self, _key: str) -> None:
        raise AppError(ErrorCategory.STORAGE_ERROR, "injected minio failure")

    def _fail_qdrant(_self, _document_id: str, **_kwargs: object) -> None:
        raise AppError(ErrorCategory.QDRANT_FAILED, "injected qdrant failure")

    with (
        patch.object(MinioObjectStorage, "delete", _fail_minio),
        patch.object(QdrantVectorStore, "delete_by_document", _fail_qdrant),
        patch("app.retention.service.ExpertVectorMembershipSynchronizer") as sync_cls,
    ):
        sync_cls.return_value.sync_document = MagicMock()
        first = RetentionPurgeService(db, settings=live_settings).purge_workspace(row.id)
    assert first is False
    db.refresh(row)
    assert row.purged_at is None
    assert db.get(Document, doc.id) is not None
    assert storage.object_exists(keys.canonical)
    assert _qdrant_has_document(vectors, doc.id)

    with patch("app.retention.service.ExpertVectorMembershipSynchronizer") as sync_cls:
        sync_cls.return_value.sync_document = MagicMock()
        second = RetentionPurgeService(db, settings=live_settings).purge_workspace(row.id)
    assert second is True
    tomb = db.get(Workspace, uuid.UUID(ws["id"]))
    assert tomb is not None and tomb.purged_at is not None
    assert db.get(Document, doc.id) is None
    assert storage.object_exists(keys.canonical) is False
    assert _qdrant_has_document(vectors, doc.id) is False


def test_document_lifecycle_purge_retries_external(client, register_user, db: Session) -> None:
    user = register_user(email="p11a-doc@example.com")
    ws = _create_workspace(client, user["access_token"], "Docs", "p11a-docs")
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    doc = Document(
        workspace_id=workspace.id,
        title="t",
        original_filename="t.pdf",
        storage_key="workspaces/x/documents/y/original.pdf",
        sha256="a" * 64,
        mime_type="application/pdf",
        byte_size=10,
        status="ready",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    storage = MagicMock()
    vectors = MagicMock()
    calls = {"n": 0}

    def _delete(_key: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise AppError(ErrorCategory.STORAGE_ERROR, "boom")

    storage.delete.side_effect = _delete
    svc = DocumentService(db, storage=storage, vectors=vectors)
    assert svc.repo.get_for_workspace(workspace.id, doc.id) is not None
    svc.purge_document_lifecycle(workspace.id, doc.id)
    assert db.get(Document, doc.id) is not None
    storage.delete.side_effect = None
    storage.delete.return_value = None
    svc.purge_document_lifecycle(workspace.id, doc.id)
    assert db.get(Document, doc.id) is None
    assert vectors.delete_by_document.called
    assert storage.delete.called


def test_workspace_soft_delete_writes_audit(client, register_user, db: Session) -> None:
    user = register_user(email="p11a-aud-ws@example.com")
    ws = _create_workspace(client, user["access_token"], "Aud", "p11a-aud-ws")
    client.delete(f"/api/workspaces/{ws['id']}", headers=_auth(user["access_token"]))
    row = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_SOFT_DELETED.value,
            AuditLog.entity_id == uuid.UUID(ws["id"]),
        )
    )
    assert row is not None
    assert row.actor_user_id == uuid.UUID(user["user"]["id"])
    assert row.workspace_id == uuid.UUID(ws["id"])
