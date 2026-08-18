"""Integration tests for forgot / reset / change password."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.identity.models import PasswordResetToken
from app.identity.password_reset_tokens import hash_password_reset_token
from app.identity.repository import PasswordResetTokenRepository, SessionRepository, UserRepository
from app.identity.security import hash_refresh_token, verify_password
from app.main import app
from app.notifications.factory import get_email_provider
from tests.support.fake_email import RecordingEmailProvider, token_from_reset_email


@pytest.fixture()
def inbox(client: TestClient) -> RecordingEmailProvider:
    provider = RecordingEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: provider
    return provider


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_forgot_password_unknown_email_returns_ok_without_mail(
    client: TestClient, inbox: RecordingEmailProvider
) -> None:
    res = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert inbox.messages == []


def test_forgot_and_reset_password_auto_login(
    client: TestClient, register_user, inbox: RecordingEmailProvider, db
) -> None:
    user = register_user(email="reset-me@example.com", password="oldpass123")
    old_refresh = user["_refresh"]

    forgot = client.post("/api/auth/forgot-password", json={"email": "RESET-ME@example.com"})
    assert forgot.status_code == 200
    assert forgot.json() == {"ok": True}
    assert len(inbox.messages) == 1
    raw = token_from_reset_email(inbox.messages[0])

    reset = client.post(
        "/api/auth/reset-password",
        json={"token": raw, "password": "newpass456"},
    )
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["access_token"]
    assert body["user"]["email"] == "reset-me@example.com"
    new_refresh = reset.cookies.get(get_settings().refresh_cookie_name)
    assert new_refresh
    assert new_refresh != old_refresh

    # Old refresh session revoked.
    old_session = SessionRepository(db).get_by_token_hash(hash_refresh_token(old_refresh))
    assert old_session is not None
    assert old_session.revoked_at is not None

    # Password updated.
    stored = UserRepository(db).get_by_id(body["user"]["id"])
    assert stored is not None
    assert verify_password("newpass456", stored.password_hash)
    assert not verify_password("oldpass123", stored.password_hash)

    # New session works; login with new password works.
    me = client.get("/api/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    login = client.post(
        "/api/auth/login",
        json={"email": "reset-me@example.com", "password": "newpass456"},
    )
    assert login.status_code == 200


def test_reset_password_rejects_used_and_expired_tokens(
    client: TestClient, register_user, inbox: RecordingEmailProvider, db
) -> None:
    register_user(email="expire-me@example.com", password="oldpass123")
    client.post("/api/auth/forgot-password", json={"email": "expire-me@example.com"})
    raw = token_from_reset_email(inbox.messages[0])

    ok = client.post(
        "/api/auth/reset-password",
        json={"token": raw, "password": "newpass456"},
    )
    assert ok.status_code == 200

    reuse = client.post(
        "/api/auth/reset-password",
        json={"token": raw, "password": "another789"},
    )
    assert reuse.status_code == 400
    assert reuse.json()["code"] == "invalid_reset_token"

    # Fresh token then expire it.
    inbox.messages.clear()
    client.post("/api/auth/forgot-password", json={"email": "expire-me@example.com"})
    raw2 = token_from_reset_email(inbox.messages[0])
    row = PasswordResetTokenRepository(db).get_by_token_hash(
        hash_password_reset_token(raw2, settings=get_settings())
    )
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.flush()

    expired = client.post(
        "/api/auth/reset-password",
        json={"token": raw2, "password": "freshpass1"},
    )
    assert expired.status_code == 410
    assert expired.json()["code"] == "reset_token_expired"


def test_reset_password_weak_password(
    client: TestClient, register_user, inbox: RecordingEmailProvider
) -> None:
    register_user(email="weak-reset@example.com")
    client.post("/api/auth/forgot-password", json={"email": "weak-reset@example.com"})
    raw = token_from_reset_email(inbox.messages[0])
    res = client.post(
        "/api/auth/reset-password",
        json={"token": raw, "password": "short"},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "weak_password"


def test_change_password_revokes_other_sessions(
    client: TestClient, register_user, db
) -> None:
    first = register_user(email="change-me@example.com", password="oldpass123")
    second = client.post(
        "/api/auth/login",
        json={"email": "change-me@example.com", "password": "oldpass123"},
    )
    assert second.status_code == 200
    second_token = second.json()["access_token"]
    second_refresh = second.cookies.get(get_settings().refresh_cookie_name)

    changed = client.post(
        "/api/auth/change-password",
        headers=_auth(first["access_token"]),
        json={"current_password": "oldpass123", "new_password": "brandnew99"},
    )
    assert changed.status_code == 200
    assert changed.json() == {"ok": True}

    # Current session still valid.
    assert (
        client.get("/api/auth/me", headers=_auth(first["access_token"])).status_code == 200
    )

    # Other session revoked.
    denied = client.get("/api/auth/me", headers=_auth(second_token))
    assert denied.status_code == 401
    tip = client.post("/api/auth/refresh", json={"refresh_token": second_refresh})
    assert tip.status_code == 401

    stored = UserRepository(db).get_by_email("change-me@example.com")
    assert stored is not None
    assert verify_password("brandnew99", stored.password_hash)


def test_change_password_wrong_current(client: TestClient, register_user) -> None:
    user = register_user(email="wrong-cur@example.com", password="oldpass123")
    res = client.post(
        "/api/auth/change-password",
        headers=_auth(user["access_token"]),
        json={"current_password": "nope-nope", "new_password": "brandnew99"},
    )
    assert res.status_code == 401
    assert res.json()["code"] == "invalid_credentials"


def test_forgot_invalidates_prior_unused_token(
    client: TestClient, register_user, inbox: RecordingEmailProvider, db
) -> None:
    register_user(email="twice-forgot@example.com")
    client.post("/api/auth/forgot-password", json={"email": "twice-forgot@example.com"})
    first = token_from_reset_email(inbox.messages[0])
    client.post("/api/auth/forgot-password", json={"email": "twice-forgot@example.com"})
    second = token_from_reset_email(inbox.messages[1])
    assert first != second

    stale = client.post(
        "/api/auth/reset-password",
        json={"token": first, "password": "newpass456"},
    )
    assert stale.status_code == 400

    ok = client.post(
        "/api/auth/reset-password",
        json={"token": second, "password": "newpass456"},
    )
    assert ok.status_code == 200

    # Ensure used_at set on both rows for this user.
    from sqlalchemy import select

    user = UserRepository(db).get_by_email("twice-forgot@example.com")
    assert user is not None
    rows = db.scalars(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    ).all()
    assert len(rows) >= 2
    assert all(r.used_at is not None for r in rows)
