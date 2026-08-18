"""Phase 10A — workspace invitation HTTP API, isolation, tokens, accept."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.identity.repository import UserRepository
from app.main import app
from app.notifications.factory import get_email_provider
from app.workspaces.invitation_service import InvitationService
from app.workspaces.models import (
    Workspace,
    WorkspaceInvitation,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceStatus,
)
from tests.conftest import TestingSessionLocal
from tests.support.fake_email import (
    FailingEmailProvider,
    RecordingEmailProvider,
    token_from_invite_email,
    url_from_invite_email,
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient, user: dict, slug: str, name: str = "Invites") -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_member(db, workspace_id: str, user_id: str, role: WorkspaceRole) -> None:
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id),
            role=role.value,
        )
    )
    db.commit()


@pytest.fixture()
def inbox(client: TestClient) -> RecordingEmailProvider:
    provider = RecordingEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: provider
    return provider


def _invite(
    client: TestClient,
    actor: dict,
    workspace_id: str,
    email: str,
    role: str = "member",
) -> object:
    return client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        headers=_auth(actor["access_token"]),
        json={"email": email, "role": role},
    )


def test_owner_invites_member_and_admin(client, register_user, inbox, db) -> None:
    owner = register_user(email="owner-inv@example.com")
    ws = _create_workspace(client, owner, "inv-owner-ws")
    member_invite = _invite(client, owner, ws["id"], "new-member@example.com", "member")
    assert member_invite.status_code == 201, member_invite.text
    body = member_invite.json()
    assert body["email"] == "new-member@example.com"
    assert body["role"] == "member"
    assert body["status"] == "pending"
    assert "token_hash" not in body
    assert "token" not in body
    admin_invite = _invite(client, owner, ws["id"], "new-admin@example.com", "admin")
    assert admin_invite.status_code == 201, admin_invite.text
    assert admin_invite.json()["role"] == "admin"
    assert len(inbox.messages) == 2
    raw = token_from_invite_email(inbox.messages[0])
    row = db.get(WorkspaceInvitation, uuid.UUID(body["id"]))
    assert row is not None
    assert row.token_hash != raw
    assert raw not in row.token_hash
    assert len(row.token_hash) == 64
    listed = client.get(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"]),
    )
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["total"] == 2
    assert {item["email"] for item in payload["items"]} == {
        "new-member@example.com",
        "new-admin@example.com",
    }
    blob = listed.text
    assert "token_hash" not in blob
    assert raw not in blob
    assert row.token_hash not in blob


def test_admin_can_invite_member_cannot(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-admin-inv@example.com")
    admin = register_user(email="adm-inv@example.com")
    member = register_user(email="mem-inv@example.com")
    ws = _create_workspace(client, owner, "inv-roles-ws")
    _add_member(db, ws["id"], admin["user"]["id"], WorkspaceRole.ADMIN)
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)

    as_admin = _invite(client, admin, ws["id"], "via-admin@example.com", "admin")
    assert as_admin.status_code == 201, as_admin.text
    as_member = _invite(client, member, ws["id"], "via-member@example.com", "member")
    assert as_member.status_code == 403
    assert as_member.json()["code"] == "insufficient_workspace_role"
    listed = client.get(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(member["access_token"]),
    )
    assert listed.status_code == 403


def test_invite_as_owner_and_invalid_role_rejected(client, register_user, inbox) -> None:
    owner = register_user(email="own-role@example.com")
    ws = _create_workspace(client, owner, "inv-bad-role")
    owner_role = _invite(client, owner, ws["id"], "x@example.com", "owner")
    assert owner_role.status_code == 422
    invalid = _invite(client, owner, ws["id"], "x@example.com", "superadmin")
    assert invalid.status_code == 422
    assert inbox.messages == []


def test_email_is_normalized(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-norm@example.com")
    ws = _create_workspace(client, owner, "inv-norm")
    res = _invite(client, owner, ws["id"], "Foo.Bar@Example.COM", "member")
    assert res.status_code == 201, res.text
    assert res.json()["email"] == "foo.bar@example.com"
    row = db.get(WorkspaceInvitation, uuid.UUID(res.json()["id"]))
    assert row is not None
    assert row.email == "foo.bar@example.com"


def test_existing_member_invite_conflicts(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-exist@example.com")
    member = register_user(email="already@example.com")
    ws = _create_workspace(client, owner, "inv-exist")
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
    res = _invite(client, owner, ws["id"], "already@example.com", "admin")
    assert res.status_code == 409
    assert res.json()["code"] == "already_workspace_member"
    assert inbox.messages == []
    members = client.get(
        f"/api/workspaces/{ws['id']}/members",
        headers=_auth(owner["access_token"]),
    )
    roles = {m["user_id"]: m["role"] for m in members.json()}
    assert roles[member["user"]["id"]] == "member"


def test_resend_and_list_hide_invite_after_email_is_member(
    client, register_user, inbox, db
) -> None:
    owner = register_user(email="own-stale-inv@example.com")
    member = register_user(email="stale-inv@example.com")
    ws = _create_workspace(client, owner, "inv-stale-member")
    created = _invite(client, owner, ws["id"], "stale-inv@example.com")
    assert created.status_code == 201, created.text
    invitation_id = created.json()["id"]
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)

    listed = client.get(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"]),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0
    assert listed.json()["items"] == []

    resend = client.post(
        f"/api/workspaces/{ws['id']}/invitations/{invitation_id}/resend",
        headers=_auth(owner["access_token"]),
    )
    assert resend.status_code == 409
    assert resend.json()["code"] == "already_workspace_member"
    assert len(inbox.messages) == 1

    revoked = client.delete(
        f"/api/workspaces/{ws['id']}/invitations/{invitation_id}",
        headers=_auth(owner["access_token"]),
    )
    assert revoked.status_code == 204


def test_duplicate_pending_invitation(client, register_user, inbox) -> None:
    owner = register_user(email="own-dup@example.com")
    ws = _create_workspace(client, owner, "inv-dup")
    first = _invite(client, owner, ws["id"], "dup@example.com")
    assert first.status_code == 201, first.text
    second = _invite(client, owner, ws["id"], "DUP@example.com")
    assert second.status_code == 409
    assert second.json()["code"] == "invitation_already_exists"
    assert len(inbox.messages) == 1


def test_same_email_two_workspaces(client, register_user, inbox) -> None:
    owner_a = register_user(email="own-a@example.com")
    owner_b = register_user(email="own-b@example.com")
    a = _create_workspace(client, owner_a, "inv-ws-a", "A")
    b = _create_workspace(client, owner_b, "inv-ws-b", "B")
    ra = _invite(client, owner_a, a["id"], "shared@example.com")
    rb = _invite(client, owner_b, b["id"], "shared@example.com")
    assert ra.status_code == 201 and rb.status_code == 201
    assert len(inbox.messages) == 2


def test_tenant_isolation_on_list_resend_revoke(client, register_user, inbox) -> None:
    owner_a = register_user(email="iso-a@example.com")
    owner_b = register_user(email="iso-b@example.com")
    a = _create_workspace(client, owner_a, "iso-a")
    b = _create_workspace(client, owner_b, "iso-b")
    created = _invite(client, owner_b, b["id"], "target@example.com")
    assert created.status_code == 201
    inv_id = created.json()["id"]

    listed = client.get(
        f"/api/workspaces/{b['id']}/invitations",
        headers=_auth(owner_a["access_token"]),
    )
    assert listed.status_code == 403
    assert listed.json()["code"] == "workspace_access_denied"

    resend = client.post(
        f"/api/workspaces/{b['id']}/invitations/{inv_id}/resend",
        headers=_auth(owner_a["access_token"]),
    )
    assert resend.status_code == 403

    revoke_b = client.delete(
        f"/api/workspaces/{b['id']}/invitations/{inv_id}",
        headers=_auth(owner_a["access_token"]),
    )
    assert revoke_b.status_code == 403

    cross = client.delete(
        f"/api/workspaces/{a['id']}/invitations/{inv_id}",
        headers=_auth(owner_a["access_token"]),
    )
    assert cross.status_code == 404
    assert cross.json()["code"] == "invitation_not_found"

    still = client.get(
        f"/api/workspaces/{b['id']}/invitations",
        headers=_auth(owner_b["access_token"]),
    )
    assert still.status_code == 200
    assert still.json()["total"] == 1


def test_resend_rotates_token_and_invalidates_old(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-resend@example.com")
    invitee = register_user(email="resend-me@example.com")
    ws = _create_workspace(client, owner, "inv-resend")
    created = _invite(client, owner, ws["id"], "resend-me@example.com")
    assert created.status_code == 201
    inv_id = created.json()["id"]
    old_token = token_from_invite_email(inbox.messages[0])
    old_hash = db.get(WorkspaceInvitation, uuid.UUID(inv_id)).token_hash
    old_expiry = db.get(WorkspaceInvitation, uuid.UUID(inv_id)).expires_at

    resent = client.post(
        f"/api/workspaces/{ws['id']}/invitations/{inv_id}/resend",
        headers=_auth(owner["access_token"]),
    )
    assert resent.status_code == 200, resent.text
    assert len(inbox.messages) == 2
    new_token = token_from_invite_email(inbox.messages[1])
    assert new_token != old_token
    db.expire_all()
    row = db.get(WorkspaceInvitation, uuid.UUID(inv_id))
    assert row.token_hash != old_hash
    assert row.token_hash != new_token
    assert row.expires_at > old_expiry

    denied = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": old_token},
    )
    assert denied.status_code == 400
    assert denied.json()["code"] == "invalid_invitation"

    accepted = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": new_token},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "member"
    assert accepted.json()["workspace_id"] == ws["id"]


def test_revoke_invalidates_and_cannot_resend(client, register_user, inbox) -> None:
    owner = register_user(email="own-rev@example.com")
    invitee = register_user(email="rev-me@example.com")
    ws = _create_workspace(client, owner, "inv-rev")
    created = _invite(client, owner, ws["id"], "rev-me@example.com")
    inv_id = created.json()["id"]
    token = token_from_invite_email(inbox.messages[0])

    revoked = client.delete(
        f"/api/workspaces/{ws['id']}/invitations/{inv_id}",
        headers=_auth(owner["access_token"]),
    )
    assert revoked.status_code == 204
    again = client.delete(
        f"/api/workspaces/{ws['id']}/invitations/{inv_id}",
        headers=_auth(owner["access_token"]),
    )
    assert again.status_code == 204

    resend = client.post(
        f"/api/workspaces/{ws['id']}/invitations/{inv_id}/resend",
        headers=_auth(owner["access_token"]),
    )
    assert resend.status_code == 409
    assert resend.json()["code"] == "invitation_revoked"

    accepted = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": token},
    )
    assert accepted.status_code == 409
    assert accepted.json()["code"] == "invitation_revoked"


def test_expired_invitation_rejected_and_recreate_rotates(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-exp@example.com")
    invitee = register_user(email="exp-me@example.com")
    ws = _create_workspace(client, owner, "inv-exp")
    created = _invite(client, owner, ws["id"], "exp-me@example.com")
    inv_id = created.json()["id"]
    old_token = token_from_invite_email(inbox.messages[0])
    row = db.get(WorkspaceInvitation, uuid.UUID(inv_id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    expired = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": old_token},
    )
    assert expired.status_code == 410
    assert expired.json()["code"] == "invitation_expired"

    listed = client.get(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"]),
    )
    assert listed.json()["total"] == 0

    recreated = _invite(client, owner, ws["id"], "exp-me@example.com")
    assert recreated.status_code == 201, recreated.text
    new_token = token_from_invite_email(inbox.messages[-1])
    assert new_token != old_token
    ok = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": new_token},
    )
    assert ok.status_code == 200, ok.text


def test_accept_creates_membership_and_is_idempotent(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-acc@example.com")
    invitee = register_user(email="acc-me@example.com")
    ws = _create_workspace(client, owner, "inv-acc")
    created = _invite(client, owner, ws["id"], "acc-me@example.com", "admin")
    token = token_from_invite_email(inbox.messages[0])
    first = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": token},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["role"] == "admin"
    assert body["already_member"] is False
    assert body["workspace_slug"] == "inv-acc"

    second = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": token},
    )
    assert second.status_code == 200, second.text
    assert second.json()["membership_id"] == body["membership_id"]
    assert second.json()["already_member"] is True

    members = client.get(
        f"/api/workspaces/{ws['id']}/members",
        headers=_auth(owner["access_token"]),
    )
    matches = [m for m in members.json() if m["user_id"] == invitee["user"]["id"]]
    assert len(matches) == 1
    assert matches[0]["role"] == "admin"
    row = db.get(WorkspaceInvitation, uuid.UUID(created.json()["id"]))
    assert row.accepted_at is not None


def test_email_mismatch_rejected(client, register_user, inbox) -> None:
    owner = register_user(email="own-mm@example.com")
    alice_invite_email = "alice-invite@example.com"
    bob = register_user(email="bob-mm@example.com")
    ws = _create_workspace(client, owner, "inv-mm")
    created = _invite(client, owner, ws["id"], alice_invite_email)
    token = token_from_invite_email(inbox.messages[0])
    res = client.post(
        "/api/invitations/accept",
        headers=_auth(bob["access_token"]),
        json={"token": token},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "invitation_email_mismatch"
    listed = client.get(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"]),
    )
    assert listed.json()["total"] == 1
    assert created.json()["id"] == listed.json()["items"][0]["id"]


def test_unknown_token_rejected(client, register_user) -> None:
    user = register_user(email="own-unk@example.com")
    res = client.post(
        "/api/invitations/accept",
        headers=_auth(user["access_token"]),
        json={"token": "not-a-real-invitation-token-value"},
    )
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_invitation"


def test_accept_when_membership_already_exists_does_not_change_role(
    client, register_user, inbox, db
) -> None:
    owner = register_user(email="own-pre@example.com")
    invitee = register_user(email="pre-mem@example.com")
    ws = _create_workspace(client, owner, "inv-pre")
    created = _invite(client, owner, ws["id"], "pre-mem@example.com", "member")
    token = token_from_invite_email(inbox.messages[0])
    _add_member(db, ws["id"], invitee["user"]["id"], WorkspaceRole.ADMIN)
    res = client.post(
        "/api/invitations/accept",
        headers=_auth(invitee["access_token"]),
        json={"token": token},
    )
    assert res.status_code == 200, res.text
    assert res.json()["already_member"] is True
    assert res.json()["role"] == "admin"
    members = client.get(
        f"/api/workspaces/{ws['id']}/members",
        headers=_auth(owner["access_token"]),
    )
    match = next(m for m in members.json() if m["user_id"] == invitee["user"]["id"])
    assert match["role"] == "admin"
    row = db.get(WorkspaceInvitation, uuid.UUID(created.json()["id"]))
    assert row.accepted_at is not None


def test_generated_url_uses_configured_frontend_base(
    client, register_user, inbox, monkeypatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSPACE_WEB_URL", "https://app.geem.test")
    get_settings.cache_clear()
    try:
        owner = register_user(email="own-url@example.com")
        ws = _create_workspace(client, owner, "inv-url")
        res = _invite(client, owner, ws["id"], "url-me@example.com")
        assert res.status_code == 201, res.text
        url = url_from_invite_email(inbox.messages[0])
        assert url.startswith("https://app.geem.test/invitations/accept?token=")
    finally:
        get_settings.cache_clear()


def test_provider_failure_rolls_back_invitation(client, register_user, db) -> None:
    owner = register_user(email="own-fail@example.com")
    ws = _create_workspace(client, owner, "inv-fail")
    app.dependency_overrides[get_email_provider] = lambda: FailingEmailProvider()
    res = _invite(client, owner, ws["id"], "fail-me@example.com")
    assert res.status_code == 502
    assert res.json()["code"] == "email_delivery_failed"
    remaining = list(db.scalars(select(WorkspaceInvitation)).all())
    assert remaining == []


def test_concurrent_accept_cannot_duplicate_membership(client, register_user, inbox, db) -> None:
    owner = register_user(email="own-con@example.com")
    invitee = register_user(email="con-me@example.com")
    ws = _create_workspace(client, owner, "inv-con")
    created = _invite(client, owner, ws["id"], "con-me@example.com", "member")
    token = token_from_invite_email(inbox.messages[0])
    user_id = uuid.UUID(invitee["user"]["id"])
    barrier = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []
    results: list[uuid.UUID] = []

    def worker() -> None:
        session = TestingSessionLocal()
        try:
            actor = UserRepository(session).get_by_id(user_id)
            assert actor is not None
            barrier.wait()
            invitation, membership, _ws, _already = InvitationService(
                session, email_provider=RecordingEmailProvider()
            ).accept(user=actor, raw_token=token)
            results.append(membership.id)
            _ = invitation
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            session.rollback()
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(set(results)) == 1
    db.expire_all()
    members = list(
        db.scalars(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == uuid.UUID(ws["id"]),
                WorkspaceMembership.user_id == uuid.UUID(invitee["user"]["id"]),
            )
        ).all()
    )
    assert len(members) == 1
    row = db.get(WorkspaceInvitation, uuid.UUID(created.json()["id"]))
    assert row.accepted_at is not None


def test_last_owner_rules_unchanged_with_invites(client, register_user, inbox) -> None:
    owner = register_user(email="solo-inv@example.com")
    ws = _create_workspace(client, owner, "inv-last-owner")
    _invite(client, owner, ws["id"], "someone@example.com")
    uid = owner["user"]["id"]
    demote = client.patch(
        f"/api/workspaces/{ws['id']}/members/{uid}",
        headers=_auth(owner["access_token"]),
        json={"role": "admin"},
    )
    assert demote.status_code == 409
    assert demote.json()["code"] == "last_workspace_owner"
    remove = client.delete(
        f"/api/workspaces/{ws['id']}/members/{uid}",
        headers=_auth(owner["access_token"]),
    )
    assert remove.status_code == 409
    assert remove.json()["code"] == "last_workspace_owner"


def test_invite_create_and_resend_require_active_workspace(
    client, register_user, inbox, db
) -> None:
    owner = register_user(email="own-inactive-inv@example.com")
    ws = _create_workspace(client, owner, "inv-inactive")
    created = _invite(client, owner, ws["id"], "pending@example.com")
    assert created.status_code == 201, created.text
    invitation_id = created.json()["id"]
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    workspace.status = WorkspaceStatus.SUSPENDED.value
    db.commit()

    refused = _invite(client, owner, ws["id"], "another@example.com")
    assert refused.status_code == 403
    assert refused.json()["code"] == "workspace_access_denied"
    assert len(inbox.messages) == 1

    resend = client.post(
        f"/api/workspaces/{ws['id']}/invitations/{invitation_id}/resend",
        headers=_auth(owner["access_token"]),
    )
    assert resend.status_code == 403
    assert resend.json()["code"] == "workspace_access_denied"
    assert len(inbox.messages) == 1

    listed = client.get(
        f"/api/workspaces/{ws['id']}/invitations",
        headers=_auth(owner["access_token"]),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1

    revoked = client.delete(
        f"/api/workspaces/{ws['id']}/invitations/{invitation_id}",
        headers=_auth(owner["access_token"]),
    )
    assert revoked.status_code == 204, revoked.text


def test_accept_requires_auth(client, register_user, inbox) -> None:
    owner = register_user(email="own-unauth@example.com")
    ws = _create_workspace(client, owner, "inv-unauth")
    created = _invite(client, owner, ws["id"], "need-auth@example.com")
    assert created.status_code == 201
    token = token_from_invite_email(inbox.messages[0])
    res = client.post("/api/invitations/accept", json={"token": token})
    assert res.status_code == 401
