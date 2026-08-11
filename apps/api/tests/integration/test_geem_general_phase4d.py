"""Phase 4D — Geem General Expert (knowledge_mode=general, LLM-only)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

from app.conversations.models import MessageStatus
from app.experts.geem_general import ensure_geem_general_expert
from app.experts.models import (
    Expert,
    ExpertKnowledgeMode,
    ExpertStatus,
    ExpertType,
)
from app.experts.status import ExpertStatusReconciler
from app.identity.models import PlatformRole
from app.identity.repository import UserRepository


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


def _fake_general_stream(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
    yield {"event": "status", "data": {"stage": "generating"}}
    yield {"event": "token", "data": {"text": "General "}}
    yield {"event": "token", "data": {"text": "hello"}}
    yield {
        "event": "final",
        "data": {
            "answer": "General hello",
            "insufficient_context": False,
            "citations": [],
            "model": "test-general",
            "used_general_knowledge": True,
        },
    }


def test_ensure_geem_general_expert_idempotent(db):
    first = ensure_geem_general_expert(db)
    second = ensure_geem_general_expert(db)
    assert first.id == second.id
    assert first.knowledge_mode == ExpertKnowledgeMode.GENERAL.value
    assert first.type == ExpertType.PLATFORM.value
    assert first.status == ExpertStatus.READY.value
    assert first.availability_mode == "all_workspaces"
    assert first.visibility == "platform_published"

    rows = db.query(Expert).filter(
        Expert.knowledge_mode == ExpertKnowledgeMode.GENERAL.value,
        Expert.deleted_at.is_(None),
    ).all()
    assert len(rows) == 1


def test_geem_general_listed_without_grant(client, db, register_user):
    ensure_geem_general_expert(db)
    user = register_user()
    token = user["access_token"]
    ws = _create_workspace(client, token, "Acme", f"acme-{uuid.uuid4().hex[:6]}")
    headers = _ws_headers(token, ws)

    res = client.get("/api/experts", headers=headers)
    assert res.status_code == 200, res.text
    experts = res.json()
    general = [e for e in experts if e.get("knowledge_mode") == "general"]
    assert len(general) == 1
    assert general[0]["name"] == "Geem General Assistant"
    assert general[0]["status"] == "ready"
    assert general[0]["ownership"] == "platform"


def test_geem_general_stream_empty_citations(client, db, register_user):
    geem = ensure_geem_general_expert(db)
    user = register_user()
    token = user["access_token"]
    ws = _create_workspace(client, token, "Acme", f"acme-{uuid.uuid4().hex[:6]}")
    headers = _ws_headers(token, ws)

    conv = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": str(geem.id)},
    )
    assert conv.status_code == 201, conv.text
    conv_id = conv.json()["id"]

    with patch(
        "app.rag.service.RagService.query_general_expert_stream",
        side_effect=_fake_general_stream,
    ):
        res = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            headers=headers,
            json={"content": "Hi Geem"},
        )
    assert res.status_code == 200, res.text
    events = _parse_sse(res.text)
    finals = [p for e, p in events if e == "final"]
    assert finals
    assert finals[0].get("citations") == []
    assert finals[0].get("answer") == "General hello"
    assert finals[0].get("status") == MessageStatus.COMPLETED.value


def test_geem_general_upload_rejected(client, db, register_user):
    geem = ensure_geem_general_expert(db)
    admin = register_user()
    _promote_platform_admin(db, admin["user"]["id"])
    token = admin["access_token"]

    res = client.post(
        f"/api/platform/experts/{geem.id}/upload",
        headers=_auth(token),
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"title": "note"},
    )
    assert res.status_code in {400, 403, 409, 422}, res.text
    body = res.json()
    code = body.get("code") or body.get("error") or ""
    assert "immutable" in str(code).lower() or "immutable" in res.text.lower() or res.status_code >= 400


def test_status_reconciler_keeps_general_ready(db):
    geem = ensure_geem_general_expert(db)
    geem.status = ExpertStatus.DRAFT.value
    db.commit()

    result = ExpertStatusReconciler(db).reconcile(geem.id)
    assert result is not None
    assert result.new_status == ExpertStatus.READY.value
    db.refresh(geem)
    assert geem.status == ExpertStatus.READY.value


def test_rag_expert_still_requires_knowledge(client, db, register_user):
    user = register_user()
    token = user["access_token"]
    ws = _create_workspace(client, token, "Acme", f"acme-{uuid.uuid4().hex[:6]}")
    headers = _ws_headers(token, ws)

    created = client.post(
        "/api/experts",
        headers=headers,
        json={"name": "Empty RAG", "status": ExpertStatus.READY.value},
    )
    assert created.status_code == 201, created.text
    expert_id = created.json()["id"]
    # Reconciler may set draft with zero docs — force ready then query should still fail.
    expert = db.get(Expert, uuid.UUID(expert_id))
    assert expert is not None
    expert.status = ExpertStatus.READY.value
    expert.knowledge_mode = ExpertKnowledgeMode.RAG.value
    db.commit()

    conv = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": expert_id},
    )
    assert conv.status_code == 201, conv.text
    conv_id = conv.json()["id"]

    res = client.post(
        f"/api/conversations/{conv_id}/messages/stream",
        headers=headers,
        json={"content": "Need RAG"},
    )
    # Pre-stream AppError may be HTTP error or SSE error event
    if res.status_code == 200:
        events = _parse_sse(res.text)
        errs = [p for e, p in events if e == "error"]
        assert errs
        assert errs[0].get("error") in {
            "expert_has_no_knowledge",
            "expert_not_ready",
        }
    else:
        assert res.status_code in {400, 404, 409, 422}
        assert "knowledge" in res.text.lower() or "expert" in res.text.lower()
