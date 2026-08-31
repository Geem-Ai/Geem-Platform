"""Transactional email is delivered by the worker, not on the request path."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.core.config import get_settings
from app.identity.models import EmailVerificationToken, PasswordResetToken
from app.identity.repository import UserRepository
from app.notifications.tasks import send_email_verification, send_password_reset
from tests.support.fake_email import (
    FailingEmailProvider,
    RecordingEmailProvider,
    deliver_email_tasks_inline,
    token_from_reset_email,
    token_from_verify_email,
)


@pytest.fixture()
def require_verification() -> Generator[None, None, None]:
    settings = get_settings()
    previous = settings.email_verification_required
    settings.email_verification_required = True
    try:
        yield
    finally:
        settings.email_verification_required = previous


def _use_provider(monkeypatch, provider) -> None:
    import app.notifications.tasks as email_tasks

    monkeypatch.setattr(
        email_tasks, "build_email_provider", lambda settings=None: provider
    )


def _unused_tokens(db, model, user_id: uuid.UUID) -> list:
    # The worker committed on its own session; drop this session's snapshot.
    db.expire_all()
    return list(
        db.scalars(
            select(model).where(model.user_id == user_id, model.used_at.is_(None))
        ).all()
    )


def test_register_succeeds_when_email_delivery_fails(
    client: TestClient, monkeypatch, require_verification, db
) -> None:
    deliver_email_tasks_inline(monkeypatch, FailingEmailProvider())

    res = client.post(
        "/api/auth/register",
        json={"email": "smtp-down@example.com", "password": "securepass1"},
    )

    # The account must exist even though the verification mail never left.
    assert res.status_code == 200, res.text
    assert res.json()["verification_required"] is True
    stored = UserRepository(db).get_by_email("smtp-down@example.com")
    assert stored is not None
    assert stored.email_verified_at is None


def test_forgot_password_succeeds_when_email_delivery_fails(
    client: TestClient, register_user, monkeypatch, db
) -> None:
    register_user(email="reset-smtp-down@example.com", password="oldpass123")
    deliver_email_tasks_inline(monkeypatch, FailingEmailProvider())

    res = client.post(
        "/api/auth/forgot-password", json={"email": "reset-smtp-down@example.com"}
    )

    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_verification_retry_invalidates_the_undelivered_token(
    client: TestClient, monkeypatch, require_verification, db
) -> None:
    deliver_email_tasks_inline(monkeypatch, FailingEmailProvider())
    client.post(
        "/api/auth/register",
        json={"email": "retry-verify@example.com", "password": "securepass1"},
    )
    user = UserRepository(db).get_by_email("retry-verify@example.com")
    assert user is not None

    inbox = RecordingEmailProvider()
    _use_provider(monkeypatch, inbox)
    send_email_verification.apply(args=[str(user.id)])

    assert len(inbox.messages) == 1
    raw = token_from_verify_email(inbox.messages[0])
    verified = client.post("/api/auth/verify-email", json={"token": raw})
    assert verified.status_code == 200, verified.text
    # The first attempt's token was replaced, so only the delivered one works.
    assert _unused_tokens(db, EmailVerificationToken, user.id) == []


def test_verification_task_is_a_no_op_once_the_account_is_verified(
    register_user, monkeypatch, db
) -> None:
    body = register_user(email="already-verified@example.com")
    inbox = RecordingEmailProvider()
    _use_provider(monkeypatch, inbox)

    result = send_email_verification.apply(args=[body["user"]["id"]])

    assert result.result == {"user_id": body["user"]["id"], "delivered": False}
    assert inbox.messages == []


def test_verification_task_is_a_no_op_for_an_unknown_user(monkeypatch) -> None:
    inbox = RecordingEmailProvider()
    _use_provider(monkeypatch, inbox)
    unknown = str(uuid.uuid4())

    result = send_email_verification.apply(args=[unknown])

    assert result.result == {"user_id": unknown, "delivered": False}
    assert inbox.messages == []


def test_password_reset_task_mints_and_sends_a_usable_token(
    client: TestClient, register_user, monkeypatch, db
) -> None:
    body = register_user(email="task-reset@example.com", password="oldpass123")
    inbox = RecordingEmailProvider()
    _use_provider(monkeypatch, inbox)

    result = send_password_reset.apply(args=[body["user"]["id"]])

    assert result.result == {"user_id": body["user"]["id"], "delivered": True}
    assert len(inbox.messages) == 1
    raw = token_from_reset_email(inbox.messages[0])
    reset = client.post(
        "/api/auth/reset-password", json={"token": raw, "password": "newpass456"}
    )
    assert reset.status_code == 200, reset.text
    assert _unused_tokens(db, PasswordResetToken, uuid.UUID(body["user"]["id"])) == []


def test_password_reset_task_is_a_no_op_for_an_unknown_user(monkeypatch) -> None:
    inbox = RecordingEmailProvider()
    _use_provider(monkeypatch, inbox)
    unknown = str(uuid.uuid4())

    result = send_password_reset.apply(args=[unknown])

    assert result.result == {"user_id": unknown, "delivered": False}
    assert inbox.messages == []
