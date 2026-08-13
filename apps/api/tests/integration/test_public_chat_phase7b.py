"""Phase 7B — public ``POST /api/v1/chat`` (API-key auth, rate limit, metering)."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey
from app.api_keys.security import (
    display_prefix,
    generate_api_key_secret,
    hash_api_key,
    last_four,
)
from app.billing.service import PlanService, SubscriptionService
from app.conversations.models import Conversation, Message
from app.conversations.turn import ChatTurnExecutor
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.entitlements.cache import invalidate_entitlements
from app.entitlements.keys import EntitlementKey
from app.experts.geem_general import ensure_geem_general_expert
from app.experts.models import ExpertStatus, ExpertVisibility
from app.identity.models import PlatformRole
from app.identity.repository import UserRepository
from app.rate_limits.service import ApiRateLimiter, reset_memory_rate_limit_buckets
from app.usage.attribution import GenerationUsageContext
from app.usage.metered import MeteredWorkspaceGeneration
from app.usage.metrics import AiUsageReservationStatus
from app.usage.models import AiUsageReservation
from app.usage.openrouter_billing import record_openrouter_event
from app.usage.weights import OpenRouterFamily
from app.workspaces.models import WorkspaceStatus


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client, user: dict, slug: str, name: str = "Pub") -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _create_key(client, user: dict, workspace: dict, name: str = "Chat Key") -> dict:
    res = client.post(
        "/api/api-keys",
        headers=_ws_headers(user, workspace),
        json={"name": name},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_workspace_expert(client, headers: dict, name: str = "API Expert") -> dict:
    res = client.post("/api/experts", headers=headers, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def _force_expert_ready(db: Session, expert_id: str) -> None:
    from app.experts.models import Expert

    expert = db.get(Expert, uuid.UUID(expert_id))
    assert expert is not None
    expert.status = ExpertStatus.READY.value
    db.commit()


def _promote_platform_admin(db: Session, user_id: str):
    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _assign_plan(db: Session, workspace_id: uuid.UUID, entitlements: dict[str, int], code: str):
    plan = PlanService(db).create_plan(
        code=code,
        name=f"Test {code}",
        description="Test-only plan — not Geem product pricing.",
        entitlements=entitlements,
        extra={"kind": "test", "commercial": False},
    )
    SubscriptionService(db).assign_plan(workspace_id, plan.id)
    db.commit()
    invalidate_entitlements(workspace_id)
    return plan


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
        events.append((event, json.loads("\n".join(data_lines))))
    return events


_CITE = {
    "chunk_id": str(uuid.uuid4()),
    "document_id": str(uuid.uuid4()),
    "document_title": "Policy",
    "page": 1,
    "snippet": "safe snippet",
}


def _fake_query(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {
        "answer": "Hello world",
        "insufficient_context": False,
        "citations": [_CITE],
        "model": "test-model",
        "billed_chat_tokens": 6,
        "usage": {
            "prompt_tokens": 4,
            "completion_tokens": 2,
            "total_tokens": 6,
            "source": "provider",
        },
    }


def _fake_stream(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
    yield {"event": "status", "data": {"stage": "generating"}}
    yield {"event": "token", "data": {"text": "Hello "}}
    yield {"event": "token", "data": {"text": "world"}}
    yield {
        "event": "final",
        "data": {
            "answer": "Hello world",
            "insufficient_context": False,
            "citations": [_CITE],
            "model": "test-model",
            "billed_chat_tokens": 6,
            "usage": {
                "prompt_tokens": 4,
                "completion_tokens": 2,
                "total_tokens": 6,
                "source": "provider",
            },
        },
    }


def _generation_patches():
    return (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_for_workspace",
            side_effect=_fake_query,
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_stream_for_workspace",
            side_effect=_fake_stream,
        ),
    )


# ---------------------------------------------------------------------------
# Auth / scope
# ---------------------------------------------------------------------------


def test_valid_key_can_chat(client, register_user, db) -> None:
    user = register_user(email="7b-ok@example.com")
    ws = _create_workspace(client, user, "p7b-ok")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "Hello"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["expert_id"] == expert["id"]
    assert body["answer"] == "Hello world"
    assert body["id"]
    assert body["citations"][0]["snippet"] == "safe snippet"
    assert body["usage"]["billed_tokens"] == 6
    assert key["key"] not in res.text


def test_client_x_request_id_is_not_reservation_key(client, register_user, db) -> None:
    user = register_user(email="7b-xid@example.com")
    ws = _create_workspace(client, user, "p7b-xid")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    client_rid = "client-replay-id"
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        first = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"], **{"X-Request-Id": client_rid}),
            json={"expert_id": expert["id"], "message": "One"},
        )
        second = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"], **{"X-Request-Id": client_rid}),
            json={"expert_id": expert["id"], "message": "Two"},
        )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["id"] != client_rid
    assert second.json()["id"] != client_rid
    db.expire_all()
    rows = db.scalars(select(AiUsageReservation)).all()
    ids = {row.request_id for row in rows}
    assert first.json()["id"] in ids
    assert second.json()["id"] in ids
    assert client_rid not in ids
    assert all(row.status == AiUsageReservationStatus.SETTLED.value for row in rows)


def test_missing_and_invalid_auth(client, register_user, db) -> None:
    user = register_user(email="7b-auth@example.com")
    ws = _create_workspace(client, user, "p7b-auth")
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    missing = client.post(
        "/api/v1/chat",
        json={"expert_id": expert["id"], "message": "Hi"},
    )
    assert missing.status_code == 401
    assert missing.json()["code"] == "unauthorized"

    invalid = client.post(
        "/api/v1/chat",
        headers=_auth("geem_sk_not-a-real-key-value-xxxxxxxx"),
        json={"expert_id": expert["id"], "message": "Hi"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "unauthorized"


def test_revoked_and_expired_keys_are_401(client, register_user, db) -> None:
    user = register_user(email="7b-rev@example.com")
    ws = _create_workspace(client, user, "p7b-rev")
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    created = _create_key(client, user, ws, "Revoke me")
    client.post(
        f"/api/api-keys/{created['id']}/revoke",
        headers=_ws_headers(user, ws),
    )
    revoked = client.post(
        "/api/v1/chat",
        headers=_auth(created["key"]),
        json={"expert_id": expert["id"], "message": "Hi"},
    )
    assert revoked.status_code == 401

    exp = _create_key(client, user, ws, "Soon expired")
    row = db.get(ApiKey, uuid.UUID(exp["id"]))
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    expired = client.post(
        "/api/v1/chat",
        headers=_auth(exp["key"]),
        json={"expert_id": expert["id"], "message": "Hi"},
    )
    assert expired.status_code == 401


def test_missing_chat_write_is_403(client, register_user, db) -> None:
    user = register_user(email="7b-scope@example.com")
    ws = _create_workspace(client, user, "p7b-scope")
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    plaintext = generate_api_key_secret()
    db.add(
        ApiKey(
            workspace_id=uuid.UUID(ws["id"]),
            name="No scope",
            key_prefix=display_prefix(plaintext),
            last_four=last_four(plaintext),
            secret_hash=hash_api_key(plaintext),
            scopes=["unused:scope"],
            created_by=uuid.UUID(user["user"]["id"]),
        )
    )
    db.commit()
    res = client.post(
        "/api/v1/chat",
        headers=_auth(plaintext),
        json={"expert_id": expert["id"], "message": "Hi"},
    )
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "forbidden"
    assert plaintext not in res.text


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_cross_workspace_experts_are_404(client, register_user, db) -> None:
    a = register_user(email="7b-iso-a@example.com")
    b = register_user(email="7b-iso-b@example.com")
    ws_a = _create_workspace(client, a, "p7b-iso-a", "A")
    ws_b = _create_workspace(client, b, "p7b-iso-b", "B")
    key_a = _create_key(client, a, ws_a)
    key_b = _create_key(client, b, ws_b)
    expert_a = _create_workspace_expert(client, _ws_headers(a, ws_a), "Expert A")
    expert_b = _create_workspace_expert(client, _ws_headers(b, ws_b), "Expert B")
    _force_expert_ready(db, expert_a["id"])
    _force_expert_ready(db, expert_b["id"])

    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        ok_a = client.post(
            "/api/v1/chat",
            headers=_auth(key_a["key"]),
            json={"expert_id": expert_a["id"], "message": "A"},
        )
        ok_b = client.post(
            "/api/v1/chat",
            headers=_auth(key_b["key"]),
            json={"expert_id": expert_b["id"], "message": "B"},
        )
    assert ok_a.status_code == 200, ok_a.text
    assert ok_b.status_code == 200, ok_b.text

    denied_a = client.post(
        "/api/v1/chat",
        headers=_auth(
            key_a["key"],
            **{
                "X-Workspace-Slug": ws_b["slug"],
                "X-Workspace-Id": ws_b["id"],
                "Host": f"{ws_b['slug']}.geem.dm",
            },
        ),
        json={"expert_id": expert_b["id"], "message": "nope"},
    )
    assert denied_a.status_code == 404
    assert denied_a.json()["code"] == "expert_not_found"

    denied_b = client.post(
        "/api/v1/chat",
        headers=_auth(key_b["key"]),
        json={"expert_id": expert_a["id"], "message": "nope"},
    )
    assert denied_b.status_code == 404


def test_session_cookie_and_jwt_cannot_override_api_key_workspace(
    client, register_user, db
) -> None:
    a = register_user(email="7b-cookie-a@example.com")
    b = register_user(email="7b-cookie-b@example.com")
    ws_a = _create_workspace(client, a, "p7b-cookie-a")
    ws_b = _create_workspace(client, b, "p7b-cookie-b")
    key_a = _create_key(client, a, ws_a)
    expert_b = _create_workspace_expert(client, _ws_headers(b, ws_b), "B only")
    denied = client.post(
        "/api/v1/chat",
        headers=_auth(key_a["key"], **{"X-Workspace-Id": ws_b["id"]}),
        json={"expert_id": expert_b["id"], "message": "hijack"},
    )
    assert denied.status_code == 404

    jwt_as_bearer = client.post(
        "/api/v1/chat",
        headers=_auth(a["access_token"]),
        json={"expert_id": expert_b["id"], "message": "jwt"},
    )
    assert jwt_as_bearer.status_code == 401


# ---------------------------------------------------------------------------
# Platform experts
# ---------------------------------------------------------------------------


def test_granted_and_ungranted_platform_experts(client, register_user, db) -> None:
    admin = register_user(email="7b-plat-admin@example.com")
    _promote_platform_admin(db, admin["user"]["id"])
    user = register_user(email="7b-plat-user@example.com")
    ws = _create_workspace(client, user, "p7b-plat")
    key = _create_key(client, user, ws)

    granted = client.post(
        "/api/platform/experts",
        headers=_auth(admin["access_token"]),
        json={
            "name": "Granted P",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
        },
    )
    assert granted.status_code == 201, granted.text
    granted_id = granted.json()["id"]
    g = client.post(
        f"/api/platform/experts/{granted_id}/grants",
        headers=_auth(admin["access_token"]),
        json={"workspace_id": ws["id"]},
    )
    assert g.status_code == 201, g.text

    hidden = client.post(
        "/api/platform/experts",
        headers=_auth(admin["access_token"]),
        json={
            "name": "Hidden P",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
        },
    )
    hidden_id = hidden.json()["id"]

    draft = client.post(
        "/api/platform/experts",
        headers=_auth(admin["access_token"]),
        json={
            "name": "Draft P",
            "visibility": "platform_draft",
            "status": ExpertStatus.READY.value,
        },
    )
    draft_id = draft.json()["id"]

    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        ok = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": granted_id, "message": "use grant"},
        )
    assert ok.status_code == 200, ok.text

    ungranted = client.post(
        "/api/v1/chat",
        headers=_auth(key["key"]),
        json={"expert_id": hidden_id, "message": "no grant"},
    )
    assert ungranted.status_code == 404

    unpublished = client.post(
        "/api/v1/chat",
        headers=_auth(key["key"]),
        json={"expert_id": draft_id, "message": "draft"},
    )
    assert unpublished.status_code == 404


def test_geem_general_is_usable_by_workspace_key(client, register_user, db) -> None:
    general = ensure_geem_general_expert(db)
    db.commit()
    user = register_user(email="7b-gen@example.com")
    ws = _create_workspace(client, user, "p7b-gen")
    key = _create_key(client, user, ws)
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": str(general.id), "message": "Hi"},
        )
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# JSON / SSE / persistence
# ---------------------------------------------------------------------------


def test_json_chat_does_not_create_conversations(client, register_user, db) -> None:
    user = register_user(email="7b-json@example.com")
    ws = _create_workspace(client, user, "p7b-json")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "  What?  ", "stream": False},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body["citations"][0].keys()) == {
        "chunk_id",
        "document_id",
        "document_title",
        "page",
        "snippet",
    }
    assert "system_instructions" not in res.text
    assert "secret_hash" not in res.text
    db.expire_all()
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0


def test_sse_chat_lifecycle_and_no_persistence(client, register_user, db) -> None:
    user = register_user(email="7b-sse@example.com")
    ws = _create_workspace(client, user, "p7b-sse")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        with client.stream(
            "POST",
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "Stream me", "stream": True},
        ) as res:
            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]
            raw = "".join(res.iter_text())
    events = _parse_sse(raw)
    names = [n for n, _ in events]
    assert names[0] == "message_start"
    assert "delta" in names
    assert "message_complete" in names
    assert "conversation_id" not in raw
    start = next(d for n, d in events if n == "message_start")
    complete = next(d for n, d in events if n == "message_complete")
    assert start["expert_id"] == expert["id"]
    assert start["request_id"]
    assert complete["answer"] == "Hello world"
    assert complete["citations"][0]["document_title"] == "Policy"
    assert complete["usage"]["billed_tokens"] == 6
    db.expire_all()
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0


def test_sse_replace_is_not_flattened_to_delta(client, register_user, db) -> None:
    user = register_user(email="7b-sse-rep@example.com")
    ws = _create_workspace(client, user, "p7b-sse-rep")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])

    def fake_stream(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        yield {"event": "token", "data": {"text": "Hi"}}
        yield {"event": "replace", "data": {"text": ""}}
        yield {"event": "replace", "data": {"text": "Final answer"}}
        yield {
            "event": "final",
            "data": {
                "answer": "Final answer",
                "insufficient_context": False,
                "citations": [_CITE],
                "model": "test-model",
                "billed_chat_tokens": 6,
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 2,
                    "total_tokens": 6,
                    "source": "provider",
                },
            },
        }

    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_for_workspace",
            side_effect=_fake_query,
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_stream_for_workspace",
            side_effect=fake_stream,
        ),
    ):
        with client.stream(
            "POST",
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "Reset me", "stream": True},
        ) as res:
            assert res.status_code == 200
            raw = "".join(res.iter_text())
    events = _parse_sse(raw)
    names = [n for n, _ in events]
    assert names == [
        "message_start",
        "delta",
        "replace",
        "replace",
        "message_complete",
    ]
    assert events[1][1]["content"] == "Hi"
    assert events[2][1]["content"] == ""
    assert events[3][1]["content"] == "Final answer"
    assert events[4][1]["answer"] == "Final answer"


# ---------------------------------------------------------------------------
# Usage attribution
# ---------------------------------------------------------------------------


def test_general_usage_events_attributed_to_api_key(client, register_user, db) -> None:
    general = ensure_geem_general_expert(db)
    db.commit()
    user = register_user(email="7b-use-g@example.com")
    ws = _create_workspace(client, user, "p7b-use-g")
    key = _create_key(client, user, ws)

    def fake_query(*args: Any, usage_context=None, **kwargs: Any) -> dict[str, Any]:
        record_openrouter_event(
            db,
            get_settings(),
            family=OpenRouterFamily.CHAT,
            operation_type="general_expert",
            usage_context=usage_context,
            model="test-general",
            fallback_tokens=8,
        )
        db.commit()
        return {
            "answer": "General hello",
            "citations": [],
            "insufficient_context": False,
            "model": "test-general",
            "billed_chat_tokens": 8,
        }

    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_for_workspace",
            side_effect=fake_query,
        ),
    ):
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": str(general.id), "message": "Hi"},
        )
    assert res.status_code == 200, res.text
    db.expire_all()
    events = db.scalars(select(UsageEvent)).all()
    assert events
    for event in events:
        assert event.workspace_id == uuid.UUID(ws["id"])
        assert event.api_key_id == uuid.UUID(key["id"])
        assert event.user_id is None
        assert event.expert_id == general.id
        assert event.conversation_id is None
        assert event.message_id is None
        assert key["key"] not in json.dumps(event.cost_metadata or {})


def test_rag_family_events_share_api_key_context(client, register_user, db) -> None:
    user = register_user(email="7b-use-r@example.com")
    ws = _create_workspace(client, user, "p7b-use-r")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])

    def fake_query(*args: Any, usage_context=None, **kwargs: Any) -> dict[str, Any]:
        for family, op, tokens in (
            (OpenRouterFamily.EMBED, "embed_query", 10),
            (OpenRouterFamily.RERANK, "rerank", 5),
            (OpenRouterFamily.CHAT, "chat", 20),
        ):
            record_openrouter_event(
                db,
                get_settings(),
                family=family,
                operation_type=op,
                usage_context=usage_context,
                fallback_tokens=tokens,
                model="test-model",
            )
        db.commit()
        return {
            "answer": "RAG hello",
            "citations": [_CITE],
            "insufficient_context": False,
            "model": "test-model",
            "billed_chat_tokens": 20,
        }

    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_for_workspace",
            side_effect=fake_query,
        ),
    ):
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "Cite me"},
        )
    assert res.status_code == 200, res.text
    db.expire_all()
    ops = {e.operation_type: e for e in db.scalars(select(UsageEvent)).all()}
    assert set(ops) >= {"embed_query", "rerank", "chat"}
    for event in ops.values():
        assert event.api_key_id == uuid.UUID(key["id"])
        assert event.user_id is None
        assert event.expert_id == uuid.UUID(expert["id"])
        assert (event.cost_metadata or {}).get("family") in {"embed", "rerank", "chat"}


def test_internal_chat_usage_still_user_not_api_key(client, register_user, db) -> None:
    user = register_user(email="7b-reg@example.com")
    ws = _create_workspace(client, user, "p7b-reg")
    headers = _ws_headers(user, ws)
    expert = _create_workspace_expert(client, headers)
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    captured: dict[str, Any] = {}

    def fake_stream(*args: Any, usage_context=None, **kwargs: Any) -> Iterator[dict[str, Any]]:
        assert isinstance(usage_context, GenerationUsageContext)
        captured["user_id"] = usage_context.user_id
        captured["api_key_id"] = usage_context.api_key_id
        captured["conversation_id"] = usage_context.conversation_id
        record_openrouter_event(
            db,
            get_settings(),
            family=OpenRouterFamily.CHAT,
            operation_type="chat",
            usage_context=usage_context,
            fallback_tokens=4,
        )
        db.commit()
        yield from _fake_stream()

    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_stream",
            side_effect=fake_stream,
        ),
        patch("app.conversations.chat_orchestrator.schedule_conversation_title"),
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/stream",
            headers=headers,
            json={"content": "Internal"},
        ) as res:
            raw = "".join(res.iter_text())
    assert "message_complete" in raw
    assert captured["user_id"] == uuid.UUID(user["user"]["id"])
    assert captured["api_key_id"] is None
    assert captured["conversation_id"] == uuid.UUID(conv["id"])
    db.expire_all()
    assert db.query(Conversation).count() == 1
    assert db.query(Message).count() == 2
    events = db.scalars(select(UsageEvent)).all()
    assert events
    for event in events:
        assert event.user_id == uuid.UUID(user["user"]["id"])
        assert event.api_key_id is None
        assert event.conversation_id == uuid.UUID(conv["id"])


# ---------------------------------------------------------------------------
# AI quota
# ---------------------------------------------------------------------------


def test_public_chat_quota_exceeded_skips_provider(client, register_user, db) -> None:
    user = register_user(email="7b-quota@example.com")
    ws = _create_workspace(client, user, "p7b-quota")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    _assign_plan(
        db,
        uuid.UUID(ws["id"]),
        {
            EntitlementKey.AI_TOKENS_DAILY.value: 1,
            EntitlementKey.AI_TOKENS_WEEKLY.value: 1,
            EntitlementKey.AI_TOKENS_MONTHLY.value: 1,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
            EntitlementKey.API_REQUESTS_PER_MINUTE.value: 60,
        },
        code="p7b_quota",
    )
    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_for_workspace",
            side_effect=_fake_query,
        ) as provider,
    ):
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "blocked"},
        )
    assert res.status_code == 429, res.text
    assert res.json()["code"] == "quota_exceeded"
    provider.assert_not_called()
    db.expire_all()
    assert db.query(Conversation).count() == 0
    reserved = db.scalars(
        select(AiUsageReservation).where(
            AiUsageReservation.status == AiUsageReservationStatus.RESERVED.value
        )
    ).all()
    assert reserved == []


def test_sse_quota_exceeded_is_http_error_not_sse(client, register_user, db) -> None:
    user = register_user(email="7b-quota-sse@example.com")
    ws = _create_workspace(client, user, "p7b-quota-sse")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    _assign_plan(
        db,
        uuid.UUID(ws["id"]),
        {
            EntitlementKey.AI_TOKENS_DAILY.value: 1,
            EntitlementKey.AI_TOKENS_WEEKLY.value: 1,
            EntitlementKey.AI_TOKENS_MONTHLY.value: 1,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
            EntitlementKey.API_REQUESTS_PER_MINUTE.value: 60,
        },
        code="p7b_quota_sse",
    )
    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_stream_for_workspace",
            side_effect=_fake_stream,
        ) as provider,
    ):
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "blocked", "stream": True},
        )
    assert res.status_code == 429, res.text
    assert res.json()["code"] == "quota_exceeded"
    assert "text/event-stream" not in res.headers.get("content-type", "")
    provider.assert_not_called()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_api_rate_limit_third_request_is_429(client, register_user, db) -> None:
    reset_memory_rate_limit_buckets()
    user = register_user(email="7b-rl@example.com")
    ws = _create_workspace(client, user, "p7b-rl")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    _assign_plan(
        db,
        uuid.UUID(ws["id"]),
        {
            EntitlementKey.AI_TOKENS_DAILY.value: 1_000_000,
            EntitlementKey.AI_TOKENS_WEEKLY.value: 1_000_000,
            EntitlementKey.AI_TOKENS_MONTHLY.value: 1_000_000,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
            EntitlementKey.API_REQUESTS_PER_MINUTE.value: 2,
        },
        code="p7b_rl2",
    )
    p_resolve = patch(
        "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
        return_value=MagicMock(),
    )
    p_query = patch(
        "app.experts.query_service.ExpertQueryService.query_for_workspace",
        side_effect=_fake_query,
    )
    p_stream = patch(
        "app.experts.query_service.ExpertQueryService.query_stream_for_workspace",
        side_effect=_fake_stream,
    )
    with p_resolve, p_query as provider, p_stream:
        first = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "1"},
        )
        second = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "2"},
        )
        third = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "3"},
        )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429, third.text
    assert third.json()["code"] == "rate_limit_exceeded"
    assert third.json()["remaining"] == 0
    assert "Retry-After" in third.headers
    assert int(third.headers["X-RateLimit-Remaining"]) >= 0
    assert provider.call_count == 2


def test_workspace_rate_limit_cannot_be_bypassed_with_two_keys(
    client, register_user, db
) -> None:
    reset_memory_rate_limit_buckets()
    user = register_user(email="7b-rlws@example.com")
    ws = _create_workspace(client, user, "p7b-rlws")
    key_a = _create_key(client, user, ws, "A")
    key_b = _create_key(client, user, ws, "B")
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    _assign_plan(
        db,
        uuid.UUID(ws["id"]),
        {
            EntitlementKey.AI_TOKENS_DAILY.value: 1_000_000,
            EntitlementKey.AI_TOKENS_WEEKLY.value: 1_000_000,
            EntitlementKey.AI_TOKENS_MONTHLY.value: 1_000_000,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
            EntitlementKey.API_REQUESTS_PER_MINUTE.value: 2,
        },
        code="p7b_rlws",
    )
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        a1 = client.post(
            "/api/v1/chat",
            headers=_auth(key_a["key"]),
            json={"expert_id": expert["id"], "message": "a"},
        )
        b1 = client.post(
            "/api/v1/chat",
            headers=_auth(key_b["key"]),
            json={"expert_id": expert["id"], "message": "b"},
        )
        a2 = client.post(
            "/api/v1/chat",
            headers=_auth(key_a["key"]),
            json={"expert_id": expert["id"], "message": "a2"},
        )
    assert a1.status_code == 200
    assert b1.status_code == 200
    assert a2.status_code == 429


def test_rate_limit_buckets_isolated_across_workspaces(
    client, register_user, db
) -> None:
    reset_memory_rate_limit_buckets()
    a = register_user(email="7b-rla@example.com")
    b = register_user(email="7b-rlb@example.com")
    ws_a = _create_workspace(client, a, "p7b-rla")
    ws_b = _create_workspace(client, b, "p7b-rlb")
    key_a = _create_key(client, a, ws_a)
    key_b = _create_key(client, b, ws_b)
    expert_a = _create_workspace_expert(client, _ws_headers(a, ws_a))
    expert_b = _create_workspace_expert(client, _ws_headers(b, ws_b))
    _force_expert_ready(db, expert_a["id"])
    _force_expert_ready(db, expert_b["id"])
    ents = {
        EntitlementKey.AI_TOKENS_DAILY.value: 1_000_000,
        EntitlementKey.AI_TOKENS_WEEKLY.value: 1_000_000,
        EntitlementKey.AI_TOKENS_MONTHLY.value: 1_000_000,
        EntitlementKey.EXPERTS_LIMIT.value: 10,
        EntitlementKey.STORAGE_BYTES.value: 10_000_000,
        EntitlementKey.API_REQUESTS_PER_MINUTE.value: 1,
    }
    _assign_plan(db, uuid.UUID(ws_a["id"]), ents, code="p7b_rla")
    _assign_plan(db, uuid.UUID(ws_b["id"]), ents, code="p7b_rlb")
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        ok_a = client.post(
            "/api/v1/chat",
            headers=_auth(key_a["key"]),
            json={"expert_id": expert_a["id"], "message": "a"},
        )
        blocked_a = client.post(
            "/api/v1/chat",
            headers=_auth(key_a["key"]),
            json={"expert_id": expert_a["id"], "message": "a2"},
        )
        ok_b = client.post(
            "/api/v1/chat",
            headers=_auth(key_b["key"]),
            json={"expert_id": expert_b["id"], "message": "b"},
        )
    assert ok_a.status_code == 200
    assert blocked_a.status_code == 429
    assert ok_b.status_code == 200


def test_concurrent_http_rate_limit_uses_atomic_limiter(client, register_user, db) -> None:
    reset_memory_rate_limit_buckets()
    user = register_user(email="7b-conc@example.com")
    ws = _create_workspace(client, user, "p7b-conc")
    key = _create_key(client, user, ws)
    limiter = ApiRateLimiter(db, allow_memory_fallback=True)
    _assign_plan(
        db,
        uuid.UUID(ws["id"]),
        {
            EntitlementKey.AI_TOKENS_DAILY.value: 1_000_000,
            EntitlementKey.AI_TOKENS_WEEKLY.value: 1_000_000,
            EntitlementKey.AI_TOKENS_MONTHLY.value: 1_000_000,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
            EntitlementKey.API_REQUESTS_PER_MINUTE.value: 3,
        },
        code="p7b_conc",
    )
    limit = limiter.quota.get_api_requests_per_minute(uuid.UUID(ws["id"]))
    allowed: list[int] = []
    blocked: list[int] = []
    lock = threading.Lock()

    def _hit() -> None:
        try:
            limiter.consume(
                workspace_id=uuid.UUID(ws["id"]),
                api_key_id=uuid.UUID(key["id"]),
                limit=limit,
            )
            with lock:
                allowed.append(1)
        except AppError as exc:
            assert exc.category == ErrorCategory.RATE_LIMIT_EXCEEDED
            with lock:
                blocked.append(1)

    threads = [threading.Thread(target=_hit) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) == 3
    assert len(blocked) == 7


# ---------------------------------------------------------------------------
# Failure / cancellation / secrets
# ---------------------------------------------------------------------------


def test_provider_failure_releases_reservation(client, register_user, db) -> None:
    user = register_user(email="7b-fail@example.com")
    ws = _create_workspace(client, user, "p7b-fail")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])

    def boom(*args: Any, **kwargs: Any):
        raise AppError(ErrorCategory.GENERATION_FAILED, "Provider down")

    with (
        patch(
            "app.experts.query_service.ExpertQueryService.resolve_knowledge_for_workspace",
            return_value=MagicMock(),
        ),
        patch(
            "app.experts.query_service.ExpertQueryService.query_for_workspace",
            side_effect=boom,
        ),
    ):
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "fail"},
        )
    assert res.status_code == 502, res.text
    assert res.json()["code"] == "generation_failed"
    db.expire_all()
    assert db.query(Conversation).count() == 0
    reserved = db.scalars(
        select(AiUsageReservation).where(
            AiUsageReservation.status == AiUsageReservationStatus.RESERVED.value
        )
    ).all()
    assert reserved == []


def test_stream_cancellation_releases_reservation(client, register_user, db) -> None:
    from app.conversations.invocation import ChatInvocationContext
    from app.workspaces.models import Workspace

    user = register_user(email="7b-cancel@example.com")
    ws = _create_workspace(client, user, "p7b-cancel")
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])

    def slow_stream(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        yield {"event": "token", "data": {"text": "partial"}}
        yield {"event": "token", "data": {"text": " more"}}

    request_id = str(uuid.uuid4())
    api_key_id = uuid.uuid4()
    meter = MeteredWorkspaceGeneration(
        db,
        workspace_id=workspace.id,
        user_id=None,
        expert_id=uuid.UUID(expert["id"]),
        api_key_id=api_key_id,
        request_id=request_id,
    )
    meter.reserve()
    invocation = ChatInvocationContext.api_key(
        workspace_id=workspace.id,
        api_key_id=api_key_id,
        expert_id=uuid.UUID(expert["id"]),
        request_id=request_id,
    )
    with patch(
        "app.experts.query_service.ExpertQueryService.query_stream_for_workspace",
        side_effect=slow_stream,
    ):
        gen = ChatTurnExecutor(db).stream(
            workspace=workspace,
            expert_id=uuid.UUID(expert["id"]),
            question="hi",
            invocation=invocation,
            meter=meter,
            request_id=request_id,
        )
        assert next(gen)["event"] == "message_start"
        assert next(gen)["event"] == "delta"
        gen.close()
    db.expire_all()
    row = db.scalars(
        select(AiUsageReservation).where(AiUsageReservation.request_id == request_id)
    ).first()
    assert row is not None
    assert row.status != AiUsageReservationStatus.RESERVED.value


def test_public_chat_never_echoes_secret(client, register_user, db, caplog) -> None:
    user = register_user(email="7b-sec@example.com")
    ws = _create_workspace(client, user, "p7b-sec")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    p_resolve, p_query, p_stream = _generation_patches()
    with caplog.at_level(logging.INFO), p_resolve, p_query, p_stream:
        res = client.post(
            "/api/v1/chat",
            headers=_auth(key["key"]),
            json={"expert_id": expert["id"], "message": "secret check"},
        )
    assert res.status_code == 200, res.text
    assert key["key"] not in res.text
    assert "secret_hash" not in res.text
    assert "API_KEY_HASH_PEPPER" not in res.text
    assert key["key"] not in caplog.text
    assert "Authorization" not in caplog.text
    row = db.get(ApiKey, uuid.UUID(key["id"]))
    assert row is not None
    assert row.secret_hash not in res.text
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    dumped = schema.text
    assert "/api/v1/chat" in dumped
    assert "geem_sk_xxxxxxxxxxxxxxxxx" in dumped or "geem_sk_" in dumped
    assert key["key"] not in dumped


def test_suspended_workspace_cannot_chat(client, register_user, db) -> None:
    user = register_user(email="7b-sus@example.com")
    ws = _create_workspace(client, user, "p7b-sus")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    from app.workspaces.models import Workspace

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    workspace.status = WorkspaceStatus.SUSPENDED.value
    db.commit()
    res = client.post(
        "/api/v1/chat",
        headers=_auth(key["key"]),
        json={"expert_id": expert["id"], "message": "nope"},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "workspace_access_denied"
