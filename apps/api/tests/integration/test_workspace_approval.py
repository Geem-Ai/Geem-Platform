"""Workspace Platform Admin approval (pending → active / archived)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit import AuditAction, AuditLog
from app.identity.models import PlatformRole, User
from app.workspaces.models import Workspace, WorkspaceStatus


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _promote_platform_admin(db, user_id: str) -> User:
    user = db.get(User, uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _create_pending_workspace(client: TestClient, db, user: dict, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    # Integration suite uses APP_ENV=test (auto-active); force pending for this slice.
    ws = db.get(Workspace, uuid.UUID(body["id"]))
    assert ws is not None
    ws.status = WorkspaceStatus.PENDING.value
    db.commit()
    body["status"] = WorkspaceStatus.PENDING.value
    return body


def test_approve_reject_workspace_lifecycle(
    client: TestClient, register_user, db
) -> None:
    admin_body = register_user(email="padmin-approve@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    owner = register_user(email="tenant-approve@example.com")
    ws = _create_pending_workspace(client, db, owner, "pending-ws-1")

    denied = client.get(
        "/api/workspaces/current",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "workspace_access_denied"

    disable_blocked = client.post(
        f"/api/platform/workspaces/{ws['id']}/disable",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "should not disable pending"},
    )
    assert disable_blocked.status_code == 409, disable_blocked.text

    approve = client.post(
        f"/api/platform/workspaces/{ws['id']}/approve",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "KYC complete"},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == WorkspaceStatus.ACTIVE.value

    row = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_APPROVED.value,
            AuditLog.entity_id == uuid.UUID(ws["id"]),
        )
    )
    assert row is not None
    assert row.extra.get("after_status") == WorkspaceStatus.ACTIVE.value
    assert row.extra.get("reason") == "KYC complete"

    ok = client.get(
        "/api/workspaces/current",
        headers=_auth(owner["access_token"], **{"X-Workspace-Id": ws["id"]}),
    )
    assert ok.status_code == 200, ok.text

    ws2 = _create_pending_workspace(client, db, owner, "pending-ws-2")
    reject = client.post(
        f"/api/platform/workspaces/{ws2['id']}/reject",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "Incomplete registration"},
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["status"] == WorkspaceStatus.ARCHIVED.value

    reject_row = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_REJECTED.value,
            AuditLog.entity_id == uuid.UUID(ws2["id"]),
        )
    )
    assert reject_row is not None
    assert reject_row.extra.get("reason") == "Incomplete registration"

    listed = client.get("/api/workspaces", headers=_auth(owner["access_token"]))
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert ws["id"] in ids
    assert ws2["id"] not in ids  # archived excluded from tenant list


def test_reject_requires_reason(client: TestClient, register_user, db) -> None:
    admin_body = register_user(email="padmin-reject-reason@example.com")
    _promote_platform_admin(db, admin_body["user"]["id"])
    owner = register_user(email="tenant-reject-reason@example.com")
    ws = _create_pending_workspace(client, db, owner, "pending-reject-reason")
    res = client.post(
        f"/api/platform/workspaces/{ws['id']}/reject",
        headers=_auth(admin_body["access_token"]),
        json={"reason": "  "},
    )
    assert res.status_code in (400, 422)


def test_create_workspace_pending_outside_test_env(db, register_user, monkeypatch) -> None:
    from app.core.config import get_settings
    from app.workspaces.service import WorkspaceService

    user = register_user(email="pending-create-env@example.com")
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "local")
    svc = WorkspaceService(db, settings=settings)
    workspace, _membership = svc.create_workspace(
        name="Pending Local",
        slug="pending-local-ws",
        created_by=uuid.UUID(user["user"]["id"]),
    )
    assert workspace.status == WorkspaceStatus.PENDING.value
