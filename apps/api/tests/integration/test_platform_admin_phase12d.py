"""Phase 12D — Platform Admin Platform Experts management."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.audit.models import AuditLog
from app.experts.geem_general import ensure_geem_general_expert
from app.experts.models import ExpertKnowledgeMode, ExpertVisibility
from app.identity.models import PlatformRole, User
from app.identity.repository import UserRepository
from sqlalchemy import select


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _promote_platform_admin(db, user_id: str) -> User:
    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _create_workspace(client, token: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


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
        patch("app.platform_admin.router.enqueue_ingest", return_value="task-id"),
        patch("app.experts.service._enqueue_ingest", return_value="task-id"),
    ):
        storage = MagicMock()
        storage.get_bytes.return_value = b"%PDF-1.4 mock"
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


def _create_platform_expert(client, admin_token: str, name: str = "Platform Expert") -> dict:
    res = client.post(
        "/api/platform/experts",
        headers=_auth(admin_token),
        json={
            "name": name,
            "description": "Test platform expert",
            "system_instructions": "You are a helpful assistant.",
            "visibility": "platform_draft",
            "availability_mode": "selected_workspaces",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_unauthenticated_platform_experts_401(client) -> None:
    res = client.get("/api/platform/experts")
    assert res.status_code == 401


def test_normal_user_platform_experts_403(client, register_user) -> None:
    user = register_user(email="normal-12d@example.com")
    res = client.get("/api/platform/experts", headers=_auth(user["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_platform_admin_list_paginated(client, register_user, db) -> None:
    admin_user = register_user(email="admin-12d-list@example.com")
    admin = _promote_platform_admin(db, admin_user["user"]["id"])
    _create_platform_expert(client, admin_user["access_token"], "Listed Expert")

    res = client.get(
        "/api/platform/experts",
        headers=_auth(admin_user["access_token"]),
        params={"limit": 10, "offset": 0, "search": "Listed"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1
    assert any(item["name"] == "Listed Expert" for item in body["items"])
    assert body["items"][0]["knowledge_document_count"] == 0


def test_platform_admin_detail_exposes_instructions(client, register_user, db) -> None:
    admin_user = register_user(email="admin-12d-detail@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    created = _create_platform_expert(client, admin_user["access_token"], "Detail Expert")

    res = client.get(
        f"/api/platform/experts/{created['id']}",
        headers=_auth(admin_user["access_token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["system_instructions"] == "You are a helpful assistant."
    assert body["rag_config"] is not None


def test_workspace_dto_redacted_for_platform_expert(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    owner = register_user(email="owner-12d-redact@example.com")
    admin_user = register_user(email="admin-12d-redact@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], "ws-12d-redact")
    created = _create_platform_expert(client, admin_user["access_token"], "Redacted Expert")

    client.post(
        f"/api/platform/experts/{created['id']}/publish",
        headers=_auth(admin_user["access_token"]),
    )
    client.post(
        f"/api/platform/experts/{created['id']}/workspace-grants",
        headers=_auth(admin_user["access_token"]),
        json={"workspace_id": ws["id"]},
    )

    tenant = client.get(
        f"/api/experts/{created['id']}",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert tenant.status_code == 200, tenant.text
    body = tenant.json()
    assert body["system_instructions"] is None
    assert body["rag_config"] is None


def test_publish_unpublish_and_audit(client, register_user, db) -> None:
    admin_user = register_user(email="admin-12d-pub@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    created = _create_platform_expert(client, admin_user["access_token"], "Publish Expert")

    pub = client.post(
        f"/api/platform/experts/{created['id']}/publish",
        headers=_auth(admin_user["access_token"]),
    )
    assert pub.status_code == 200, pub.text
    assert pub.json()["visibility"] == ExpertVisibility.PLATFORM_PUBLISHED.value

    db.commit()
    db.expire_all()
    audits = db.scalars(
        select(AuditLog).where(AuditLog.action == "platform_expert.publish")
    ).all()
    assert any(str(a.entity_id) == created["id"] for a in audits)

    unp = client.post(
        f"/api/platform/experts/{created['id']}/unpublish",
        headers=_auth(admin_user["access_token"]),
    )
    assert unp.status_code == 200, unp.text
    assert unp.json()["visibility"] == ExpertVisibility.PLATFORM_DRAFT.value


def test_create_expert_audit_persists_after_commit(client, register_user, db) -> None:
    from app.db.session import SessionLocal

    admin_user = register_user(email="admin-12d-audit-create@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    created = _create_platform_expert(client, admin_user["access_token"], "Audit Create Expert")
    expert_id = created["id"]

    fresh = SessionLocal()
    try:
        rows = fresh.scalars(
            select(AuditLog).where(
                AuditLog.action == "platform_expert.create",
                AuditLog.entity_id == uuid.UUID(expert_id),
            )
        ).all()
        assert len(rows) == 1
    finally:
        fresh.close()


def test_patch_visibility_audits_publish(client, register_user, db) -> None:
    admin_user = register_user(email="admin-12d-patch-vis@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    created = _create_platform_expert(client, admin_user["access_token"], "Patch Vis Expert")

    res = client.patch(
        f"/api/platform/experts/{created['id']}",
        headers=_auth(admin_user["access_token"]),
        json={"visibility": ExpertVisibility.PLATFORM_PUBLISHED.value},
    )
    assert res.status_code == 200, res.text

    db.commit()
    db.expire_all()
    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.action == "platform_expert.publish",
            AuditLog.entity_id == uuid.UUID(created["id"]),
        )
    ).all()
    assert len(audits) == 1
    assert audits[0].extra.get("via") == "patch"


def test_geem_general_cannot_unpublish(client, register_user, db) -> None:
    admin_user = register_user(email="admin-12d-general@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    geem = ensure_geem_general_expert(db)
    assert geem.knowledge_mode == ExpertKnowledgeMode.GENERAL.value

    res = client.post(
        f"/api/platform/experts/{geem.id}/unpublish",
        headers=_auth(admin_user["access_token"]),
    )
    assert res.status_code == 403
    assert res.json()["code"] == "expert_immutable"


def test_workspace_grants_and_revoke(client, register_user, db) -> None:
    owner = register_user(email="owner-12d-grant@example.com")
    admin_user = register_user(email="admin-12d-grant@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], "ws-12d-grant")
    created = _create_platform_expert(client, admin_user["access_token"], "Grant Expert")

    client.post(
        f"/api/platform/experts/{created['id']}/publish",
        headers=_auth(admin_user["access_token"]),
    )

    grant = client.post(
        f"/api/platform/experts/{created['id']}/workspace-grants",
        headers=_auth(admin_user["access_token"]),
        json={"workspace_id": ws["id"]},
    )
    assert grant.status_code == 201, grant.text

    dup = client.post(
        f"/api/platform/experts/{created['id']}/workspace-grants",
        headers=_auth(admin_user["access_token"]),
        json={"workspace_id": ws["id"]},
    )
    assert dup.status_code == 201

    listed = client.get(
        f"/api/platform/experts/{created['id']}/workspace-grants",
        headers=_auth(admin_user["access_token"]),
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    tenant_list = client.get(
        "/api/experts",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert any(e["id"] == created["id"] for e in tenant_list.json())

    revoke = client.delete(
        f"/api/platform/experts/{created['id']}/workspace-grants/{ws['id']}",
        headers=_auth(admin_user["access_token"]),
    )
    assert revoke.status_code == 204

    tenant_list2 = client.get(
        "/api/experts",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert not any(e["id"] == created["id"] for e in tenant_list2.json())


def test_all_workspaces_access(client, register_user, db) -> None:
    owner = register_user(email="owner-12d-all@example.com")
    admin_user = register_user(email="admin-12d-all@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], "ws-12d-all")
    created = _create_platform_expert(client, admin_user["access_token"], "All WS Expert")

    client.post(
        f"/api/platform/experts/{created['id']}/publish",
        headers=_auth(admin_user["access_token"]),
    )
    client.post(
        f"/api/platform/experts/{created['id']}/access/all",
        headers=_auth(admin_user["access_token"]),
    )

    tenant_list = client.get(
        "/api/experts",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert any(e["id"] == created["id"] for e in tenant_list.json())

    client.delete(
        f"/api/platform/experts/{created['id']}/access/all",
        headers=_auth(admin_user["access_token"]),
    )
    tenant_list2 = client.get(
        "/api/experts",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert not any(e["id"] == created["id"] for e in tenant_list2.json())


def test_platform_knowledge_upload_txt(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    admin_user = register_user(email="admin-12d-upload@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    created = _create_platform_expert(client, admin_user["access_token"], "Upload Expert")

    res = client.post(
        f"/api/platform/experts/{created['id']}/knowledge",
        headers=_auth(admin_user["access_token"]),
        files={"file": ("notes.txt", b"Platform knowledge content", "text/plain")},
    )
    assert res.status_code == 201, res.text

    listed = client.get(
        f"/api/platform/experts/{created['id']}/knowledge",
        headers=_auth(admin_user["access_token"]),
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["original_filename"] == "notes.txt"

    detail = client.get(
        f"/api/platform/experts/{created['id']}",
        headers=_auth(admin_user["access_token"]),
    )
    assert detail.json()["knowledge_document_count"] == 1


def test_tenant_cannot_list_platform_knowledge(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    owner = register_user(email="owner-12d-khide@example.com")
    admin_user = register_user(email="admin-12d-khide@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], "ws-12d-khide")
    created = _create_platform_expert(client, admin_user["access_token"], "Hidden Knowledge")

    client.post(
        f"/api/platform/experts/{created['id']}/knowledge",
        headers=_auth(admin_user["access_token"]),
        files={"file": ("secret.txt", b"secret", "text/plain")},
    )
    client.post(
        f"/api/platform/experts/{created['id']}/publish",
        headers=_auth(admin_user["access_token"]),
    )
    client.post(
        f"/api/platform/experts/{created['id']}/workspace-grants",
        headers=_auth(admin_user["access_token"]),
        json={"workspace_id": ws["id"]},
    )

    docs = client.get(
        f"/api/experts/{created['id']}/documents",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert docs.status_code == 200
    assert docs.json() == []
