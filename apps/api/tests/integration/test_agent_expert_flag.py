"""Paid false-to-true transition tests for the Expert client-agent flag."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENTS_AI_APP_SLUG,
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
)
from app.apps_catalog.seed import ensure_app_catalog
from app.core.errors import ErrorCategory


def _headers(token: str, workspace_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Workspace-Id": workspace_id,
    }


def _workspace(client, register_user) -> tuple[dict, dict]:
    user = register_user(email=f"agent-flag-{uuid.uuid4().hex[:8]}@example.com")
    response = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={
            "name": "Agent Expert flag fixture",
            "slug": f"agent-flag-{uuid.uuid4().hex[:8]}",
        },
    )
    assert response.status_code in {200, 201}, response.text
    return user, response.json()


def _grant(db: Session, workspace_id: uuid.UUID) -> AppInstallation:
    ensure_app_catalog(db)
    catalog = AppAccessService(db).repo.get_app_by_slug(AGENTS_AI_APP_SLUG)
    assert catalog is not None
    catalog.status = AppStatus.PUBLISHED.value
    plan = AppPlan(
        app_id=catalog.id,
        code=f"flag-fixture-{uuid.uuid4().hex[:8]}",
        name="Flag test plan",
        description="Isolated non-production fixture.",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=Decimal("1.00"),
        currency="SAR",
        sort_order=1,
        is_default=True,
        is_active=True,
    )
    db.add(plan)
    db.flush()
    db.add(
        AppPlanEntitlement(
            app_plan_id=plan.id,
            key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
            value=2,
        )
    )
    now = datetime.now(timezone.utc)
    installation = AppInstallation(
        workspace_id=workspace_id,
        app_id=catalog.id,
        status=AppInstallationStatus.ACTIVE.value,
        installed_at=now,
    )
    db.add_all(
        [
            installation,
            AppSubscription(
                workspace_id=workspace_id,
                app_id=catalog.id,
                app_plan_id=plan.id,
                status=AppSubscriptionStatus.ACTIVE.value,
                current_period_start=now - timedelta(minutes=1),
                current_period_end=now + timedelta(days=30),
            ),
        ]
    )
    db.commit()
    return installation


def test_client_agent_enable_requires_paid_access_but_disable_remains_reachable(
    client, register_user, db: Session
) -> None:
    user, workspace = _workspace(client, register_user)
    headers = _headers(user["access_token"], workspace["id"])
    created = client.post(
        "/api/experts",
        headers=headers,
        json={"name": "Flag fixture"},
    )
    assert created.status_code == 201, created.text
    expert_id = created.json()["id"]

    denied = client.patch(
        f"/api/experts/{expert_id}",
        headers=headers,
        json={"rag_config": {"client_agent": {"enabled": True}}},
    )
    assert denied.status_code == 404 or denied.status_code == 409
    assert denied.json()["code"] in {
        ErrorCategory.APP_NOT_FOUND.value,
        ErrorCategory.APP_NOT_AVAILABLE.value,
    }
    db.rollback()

    installation = _grant(db, uuid.UUID(workspace["id"]))
    enabled = client.patch(
        f"/api/experts/{expert_id}",
        headers=headers,
        json={
            "rag_config": {
                "top_k": 4,
                "client_agent": {"enabled": True},
            }
        },
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["rag_config"] == {
        "top_k": 4,
        "client_agent": {"enabled": True},
    }

    installation.status = AppInstallationStatus.UNINSTALLED.value
    db.commit()

    # Expiry/uninstall makes the stored flag inert, but cannot trap an owner
    # in the enabled state or prevent unrelated RAG tuning from being saved.
    persisted = client.patch(
        f"/api/experts/{expert_id}",
        headers=headers,
        json={
            "rag_config": {
                "top_k": 5,
                "client_agent": {"enabled": True},
            }
        },
    )
    assert persisted.status_code == 200, persisted.text
    disabled = client.patch(
        f"/api/experts/{expert_id}",
        headers=headers,
        json={"rag_config": {"client_agent": {"enabled": False}}},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["rag_config"]["client_agent"] == {"enabled": False}


def test_create_with_client_agent_enabled_is_also_paid_gated(
    client, register_user, db: Session
) -> None:
    user, workspace = _workspace(client, register_user)
    denied = client.post(
        "/api/experts",
        headers=_headers(user["access_token"], workspace["id"]),
        json={
            "name": "Cannot bypass transition",
            "rag_config": {"client_agent": {"enabled": True}},
        },
    )
    assert denied.status_code == 404 or denied.status_code == 409
    assert denied.json()["code"] in {
        ErrorCategory.APP_NOT_FOUND.value,
        ErrorCategory.APP_NOT_AVAILABLE.value,
    }
    db.rollback()


def test_client_agent_enable_requires_the_typed_agents_entitlement(
    client, register_user, db: Session
) -> None:
    user, workspace = _workspace(client, register_user)
    headers = _headers(user["access_token"], workspace["id"])
    created = client.post(
        "/api/experts",
        headers=headers,
        json={"name": "Typed entitlement fixture"},
    )
    assert created.status_code == 201, created.text
    _grant(db, uuid.UUID(workspace["id"]))
    db.execute(
        delete(AppPlanEntitlement).where(
            AppPlanEntitlement.key == AGENT_REQUESTS_DAILY_ENTITLEMENT
        )
    )
    db.commit()

    denied = client.patch(
        f"/api/experts/{created.json()['id']}",
        headers=headers,
        json={"rag_config": {"client_agent": {"enabled": True}}},
    )

    assert denied.status_code == 422, denied.text
    assert denied.json()["code"] == ErrorCategory.ENTITLEMENT_INVALID.value
