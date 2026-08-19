"""Phase 11D — messages.usage_event_id is a logical reference, not an FK."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.conversations.models import MessageRole, MessageStatus
from app.conversations.service import ConversationService
from app.db.models import UsageEvent
from app.usage.lookup import get_usage_event_by_id


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client, token: str, name: str, slug: str) -> dict:
    res = client.post("/api/workspaces", headers=_auth(token), json={"name": name, "slug": slug})
    assert res.status_code in {200, 201}, res.text
    return res.json()


def test_message_survives_usage_event_retention_drop(client, register_user, db: Session) -> None:
    user = register_user(email="ue-logical@example.com")
    ws = _create_workspace(client, user["access_token"], "UE WS", "ue-logical-ws")
    headers = _auth(user["access_token"], **{"X-Workspace-Id": ws["id"]})
    expert = client.post("/api/experts", headers=headers, json={"name": "UE Expert"})
    assert expert.status_code == 201, expert.text
    conv = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": expert.json()["id"]},
    )
    assert conv.status_code == 201, conv.text

    event = UsageEvent(
        operation_type="chat",
        workspace_id=uuid.UUID(ws["id"]),
        input_tokens=3,
        output_tokens=5,
    )
    db.add(event)
    db.flush()
    event_id = event.id

    from app.identity.repository import UserRepository
    from app.workspaces.repository import MembershipRepository, WorkspaceRepository

    workspace = WorkspaceRepository(db).get_by_id(uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(
        uuid.UUID(ws["id"]), uuid.UUID(user["user"]["id"])
    )
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    svc = ConversationService(db)
    msg = svc.append_message(
        workspace=workspace,
        membership=membership,
        actor=actor,
        conversation_id=uuid.UUID(conv.json()["id"]),
        role=MessageRole.ASSISTANT.value,
        content="hello after meter",
        status=MessageStatus.COMPLETED.value,
        usage_event_id=event_id,
    )
    db.commit()
    assert get_usage_event_by_id(db, event_id) is not None

    db.execute(delete(UsageEvent).where(UsageEvent.id == event_id))
    db.commit()
    assert get_usage_event_by_id(db, event_id) is None

    listed = client.get(f"/api/conversations/{conv.json()['id']}/messages", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert isinstance(body, list)
    assistant = next(row for row in body if row["id"] == str(msg.id))
    assert assistant["content"] == "hello after meter"
    assert assistant.get("usage_event_id") in {str(event_id), None}
    detail = client.get(f"/api/conversations/{conv.json()['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
