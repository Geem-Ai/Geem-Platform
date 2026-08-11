"""Phase 4B — ChatOrchestrator persisted SSE, retry, isolation, title."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.conversations.models import MessageRole, MessageStatus
from app.conversations.title import derive_conversation_title
from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertStatus, ExpertType, ExpertVisibility
from app.identity.models import PlatformRole
from app.identity.repository import UserRepository
from app.workspaces.models import WorkspaceMembership, WorkspaceRole
from app.workspaces.repository import MembershipRepository


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
    res = client.post(
        "/api/experts",
        headers=headers,
        json={"name": name, "status": ExpertStatus.READY.value},
    )
    assert res.status_code == 201, res.text
    # Force ready even if reconciler would leave draft without knowledge —
    # Phase 4B stream mocks RAG; ExpertQueryService still requires READY.
    body = res.json()
    return body


def _force_expert_ready(db, expert_id: str) -> None:
    from app.experts.models import Expert

    expert = db.get(Expert, uuid.UUID(expert_id))
    assert expert is not None
    expert.status = ExpertStatus.READY.value
    db.commit()


def _add_member(db, workspace_id: str, user_id: str, role: str = WorkspaceRole.MEMBER.value) -> None:
    MembershipRepository(db).create(
        WorkspaceMembership(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id),
            role=role,
        )
    )
    db.commit()


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        payload = json.loads("\n".join(data_lines))
        events.append((event, payload))
    return events


def _fake_stream_success(
    *args: Any,
    question: str = "",
    **kwargs: Any,
) -> Iterator[dict[str, Any]]:
    yield {"event": "status", "data": {"stage": "retrieving"}}
    yield {"event": "status", "data": {"stage": "generating"}}
    yield {"event": "token", "data": {"text": "Hello "}}
    yield {"event": "token", "data": {"text": "world"}}
    cite = {
        "chunk_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "document_title": "Policy",
        "page": 1,
        "snippet": "safe snippet",
    }
    yield {
        "event": "final",
        "data": {
            "answer": "Hello world",
            "insufficient_context": False,
            "citations": [cite],
            "model": "test-model",
            "general_answer": None,
            "used_general_knowledge": False,
            "general_model": None,
        },
    }


def _fake_stream_fail(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
    yield {"event": "status", "data": {"stage": "generating"}}
    raise AppError(ErrorCategory.GENERATION_FAILED, "Provider down")


# ---------------------------------------------------------------------------
# Title helper
# ---------------------------------------------------------------------------


def test_derive_conversation_title_unicode_and_trim() -> None:
    assert derive_conversation_title("  What is this?\n\nNext  ") == "What is this? Next"
    arabic = "ما هي قواعد الإلغاء في العقد؟"
    assert derive_conversation_title(arabic) == arabic
    long = "word " * 40
    titled = derive_conversation_title(long, max_length=40)
    assert titled.endswith("…")
    assert len(titled) <= 41


# ---------------------------------------------------------------------------
# Standard flow
# ---------------------------------------------------------------------------


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_stream_turn_persists_messages_and_citations(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    user = register_user(email="4b-flow@example.com")
    ws = _create_workspace(client, user["access_token"], "Flow", "conv-4b-flow")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])

    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()
    assert conv["title"] is None

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=headers,
        json={"content": "What does the policy say?"},
    ) as res:
        assert res.status_code == 200, res.text
        raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    names = [e for e, _ in events]
    assert "message_start" in names
    assert "token" in names
    assert "final" in names
    assert "message_complete" in names

    start = next(d for n, d in events if n == "message_start")
    final = next(d for n, d in events if n == "final")
    assert start["conversation_id"] == conv["id"]
    assert start["user_message_id"]
    assert start["assistant_message_id"]
    assert start.get("title")  # auto-titled from first message
    assert final["assistant_message_id"] == start["assistant_message_id"]
    assert final["citations"][0]["document_title"] == "Policy"
    assert set(final["citations"][0].keys()) == {
        "chunk_id",
        "document_id",
        "document_title",
        "page",
        "snippet",
    }

    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers)
    assert msgs.status_code == 200
    body = msgs.json()
    assert len(body) == 2
    assert body[0]["role"] == "user"
    assert body[0]["status"] == "completed"
    assert body[0]["content"] == "What does the policy say?"
    assert body[1]["role"] == "assistant"
    assert body[1]["status"] == "completed"
    assert body[1]["content"] == "Hello world"
    assert body[1]["citations"][0]["snippet"] == "safe snippet"

    detail = client.get(f"/api/conversations/{conv['id']}", headers=headers).json()
    assert detail["title"] == "What does the policy say?"


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_fail,
)
def test_stream_failure_settles_assistant_failed(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    user = register_user(email="4b-fail@example.com")
    ws = _create_workspace(client, user["access_token"], "Fail", "conv-4b-fail")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=headers,
        json={"content": "Will fail"},
    ) as res:
        raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    assert any(n == "error" for n, _ in events)
    err = next(d for n, d in events if n == "error")
    assert err["error"] == "generation_failed"
    assert err["status"] == "failed"

    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    assert len(msgs) == 2
    assert msgs[1]["status"] == MessageStatus.FAILED.value
    assert msgs[1]["role"] == "assistant"
    # No permanently streaming rows
    assert all(m["status"] != MessageStatus.STREAMING.value for m in msgs)


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
def test_retry_without_duplicate_user_message(
    _mock_resolve, client, register_user, db
) -> None:
    user = register_user(email="4b-retry@example.com")
    ws = _create_workspace(client, user["access_token"], "Retry", "conv-4b-retry")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    with patch(
        "app.experts.query_service.ExpertQueryService.query_stream",
        side_effect=_fake_stream_fail,
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/stream",
            headers=headers,
            json={"content": "Retry me"},
        ) as res:
            "".join(res.iter_text())

    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    failed_id = msgs[1]["id"]
    assert msgs[1]["status"] == "failed"

    with patch(
        "app.experts.query_service.ExpertQueryService.query_stream",
        side_effect=_fake_stream_success,
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/{failed_id}/retry/stream",
            headers=headers,
            json={},
        ) as res:
            raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    start = next(d for n, d in events if n == "message_start")
    assert start["user_message_id"] == msgs[0]["id"]
    assert start["assistant_message_id"] != failed_id
    assert start.get("retry_of_message_id") == failed_id

    msgs2 = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    users = [m for m in msgs2 if m["role"] == "user"]
    assistants = [m for m in msgs2 if m["role"] == "assistant"]
    assert len(users) == 1
    assert len(assistants) == 2
    assert assistants[0]["status"] == "failed"
    assert assistants[1]["status"] == "completed"
    assert assistants[1]["content"] == "Hello world"


# ---------------------------------------------------------------------------
# Isolation / grant revocation
# ---------------------------------------------------------------------------


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_cross_workspace_cannot_stream(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    user_a = register_user(email="4b-iso-a@example.com")
    user_b = register_user(email="4b-iso-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "conv-4b-iso-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "conv-4b-iso-b")
    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)
    expert_a = _create_workspace_expert(client, ha)
    _force_expert_ready(db, expert_a["id"])
    conv_a = client.post(
        "/api/conversations", headers=ha, json={"expert_id": expert_a["id"]}
    ).json()

    with client.stream(
        "POST",
        f"/api/conversations/{conv_a['id']}/messages/stream",
        headers=hb,
        json={"content": "Hijack"},
    ) as res:
        raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    assert any(n == "error" for n, _ in events)
    err = next(d for n, d in events if n == "error")
    assert err["error"] == "conversation_not_found"


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_cross_user_same_workspace_cannot_stream(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    owner = register_user(email="4b-own@example.com")
    member = register_user(email="4b-mem@example.com")
    ws = _create_workspace(client, owner["access_token"], "Shared", "conv-4b-same")
    _add_member(db, ws["id"], member["user"]["id"])
    owner_h = _ws_headers(owner["access_token"], ws)
    member_h = _ws_headers(member["access_token"], ws)
    expert = _create_workspace_expert(client, owner_h)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=owner_h, json={"expert_id": expert["id"]}
    ).json()

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=member_h,
        json={"content": "Nope"},
    ) as res:
        raw = "".join(res.iter_text())

    err = next(d for n, d in _parse_sse(raw) if n == "error")
    assert err["error"] == "conversation_not_found"


def test_revoked_platform_expert_blocks_new_turn(client, register_user, db) -> None:
    admin_body = register_user(email="4b-plat-admin@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    user = register_user(email="4b-plat-user@example.com")
    ws = _create_workspace(client, user["access_token"], "Plat", "conv-4b-plat")
    headers = _ws_headers(user["access_token"], ws)

    plat = client.post(
        "/api/platform/experts",
        headers=_auth(admin_body["access_token"]),
        json={
            "name": "P Chat",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
            "system_instructions": "SECRET",
        },
    ).json()
    client.post(
        f"/api/platform/experts/{plat['id']}/grants",
        headers=_auth(admin_body["access_token"]),
        json={"workspace_id": ws["id"]},
    )

    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": plat["id"]}
    ).json()

    # Revoke grant
    client.delete(
        f"/api/platform/experts/{plat['id']}/grants/{ws['id']}",
        headers=_auth(admin_body["access_token"]),
    )

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=headers,
        json={"content": "Still allowed?"},
    ) as res:
        raw = "".join(res.iter_text())

    err = next(d for n, d in _parse_sse(raw) if n == "error")
    assert err["error"] == "expert_not_found"

    # History still readable
    listed = client.get(f"/api/conversations/{conv['id']}", headers=headers)
    assert listed.status_code == 200


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_stale_streaming_message_is_healed(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    """Abandoned streaming rows older than lock TTL must not block forever."""
    from datetime import datetime, timedelta, timezone

    from app.conversations.models import Message
    from app.conversations.repository import ConversationRepository

    user = register_user(email="4b-stale@example.com")
    ws = _create_workspace(client, user["access_token"], "Stale", "conv-4b-stale")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    stale = Message(
        conversation_id=uuid.UUID(conv["id"]),
        role=MessageRole.ASSISTANT.value,
        content="orphaned",
        citations=[],
        status=MessageStatus.STREAMING.value,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    ConversationRepository(db).create_message(stale)
    db.commit()

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=headers,
        json={"content": "After crash"},
    ) as res:
        raw = "".join(res.iter_text())

    assert any(n == "final" for n, _ in _parse_sse(raw))
    db.expire_all()
    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    statuses = [m["status"] for m in msgs if m["role"] == "assistant"]
    assert MessageStatus.CANCELLED.value in statuses
    assert MessageStatus.COMPLETED.value in statuses
    assert MessageStatus.STREAMING.value not in statuses


def test_generation_lock_fails_closed_without_memory_fallback() -> None:
    from app.conversations.locks import ConversationGenerationLock

    def _boom() -> None:
        raise OSError("redis down")

    lock = ConversationGenerationLock(
        ttl_seconds=30,
        redis_factory=_boom,  # type: ignore[arg-type]
        allow_memory_fallback=False,
    )
    assert lock.acquire(uuid.uuid4()) is False


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_busy_lock_rejects_overlapping_stream(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    from app.conversations.locks import ConversationGenerationLock

    user = register_user(email="4b-busy@example.com")
    ws = _create_workspace(client, user["access_token"], "Busy", "conv-4b-busy")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    lock = ConversationGenerationLock(ttl_seconds=60)
    assert lock.acquire(uuid.UUID(conv["id"]))
    try:
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/stream",
            headers=headers,
            json={"content": "Blocked"},
        ) as res:
            raw = "".join(res.iter_text())
        err = next(d for n, d in _parse_sse(raw) if n == "error")
        assert err["error"] == "conversation_busy"
    finally:
        lock.release(uuid.UUID(conv["id"]))


def test_cancel_settles_streaming_message(client, register_user, db) -> None:
    """Closing the generator mid-stream must leave status=cancelled, not streaming."""
    from app.conversations.chat_orchestrator import ChatOrchestrator
    from app.conversations.models import Message
    from app.workspaces.repository import WorkspaceRepository
    from sqlalchemy import select

    user = register_user(email="4b-cancel@example.com")
    ws = _create_workspace(client, user["access_token"], "Cancel", "conv-4b-cancel")
    headers = _ws_headers(user["access_token"], ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    membership = MembershipRepository(db).get(
        uuid.UUID(ws["id"]), uuid.UUID(user["user"]["id"])
    )
    workspace = WorkspaceRepository(db).get_by_id(uuid.UUID(ws["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    assert membership and workspace and actor

    def _slow_stream(*args, **kwargs):
        yield {"event": "status", "data": {"stage": "generating"}}
        yield {"event": "token", "data": {"text": "partial"}}
        # Simulate client disconnect by closing the consumer mid-iteration.
        raise GeneratorExit

    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_stream",
            side_effect=_slow_stream,
        ),
    ):
        orch = ChatOrchestrator(db)
        gen = orch.stream_turn(
            workspace=workspace,
            membership=membership,
            actor=actor,
            conversation_id=uuid.UUID(conv["id"]),
            content="Cancel please",
        )
        try:
            next(gen)
            next(gen)
            next(gen)
            gen.close()
        except StopIteration:
            pass
        except GeneratorExit:
            pass

    msgs = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conv["id"]))
            .order_by(Message.created_at.asc())
        )
    )
    assert len(msgs) == 2
    assert msgs[1].role == MessageRole.ASSISTANT.value
    assert msgs[1].status == MessageStatus.CANCELLED.value
    assert msgs[1].content == "partial"
