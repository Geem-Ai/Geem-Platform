from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.identity.models import Session as AuthSession
from app.identity.repository import SessionRepository
from app.identity.security import hash_password, hash_refresh_token, normalize_email, verify_password


def test_register_success(client, register_user) -> None:
    body = register_user(email="Alice@Example.COM", password="securepass1")
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["platform_role"] == "none"


def test_register_duplicate_email_normalized(client, register_user) -> None:
    register_user(email="dup@example.com")
    res = client.post(
        "/api/auth/register",
        json={"email": "DUP@example.com", "password": "securepass1"},
    )
    assert res.status_code == 409
    assert res.json()["code"] == "email_already_exists"


def test_password_hashed_not_plaintext(db, register_user) -> None:
    body = register_user(email="hashme@example.com", password="securepass1")
    from app.identity.repository import UserRepository

    user = UserRepository(db).get_by_id(body["user"]["id"])
    assert user is not None
    assert user.password_hash != "securepass1"
    assert user.password_hash.startswith("$argon2")
    assert verify_password("securepass1", user.password_hash)
    assert normalize_email("HashMe@Example.com") == "hashme@example.com"


def test_login_success_and_invalid(client, register_user) -> None:
    body = register_user(email="login@example.com", password="securepass1")
    ok = client.post(
        "/api/auth/login",
        json={"email": "LOGIN@example.com", "password": "securepass1"},
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["id"] == body["user"]["id"]

    bad = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == "invalid_credentials"


def test_refresh_rotation_and_multitab_grace(client, register_user) -> None:
    body = register_user(email="refresh@example.com")
    refresh = body["_refresh"]
    assert refresh

    first = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert first.status_code == 200
    new_refresh = first.cookies.get(get_settings().refresh_cookie_name)
    assert new_refresh
    assert new_refresh != refresh

    # Immediate reuse of the previous token (multi-tab) continues from tip — no family wipe.
    grace = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert grace.status_code == 200
    grace_refresh = grace.cookies.get(get_settings().refresh_cookie_name)
    assert grace_refresh
    assert grace_refresh != refresh

    # Tip from first rotation should still refresh via grace chain, then work.
    tip = client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert tip.status_code == 200


def test_refresh_delayed_replay_revokes_family(client, register_user, db) -> None:
    body = register_user(email="replay@example.com")
    refresh_a = body["_refresh"]
    first = client.post("/api/auth/refresh", json={"refresh_token": refresh_a})
    assert first.status_code == 200
    refresh_b = first.cookies.get(get_settings().refresh_cookie_name)

    # Age the rotation beyond grace so reuse of A is treated as theft.
    session_a = SessionRepository(db).get_by_token_hash(hash_refresh_token(refresh_a))
    assert session_a is not None and session_a.revoked_at is not None
    session_a.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    db.flush()

    replay = client.post("/api/auth/refresh", json={"refresh_token": refresh_a})
    assert replay.status_code == 401
    assert replay.json()["code"] == "session_revoked"

    # Family wiped — tip B must also fail.
    tip = client.post("/api/auth/refresh", json={"refresh_token": refresh_b})
    assert tip.status_code == 401


def test_revoked_access_token_rejected(client, register_user) -> None:
    body = register_user(email="revoked-access@example.com")
    token = body["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    client.post("/api/auth/logout", json={"refresh_token": body["_refresh"]})
    denied = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 401
    assert denied.json()["code"] in {"session_revoked", "unauthorized"}


def test_logout_revokes_session(client, register_user) -> None:
    body = register_user(email="logout@example.com")
    refresh = body["_refresh"]
    out = client.post("/api/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204

    again = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401
    assert again.json()["code"] == "session_revoked"


def test_expired_session_fails(client, register_user, db) -> None:
    body = register_user(email="expire@example.com")
    refresh = body["_refresh"]
    session = SessionRepository(db).get_by_token_hash(hash_refresh_token(refresh))
    assert session is not None
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.flush()

    res = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 401
    assert res.json()["code"] == "session_expired"


def test_me_requires_auth(client, register_user) -> None:
    assert client.get("/api/auth/me").status_code == 401
    body = register_user(email="me@example.com")
    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "me@example.com"
    assert data["workspaces"] == []
    assert data["current_workspace"] is None


def test_hash_password_helper() -> None:
    h = hash_password("securepass1")
    assert verify_password("securepass1", h)
    assert not verify_password("nope", h)
