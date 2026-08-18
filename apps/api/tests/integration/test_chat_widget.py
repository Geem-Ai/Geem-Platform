"""Chat Widget app — catalog, config, public bootstrap, allowed_origins."""

from __future__ import annotations

import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.models import CatalogApp
from app.apps_catalog.seed import ensure_app_catalog
from app.experts.models import Expert, ExpertStatus


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _create_workspace(client: TestClient, user: dict, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _return_token(redirect_url: str) -> str:
    return parse_qs(urlparse(redirect_url).query)["rt"][0]


def _complete_noop(client: TestClient, checkout: dict) -> dict:
    rt = _return_token(checkout["redirect_url"])
    res = client.get(
        f"/api/billing/return/noop/{checkout['purchase_id']}",
        params={"rt": rt},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _subscribe_and_install(client: TestClient, headers: dict[str, str], db: Session) -> dict:
    ensure_app_catalog(db)
    db.commit()
    detail = client.get("/api/apps/chat-widget", headers=headers)
    assert detail.status_code == 200, detail.text
    plan_id = detail.json()["plans"][0]["id"]
    checkout = client.post(
        "/api/apps/chat-widget/checkout",
        headers=headers,
        json={"plan_id": plan_id},
    )
    assert checkout.status_code == 200, checkout.text
    _complete_noop(client, checkout.json())
    # Fulfillment may auto-install; install is idempotent for entitlement.
    installed = client.post("/api/apps/chat-widget/install", headers=headers)
    assert installed.status_code in {200, 201, 409}, installed.text
    detail = client.get("/api/apps/chat-widget", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["installation_status"] == "active"
    return detail.json()


@pytest.fixture
def owner_ws(client, register_user):
    user = register_user()
    ws = _create_workspace(
        client, user, "Widget WS", f"widget-{uuid.uuid4().hex[:8]}"
    )
    return user, ws


class TestChatWidgetCatalog:
    def test_seeded_subscription_plan(self, client, owner_ws, db):
        user, ws = owner_ws
        ensure_app_catalog(db)
        db.commit()
        headers = _ws_headers(user, ws)
        res = client.get("/api/apps/chat-widget", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["slug"] == "chat-widget"
        assert body["billing_type"] == "subscription"
        assert body["connector"] is None
        assert body["plans"][0]["code"] == "standard"
        assert body["plans"][0]["price_amount"] in {"199.00", "199.0", "199"}
        assert body["plans"][0]["entitlements"].get("widgets") == 1


class TestChatWidgetConfigAndPublic:
    def test_configure_bootstrap_and_origins(self, client, owner_ws, db):
        user, ws = owner_ws
        headers = _ws_headers(user, ws)
        _subscribe_and_install(client, headers, db)

        expert = client.post(
            "/api/experts",
            headers=headers,
            json={"name": "Widget Expert"},
        )
        assert expert.status_code == 201, expert.text
        expert_id = expert.json()["id"]
        row = db.get(Expert, uuid.UUID(expert_id))
        assert row is not None
        row.status = ExpertStatus.READY.value
        db.commit()

        created = client.get("/api/apps/chat-widget/widget", headers=headers)
        assert created.status_code == 200, created.text
        widget = created.json()
        widget_id = widget["id"]
        assert "geem-widget.js" in widget["embed_script_url"]
        assert widget_id in widget["embed_html"]

        updated = client.put(
            "/api/apps/chat-widget/widget",
            headers=headers,
            json={
                "expert_id": expert_id,
                "title": "Geem",
                "subtitle": "DAL SEEN",
                "greeting": "مرحباً بك",
                "locale": "ar",
                "position": "bottom-right",
                "primary_color": "#0e2f44",
                "text_color": "#f2f2f2",
                "allowed_origins": ["https://www.example.com"],
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["expert_id"] == expert_id
        assert updated.json()["allowed_origins"] == ["https://www.example.com"]

        # Empty allowlist path was replaced — matching origin OK
        ok = client.get(
            f"/api/public/widgets/{widget_id}/bootstrap",
            headers={"Origin": "https://www.example.com"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["title"] == "Geem"
        assert ok.headers.get("access-control-allow-origin") == "https://www.example.com"

        denied = client.get(
            f"/api/public/widgets/{widget_id}/bootstrap",
            headers={"Origin": "https://evil.example"},
        )
        assert denied.status_code == 403

        # Clear allowlist → any origin
        cleared = client.put(
            "/api/apps/chat-widget/widget",
            headers=headers,
            json={"allowed_origins": []},
        )
        assert cleared.status_code == 200, cleared.text
        any_origin = client.get(
            f"/api/public/widgets/{widget_id}/bootstrap",
            headers={"Origin": "https://anywhere.test"},
        )
        assert any_origin.status_code == 200, any_origin.text

        with patch(
            "app.widgets.service.ChatTurnExecutor.execute",
            return_value={
                "answer": "مرحبا",
                "citations": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "document_id": str(uuid.uuid4()),
                        "document_title": "secret.pdf",
                        "page": 1,
                        "snippet": "private text",
                    }
                ],
                "billed_tokens": 1,
            },
        ), patch(
            "app.widgets.service.ChatTurnExecutor.authorize_expert",
            return_value=None,
        ), patch(
            "app.widgets.service.MeteredWorkspaceGeneration.reserve",
            return_value=None,
        ), patch(
            "app.widgets.service.MeteredWorkspaceGeneration.settle",
            return_value=None,
        ), patch(
            "app.widgets.service.MeteredWorkspaceGeneration.release",
            return_value=None,
        ):
            msg = client.post(
                f"/api/public/widgets/{widget_id}/messages",
                headers={"Origin": "https://anywhere.test"},
                json={"message": "hello"},
            )
        assert msg.status_code == 200, msg.text
        assert msg.json()["answer"] == "مرحبا"
        assert "citations" not in msg.json()
        assert msg.json().get("session_id")
        assert "." in msg.json()["session_id"]  # HMAC-signed token

        # Second turn with the same session_id must pass prior history into RAG.
        session_id = msg.json()["session_id"]
        with patch(
            "app.widgets.service.ChatTurnExecutor.execute",
            return_value={
                "answer": "follow-up",
                "citations": [],
                "billed_tokens": 1,
            },
        ) as execute_mock, patch(
            "app.widgets.service.ChatTurnExecutor.authorize_expert",
            return_value=None,
        ), patch(
            "app.widgets.service.MeteredWorkspaceGeneration.reserve",
            return_value=None,
        ), patch(
            "app.widgets.service.MeteredWorkspaceGeneration.settle",
            return_value=None,
        ), patch(
            "app.widgets.service.MeteredWorkspaceGeneration.release",
            return_value=None,
        ):
            msg2 = client.post(
                f"/api/public/widgets/{widget_id}/messages",
                headers={"Origin": "https://anywhere.test"},
                json={"message": "and then?", "session_id": session_id},
            )
        assert msg2.status_code == 200, msg2.text
        assert msg2.json()["answer"] == "follow-up"
        assert msg2.json()["session_id"] == session_id
        assert execute_mock.call_count == 1
        history = execute_mock.call_args.kwargs.get("history") or []
        assert any(
            turn.get("role") == "user" and turn.get("content") == "hello"
            for turn in history
        )
        assert any(
            turn.get("role") == "assistant" and turn.get("content") == "مرحبا"
            for turn in history
        )

        # Unsigned / forged session_id is rejected.
        forged = client.post(
            f"/api/public/widgets/{widget_id}/messages",
            headers={"Origin": "https://anywhere.test"},
            json={"message": "nope", "session_id": str(uuid.uuid4())},
        )
        assert forged.status_code == 422, forged.text

        # Re-lock origins: denied Origin must not receive ACAO.
        locked = client.put(
            "/api/apps/chat-widget/widget",
            headers=headers,
            json={"allowed_origins": ["https://www.example.com"]},
        )
        assert locked.status_code == 200, locked.text
        denied_again = client.get(
            f"/api/public/widgets/{widget_id}/bootstrap",
            headers={"Origin": "https://evil.example"},
        )
        assert denied_again.status_code == 403
        assert denied_again.headers.get("access-control-allow-origin") is None

        # Allowed Origin still gets ACAO on error responses (e.g. unbound Expert).
        unbound = client.put(
            "/api/apps/chat-widget/widget",
            headers=headers,
            json={"expert_id": None, "allowed_origins": ["https://www.example.com"]},
        )
        assert unbound.status_code == 200, unbound.text
        with patch(
            "app.widgets.service.ChatTurnExecutor.authorize_expert",
            return_value=None,
        ):
            err = client.post(
                f"/api/public/widgets/{widget_id}/messages",
                headers={"Origin": "https://www.example.com"},
                json={"message": "hello"},
            )
        assert err.status_code == 422
        assert err.headers.get("access-control-allow-origin") == "https://www.example.com"

    def test_disconnect_reinstall_reactivates(self, client, owner_ws, db):
        user, ws = owner_ws
        headers = _ws_headers(user, ws)
        _subscribe_and_install(client, headers, db)
        widget = client.get("/api/apps/chat-widget/widget", headers=headers).json()
        widget_id = widget["id"]
        assert widget["status"] == "active"

        disc = client.post(
            "/api/apps/chat-widget/widget/disconnect",
            headers=headers,
        )
        assert disc.status_code == 204, disc.text

        boot = client.get(f"/api/public/widgets/{widget_id}/bootstrap")
        assert boot.status_code == 404

        # Subscription still valid — reinstall and open config restores row.
        installed = client.post("/api/apps/chat-widget/install", headers=headers)
        assert installed.status_code in {200, 201}, installed.text
        restored = client.get("/api/apps/chat-widget/widget", headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()["status"] == "active"
        assert restored.json()["id"] == widget_id

        boot2 = client.get(f"/api/public/widgets/{widget_id}/bootstrap")
        assert boot2.status_code == 200, boot2.text

    def test_isolation_other_workspace(self, client, owner_ws, db, register_user):
        user, ws = owner_ws
        headers = _ws_headers(user, ws)
        _subscribe_and_install(client, headers, db)
        widget = client.get("/api/apps/chat-widget/widget", headers=headers).json()

        other = register_user()
        other_ws = _create_workspace(
            client, other, "Other", f"other-{uuid.uuid4().hex[:8]}"
        )
        other_headers = _ws_headers(other, other_ws)
        # Other workspace cannot manage this widget via workspace API
        # (widget id is global; public bootstrap still works if entitled)
        sneak = client.get("/api/apps/chat-widget/widget", headers=other_headers)
        assert sneak.status_code in {402, 403, 404}

        # Public bootstrap without subscription on owning workspace still OK
        # until we disconnect — owning workspace is still entitled
        boot = client.get(f"/api/public/widgets/{widget['id']}/bootstrap")
        assert boot.status_code == 200

        app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "chat-widget"))
        assert app is not None

    def test_daily_session_message_quota(self, client, owner_ws, db, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("WIDGET_SESSION_MAX_MESSAGES_PER_DAY", "1")
        get_settings.cache_clear()
        try:
            user, ws = owner_ws
            headers = _ws_headers(user, ws)
            _subscribe_and_install(client, headers, db)
            expert = client.post(
                "/api/experts",
                headers=headers,
                json={"name": "Quota Expert"},
            )
            assert expert.status_code == 201, expert.text
            expert_id = expert.json()["id"]
            row = db.get(Expert, uuid.UUID(expert_id))
            assert row is not None
            row.status = ExpertStatus.READY.value
            db.commit()

            widget = client.get("/api/apps/chat-widget/widget", headers=headers).json()
            widget_id = widget["id"]
            client.put(
                "/api/apps/chat-widget/widget",
                headers=headers,
                json={"expert_id": expert_id, "allowed_origins": []},
            )

            patches = (
                patch(
                    "app.widgets.service.ChatTurnExecutor.execute",
                    return_value={"answer": "ok", "citations": [], "billed_tokens": 1},
                ),
                patch(
                    "app.widgets.service.ChatTurnExecutor.authorize_expert",
                    return_value=None,
                ),
                patch(
                    "app.widgets.service.MeteredWorkspaceGeneration.reserve",
                    return_value=None,
                ),
                patch(
                    "app.widgets.service.MeteredWorkspaceGeneration.settle",
                    return_value=None,
                ),
                patch(
                    "app.widgets.service.MeteredWorkspaceGeneration.release",
                    return_value=None,
                ),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                first = client.post(
                    f"/api/public/widgets/{widget_id}/messages",
                    headers={"Origin": "https://quota.test"},
                    json={"message": "one"},
                )
            assert first.status_code == 200, first.text
            session_id = first.json()["session_id"]

            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                second = client.post(
                    f"/api/public/widgets/{widget_id}/messages",
                    headers={"Origin": "https://quota.test"},
                    json={"message": "two", "session_id": session_id},
                )
            assert second.status_code == 429, second.text
        finally:
            monkeypatch.delenv("WIDGET_SESSION_MAX_MESSAGES_PER_DAY", raising=False)
            get_settings.cache_clear()
