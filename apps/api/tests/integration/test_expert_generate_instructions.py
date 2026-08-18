"""Integration — POST /api/experts/generate-instructions (auth + CHAT billing)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.billing.service import PlanService, SubscriptionService
from app.db.models import UsageEvent
from app.entitlements.cache import invalidate_entitlements
from app.entitlements.keys import EntitlementKey
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


def _create_ai_plan(db, *, code: str, daily: int, weekly: int, monthly: int):
    return PlanService(db).create_plan(
        code=code,
        name=f"Test {code}",
        description="Test-only plan — not Geem product pricing.",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: daily,
            EntitlementKey.AI_TOKENS_WEEKLY.value: weekly,
            EntitlementKey.AI_TOKENS_MONTHLY.value: monthly,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
        },
        extra={"kind": "test", "commercial": False},
    )


def _assign_plan(db, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> None:
    SubscriptionService(db).assign_plan(workspace_id, plan_id)
    db.commit()
    invalidate_entitlements(workspace_id)


def _mock_openrouter_ok(*, content: str = "You are a careful legal assistant."):
    client = MagicMock()
    client.provider_preferences.return_value = {"allow_fallbacks": True}
    client.request.return_value = (
        {
            "choices": [{"message": {"content": content}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
            "model": "test-general",
        },
        {
            "request_id": "or-gen-1",
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
            "model": "test-general",
        },
        200,
    )
    return client


@patch(
    "app.experts.generate_instructions.OpenRouterClient",
    return_value=_mock_openrouter_ok(),
)
def test_generate_instructions_happy_path_bills_chat(
    _mock_cls, client, register_user, db
) -> None:
    user = register_user(email="gen-inst-ok@example.com")
    ws = _create_workspace(client, user["access_token"], "GenOK", "gen-inst-ok")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_ai_plan(db, code="gen_inst_ok", daily=100_000, weekly=100_000, monthly=100_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    res = client.post(
        "/api/experts/generate-instructions",
        headers=headers,
        json={
            "brief": "Help with Saudi employment contracts",
            "persona": "Employment counsel",
            "audience": "HR managers",
            "tone": "Precise",
            "constraints": "Do not give binding legal advice",
            "name": "Legal Assistant",
            "description": "Employment law helper",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "legal assistant" in body["system_instructions"].lower()

    db.expire_all()
    events = list(
        db.scalars(
            select(UsageEvent).where(UsageEvent.workspace_id == uuid.UUID(ws["id"]))
        )
    )
    assert len(events) == 1
    assert events[0].operation_type == "expert_instructions"
    assert (events[0].cost_metadata or {}).get("family") == "chat"
    assert int((events[0].cost_metadata or {}).get("billed_tokens") or 0) > 0


def test_generate_instructions_empty_brief_422(client, register_user, db) -> None:
    user = register_user(email="gen-inst-422@example.com")
    ws = _create_workspace(client, user["access_token"], "Gen422", "gen-inst-422")
    headers = _ws_headers(user["access_token"], ws)
    res = client.post(
        "/api/experts/generate-instructions",
        headers=headers,
        json={"brief": "   "},
    )
    assert res.status_code == 422


def test_member_cannot_generate_instructions(client, register_user, db) -> None:
    owner = register_user(email="gen-inst-own@example.com")
    member = register_user(email="gen-inst-mem@example.com")
    ws = _create_workspace(client, owner["access_token"], "GenMem", "gen-inst-mem")
    from tests.support.rbac import add_workspace_member
    add_workspace_member(db, ws["id"], member["user"]["id"], 'member')

    res = client.post(
        "/api/experts/generate-instructions",
        headers=_ws_headers(member["access_token"], ws),
        json={"brief": "Anything"},
    )
    assert res.status_code == 403
    assert res.json()["error"] == "insufficient_workspace_role"


@patch(
    "app.experts.generate_instructions.OpenRouterClient",
    return_value=_mock_openrouter_ok(),
)
def test_generate_instructions_quota_blocked(
    _mock_cls, client, register_user, db
) -> None:
    user = register_user(email="gen-inst-quota@example.com")
    ws = _create_workspace(client, user["access_token"], "GenQ", "gen-inst-quota")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_ai_plan(db, code="gen_inst_quota", daily=1, weekly=1, monthly=1)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    res = client.post(
        "/api/experts/generate-instructions",
        headers=headers,
        json={"brief": "Blocked by quota"},
    )
    assert res.status_code == 429
    assert res.json()["error"] in {"quota_exceeded", "insufficient_credits"}
