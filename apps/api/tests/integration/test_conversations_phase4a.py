"""Phase 4A — Conversation CRUD, isolation, soft-delete, Platform Expert privacy."""

from __future__ import annotations

import uuid

import pytest

from app.conversations.models import MessageRole, MessageStatus
from app.conversations.service import ConversationService
from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertStatus, ExpertType, ExpertVisibility
from app.identity.models import PlatformRole
from app.identity.repository import UserRepository
from app.workspaces.models import WorkspaceMembership, WorkspaceRole
from app.workspaces.repository import MembershipRepository, WorkspaceRepository


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


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


def _promote_platform_admin(db, user_id: str):
    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _create_workspace_expert(client, headers: dict, name: str = "Chat Expert") -> dict:
    res = client.post("/api/experts", headers=headers, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def _add_member(db, workspace_id: str, user_id: str, role=WorkspaceRole.MEMBER) -> None:
    from tests.support.rbac import add_workspace_member
    key = role.value if hasattr(role, "value") else role
    add_workspace_member(db, workspace_id, user_id, key)



# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_conversation_with_workspace_expert(client, register_user) -> None:
    user = register_user(email="conv-ws@example.com")
    ws = _create_workspace(client, user["access_token"], "Conv WS", "conv-ws-crud")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)

    created = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": expert["id"]},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["workspace_id"] == ws["id"]
    assert body["expert_id"] == expert["id"]
    assert body["user_id"] == user["user"]["id"]
    assert body["title"] is None
    assert body["is_pinned"] is False
    assert body["pinned_at"] is None
    assert body["is_favorite"] is False
    assert body["favorited_at"] is None
    assert body["expert"]["id"] == expert["id"]
    assert body["expert"]["ownership"] == "workspace"
    assert body["expert"]["name"] == expert["name"]
    assert "system_instructions" not in body["expert"]
    assert "rag_config" not in body["expert"]
    assert body["last_message"] is None


def test_create_conversation_with_granted_platform_expert(
    client, register_user, db
) -> None:
    admin_body = register_user(email="conv-plat-admin@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    user = register_user(email="conv-plat-user@example.com")
    ws = _create_workspace(client, user["access_token"], "Plat Conv", "conv-plat-ok")

    plat = client.post(
        "/api/platform/experts",
        headers=_auth(admin_body["access_token"]),
        json={
            "name": "Platform Chat",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
            "system_instructions": "SECRET PLATFORM PROMPT",
            "rag_config": {"top_k": 9},
        },
    )
    assert plat.status_code == 201, plat.text
    expert_id = plat.json()["id"]
    assert plat.json()["workspace_id"] is None

    grant = client.post(
        f"/api/platform/experts/{expert_id}/grants",
        headers=_auth(admin_body["access_token"]),
        json={"workspace_id": ws["id"]},
    )
    assert grant.status_code == 201, grant.text

    headers = _ws_headers(user["access_token"], ws)
    created = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": expert_id},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    # Consumer workspace != expert.workspace_id (platform experts have NULL)
    assert body["workspace_id"] == ws["id"]
    assert body["expert_id"] == expert_id
    assert body["expert"]["ownership"] == "platform"
    assert body["expert"]["type"] == ExpertType.PLATFORM.value
    assert "system_instructions" not in body["expert"]
    assert "rag_config" not in body["expert"]


def test_reject_ungranted_platform_expert(client, register_user, db) -> None:
    admin_body = register_user(email="conv-ungrant-admin@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    user = register_user(email="conv-ungrant-user@example.com")
    ws = _create_workspace(client, user["access_token"], "No Grant", "conv-no-grant")

    plat = client.post(
        "/api/platform/experts",
        headers=_auth(admin_body["access_token"]),
        json={
            "name": "Hidden P",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
        },
    )
    assert plat.status_code == 201
    expert_id = plat.json()["id"]

    denied = client.post(
        "/api/conversations",
        headers=_ws_headers(user["access_token"], ws),
        json={"expert_id": expert_id},
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "expert_not_found"


def test_reject_expert_from_another_workspace(client, register_user) -> None:
    user_a = register_user(email="conv-ex-a@example.com")
    user_b = register_user(email="conv-ex-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "conv-ex-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "conv-ex-b")
    expert_b = _create_workspace_expert(
        client, _ws_headers(user_b["access_token"], ws_b), "B Expert"
    )

    denied = client.post(
        "/api/conversations",
        headers=_ws_headers(user_a["access_token"], ws_a),
        json={"expert_id": expert_b["id"]},
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "expert_not_found"


def test_noop_patch_does_not_bump_updated_at(client, register_user) -> None:
    user = register_user(email="conv-noop@example.com")
    ws = _create_workspace(client, user["access_token"], "Noop", "conv-noop")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)

    created = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"], "title": "Keep"}
    ).json()
    before = created["updated_at"]

    empty = client.patch(f"/api/conversations/{created['id']}", headers=headers, json={})
    assert empty.status_code == 200
    assert empty.json()["updated_at"] == before
    assert empty.json()["title"] == "Keep"

    same_title = client.patch(
        f"/api/conversations/{created['id']}",
        headers=headers,
        json={"title": "Keep"},
    )
    assert same_title.status_code == 200
    assert same_title.json()["updated_at"] == before

    pinned = client.patch(
        f"/api/conversations/{created['id']}",
        headers=headers,
        json={"is_pinned": True},
    )
    assert pinned.status_code == 200
    assert pinned.json()["is_pinned"] is True
    assert pinned.json()["updated_at"] != before
    after_pin = pinned.json()["updated_at"]

    # Re-pin is a no-op and must not reshuffle sidebar ordering.
    repin = client.patch(
        f"/api/conversations/{created['id']}",
        headers=headers,
        json={"is_pinned": True},
    )
    assert repin.status_code == 200
    assert repin.json()["updated_at"] == after_pin

    favorited = client.patch(
        f"/api/conversations/{created['id']}",
        headers=headers,
        json={"is_favorite": True},
    )
    assert favorited.status_code == 200
    assert favorited.json()["is_favorite"] is True
    assert favorited.json()["favorited_at"] is not None
    after_fav = favorited.json()["updated_at"]

    refav = client.patch(
        f"/api/conversations/{created['id']}",
        headers=headers,
        json={"is_favorite": True},
    )
    assert refav.status_code == 200
    assert refav.json()["updated_at"] == after_fav

    unfav = client.patch(
        f"/api/conversations/{created['id']}",
        headers=headers,
        json={"is_favorite": False},
    )
    assert unfav.status_code == 200
    assert unfav.json()["is_favorite"] is False
    assert unfav.json()["favorited_at"] is None


def test_list_retrieve_rename_pin_delete(client, register_user, db) -> None:
    user = register_user(email="conv-lifecycle@example.com")
    ws = _create_workspace(client, user["access_token"], "Life", "conv-life")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)

    c1 = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()
    c2 = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": expert["id"], "title": "Second"},
    ).json()

    listed = client.get("/api/conversations", headers=headers)
    assert listed.status_code == 200
    ids = [c["id"] for c in listed.json()]
    assert c1["id"] in ids and c2["id"] in ids

    got = client.get(f"/api/conversations/{c1['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["id"] == c1["id"]

    renamed = client.patch(
        f"/api/conversations/{c1['id']}",
        headers=headers,
        json={"title": "Renamed chat"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed chat"

    pinned = client.patch(
        f"/api/conversations/{c1['id']}",
        headers=headers,
        json={"is_pinned": True},
    )
    assert pinned.status_code == 200
    assert pinned.json()["is_pinned"] is True
    assert pinned.json()["pinned_at"] is not None

    # Pinned sorts first
    listed2 = client.get("/api/conversations", headers=headers).json()
    assert listed2[0]["id"] == c1["id"]
    assert listed2[0]["is_pinned"] is True

    unpinned = client.patch(
        f"/api/conversations/{c1['id']}",
        headers=headers,
        json={"is_pinned": False},
    )
    assert unpinned.status_code == 200
    assert unpinned.json()["is_pinned"] is False
    assert unpinned.json()["pinned_at"] is None

    # Persist messages via service (public write API is Phase 4B)
    membership = MembershipRepository(db).get(
        uuid.UUID(ws["id"]), uuid.UUID(user["user"]["id"])
    )
    workspace = WorkspaceRepository(db).get_by_id(uuid.UUID(ws["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    assert membership and workspace and actor

    citation = {
        "chunk_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "document_title": "Safe Doc",
        "page": 1,
        "snippet": "safe snippet",
    }
    ConversationService(db).append_message(
        workspace=workspace,
        membership=membership,
        actor=actor,
        conversation_id=uuid.UUID(c1["id"]),
        role=MessageRole.USER.value,
        content="Hello expert",
    )
    ConversationService(db).append_message(
        workspace=workspace,
        membership=membership,
        actor=actor,
        conversation_id=uuid.UUID(c1["id"]),
        role=MessageRole.ASSISTANT.value,
        content="Answer with cite",
        citations=[citation],
        status=MessageStatus.COMPLETED.value,
    )

    msgs = client.get(f"/api/conversations/{c1['id']}/messages", headers=headers)
    assert msgs.status_code == 200
    assert len(msgs.json()) == 2
    assert msgs.json()[0]["role"] == "user"
    assert msgs.json()[1]["role"] == "assistant"
    assert msgs.json()[1]["citations"][0]["document_title"] == "Safe Doc"
    assert msgs.json()[1]["citations"][0]["snippet"] == "safe snippet"
    # No internal path leakage keys
    cite = msgs.json()[1]["citations"][0]
    assert set(cite.keys()) == {
        "chunk_id",
        "document_id",
        "document_title",
        "page",
        "snippet",
    }

    detail = client.get(f"/api/conversations/{c1['id']}", headers=headers).json()
    assert detail["last_message"]["role"] == "assistant"
    assert "Answer" in detail["last_message"]["content"]

    deleted = client.delete(f"/api/conversations/{c1['id']}", headers=headers)
    assert deleted.status_code == 204

    assert (
        client.get(f"/api/conversations/{c1['id']}", headers=headers).status_code == 404
    )
    assert (
        client.get(
            f"/api/conversations/{c1['id']}/messages", headers=headers
        ).status_code
        == 404
    )
    listed3 = client.get("/api/conversations", headers=headers).json()
    assert c1["id"] not in {c["id"] for c in listed3}
    assert c2["id"] in {c["id"] for c in listed3}


def test_clear_conversation_history(client, register_user) -> None:
    user = register_user(email="conv-clear@example.com")
    ws = _create_workspace(client, user["access_token"], "Clear", "conv-clear")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)

    ids = []
    for i in range(3):
        created = client.post(
            "/api/conversations",
            headers=headers,
            json={"expert_id": expert["id"], "title": f"C{i}"},
        )
        assert created.status_code == 201
        ids.append(created.json()["id"])

    cleared = client.delete("/api/conversations", headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted_count"] == 3

    listed = client.get("/api/conversations", headers=headers).json()
    assert listed == []

    for cid in ids:
        assert client.get(f"/api/conversations/{cid}", headers=headers).status_code == 404

    # Idempotent empty clear
    again = client.delete("/api/conversations", headers=headers)
    assert again.status_code == 200
    assert again.json()["deleted_count"] == 0


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_cross_workspace_conversation_isolation(client, register_user) -> None:
    user_a = register_user(email="iso-a@example.com")
    user_b = register_user(email="iso-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "IsoA", "conv-iso-a")
    ws_b = _create_workspace(client, user_b["access_token"], "IsoB", "conv-iso-b")
    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)

    expert_a = _create_workspace_expert(client, ha, "EA")
    expert_b = _create_workspace_expert(client, hb, "EB")

    conv_a = client.post(
        "/api/conversations", headers=ha, json={"expert_id": expert_a["id"]}
    ).json()
    conv_b = client.post(
        "/api/conversations", headers=hb, json={"expert_id": expert_b["id"]}
    ).json()

    # A cannot list B
    listed_a = client.get("/api/conversations", headers=ha).json()
    assert conv_a["id"] in {c["id"] for c in listed_a}
    assert conv_b["id"] not in {c["id"] for c in listed_a}

    # A cannot retrieve / rename / pin / delete / messages for B's UUID
    assert client.get(f"/api/conversations/{conv_b['id']}", headers=ha).status_code == 404
    assert (
        client.patch(
            f"/api/conversations/{conv_b['id']}",
            headers=ha,
            json={"title": "Hijack"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/conversations/{conv_b['id']}",
            headers=ha,
            json={"is_pinned": True},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/conversations/{conv_b['id']}", headers=ha).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/conversations/{conv_b['id']}/messages", headers=ha
        ).status_code
        == 404
    )

    # Forged workspace header does not help
    forged = client.get(
        f"/api/conversations/{conv_b['id']}",
        headers=_auth(user_a["access_token"], **{"X-Workspace-Id": ws_b["id"]}),
    )
    assert forged.status_code in {403, 404}


def test_same_workspace_user_isolation(client, register_user, db) -> None:
    owner = register_user(email="same-owner@example.com")
    member = register_user(email="same-member@example.com")
    ws = _create_workspace(client, owner["access_token"], "Shared", "conv-same-ws")
    _add_member(db, ws["id"], member["user"]["id"])

    owner_h = _ws_headers(owner["access_token"], ws)
    member_h = _ws_headers(member["access_token"], ws)

    expert = _create_workspace_expert(client, owner_h, "Shared Expert")
    # Member can USE expert to create own conversation
    owner_conv = client.post(
        "/api/conversations", headers=owner_h, json={"expert_id": expert["id"]}
    ).json()
    member_conv = client.post(
        "/api/conversations", headers=member_h, json={"expert_id": expert["id"]}
    ).json()

    owner_list = client.get("/api/conversations", headers=owner_h).json()
    assert owner_conv["id"] in {c["id"] for c in owner_list}
    assert member_conv["id"] not in {c["id"] for c in owner_list}

    member_list = client.get("/api/conversations", headers=member_h).json()
    assert member_conv["id"] in {c["id"] for c in member_list}
    assert owner_conv["id"] not in {c["id"] for c in member_list}

    assert (
        client.get(f"/api/conversations/{owner_conv['id']}", headers=member_h).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/conversations/{owner_conv['id']}",
            headers=member_h,
            json={"title": "Nope"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/conversations/{owner_conv['id']}/messages", headers=member_h
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Platform Expert privacy on conversation APIs
# ---------------------------------------------------------------------------


def test_conversation_api_does_not_leak_platform_expert_internals(
    client, register_user, db
) -> None:
    admin_body = register_user(email="priv-admin@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    user = register_user(email="priv-user@example.com")
    ws = _create_workspace(client, user["access_token"], "Priv", "conv-priv")

    plat = client.post(
        "/api/platform/experts",
        headers=_auth(admin_body["access_token"]),
        json={
            "name": "Private Brain",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
            "system_instructions": "DO NOT LEAK",
            "rag_config": {"top_k": 3, "similarity_threshold": 0.1},
        },
    ).json()
    client.post(
        f"/api/platform/experts/{plat['id']}/grants",
        headers=_auth(admin_body["access_token"]),
        json={"workspace_id": ws["id"]},
    )

    headers = _ws_headers(user["access_token"], ws)
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": plat["id"]}
    ).json()

    for payload in (
        conv,
        client.get(f"/api/conversations/{conv['id']}", headers=headers).json(),
        client.get("/api/conversations", headers=headers).json()[0],
    ):
        expert = payload["expert"]
        assert expert is not None
        assert "system_instructions" not in expert
        assert "rag_config" not in expert
        assert "knowledge_document_count" not in expert
        dumped = str(payload)
        assert "DO NOT LEAK" not in dumped
        assert "similarity_threshold" not in dumped


# ---------------------------------------------------------------------------
# Citation normalization
# ---------------------------------------------------------------------------


def test_normalize_citations_strips_to_safe_contract() -> None:
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    out = ConversationService.normalize_citations(
        [
            {
                "chunk_id": str(chunk_id),
                "document_id": str(doc_id),
                "document_title": "T",
                "page": 2,
                "snippet": "hello",
                "storage_key": "secret/path",
                "minio_path": "/x",
            }
        ]
    )
    assert len(out) == 1
    assert set(out[0].keys()) == {
        "chunk_id",
        "document_id",
        "document_title",
        "page",
        "snippet",
    }
    assert "storage_key" not in out[0]
    assert out[0]["page"] == 2


def test_normalize_citations_invalid_raises() -> None:
    with pytest.raises(AppError) as exc:
        ConversationService.normalize_citations([{"page": "nope"}])
    assert exc.value.category == ErrorCategory.VALIDATION
