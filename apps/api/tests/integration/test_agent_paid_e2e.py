"""Paid Phase 14 contract through the real FastAPI Agent routes.

Only the two external boundaries (RAG retrieval and OpenRouter transport) are
faked.  Catalog checkout/fulfillment, API-key authentication and scope,
Expert opt-in, paid admission, daily/AI metering, and response serialization
all execute through their production code paths.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.agent.router as agent_router
import app.agent.service as agent_service
from app.agent.retrieval import AgentRetrievalResult, AgentRetrievalService
from app.agent.schemas import (
    AgentAssistantResponseMessage,
    AgentProviderResult,
    AgentUsage,
)
from app.api_keys.scopes import SCOPE_AGENT_WRITE
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENT_REQUESTS_USAGE_METRIC,
    AGENTS_AI_APP_SLUG,
    AGENTS_AI_PLAN_CODES,
)
from app.apps_catalog.models import (
    AppInstallation,
    AppInstallationStatus,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.apps_catalog.seed import ensure_app_catalog
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.config import Settings
from app.core.errors import ErrorCategory
from app.db.models import Document
from app.experts.models import (
    Expert,
    ExpertDocument,
    ExpertSource,
    ExpertSourceStatus,
    ExpertSourceType,
    ExpertStatus,
)
from app.openrouter.chat import OpenRouterChatProvider
from app.usage.models import UsagePeriodCounter
from app.workspaces.models import Workspace, WorkspaceStatus


AGENT_CHAT = "/api/v1/agent/chat/completions"
AGENT_MODELS = "/api/v1/agent/models"


def _session_headers(token: str, workspace_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Workspace-Id": workspace_id,
    }


def _api_key_headers(key: str, expert_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {key}"}
    if expert_id is not None:
        headers["X-Geem-Expert-Id"] = expert_id
    return headers


def _create_workspace(client, register_user) -> tuple[dict, dict]:
    user = register_user(email=f"agent-paid-{uuid.uuid4().hex[:8]}@example.com")
    response = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={
            "name": "Agent paid E2E",
            "slug": f"agent-paid-{uuid.uuid4().hex[:8]}",
        },
    )
    assert response.status_code == 201, response.text
    return user, response.json()


def _publish_isolated_release_candidate(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Publish exact-shaped, explicitly test-only Agents AI commercial data."""

    ensure_app_catalog(db)
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == AGENTS_AI_APP_SLUG))
    assert app is not None
    app.status = AppStatus.PUBLISHED.value
    app.extra = {
        **(app.extra or {}),
        "test_fixture": "phase14-paid-e2e",
        "commercial": False,
    }

    if app.plans:
        default_plan = next(plan for plan in app.plans if plan.is_default)
        db.commit()
        return app.id, default_plan.id

    selected_plan_id: uuid.UUID | None = None
    for index, code in enumerate(AGENTS_AI_PLAN_CODES):
        plan = AppPlan(
            app_id=app.id,
            code=code,
            name=f"{code} release-candidate fixture",
            description="Isolated automated-test pricing; never production seed data.",
            billing_interval=AppPlanBillingInterval.MONTHLY.value,
            price_amount=Decimal("1.00") + Decimal(index),
            currency="SAR",
            sort_order=(index + 1) * 10,
            is_default=index == 0,
            is_active=True,
            extra={"test_fixture": True, "commercial": False},
        )
        db.add(plan)
        db.flush()
        db.add(
            AppPlanEntitlement(
                app_plan_id=plan.id,
                key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
                value=10 * (index + 1),
            )
        )
        if index == 0:
            selected_plan_id = plan.id
    db.commit()
    assert selected_plan_id is not None
    return app.id, selected_plan_id


def _complete_noop_checkout(client, checkout: dict) -> dict:
    query = parse_qs(urlparse(checkout["redirect_url"]).query)
    token = query["rt"][0]
    response = client.get(
        f"/api/billing/return/noop/{checkout['purchase_id']}",
        params={"rt": token},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _subscribe(
    client,
    *,
    user: dict,
    workspace: dict,
    plan_id: uuid.UUID,
) -> None:
    checkout = client.post(
        f"/api/apps/{AGENTS_AI_APP_SLUG}/checkout",
        headers=_session_headers(user["access_token"], workspace["id"]),
        json={"plan_id": str(plan_id)},
    )
    assert checkout.status_code == 200, checkout.text
    paid = _complete_noop_checkout(client, checkout.json())
    assert paid["status"] == "paid"


def _create_agent_key(client, *, user: dict, workspace: dict) -> dict:
    response = client.post(
        "/api/api-keys",
        headers=_session_headers(user["access_token"], workspace["id"]),
        json={"name": "Paid Agent key", "scopes": [SCOPE_AGENT_WRITE]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["scopes"] == [SCOPE_AGENT_WRITE]
    return response.json()


def _create_enabled_expert(
    client,
    db: Session,
    *,
    user: dict,
    workspace: dict,
) -> dict:
    headers = _session_headers(user["access_token"], workspace["id"])
    created = client.post(
        "/api/experts",
        headers=headers,
        json={
            "name": "Paid Agent Expert",
            "status": "ready",
            "system_instructions": "Answer from the authorized source.",
        },
    )
    assert created.status_code == 201, created.text
    expert = created.json()

    document = Document(
        workspace_id=uuid.UUID(workspace["id"]),
        title="Paid Agent fixture source",
        original_filename="paid-agent.txt",
        storage_key=f"tests/{workspace['id']}/paid-agent.txt",
        sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        mime_type="text/plain",
        byte_size=20,
        page_count=1,
        status="ready",
        processing_version={"fixture": "phase14-paid-e2e"},
    )
    db.add(document)
    db.flush()
    db.add(
        ExpertDocument(
            expert_id=uuid.UUID(expert["id"]),
            document_id=document.id,
        )
    )
    db.commit()

    enabled = client.patch(
        f"/api/experts/{expert['id']}",
        headers=headers,
        json={"rag_config": {"client_agent": {"enabled": True}}},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["rag_config"]["client_agent"] == {"enabled": True}
    return enabled.json()


def _create_empty_enabled_expert(
    client,
    *,
    user: dict,
    workspace: dict,
) -> dict:
    headers = _session_headers(user["access_token"], workspace["id"])
    created = client.post(
        "/api/experts",
        headers=headers,
        json={
            "name": "Paid Agent without uploaded knowledge",
            "system_instructions": "Keep the configured concise voice.",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == ExpertStatus.DRAFT.value

    enabled = client.patch(
        f"/api/experts/{created.json()['id']}",
        headers=headers,
        json={"rag_config": {"client_agent": {"enabled": True}}},
    )
    assert enabled.status_code == 200, enabled.text
    return enabled.json()


def _error_code(response) -> str:
    payload = response.json()
    error = payload.get("error")
    assert isinstance(error, dict), payload
    return str(error.get("code") or "")


def _revoke_runtime_access(
    db: Session,
    *,
    denial: str,
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
) -> None:
    db.expire_all()
    if denial == "expiry":
        subscription = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == workspace_id,
                AppSubscription.app_id == app_id,
            )
        )
        assert subscription is not None
        subscription.current_period_end = datetime.now(timezone.utc) - timedelta(
            seconds=1
        )
    elif denial == "uninstall":
        installation = db.scalar(
            select(AppInstallation).where(
                AppInstallation.workspace_id == workspace_id,
                AppInstallation.app_id == app_id,
            )
        )
        assert installation is not None
        installation.status = AppInstallationStatus.UNINSTALLED.value
    elif denial == "unpublish":
        app = db.get(CatalogApp, app_id)
        assert app is not None
        app.status = AppStatus.COMING_SOON.value
    elif denial == "subscription_revoke":
        subscription = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == workspace_id,
                AppSubscription.app_id == app_id,
            )
        )
        assert subscription is not None
        subscription.status = AppSubscriptionStatus.CANCELLED.value
    elif denial == "workspace_suspend":
        workspace = db.get(Workspace, workspace_id)
        assert workspace is not None
        workspace.status = WorkspaceStatus.SUSPENDED.value
    else:  # pragma: no cover - parameter list is closed
        raise AssertionError(f"Unknown denial mutation: {denial}")
    db.commit()


@pytest.mark.parametrize(
    ("denial", "expected_status", "expected_code"),
    [
        ("expiry", 402, "app_subscription_expired"),
        ("uninstall", 409, "app_not_installed"),
        ("unpublish", 409, "app_not_available"),
        ("subscription_revoke", 402, "app_subscription_expired"),
        ("workspace_suspend", 403, "workspace_access_denied"),
    ],
)
def test_paid_checkout_scoped_key_expert_and_immediate_runtime_denial(
    client,
    register_user,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    denial: str,
    expected_status: int,
    expected_code: str,
) -> None:
    """A paid route works, then the next denied route starts no expensive work."""

    settings = Settings(
        _env_file=None,
        client_agent_api_enabled=True,
        # Readiness intentionally requires a configured credential even though
        # this test replaces the external transport before any network call.
        openrouter_api_key="test-openrouter-key",
    )
    monkeypatch.setattr(agent_router, "get_settings", lambda: settings)

    calls = {"retrieval": 0, "provider": 0}

    def fake_retrieval_prepare(self, **kwargs) -> AgentRetrievalResult:
        calls["retrieval"] += 1
        assert kwargs["question"] == "What is covered?"
        assert kwargs["continuation"] is False
        return AgentRetrievalResult(
            # Retrieval returns flat SOURCE blocks; prompt composition owns the
            # outer trusted SOURCES envelope.
            source_xml='<SOURCE id="fixture">Paid route evidence.</SOURCE>',
            citations=(),
            insufficient_context=False,
            status="executed",
            question_hash=hashlib.sha256(b"What is covered?").hexdigest(),
            knowledge_revision="paid-e2e-v1",
        )

    def fake_provider_complete(self, messages, **kwargs) -> AgentProviderResult:
        calls["provider"] += 1
        assert messages == [{"role": "user", "content": "What is covered?"}]
        assert "Paid route evidence" in kwargs["system_prompt"]
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(
                content="The paid Agent route is covered."
            ),
            finish_reason="stop",
            usage=AgentUsage(
                prompt_tokens=5,
                completion_tokens=2,
                total_tokens=7,
            ),
            provider_model=settings.openrouter_chat_model,
            provider_request_id="provider-request-paid-e2e",
            provider_completion_id="provider-completion-paid-e2e",
        )

    monkeypatch.setattr(AgentRetrievalService, "prepare", fake_retrieval_prepare)
    monkeypatch.setattr(
        OpenRouterChatProvider,
        "complete_for_agent",
        fake_provider_complete,
    )

    user, workspace = _create_workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    app_id, plan_id = _publish_isolated_release_candidate(db)
    _subscribe(client, user=user, workspace=workspace, plan_id=plan_id)
    key = _create_agent_key(client, user=user, workspace=workspace)
    expert = _create_enabled_expert(
        client,
        db,
        user=user,
        workspace=workspace,
    )

    models = client.get(AGENT_MODELS, headers=_api_key_headers(key["key"]))
    assert models.status_code == 200, models.text
    assert models.json() == {
        "object": "list",
        "data": [
            {
                "id": PUBLIC_MODEL_ID,
                "object": "model",
                "created": 1_770_000_000,
                "owned_by": "geem",
            }
        ],
    }
    db.rollback()
    assert (
        db.scalar(
            select(func.count())
            .select_from(UsagePeriodCounter)
            .where(
                UsagePeriodCounter.workspace_id == workspace_id,
                UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
            )
        )
        == 0
    )
    db.rollback()

    completion = client.post(
        AGENT_CHAT,
        headers=_api_key_headers(key["key"], expert["id"]),
        json={
            "model": PUBLIC_MODEL_ID,
            "messages": [{"role": "user", "content": "What is covered?"}],
        },
    )
    assert completion.status_code == 200, completion.text
    body = completion.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == PUBLIC_MODEL_ID
    assert body["choices"] == [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "The paid Agent route is covered.",
            },
            "finish_reason": "stop",
        }
    ]
    assert body["usage"] == {
        "prompt_tokens": 5,
        "completion_tokens": 2,
        "total_tokens": 7,
    }
    assert body["geem"] == {
        "retrieval": "executed",
        "citations": [],
        "insufficient_context": False,
        "billed_tokens": 7,
    }
    assert calls == {"retrieval": 1, "provider": 1}

    db.expire_all()
    used = db.scalar(
        select(UsagePeriodCounter.used).where(
            UsagePeriodCounter.workspace_id == workspace_id,
            UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
        )
    )
    assert used == 1
    db.rollback()

    _revoke_runtime_access(
        db,
        denial=denial,
        workspace_id=workspace_id,
        app_id=app_id,
    )
    denied = client.post(
        AGENT_CHAT,
        headers=_api_key_headers(key["key"], expert["id"]),
        json={
            "model": PUBLIC_MODEL_ID,
            "messages": [{"role": "user", "content": "What is covered?"}],
        },
    )
    assert denied.status_code == expected_status, denied.text
    assert _error_code(denied) == expected_code
    assert calls == {"retrieval": 1, "provider": 1}

    if denial == "uninstall":
        # Commercial access and the stored Expert opt-in survive uninstall.
        # Reinstall through the production route and prove that the exact same
        # key and Expert header regain access immediately.
        reinstalled = client.post(
            f"/api/apps/{AGENTS_AI_APP_SLUG}/install",
            headers=_session_headers(user["access_token"], workspace["id"]),
        )
        assert reinstalled.status_code == 201, reinstalled.text
        assert reinstalled.json()["status"] == AppInstallationStatus.ACTIVE.value

        restored = client.post(
            AGENT_CHAT,
            headers=_api_key_headers(key["key"], expert["id"]),
            json={
                "model": PUBLIC_MODEL_ID,
                "messages": [
                    {"role": "user", "content": "What is covered?"}
                ],
            },
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["choices"][0]["message"]["content"] == (
            "The paid Agent route is covered."
        )
        assert calls == {"retrieval": 2, "provider": 2}


def test_empty_expert_runs_general_but_source_only_expert_remains_not_ready(
    client,
    register_user,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback stays behind paid admission and never bypasses a source."""

    settings = Settings(
        _env_file=None,
        client_agent_api_enabled=True,
        openrouter_api_key="test-openrouter-key",
    )
    monkeypatch.setattr(agent_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_service,
        "load_general_chat_prompt",
        lambda: "GENERAL AGENT EXECUTION",
    )

    def unexpected_rag_prompt():  # pragma: no cover - must stay General
        raise AssertionError("empty Expert loaded the Agent RAG prompt")

    def unexpected_retrieval(self, **kwargs):  # pragma: no cover - must skip
        raise AssertionError("empty Expert reached retrieval")

    calls = {"provider": 0}

    def fake_provider_complete(self, messages, **kwargs) -> AgentProviderResult:
        calls["provider"] += 1
        assert messages == [{"role": "user", "content": "Say hello"}]
        assert "GENERAL AGENT EXECUTION" in kwargs["system_prompt"]
        assert "Keep the configured concise voice." in kwargs["system_prompt"]
        assert "GEEM_RAG_CONTEXT" not in kwargs["system_prompt"]
        return AgentProviderResult(
            message=AgentAssistantResponseMessage(content="Hello."),
            finish_reason="stop",
            usage=AgentUsage(
                prompt_tokens=4,
                completion_tokens=1,
                total_tokens=5,
            ),
            provider_model=settings.openrouter_chat_model,
            provider_request_id="provider-request-general-fallback",
            provider_completion_id="provider-completion-general-fallback",
        )

    monkeypatch.setattr(agent_service, "load_agent_rag_prompt", unexpected_rag_prompt)
    monkeypatch.setattr(AgentRetrievalService, "prepare", unexpected_retrieval)
    monkeypatch.setattr(
        OpenRouterChatProvider,
        "complete_for_agent",
        fake_provider_complete,
    )

    user, workspace = _create_workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    _app_id, plan_id = _publish_isolated_release_candidate(db)
    _subscribe(client, user=user, workspace=workspace, plan_id=plan_id)
    key = _create_agent_key(client, user=user, workspace=workspace)
    expert = _create_empty_enabled_expert(
        client,
        user=user,
        workspace=workspace,
    )

    completion = client.post(
        AGENT_CHAT,
        headers=_api_key_headers(key["key"], expert["id"]),
        json={
            "model": PUBLIC_MODEL_ID,
            "messages": [{"role": "user", "content": "Say hello"}],
        },
    )

    assert completion.status_code == 200, completion.text
    assert completion.json()["choices"][0]["message"]["content"] == "Hello."
    assert completion.json()["geem"] == {
        "retrieval": "skipped_general",
        "citations": [],
        "insufficient_context": None,
        "billed_tokens": 5,
    }
    assert calls == {"provider": 1}

    db.expire_all()
    assert (
        db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == workspace_id,
                UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
            )
        )
        == 1
    )
    db.rollback()

    # Connector/upload sources can precede their first Document. This is
    # expected knowledge, so the next request must fail before provider work
    # and before consuming another paid request unit.
    expert_row = db.get(Expert, uuid.UUID(expert["id"]))
    assert expert_row is not None
    expert_row.status = ExpertStatus.DRAFT.value
    db.add(
        ExpertSource(
            expert_id=expert_row.id,
            type=ExpertSourceType.CONNECTOR.value,
            name="Pending connector source",
            status=ExpertSourceStatus.PROCESSING.value,
            config={},
        )
    )
    db.commit()

    blocked = client.post(
        AGENT_CHAT,
        headers=_api_key_headers(key["key"], expert["id"]),
        json={
            "model": PUBLIC_MODEL_ID,
            "messages": [{"role": "user", "content": "Say hello"}],
        },
    )

    assert blocked.status_code in {409, 422}, blocked.text
    assert _error_code(blocked) == ErrorCategory.EXPERT_NOT_READY.value
    assert calls == {"provider": 1}
    db.expire_all()
    assert (
        db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == workspace_id,
                UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
            )
        )
        == 1
    )


def test_agent_key_cannot_select_another_workspaces_expert(
    client,
    register_user,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        client_agent_api_enabled=True,
        openrouter_api_key="test-openrouter-key",
    )
    monkeypatch.setattr(agent_router, "get_settings", lambda: settings)

    def unexpected_retrieval(self, **kwargs):  # pragma: no cover - must stay gated
        raise AssertionError("cross-Workspace request reached retrieval")

    def unexpected_provider(self, messages, **kwargs):  # pragma: no cover
        raise AssertionError("cross-Workspace request reached the provider")

    monkeypatch.setattr(AgentRetrievalService, "prepare", unexpected_retrieval)
    monkeypatch.setattr(
        OpenRouterChatProvider,
        "complete_for_agent",
        unexpected_provider,
    )

    user_a, workspace_a = _create_workspace(client, register_user)
    user_b, workspace_b = _create_workspace(client, register_user)
    _app_id, plan_id = _publish_isolated_release_candidate(db)
    _subscribe(client, user=user_a, workspace=workspace_a, plan_id=plan_id)
    _subscribe(client, user=user_b, workspace=workspace_b, plan_id=plan_id)
    key_a = _create_agent_key(client, user=user_a, workspace=workspace_a)
    expert_b = _create_enabled_expert(
        client,
        db,
        user=user_b,
        workspace=workspace_b,
    )

    denied = client.post(
        AGENT_CHAT,
        headers=_api_key_headers(key_a["key"], expert_b["id"]),
        json={
            "model": PUBLIC_MODEL_ID,
            "messages": [{"role": "user", "content": "What is covered?"}],
        },
    )

    assert denied.status_code == 404, denied.text
    assert _error_code(denied) == "expert_not_found"
    assert (
        db.scalar(
            select(func.count())
            .select_from(UsagePeriodCounter)
            .where(
                UsagePeriodCounter.workspace_id == uuid.UUID(workspace_a["id"]),
                UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
            )
        )
        == 0
    )
