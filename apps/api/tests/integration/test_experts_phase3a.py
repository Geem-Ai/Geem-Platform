"""Phase 3A — system Workspace isolation + Expert cross-tenant / Platform grant tests."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertStatus, ExpertType, ExpertVisibility
from app.experts.service import ExpertService
from app.identity.models import PlatformRole, User, UserStatus
from app.identity.repository import UserRepository
from app.identity.security import hash_password
from app.workspaces.models import WorkspaceKind
from app.workspaces.service import WorkspaceService
from app.workspaces.slug import validate_workspace_slug


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
        patch("app.platform_admin.router.enqueue_ingest", return_value="task-id"),
    ):
        storage = MagicMock()
        storage.get_bytes.return_value = b"%PDF-1.4 mock"
        storage.get_document_bytes.return_value = (b"%PDF-1.4 mock", "workspaces/x/documents/y/original.pdf")

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


def _promote_platform_admin(db, user_id: str) -> User:
    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# System Workspace isolation
# ---------------------------------------------------------------------------


def test_platform_knowledge_slug_reserved() -> None:
    settings = get_settings()
    with pytest.raises(AppError) as exc:
        validate_workspace_slug(settings.platform_knowledge_workspace_slug, settings=settings)
    assert exc.value.category == ErrorCategory.WORKSPACE_SLUG_INVALID


def test_system_workspace_hidden_from_tenant_lists(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="sys-hide@example.com")
    pk = WorkspaceService(db).ensure_platform_knowledge_workspace()
    assert pk.kind == WorkspaceKind.SYSTEM.value

    me = client.get("/api/auth/me", headers=_auth(user["access_token"]))
    assert me.status_code == 200
    slugs = {w["slug"] for w in me.json()["workspaces"]}
    assert pk.slug not in slugs

    listed = client.get("/api/workspaces", headers=_auth(user["access_token"]))
    assert listed.status_code == 200
    assert pk.slug not in {w["slug"] for w in listed.json()}


def test_system_workspace_not_selectable_via_header(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="sys-select@example.com")
    pk = WorkspaceService(db).ensure_platform_knowledge_workspace()
    # Forge system Workspace ID — must not become current Workspace.
    res = client.get(
        "/api/workspaces/current",
        headers=_auth(user["access_token"], **{"X-Workspace-Id": str(pk.id)}),
    )
    assert res.status_code in {403, 404}


def test_system_workspace_hostname_not_tenant(db) -> None:
    from app.common.workspace_resolver import extract_subdomain_slug

    settings = get_settings()
    pk = WorkspaceService(db).ensure_platform_knowledge_workspace()
    slug = extract_subdomain_slug(
        f"{pk.slug}.geem.ai",
        "geem.ai",
        reserved_slugs=settings.reserved_slugs,
    )
    assert slug is None


def test_reserved_slug_cannot_register_as_tenant(client, register_user) -> None:
    user = register_user(email="sys-reg@example.com")
    settings = get_settings()
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": "Evil", "slug": settings.platform_knowledge_workspace_slug},
    )
    assert res.status_code == 422


def test_tenant_cannot_access_system_docs_via_documents_api(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="sys-docs@example.com")
    admin_body = register_user(email="sys-admin@example.com")
    admin = _promote_platform_admin(db, admin_body["user"]["id"])

    svc = ExpertService(db)
    doc = svc.upload_platform_knowledge_document(
        actor=admin,
        file_bytes=_unique_pdf(b"PK"),
        filename="pk.pdf",
    )
    pk = WorkspaceService(db).get_platform_knowledge_workspace()

    ws = _create_workspace(client, user["access_token"], "Tenant", "tenant-sys-docs")
    # Even forging system workspace id must not expose the document.
    forged = client.get(
        f"/api/documents/{doc.id}",
        headers=_auth(user["access_token"], **{"X-Workspace-Id": str(pk.id)}),
    )
    assert forged.status_code in {403, 404}

    via_tenant = client.get(
        f"/api/documents/{doc.id}",
        headers=_ws_headers(user["access_token"], ws),
    )
    assert via_tenant.status_code == 404


def test_platform_admin_can_operate_on_system_workspace(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    admin_body = register_user(email="pk-admin@example.com")
    admin = _promote_platform_admin(db, admin_body["user"]["id"])
    svc = ExpertService(db)
    doc = svc.upload_platform_knowledge_document(
        actor=admin,
        file_bytes=_unique_pdf(b"PK2"),
        filename="pk2.pdf",
    )
    pk = WorkspaceService(db).get_platform_knowledge_workspace()
    assert doc.workspace_id == pk.id
    assert pk.kind == WorkspaceKind.SYSTEM.value


# ---------------------------------------------------------------------------
# Workspace Expert isolation
# ---------------------------------------------------------------------------


def test_cross_workspace_expert_isolation(
    client, register_user, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="ex-a@example.com")
    user_b = register_user(email="ex-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "ex-ws-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "ex-ws-b")

    create_a = client.post(
        "/api/experts",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"name": "Expert A", "system_instructions": "Be helpful A"},
    )
    assert create_a.status_code == 201, create_a.text
    expert_a = create_a.json()["id"]

    create_b = client.post(
        "/api/experts",
        headers=_ws_headers(user_b["access_token"], ws_b),
        json={"name": "Expert B"},
    )
    assert create_b.status_code == 201
    expert_b = create_b.json()["id"]

    # A cannot get/edit/delete B
    assert (
        client.get(
            f"/api/experts/{expert_b}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/experts/{expert_b}",
            headers=_ws_headers(user_a["access_token"], ws_a),
            json={"name": "Hijack"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/experts/{expert_b}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )

    # List only own
    listed = client.get("/api/experts", headers=_ws_headers(user_a["access_token"], ws_a))
    assert listed.status_code == 200
    ids = {e["id"] for e in listed.json()}
    assert expert_a in ids
    assert expert_b not in ids

    # Forged workspace header does not help A access B's expert as B's workspace
    forged = client.get(
        f"/api/experts/{expert_b}",
        headers=_auth(user_a["access_token"], **{"X-Workspace-Id": ws_b["id"]}),
    )
    assert forged.status_code in {403, 404}


def test_cross_workspace_document_link_denied(
    client, register_user, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="link-a@example.com")
    user_b = register_user(email="link-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "LA", "link-ws-a")
    ws_b = _create_workspace(client, user_b["access_token"], "LB", "link-ws-b")

    expert_a = client.post(
        "/api/experts",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"name": "EA"},
    ).json()["id"]
    expert_b = client.post(
        "/api/experts",
        headers=_ws_headers(user_b["access_token"], ws_b),
        json={"name": "EB"},
    ).json()["id"]

    up_a = client.post(
        "/api/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
        files={"file": ("a.pdf", _unique_pdf(b"LA"), "application/pdf")},
    )
    assert up_a.status_code == 200, up_a.text
    doc_a = up_a.json()["id"]

    up_b = client.post(
        "/api/documents",
        headers=_ws_headers(user_b["access_token"], ws_b),
        files={"file": ("b.pdf", _unique_pdf(b"LB"), "application/pdf")},
    )
    doc_b = up_b.json()["id"]

    # A cannot attach B's document to A's expert
    deny_b_doc = client.post(
        f"/api/experts/{expert_a}/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"document_id": doc_b},
    )
    assert deny_b_doc.status_code == 404

    # A cannot attach A's document to B's expert
    deny_b_expert = client.post(
        f"/api/experts/{expert_b}/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"document_id": doc_a},
    )
    assert deny_b_expert.status_code == 404

    # Same-workspace link succeeds; same doc may link to another expert later
    ok = client.post(
        f"/api/experts/{expert_a}/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"document_id": doc_a},
    )
    assert ok.status_code == 201, ok.text

    expert_a2 = client.post(
        "/api/experts",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"name": "EA2"},
    ).json()["id"]
    ok2 = client.post(
        f"/api/experts/{expert_a2}/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"document_id": doc_a},
    )
    assert ok2.status_code == 201


# ---------------------------------------------------------------------------
# Platform Expert grants + mutations
# ---------------------------------------------------------------------------


def test_platform_expert_grant_and_isolation(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    admin_body = register_user(email="plat-admin@example.com")
    admin = _promote_platform_admin(db, admin_body["user"]["id"])
    # Refresh token after role change — JWT still has old role; platform APIs read DB user.
    # get_current_user loads user from DB, so platform_role is current. Good.

    user_a = register_user(email="plat-a@example.com")
    user_b = register_user(email="plat-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "PA", "plat-ws-a")
    ws_b = _create_workspace(client, user_b["access_token"], "PB", "plat-ws-b")

    created = client.post(
        "/api/platform/experts",
        headers=_auth(admin_body["access_token"]),
        json={
            "name": "Platform P",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
            "system_instructions": "Platform brain",
        },
    )
    assert created.status_code == 201, created.text
    expert_p = created.json()["id"]
    assert created.json()["type"] == ExpertType.PLATFORM.value
    assert created.json()["ownership"] == "platform"
    assert created.json()["workspace_id"] is None

    # Without grant — neither workspace sees it
    list_a = client.get("/api/experts", headers=_ws_headers(user_a["access_token"], ws_a))
    assert expert_p not in {e["id"] for e in list_a.json()}
    assert (
        client.get(
            f"/api/experts/{expert_p}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )

    # Grant to A only
    grant = client.post(
        f"/api/platform/experts/{expert_p}/grants",
        headers=_auth(admin_body["access_token"]),
        json={"workspace_id": ws_a["id"]},
    )
    assert grant.status_code == 201, grant.text

    list_a2 = client.get("/api/experts", headers=_ws_headers(user_a["access_token"], ws_a))
    assert expert_p in {e["id"] for e in list_a2.json()}
    owned = next(e for e in list_a2.json() if e["id"] == expert_p)
    assert owned["ownership"] == "platform"
    assert owned["type"] == "platform"

    get_a = client.get(
        f"/api/experts/{expert_p}",
        headers=_ws_headers(user_a["access_token"], ws_a),
    )
    assert get_a.status_code == 200
    # Phase 3C — Workspace-facing Platform Expert DTO redacts internals
    assert get_a.json().get("system_instructions") is None
    assert get_a.json().get("rag_config") is None
    listed_plat = next(e for e in list_a2.json() if e["id"] == expert_p)
    assert listed_plat.get("system_instructions") is None
    assert listed_plat.get("rag_config") is None
    # Knowledge membership is not exposed on Workspace product API
    docs_list = client.get(
        f"/api/experts/{expert_p}/documents",
        headers=_ws_headers(user_a["access_token"], ws_a),
    )
    assert docs_list.status_code == 200
    assert docs_list.json() == []

    # B still cannot
    assert expert_p not in {
        e["id"]
        for e in client.get(
            "/api/experts", headers=_ws_headers(user_b["access_token"], ws_b)
        ).json()
    }

    # A cannot PATCH/DELETE platform expert
    assert (
        client.patch(
            f"/api/experts/{expert_p}",
            headers=_ws_headers(user_a["access_token"], ws_a),
            json={"name": "Nope"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/experts/{expert_p}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 403
    )

    # Platform admin can manage
    patch = client.patch(
        f"/api/platform/experts/{expert_p}",
        headers=_auth(admin_body["access_token"]),
        json={"name": "Platform P2"},
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Platform P2"


def test_platform_document_not_directly_accessible_when_expert_granted(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    admin_body = register_user(email="pd-admin@example.com")
    admin = _promote_platform_admin(db, admin_body["user"]["id"])
    user_a = register_user(email="pd-a@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "PDA", "pd-ws-a")

    svc = ExpertService(db)
    doc = svc.upload_platform_knowledge_document(
        actor=admin,
        file_bytes=_unique_pdf(b"PD"),
        filename="pd.pdf",
    )
    expert = svc.create_platform_expert(
        actor=admin,
        name="Granted P",
        visibility=ExpertVisibility.PLATFORM_PUBLISHED.value,
        status=ExpertStatus.READY.value,
    )
    svc.link_platform_document(actor=admin, expert_id=expert.id, document_id=doc.id)
    svc.grant_platform_expert(actor=admin, expert_id=expert.id, workspace_id=uuid.UUID(ws_a["id"]))

    # Can see Expert
    assert (
        client.get(
            f"/api/experts/{expert.id}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 200
    )
    # Cannot download/read platform Document via tenant Document API
    assert (
        client.get(
            f"/api/documents/{doc.id}",
            headers=_ws_headers(user_a["access_token"], ws_a),
        ).status_code
        == 404
    )


def test_workspace_expert_create_ignores_client_workspace_id(
    client, register_user, mock_storage_and_ingest
) -> None:
    user = register_user(email="own@example.com")
    other = register_user(email="other@example.com")
    ws = _create_workspace(client, user["access_token"], "Own", "own-ws")
    other_ws = _create_workspace(client, other["access_token"], "Other", "other-ws")

    res = client.post(
        "/api/experts",
        headers=_ws_headers(user["access_token"], ws),
        json={
            "name": "Mine",
            "workspace_id": other_ws["id"],  # ignored / not in schema
        },
    )
    assert res.status_code == 201
    assert res.json()["workspace_id"] == ws["id"]
    assert res.json()["type"] == "workspace"
    assert res.json()["ownership"] == "workspace"


def test_member_cannot_create_expert(client, register_user, db, mock_storage_and_ingest) -> None:
    owner = register_user(email="own-m@example.com")
    member = register_user(email="mem-m@example.com")
    ws = _create_workspace(client, owner["access_token"], "MemWS", "mem-ws")

    # Add member via direct membership (service)
    from app.workspaces.models import WorkspaceMembership, WorkspaceRole
    from app.workspaces.repository import MembershipRepository

    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(ws["id"]),
            user_id=uuid.UUID(member["user"]["id"]),
            role=WorkspaceRole.MEMBER.value,
        )
    )
    db.commit()

    res = client.post(
        "/api/experts",
        headers=_ws_headers(member["access_token"], ws),
        json={"name": "Nope"},
    )
    assert res.status_code == 403


def test_expert_soft_delete_keeps_documents(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="del-ex@example.com")
    ws = _create_workspace(client, user["access_token"], "Del", "del-ex-ws")
    headers = _ws_headers(user["access_token"], ws)

    expert = client.post("/api/experts", headers=headers, json={"name": "Temp"}).json()
    up = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("d.pdf", _unique_pdf(b"DEL"), "application/pdf")},
    )
    doc_id = up.json()["id"]
    client.post(
        f"/api/experts/{expert['id']}/documents",
        headers=headers,
        json={"document_id": doc_id},
    )
    assert client.delete(f"/api/experts/{expert['id']}", headers=headers).status_code == 204

    # Document still listed in workspace
    docs = client.get("/api/documents", headers=headers)
    assert doc_id in {d["id"] for d in docs.json()["items"]}
