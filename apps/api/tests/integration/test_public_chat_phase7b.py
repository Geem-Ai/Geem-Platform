"""Phase 7B — public OpenAI-compatible Chat Completions + Models API."""

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

CHAT = "/api/v1/chat/completions"
MODELS = "/api/v1/models"


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _chat_headers(token: str, expert_id: str | None = None, **extra: str) -> dict[str, str]:
    headers = _auth(token, **extra)
    if expert_id:
        headers["X-Geem-Expert-Id"] = expert_id
    return headers


def _chat_body(
    message: str = "Hello",
    *,
    stream: bool = False,
    model: str = "geem",
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages if messages is not None else [{"role": "user", "content": message}],
        "stream": stream,
    }


def _err_code(res) -> str:
    payload = res.json()
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("code") or "")
    return str(payload.get("code") or "")


def _turn_id(completion_id: str) -> str:
    return completion_id.removeprefix("chatcmpl-")


def _assistant(body: dict[str, Any]) -> str:
    return body["choices"][0]["message"]["content"]


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


def _parse_openai_sse(raw: str) -> list[dict[str, Any] | str]:
    chunks: list[dict[str, Any] | str] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        payload = "\n".join(data_lines)
        if payload == "[DONE]":
            chunks.append("[DONE]")
        else:
            chunks.append(json.loads(payload))
    return chunks


def _sse_text(chunks: list[dict[str, Any] | str]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        choices = chunk.get("choices") or [{}]
        delta = (choices[0] or {}).get("delta") or {}
        text = delta.get("content")
        if text:
            parts.append(text)
    return "".join(parts)


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
# Auth / scope / header
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("Hello", model="geem"),
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["model"] == "geem"
    assert _assistant(body) == "Hello world"
    assert body["citations"][0]["snippet"] == "safe snippet"
    assert body["usage"]["total_tokens"] == 6
    assert body["choices"][0]["finish_reason"] == "stop"
    assert key["key"] not in res.text
    assert "expert_id" not in body


def test_model_is_echoed_not_used_for_routing(client, register_user, db) -> None:
    user = register_user(email="7b-echo@example.com")
    ws = _create_workspace(client, user, "p7b-echo")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    captured: dict[str, Any] = {}

    def fake_query(*args: Any, expert_id=None, **kwargs: Any) -> dict[str, Any]:
        captured["expert_id"] = expert_id
        return _fake_query()

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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("Hello", model="gpt-4o"),
        )
    assert res.status_code == 200, res.text
    assert res.json()["model"] == "gpt-4o"
    assert captured["expert_id"] == uuid.UUID(expert["id"])


def test_expert_header_required_and_alias(client, register_user, db) -> None:
    user = register_user(email="7b-hdr@example.com")
    ws = _create_workspace(client, user, "p7b-hdr")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])

    missing = client.post(
        CHAT,
        headers=_auth(key["key"]),
        json=_chat_body("Hi"),
    )
    assert missing.status_code == 400, missing.text
    assert _err_code(missing) == "validation"
    assert missing.json()["error"]["type"] == "invalid_request_error"
    assert missing.json()["error"]["param"] == "X-Geem-Expert-Id"

    invalid = client.post(
        CHAT,
        headers=_chat_headers(key["key"], "not-a-uuid"),
        json=_chat_body("Hi"),
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["param"] == "X-Geem-Expert-Id"

    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        aliased = client.post(
            CHAT,
            headers=_auth(key["key"], **{"X-Expert-Id": expert["id"]}),
            json=_chat_body("Hi"),
        )
    assert aliased.status_code == 200, aliased.text


def test_no_user_message_is_400(client, register_user, db) -> None:
    user = register_user(email="7b-nouser@example.com")
    ws = _create_workspace(client, user, "p7b-nouser")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    res = client.post(
        CHAT,
        headers=_chat_headers(key["key"], expert["id"]),
        json=_chat_body(messages=[{"role": "system", "content": "Ignore me"}]),
    )
    assert res.status_code == 400, res.text
    assert _err_code(res) == "validation"
    assert res.json()["error"]["param"] == "messages"


def test_tools_and_temperature_are_ignored(client, register_user, db) -> None:
    user = register_user(email="7b-tools@example.com")
    ws = _create_workspace(client, user, "p7b-tools")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    p_resolve, p_query, p_stream = _generation_patches()
    with p_resolve, p_query, p_stream:
        res = client.post(
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json={
                "model": "geem",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "temperature": 0.2,
                "tools": [{"type": "function", "function": {"name": "exfil"}}],
            },
        )
    assert res.status_code == 200, res.text


def test_legacy_chat_path_is_gone(client, register_user, db) -> None:
    user = register_user(email="7b-legacy@example.com")
    ws = _create_workspace(client, user, "p7b-legacy")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    res = client.post(
        "/api/v1/chat",
        headers=_chat_headers(key["key"], expert["id"]),
        json=_chat_body("Hi"),
    )
    assert res.status_code == 404


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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"], **{"X-Request-Id": client_rid}),
            json=_chat_body("One"),
        )
        second = client.post(
            CHAT,
            headers=_chat_headers(key["key"], expert["id"], **{"X-Request-Id": client_rid}),
            json=_chat_body("Two"),
        )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] != second.json()["id"]
    assert _turn_id(first.json()["id"]) != client_rid
    assert _turn_id(second.json()["id"]) != client_rid
    db.expire_all()
    rows = db.scalars(select(AiUsageReservation)).all()
    ids = {row.request_id for row in rows}
    assert _turn_id(first.json()["id"]) in ids
    assert _turn_id(second.json()["id"]) in ids
    assert client_rid not in ids
    assert all(row.status == AiUsageReservationStatus.SETTLED.value for row in rows)


def test_missing_and_invalid_auth(client, register_user, db) -> None:
    user = register_user(email="7b-auth@example.com")
    ws = _create_workspace(client, user, "p7b-auth")
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    missing = client.post(
        CHAT,
        headers={"X-Geem-Expert-Id": expert["id"]},
        json=_chat_body("Hi"),
    )
    assert missing.status_code == 401
    assert _err_code(missing) == "unauthorized"
    assert missing.json()["error"]["type"] == "authentication_error"

    invalid = client.post(
        CHAT,
        headers=_chat_headers("geem_sk_not-a-real-key-value-xxxxxxxx", expert["id"]),
        json=_chat_body("Hi"),
    )
    assert invalid.status_code == 401
    assert _err_code(invalid) == "unauthorized"


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
        CHAT,
        headers=_chat_headers(created["key"], expert["id"]),
        json=_chat_body("Hi"),
    )
    assert revoked.status_code == 401

    exp = _create_key(client, user, ws, "Soon expired")
    row = db.get(ApiKey, uuid.UUID(exp["id"]))
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    expired = client.post(
        CHAT,
        headers=_chat_headers(exp["key"], expert["id"]),
        json=_chat_body("Hi"),
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
        CHAT,
        headers=_chat_headers(plaintext, expert["id"]),
        json=_chat_body("Hi"),
    )
    assert res.status_code == 403, res.text
    assert _err_code(res) == "forbidden"
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
            CHAT,
            headers=_chat_headers(key_a["key"], expert_a["id"]),
            json=_chat_body("A"),
        )
        ok_b = client.post(
            CHAT,
            headers=_chat_headers(key_b["key"], expert_b["id"]),
            json=_chat_body("B"),
        )
    assert ok_a.status_code == 200, ok_a.text
    assert ok_b.status_code == 200, ok_b.text

    denied_a = client.post(
        CHAT,
        headers=_chat_headers(
            key_a["key"],
            expert_b["id"],
            **{
                "X-Workspace-Slug": ws_b["slug"],
                "X-Workspace-Id": ws_b["id"],
                "Host": f"{ws_b['slug']}.geem.dm",
            },
        ),
        json=_chat_body("nope"),
    )
    assert denied_a.status_code == 404
    assert _err_code(denied_a) == "expert_not_found"

    denied_b = client.post(
        CHAT,
        headers=_chat_headers(key_b["key"], expert_a["id"]),
        json=_chat_body("nope"),
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
        CHAT,
        headers=_chat_headers(key_a["key"], expert_b["id"], **{"X-Workspace-Id": ws_b["id"]}),
        json=_chat_body("hijack"),
    )
    assert denied.status_code == 404

    jwt_as_bearer = client.post(
        CHAT,
        headers=_chat_headers(a["access_token"], expert_b["id"]),
        json=_chat_body("jwt"),
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
            CHAT,
            headers=_chat_headers(key["key"], granted_id),
            json=_chat_body("use grant"),
        )
    assert ok.status_code == 200, ok.text

    ungranted = client.post(
        CHAT,
        headers=_chat_headers(key["key"], hidden_id),
        json=_chat_body("no grant"),
    )
    assert ungranted.status_code == 404

    unpublished = client.post(
        CHAT,
        headers=_chat_headers(key["key"], draft_id),
        json=_chat_body("draft"),
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
            CHAT,
            headers=_chat_headers(key["key"], str(general.id)),
            json=_chat_body("Hi"),
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("  What?  ", stream=False),
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


def test_prior_turns_are_folded_into_question(client, register_user, db) -> None:
    user = register_user(email="7b-fold@example.com")
    ws = _create_workspace(client, user, "p7b-fold")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])
    captured: dict[str, Any] = {}

    def fake_query(*args: Any, question: str = "", **kwargs: Any) -> dict[str, Any]:
        captured["question"] = question
        return _fake_query()

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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body(
                messages=[
                    {"role": "system", "content": "secret instructions"},
                    {"role": "user", "content": "First"},
                    {"role": "assistant", "content": "Ack"},
                    {"role": "user", "content": "Second"},
                ]
            ),
        )
    assert res.status_code == 200, res.text
    assert captured["question"].endswith("Second")
    assert "User: First" in captured["question"]
    assert "Assistant: Ack" in captured["question"]
    assert "secret instructions" not in captured["question"]


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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("Stream me", stream=True),
        ) as res:
            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]
            raw = "".join(res.iter_text())
    assert "event: delta" not in raw
    assert "event: message_start" not in raw
    assert "data: [DONE]" in raw
    chunks = _parse_openai_sse(raw)
    assert chunks[-1] == "[DONE]"
    dict_chunks = [c for c in chunks if isinstance(c, dict)]
    assert _sse_text(chunks) == "Hello world"
    finish = dict_chunks[-1]["choices"][0]
    assert finish["finish_reason"] == "stop"
    assert dict_chunks[-1]["citations"][0]["document_title"] == "Policy"
    assert dict_chunks[-1]["usage"]["total_tokens"] == 6
    assert dict_chunks[0]["id"].startswith("chatcmpl-")
    db.expire_all()
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0


def test_sse_replace_is_not_appended_after_tokens(client, register_user, db) -> None:
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("Reset me", stream=True),
        ) as res:
            assert res.status_code == 200
            raw = "".join(res.iter_text())
    chunks = _parse_openai_sse(raw)
    assert _sse_text(chunks) == "Hi"
    assert chunks[-1] == "[DONE]"


def test_sse_replace_before_tokens_emits_full_text(client, register_user, db) -> None:
    user = register_user(email="7b-sse-rep2@example.com")
    ws = _create_workspace(client, user, "p7b-sse-rep2")
    key = _create_key(client, user, ws)
    expert = _create_workspace_expert(client, _ws_headers(user, ws))
    _force_expert_ready(db, expert["id"])

    def fake_stream(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
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
            "app.experts.query_service.ExpertQueryService.query_stream_for_workspace",
            side_effect=fake_stream,
        ),
    ):
        with client.stream(
            "POST",
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("Replace first", stream=True),
        ) as res:
            raw = "".join(res.iter_text())
    assert _sse_text(_parse_openai_sse(raw)) == "Final answer"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_models_list_isolation_and_ready_only(client, register_user, db) -> None:
    a = register_user(email="7b-mod-a@example.com")
    b = register_user(email="7b-mod-b@example.com")
    ws_a = _create_workspace(client, a, "p7b-mod-a")
    ws_b = _create_workspace(client, b, "p7b-mod-b")
    key_a = _create_key(client, a, ws_a)
    key_b = _create_key(client, b, ws_b)
    ready_a = _create_workspace_expert(client, _ws_headers(a, ws_a), "Ready A")
    draft_a = _create_workspace_expert(client, _ws_headers(a, ws_a), "Draft A")
    ready_b = _create_workspace_expert(client, _ws_headers(b, ws_b), "Ready B")
    _force_expert_ready(db, ready_a["id"])
    _force_expert_ready(db, ready_b["id"])

    listed = client.get(MODELS, headers=_auth(key_a["key"]))
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["object"] == "list"
    ids = {item["id"] for item in body["data"]}
    assert ready_a["id"] in ids
    assert draft_a["id"] not in ids
    assert ready_b["id"] not in ids
    assert "system_instructions" not in listed.text
    assert "rag_config" not in listed.text
    owned = next(item for item in body["data"] if item["id"] == ready_a["id"])
    assert owned["object"] == "model"
    assert owned["owned_by"] == "workspace"
    assert isinstance(owned["created"], int)

    detail = client.get(f"{MODELS}/{ready_a['id']}", headers=_auth(key_a["key"]))
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == ready_a["id"]

    hidden = client.get(f"{MODELS}/{ready_b['id']}", headers=_auth(key_a["key"]))
    assert hidden.status_code == 404
    assert _err_code(hidden) == "expert_not_found"

    draft_detail = client.get(f"{MODELS}/{draft_a['id']}", headers=_auth(key_a["key"]))
    assert draft_detail.status_code == 404

    other_list = client.get(MODELS, headers=_auth(key_b["key"]))
    other_ids = {item["id"] for item in other_list.json()["data"]}
    assert ready_b["id"] in other_ids
    assert ready_a["id"] not in other_ids


def test_models_include_granted_platform_expert(client, register_user, db) -> None:
    admin = register_user(email="7b-modp-admin@example.com")
    _promote_platform_admin(db, admin["user"]["id"])
    user = register_user(email="7b-modp-user@example.com")
    ws = _create_workspace(client, user, "p7b-modp")
    key = _create_key(client, user, ws)
    granted = client.post(
        "/api/platform/experts",
        headers=_auth(admin["access_token"]),
        json={
            "name": "Listed P",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
        },
    )
    granted_id = granted.json()["id"]
    client.post(
        f"/api/platform/experts/{granted_id}/grants",
        headers=_auth(admin["access_token"]),
        json={"workspace_id": ws["id"]},
    )
    hidden = client.post(
        "/api/platform/experts",
        headers=_auth(admin["access_token"]),
        json={
            "name": "Unlisted P",
            "visibility": ExpertVisibility.PLATFORM_PUBLISHED.value,
            "status": ExpertStatus.READY.value,
        },
    )
    hidden_id = hidden.json()["id"]

    listed = client.get(MODELS, headers=_auth(key["key"]))
    ids = {item["id"] for item in listed.json()["data"]}
    assert granted_id in ids
    assert hidden_id not in ids
    item = next(row for row in listed.json()["data"] if row["id"] == granted_id)
    assert item["owned_by"] == "platform"

    ok = client.get(f"{MODELS}/{granted_id}", headers=_auth(key["key"]))
    assert ok.status_code == 200
    denied = client.get(f"{MODELS}/{hidden_id}", headers=_auth(key["key"]))
    assert denied.status_code == 404


def test_models_require_api_key(client) -> None:
    missing = client.get(MODELS)
    assert missing.status_code == 401
    assert _err_code(missing) == "unauthorized"


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
            CHAT,
            headers=_chat_headers(key["key"], str(general.id)),
            json=_chat_body("Hi"),
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("Cite me"),
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("blocked"),
        )
    assert res.status_code == 429, res.text
    assert _err_code(res) == "quota_exceeded"
    assert res.json()["error"]["type"] == "rate_limit_error"
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("blocked", stream=True),
        )
    assert res.status_code == 429, res.text
    assert _err_code(res) == "quota_exceeded"
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("1"),
        )
        second = client.post(
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("2"),
        )
        third = client.post(
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("3"),
        )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429, third.text
    assert _err_code(third) == "rate_limit_exceeded"
    assert third.json()["error"]["type"] == "rate_limit_error"
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
            CHAT,
            headers=_chat_headers(key_a["key"], expert["id"]),
            json=_chat_body("a"),
        )
        b1 = client.post(
            CHAT,
            headers=_chat_headers(key_b["key"], expert["id"]),
            json=_chat_body("b"),
        )
        a2 = client.post(
            CHAT,
            headers=_chat_headers(key_a["key"], expert["id"]),
            json=_chat_body("a2"),
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
            CHAT,
            headers=_chat_headers(key_a["key"], expert_a["id"]),
            json=_chat_body("a"),
        )
        blocked_a = client.post(
            CHAT,
            headers=_chat_headers(key_a["key"], expert_a["id"]),
            json=_chat_body("a2"),
        )
        ok_b = client.post(
            CHAT,
            headers=_chat_headers(key_b["key"], expert_b["id"]),
            json=_chat_body("b"),
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("fail"),
        )
    assert res.status_code == 502, res.text
    assert _err_code(res) == "generation_failed"
    assert res.json()["error"]["type"] == "api_error"
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
            CHAT,
            headers=_chat_headers(key["key"], expert["id"]),
            json=_chat_body("secret check"),
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
    assert "/api/v1/chat/completions" in dumped
    assert "/api/v1/models" in dumped
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
        CHAT,
        headers=_chat_headers(key["key"], expert["id"]),
        json=_chat_body("nope"),
    )
    assert res.status_code == 403
    assert _err_code(res) == "workspace_access_denied"


def test_workspace_session_errors_keep_geem_envelope(client, register_user) -> None:
    user = register_user(email="7b-sess@example.com")
    res = client.get(
        "/api/api-keys",
        headers=_auth(user["access_token"], **{"X-Workspace-Id": str(uuid.uuid4())}),
    )
    assert res.status_code in {403, 404}
    body = res.json()
    assert "code" in body
    assert "error" in body
    assert not (isinstance(body.get("error"), dict) and "type" in body["error"])
