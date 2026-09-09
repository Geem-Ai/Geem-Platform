"""Integration tests for register email verification."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.identity.email_verification_tokens import hash_email_verification_token
from app.identity.repository import EmailVerificationTokenRepository, UserRepository
from tests.support.fake_email import (
    RecordingEmailProvider,
    deliver_email_tasks_inline,
    token_from_verify_email,
)


@pytest.fixture()
def inbox(client: TestClient, monkeypatch) -> RecordingEmailProvider:
    provider = RecordingEmailProvider()
    deliver_email_tasks_inline(monkeypatch, provider)
    return provider


@pytest.fixture()
def require_verification() -> Generator[None, None, None]:
    settings = get_settings()
    previous = settings.email_verification_required
    settings.email_verification_required = True
    try:
        yield
    finally:
        settings.email_verification_required = previous


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_without_verification_still_issues_session(register_user) -> None:
    body = register_user(email="auto-verify@example.com", password="securepass1")
    assert body["verification_required"] is False
    assert body["access_token"]
    assert body["user"]["email_verified_at"]


def test_register_requires_verification_and_does_not_authenticate(
    client: TestClient,
    inbox: RecordingEmailProvider,
    require_verification,
    db,
) -> None:
    res = client.post(
        "/api/auth/register",
        json={"email": "pending@example.com", "password": "securepass1"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["verification_required"] is True
    assert body.get("access_token") in (None, "")
    assert get_settings().refresh_cookie_name not in res.cookies
    assert len(inbox.messages) == 1

    stored = UserRepository(db).get_by_email("pending@example.com")
    assert stored is not None
    assert stored.email_verified_at is None

    login = client.post(
        "/api/auth/login",
        json={"email": "pending@example.com", "password": "securepass1"},
    )
    assert login.status_code == 403
    assert login.json()["code"] == "email_not_verified"


def test_verify_email_auto_login(
    client: TestClient,
    inbox: RecordingEmailProvider,
    require_verification,
    db,
) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "verify-me@example.com", "password": "securepass1"},
    )
    raw = token_from_verify_email(inbox.messages[0])

    verified = client.post("/api/auth/verify-email", json={"token": raw})
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["access_token"]
    assert body["user"]["email"] == "verify-me@example.com"
    assert body["user"]["email_verified_at"]
    assert verified.cookies.get(get_settings().refresh_cookie_name)

    me = client.get("/api/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200

    stored = UserRepository(db).get_by_email("verify-me@example.com")
    assert stored is not None
    assert stored.email_verified_at is not None

    reused = client.post("/api/auth/verify-email", json={"token": raw})
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_verification_token"


def test_resend_verification_unknown_email_returns_ok(
    client: TestClient, inbox: RecordingEmailProvider, require_verification
) -> None:
    res = client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert inbox.messages == []


def test_resend_verification_rotates_token(
    client: TestClient, inbox: RecordingEmailProvider, require_verification, db
) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "resend-me@example.com", "password": "securepass1"},
    )
    first = token_from_verify_email(inbox.messages[0])

    again = client.post("/api/auth/resend-verification", json={"email": "RESEND-ME@example.com"})
    assert again.status_code == 200
    assert len(inbox.messages) == 2
    second = token_from_verify_email(inbox.messages[1])
    assert first != second

    stale = client.post("/api/auth/verify-email", json={"token": first})
    assert stale.status_code == 400

    ok = client.post("/api/auth/verify-email", json={"token": second})
    assert ok.status_code == 200


def test_expired_verification_token(
    client: TestClient, inbox: RecordingEmailProvider, require_verification, db
) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "expire-verify@example.com", "password": "securepass1"},
    )
    raw = token_from_verify_email(inbox.messages[0])
    row = EmailVerificationTokenRepository(db).get_by_token_hash(
        hash_email_verification_token(raw, settings=get_settings())
    )
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.flush()

    res = client.post("/api/auth/verify-email", json={"token": raw})
    assert res.status_code == 410
    assert res.json()["code"] == "verification_token_expired"


def test_login_wrong_password_does_not_reveal_unverified(
    client: TestClient, inbox: RecordingEmailProvider, require_verification
) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "hidden@example.com", "password": "securepass1"},
    )
    bad = client.post(
        "/api/auth/login",
        json={"email": "hidden@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == "invalid_credentials"


def test_password_reset_marks_email_verified(
    client: TestClient, inbox: RecordingEmailProvider, require_verification, db
) -> None:
    from tests.support.fake_email import token_from_reset_email

    client.post(
        "/api/auth/register",
        json={"email": "reset-verify@example.com", "password": "oldpass123"},
    )
    client.post("/api/auth/forgot-password", json={"email": "reset-verify@example.com"})
    reset_raw = token_from_reset_email(inbox.messages[-1])
    reset = client.post(
        "/api/auth/reset-password",
        json={"token": reset_raw, "password": "newpass456"},
    )
    assert reset.status_code == 200, reset.text
    stored = UserRepository(db).get_by_email("reset-verify@example.com")
    assert stored is not None
    assert stored.email_verified_at is not None
