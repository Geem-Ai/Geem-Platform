"""Phase 9F — OpenWA / WhatsApp integration tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.models import (
    AppBillingType,
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
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.seed import ensure_app_catalog
from app.common.crypto import decrypt_secret
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import (
    AppConnection,
    ChannelConversationBinding,
    ConnectorWebhookEvent,
)
from app.connectors.providers.openwa import register_openwa_connector
from app.connectors.providers.openwa.channel import OpenWAChannelProcessor
from app.connectors.providers.openwa.errors import OpenWAClientError
from app.connectors.providers.openwa.schemas import (
    OPENWA_WEBHOOK_EVENTS,
    OpenWAPairingCodeResponse,
    OpenWAQrResponse,
    OpenWASendTextResponse,
    OpenWASession,
    OpenWAWebhook,
)
from app.connectors.providers.openwa.service import OpenWAChannelService
from app.connectors.registry import connector_registry
from app.connectors.webhooks import ConnectorWebhookDispatcher
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.conversations.models import Conversation, ConversationSource
from app.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _create_workspace(client: TestClient, user: dict, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": "OpenWA", "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_member(db: Session, workspace_id: str, user_id: str, role: WorkspaceRole) -> None:
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id),
            role=role.value,
        )
    )
    db.commit()


def _seed(db: Session) -> None:
    ensure_app_catalog(db)
    db.commit()


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


class FakeOpenWAClient:
    sessions: dict[str, dict] = {}
    webhooks: dict[str, dict[str, dict]] = {}
    sent_messages: list[dict] = []
    deleted_sessions: list[str] = []

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> "FakeOpenWAClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    @classmethod
    def reset(cls) -> None:
        cls.sessions = {}
        cls.webhooks = {}
        cls.sent_messages = []
        cls.deleted_sessions = []

    def create_session(self, *, name: str) -> OpenWASession:
        session_id = f"sess-{len(self.sessions) + 1}"
        self.sessions[session_id] = {
            "id": session_id,
            "name": name,
            "status": "created",
            "engineLoaded": False,
            "phone": None,
            "pushName": None,
            "lastError": None,
        }
        return OpenWASession.model_validate(self.sessions[session_id])

    def get_session(self, session_id: str) -> OpenWASession:
        data = self.sessions.get(session_id)
        if data is None:
            raise OpenWAClientError(
                ErrorCategory.OPENWA_SESSION_NOT_FOUND,
                "Session not found.",
            )
        return OpenWASession.model_validate(data)

    def start_session(self, session_id: str) -> OpenWASession:
        data = self.sessions[session_id]
        data["status"] = "qr_ready"
        data["engineLoaded"] = True
        return OpenWASession.model_validate(data)

    def get_qr(self, session_id: str) -> OpenWAQrResponse:
        _ = session_id
        return OpenWAQrResponse(
            status="qr_ready",
            qrCode="data:image/png;base64,qr",
        )

    def request_pairing_code(
        self,
        session_id: str,
        *,
        phone_number: str,
    ) -> OpenWAPairingCodeResponse:
        data = self.sessions[session_id]
        data["phone"] = phone_number
        return OpenWAPairingCodeResponse(
            status="qr_ready",
            pairingCode="ABCD1234",
        )

    def list_webhooks(self, session_id: str) -> list[OpenWAWebhook]:
        rows = self.webhooks.get(session_id, {})
        return [OpenWAWebhook.model_validate(item) for item in rows.values()]

    def register_webhook(
        self,
        session_id: str,
        *,
        url: str,
        secret: str,
        events: list[str] | None = None,
    ) -> OpenWAWebhook:
        webhook_id = f"wh-{len(self.webhooks.get(session_id, {})) + 1}"
        item = {
            "id": webhook_id,
            "sessionId": session_id,
            "url": url,
            "events": list(events or OPENWA_WEBHOOK_EVENTS),
            "active": True,
            "retryCount": 3,
        }
        self.webhooks.setdefault(session_id, {})[webhook_id] = item
        _ = secret
        return OpenWAWebhook.model_validate(item)

    def update_webhook(
        self,
        session_id: str,
        webhook_id: str,
        *,
        url: str | None = None,
        secret: str | None = None,
        events: list[str] | None = None,
        active: bool | None = None,
    ) -> OpenWAWebhook:
        item = dict(self.webhooks[session_id][webhook_id])
        if url is not None:
            item["url"] = url
        if events is not None:
            item["events"] = list(events)
        if active is not None:
            item["active"] = active
        self.webhooks[session_id][webhook_id] = item
        _ = secret
        return OpenWAWebhook.model_validate(item)

    def delete_webhook(self, session_id: str, webhook_id: str) -> None:
        self.webhooks.get(session_id, {}).pop(webhook_id, None)

    def logout_session(self, session_id: str) -> OpenWASession | None:
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "disconnected"
            return OpenWASession.model_validate(self.sessions[session_id])
        return None

    def delete_session(self, session_id: str) -> None:
        self.deleted_sessions.append(session_id)
        self.sessions.pop(session_id, None)
        self.webhooks.pop(session_id, None)

    def send_text(
        self,
        session_id: str,
        *,
        chat_id: str,
        text: str,
        link_preview: bool = False,
    ) -> OpenWASendTextResponse:
        self.sent_messages.append(
            {
                "session_id": session_id,
                "chat_id": chat_id,
                "text": text,
                "link_preview": link_preview,
            }
        )
        return OpenWASendTextResponse(messageId=f"msg-{len(self.sent_messages)}", timestamp=1)


class FakeExecutor:
    def __init__(self, db: Session, settings=None) -> None:  # noqa: ANN001
        _ = db, settings

    def execute(self, *, expert_id: uuid.UUID, question: str, **_: object) -> dict:
        return {
            "answer": f"reply:{expert_id}:{question}",
            "citations": [],
        }


class FakeMeter:
    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = args, kwargs

    def reserve(self) -> None:
        return None

    def release(self) -> None:
        return None


class FakeLock:
    def acquire(self, lock_id: uuid.UUID) -> bool:
        _ = lock_id
        return True

    def release(self, lock_id: uuid.UUID) -> None:
        _ = lock_id


@pytest.fixture(autouse=True)
def _reset_openwa(monkeypatch):
    FakeOpenWAClient.reset()
    monkeypatch.setenv("OPENWA_API_KEY", "test-openwa-key")
    monkeypatch.setenv("OPENWA_BASE_URL", "https://openwa.example.test")
    monkeypatch.setenv("APP_URL", "https://api.example.test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.connectors.providers.openwa.service.OpenWAClient",
        FakeOpenWAClient,
    )
    monkeypatch.setattr(
        "app.connectors.providers.openwa.channel.OpenWAClient",
        FakeOpenWAClient,
    )
    monkeypatch.setattr(
        "app.connectors.providers.openwa.adapter.OpenWAClient",
        FakeOpenWAClient,
    )
    register_openwa_connector(client_factory=FakeOpenWAClient)
    yield
    get_settings.cache_clear()
    register_openwa_connector()


def _publish_whatsapp_for_test(
    db: Session,
    *,
    connections_limit: int = 1,
) -> tuple[CatalogApp, AppPlan]:
    repo = AppCatalogRepository(db)
    app = repo.get_app_by_slug("whatsapp")
    assert app is not None
    app.billing_type = AppBillingType.SUBSCRIPTION.value
    app.status = AppStatus.PUBLISHED.value
    repo.upsert_app(app)
    plan = AppPlan(
        app_id=app.id,
        code=f"test-monthly-{uuid.uuid4().hex[:8]}",
        name="Test Monthly",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=9,
        currency="SAR",
        is_default=True,
        is_active=True,
        extra={"test": True},
    )
    repo.upsert_plan(plan)
    repo.upsert_entitlement(
        AppPlanEntitlement(app_plan_id=plan.id, key="connections", value=connections_limit)
    )
    db.commit()
    db.refresh(app)
    return app, plan


def _grant_whatsapp_access(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    app: CatalogApp,
    plan: AppPlan,
    actor_id: uuid.UUID,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        AppInstallation(
            workspace_id=workspace_id,
            app_id=app.id,
            status=AppInstallationStatus.ACTIVE.value,
            installed_by_user_id=actor_id,
        )
    )
    db.add(
        AppSubscription(
            workspace_id=workspace_id,
            app_id=app.id,
            app_plan_id=plan.id,
            status=AppSubscriptionStatus.ACTIVE.value,
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=30),
        )
    )
    db.commit()


def _connection_row(db: Session, connection_id: str) -> AppConnection:
    row = db.get(AppConnection, uuid.UUID(connection_id))
    assert row is not None
    return row


def _mark_connection_ready(
    db: Session,
    *,
    workspace_id: str,
    connection_id: str,
) -> AppConnection:
    row = _connection_row(db, connection_id)
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    session_id = str(creds["session_id"])
    FakeOpenWAClient.sessions[session_id]["status"] = "ready"
    FakeOpenWAClient.sessions[session_id]["phone"] = "966500000000"
    FakeOpenWAClient.sessions[session_id]["pushName"] = "Sales Line"
    workspace = db.get(Workspace, uuid.UUID(workspace_id))
    assert workspace is not None
    OpenWAChannelService(db, client_factory=FakeOpenWAClient).get_session_status(
        workspace,
        WorkspaceRole.OWNER.value,
        app_slug="whatsapp",
        connection_id=uuid.UUID(connection_id),
    )
    db.commit()
    return _connection_row(db, connection_id)


def _token_and_secret(db: Session, row: AppConnection) -> tuple[str, str]:
    token = decrypt_secret(
        row.webhook_routing_token_encrypted,
        settings=get_settings(),
    )
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    secret = str(creds.get("webhook_secret") or "")
    return token, secret


def _message_event(
    *,
    session_id: str,
    message_id: str,
    chat_id: str,
    body: str,
    from_me: bool = False,
    is_group: bool = False,
) -> bytes:
    return json.dumps(
        {
            "event": "message.received",
            "sessionId": session_id,
            "data": {
                "id": message_id,
                "from": "966500000001@c.us",
                "chatId": chat_id,
                "body": body,
                "type": "chat",
                "timestamp": 1723900000,
                "fromMe": from_me,
                "isGroup": is_group,
                "hasMedia": False,
            },
        }
    ).encode("utf-8")


def _processor(monkeypatch, db: Session) -> OpenWAChannelProcessor:
    monkeypatch.setattr(
        "app.connectors.providers.openwa.channel.ChatTurnExecutor",
        FakeExecutor,
    )
    monkeypatch.setattr(
        "app.connectors.providers.openwa.channel.MeteredWorkspaceGeneration",
        FakeMeter,
    )
    monkeypatch.setattr(
        "app.connectors.providers.openwa.channel.ConversationGenerationLock",
        lambda settings=None: FakeLock(),
    )
    return OpenWAChannelProcessor(db, client_factory=FakeOpenWAClient)


def test_openwa_registry_and_access_gates(client, register_user, db, monkeypatch) -> None:
    _ = monkeypatch
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    assert connector_registry.has("openwa")
    assert connector_registry.is_available("openwa")
    assert connector_registry.describe("openwa")["available"] is True

    owner = register_user(email="openwa-owner@example.com")
    member = register_user(email="openwa-member@example.com")
    ws = _create_workspace(client, owner, "openwa-gates")
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    denied = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(member, ws),
        json={"connect_mode": "qr"},
    )
    assert denied.status_code == 403

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["connector_key"] == "openwa"
    assert body["connect_mode"] == "qr"
    assert body["provider_status"] == "qr_ready"

    status = client.get(
        f"/api/apps/whatsapp/connections/{body['id']}/openwa/status",
        headers=_ws_headers(member, ws),
    )
    assert status.status_code == 200, status.text

    qr = client.get(
        f"/api/apps/whatsapp/connections/{body['id']}/openwa/qr",
        headers=_ws_headers(owner, ws),
    )
    assert qr.status_code == 200, qr.text
    assert qr.json()["qr_code"].startswith("data:image/png")


def test_openwa_expert_binding_and_disconnect_fail_closed(
    client, register_user, db
) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-bind@example.com")
    ws = _create_workspace(client, owner, "openwa-bind")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    )
    assert started.status_code == 201, started.text
    conn_id = started.json()["id"]

    expert = client.post(
        "/api/experts",
        headers=_ws_headers(owner, ws),
        json={"name": "WhatsApp Expert"},
    )
    assert expert.status_code == 201, expert.text

    bound = client.patch(
        f"/api/apps/whatsapp/connections/{conn_id}/channel-settings",
        headers=_ws_headers(owner, ws),
        json={
            "expert_id": expert.json()["id"],
            "auto_reply_enabled": True,
            "respond_to_groups": True,
            "enabled": True,
        },
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["expert_id"] == expert.json()["id"]
    assert bound.json()["respond_to_groups"] is True

    row = _connection_row(db, conn_id)
    token, _secret = _token_and_secret(db, row)

    disconnected = client.delete(
        f"/api/apps/whatsapp/connections/{conn_id}",
        headers=_ws_headers(owner, ws),
    )
    assert disconnected.status_code == 200, disconnected.text
    assert disconnected.json()["status"] == "disconnected"
    db.refresh(row)
    assert row.credentials_encrypted is None
    assert row.sync_state_encrypted is None
    assert FakeOpenWAClient.deleted_sessions

    dispatcher = ConnectorWebhookDispatcher(db, enqueue_fn=lambda payload: payload)
    with pytest.raises(AppError) as excinfo:
        dispatcher.dispatch(
            connector_key="openwa",
            routing_token=token,
            raw_body=b'{"event":"message.received"}',
            headers={},
            query_params={},
        )
    assert excinfo.value.category in {
        ErrorCategory.CONNECTOR_WEBHOOK_INVALID,
        ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED,
    }

    FakeOpenWAClient.reset()
    deleted = client.delete(
        f"/api/apps/whatsapp/connections/{conn_id}/permanent",
        headers=_ws_headers(owner, ws),
    )
    assert deleted.status_code == 204, deleted.text
    db.expire_all()
    assert db.get(AppConnection, uuid.UUID(conn_id)) is None

    listed = client.get(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0


def test_openwa_permanent_delete_rejects_active_connection(
    client, register_user, db
) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-delete-active@example.com")
    ws = _create_workspace(client, owner, "openwa-del-active")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    )
    assert started.status_code == 201, started.text
    conn_id = started.json()["id"]

    rejected = client.delete(
        f"/api/apps/whatsapp/connections/{conn_id}/permanent",
        headers=_ws_headers(owner, ws),
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"] == ErrorCategory.CONNECTOR_INVALID_TRANSITION.value
    assert _connection_row(db, conn_id) is not None


def test_openwa_permanent_delete_removes_openwa_session(
    client, register_user, db
) -> None:
    """Disconnected row with leftover session_id must delete OpenWA then Geem."""
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-delete-session@example.com")
    ws = _create_workspace(client, owner, "openwa-del-sess")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    )
    assert started.status_code == 201, started.text
    conn_id = started.json()["id"]
    row = _connection_row(db, conn_id)
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    session_id = str(creds["session_id"])

    from app.connectors.types import ConnectionStatus

    row.status = ConnectionStatus.DISCONNECTED.value
    row.disconnected_at = datetime.now(timezone.utc)
    db.commit()

    FakeOpenWAClient.deleted_sessions = []
    deleted = client.delete(
        f"/api/apps/whatsapp/connections/{conn_id}/permanent",
        headers=_ws_headers(owner, ws),
    )
    assert deleted.status_code == 204, deleted.text
    assert session_id in FakeOpenWAClient.deleted_sessions
    db.expire_all()
    assert db.get(AppConnection, uuid.UUID(conn_id)) is None


def test_openwa_webhook_hmac_idempotency_groups_and_outbound_send(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-webhook@example.com")
    ws = _create_workspace(client, owner, "openwa-webhook")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "pairing"},
    )
    assert started.status_code == 201, started.text
    conn_id = started.json()["id"]
    row = _mark_connection_ready(db, workspace_id=ws["id"], connection_id=conn_id)

    expert = client.post(
        "/api/experts",
        headers=_ws_headers(owner, ws),
        json={"name": "Channel Expert"},
    ).json()
    client.patch(
        f"/api/apps/whatsapp/connections/{conn_id}/channel-settings",
        headers=_ws_headers(owner, ws),
        json={
            "expert_id": expert["id"],
            "auto_reply_enabled": True,
            "respond_to_groups": False,
            "enabled": True,
        },
    )

    token, secret = _token_and_secret(db, row)
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    session_id = str(creds["session_id"])
    body = _message_event(
        session_id=session_id,
        message_id="msg-provider-1",
        chat_id="966500000001@c.us",
        body="مرحبا",
    )
    dispatcher = ConnectorWebhookDispatcher(db, enqueue_fn=lambda payload: queued.append(payload))
    queued: list[dict] = []

    with pytest.raises(AppError) as excinfo:
        dispatcher.dispatch(
            connector_key="openwa",
            routing_token=token,
            raw_body=body,
            headers={"x-openwa-signature": "sha256=bad"},
            query_params={},
        )
    assert excinfo.value.category == ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED

    status, _resp, _headers = dispatcher.dispatch(
        connector_key="openwa",
        routing_token=token,
        raw_body=body,
        headers={
            "x-openwa-signature": _signature(secret, body),
            "x-openwa-idempotency-key": "evt-1",
            "x-openwa-delivery-id": "delivery-1",
        },
        query_params={},
    )
    assert status == 200
    assert len(queued) == 1

    result = _processor(monkeypatch, db).process_adapter_payload(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(conn_id),
        payload=queued[0]["adapter_payload"],
    )
    assert result["status"] == "processed"
    assert len(FakeOpenWAClient.sent_messages) == 1
    assert FakeOpenWAClient.sent_messages[0]["chat_id"] == "966500000001@c.us"

    status2, _resp2, _headers2 = dispatcher.dispatch(
        connector_key="openwa",
        routing_token=token,
        raw_body=body,
        headers={
            "x-openwa-signature": _signature(secret, body),
            "x-openwa-idempotency-key": "evt-1",
            "x-openwa-delivery-id": "delivery-1",
        },
        query_params={},
    )
    assert status2 == 200
    assert len(queued) == 1
    assert db.query(ConnectorWebhookEvent).count() == 1
    assert len(FakeOpenWAClient.sent_messages) == 1

    from_me_body = _message_event(
        session_id=session_id,
        message_id="msg-provider-2",
        chat_id="966500000001@c.us",
        body="outbound echo",
        from_me=True,
    )
    status3, _resp3, _headers3 = dispatcher.dispatch(
        connector_key="openwa",
        routing_token=token,
        raw_body=from_me_body,
        headers={"x-openwa-signature": _signature(secret, from_me_body)},
        query_params={},
    )
    assert status3 == 200
    assert len(queued) == 1

    group_body = _message_event(
        session_id=session_id,
        message_id="msg-provider-3",
        chat_id="team@g.us",
        body="مرحبا يا فريق",
        is_group=True,
    )
    status4, _resp4, _headers4 = dispatcher.dispatch(
        connector_key="openwa",
        routing_token=token,
        raw_body=group_body,
        headers={
            "x-openwa-signature": _signature(secret, group_body),
            "x-openwa-idempotency-key": "evt-group",
        },
        query_params={},
    )
    assert status4 == 200
    assert len(queued) == 2
    ignored = _processor(monkeypatch, db).process_adapter_payload(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(conn_id),
        payload=queued[1]["adapter_payload"],
    )
    assert ignored == {"status": "ignored", "reason": "group_disabled"}


def test_openwa_channel_conversation_isolation(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db, connections_limit=2)
    owner = register_user(email="openwa-isolation@example.com")
    ws = _create_workspace(client, owner, "openwa-isolation")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    expert_a = client.post(
        "/api/experts",
        headers=_ws_headers(owner, ws),
        json={"name": "Expert A"},
    ).json()
    expert_b = client.post(
        "/api/experts",
        headers=_ws_headers(owner, ws),
        json={"name": "Expert B"},
    ).json()

    first = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    ).json()
    second = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "pairing"},
    ).json()

    row_a = _mark_connection_ready(db, workspace_id=ws["id"], connection_id=first["id"])
    row_b = _mark_connection_ready(db, workspace_id=ws["id"], connection_id=second["id"])

    client.patch(
        f"/api/apps/whatsapp/connections/{first['id']}/channel-settings",
        headers=_ws_headers(owner, ws),
        json={"expert_id": expert_a["id"], "enabled": True, "auto_reply_enabled": True},
    )
    client.patch(
        f"/api/apps/whatsapp/connections/{second['id']}/channel-settings",
        headers=_ws_headers(owner, ws),
        json={"expert_id": expert_b["id"], "enabled": True, "auto_reply_enabled": True},
    )

    processor = _processor(monkeypatch, db)
    processor.process_adapter_payload(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=row_a.id,
        payload={
            "kind": "openwa_message_received",
            "provider_message_id": "m-a",
            "external_chat_id": "shared-chat@c.us",
            "sender_id": "966500000001@c.us",
            "body": "message a",
            "message_type": "chat",
            "provider_timestamp": 1,
            "is_group": False,
            "has_media": False,
            "chat_kind": "chat",
        },
    )
    processor.process_adapter_payload(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=row_b.id,
        payload={
            "kind": "openwa_message_received",
            "provider_message_id": "m-b",
            "external_chat_id": "shared-chat@c.us",
            "sender_id": "966500000001@c.us",
            "body": "message b",
            "message_type": "chat",
            "provider_timestamp": 2,
            "is_group": False,
            "has_media": False,
            "chat_kind": "chat",
        },
    )

    bindings = db.scalars(
        select(ChannelConversationBinding).where(
            ChannelConversationBinding.workspace_id == uuid.UUID(ws["id"])
        )
    ).all()
    assert len(bindings) == 2
    assert {str(item.app_connection_id) for item in bindings} == {first["id"], second["id"]}
    assert len({str(item.conversation_id) for item in bindings}) == 2

    conversations = db.scalars(
        select(Conversation).where(Conversation.workspace_id == uuid.UUID(ws["id"]))
    ).all()
    assert len(conversations) == 2
    assert all(conv.source == ConversationSource.CHANNEL.value for conv in conversations)


def test_openwa_webhook_revoked_when_subscription_expired(
    client, register_user, db
) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-expired-wh@example.com")
    ws = _create_workspace(client, owner, "openwa-expired-wh")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    )
    assert started.status_code == 201, started.text
    conn_id = started.json()["id"]
    row = _mark_connection_ready(db, workspace_id=ws["id"], connection_id=conn_id)
    token, secret = _token_and_secret(db, row)
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    session_id = str(creds["session_id"])
    sync_state = ConnectorCredentialService(db).get_sync_state(row) or {}
    webhook_id = str(sync_state.get("webhook_id") or "")
    assert webhook_id
    assert webhook_id in FakeOpenWAClient.webhooks.get(session_id, {})

    sub = db.scalar(
        select(AppSubscription).where(
            AppSubscription.workspace_id == uuid.UUID(ws["id"]),
            AppSubscription.app_id == app.id,
        )
    )
    assert sub is not None
    sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    body = _message_event(
        session_id=session_id,
        message_id="msg-expired-1",
        chat_id="966500000001@c.us",
        body="still arriving",
    )
    dispatcher = ConnectorWebhookDispatcher(db, enqueue_fn=lambda payload: None)
    with pytest.raises(AppError) as excinfo:
        dispatcher.dispatch(
            connector_key="openwa",
            routing_token=token,
            raw_body=body,
            headers={
                "x-openwa-signature": _signature(secret, body),
                "x-openwa-idempotency-key": "evt-expired",
            },
            query_params={},
        )
    assert excinfo.value.category == ErrorCategory.APP_SUBSCRIPTION_EXPIRED
    assert webhook_id not in FakeOpenWAClient.webhooks.get(session_id, {})
    db.refresh(row)
    sync_after = ConnectorCredentialService(db).get_sync_state(row) or {}
    assert "webhook_id" not in sync_after


def test_openwa_webhook_not_revoked_on_bad_signature_when_expired(
    client, register_user, db
) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-expired-bad-sig@example.com")
    ws = _create_workspace(client, owner, "openwa-expired-bad-sig")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    ).json()
    row = _mark_connection_ready(db, workspace_id=ws["id"], connection_id=started["id"])
    token, _secret = _token_and_secret(db, row)
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    session_id = str(creds["session_id"])
    sync_state = ConnectorCredentialService(db).get_sync_state(row) or {}
    webhook_id = str(sync_state.get("webhook_id") or "")
    assert webhook_id in FakeOpenWAClient.webhooks.get(session_id, {})

    sub = db.scalar(
        select(AppSubscription).where(
            AppSubscription.workspace_id == uuid.UUID(ws["id"]),
            AppSubscription.app_id == app.id,
        )
    )
    assert sub is not None
    sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    body = _message_event(
        session_id=session_id,
        message_id="msg-bad-sig",
        chat_id="966500000001@c.us",
        body="forged",
    )
    dispatcher = ConnectorWebhookDispatcher(db, enqueue_fn=lambda payload: None)
    with pytest.raises(AppError) as excinfo:
        dispatcher.dispatch(
            connector_key="openwa",
            routing_token=token,
            raw_body=body,
            headers={"x-openwa-signature": "sha256=deadbeef"},
            query_params={},
        )
    assert excinfo.value.category == ErrorCategory.APP_SUBSCRIPTION_EXPIRED
    assert webhook_id in FakeOpenWAClient.webhooks.get(session_id, {})


def test_openwa_reinstall_reregisters_webhook_for_ready_session(
    client, register_user, db
) -> None:
    _seed(db)
    app, plan = _publish_whatsapp_for_test(db)
    owner = register_user(email="openwa-reinstall-wh@example.com")
    ws = _create_workspace(client, owner, "openwa-reinstall-wh")
    _grant_whatsapp_access(
        db,
        workspace_id=uuid.UUID(ws["id"]),
        app=app,
        plan=plan,
        actor_id=uuid.UUID(owner["user"]["id"]),
    )

    started = client.post(
        "/api/apps/whatsapp/connections",
        headers=_ws_headers(owner, ws),
        json={"connect_mode": "qr"},
    ).json()
    row = _mark_connection_ready(db, workspace_id=ws["id"], connection_id=started["id"])
    creds = ConnectorCredentialService(db).get_credentials(row) or {}
    session_id = str(creds["session_id"])
    sync_state = ConnectorCredentialService(db).get_sync_state(row) or {}
    webhook_id = str(sync_state.get("webhook_id") or "")
    assert webhook_id

    uninstalled = client.delete(
        "/api/apps/whatsapp/install",
        headers=_ws_headers(owner, ws),
    )
    assert uninstalled.status_code == 200, uninstalled.text
    assert webhook_id not in FakeOpenWAClient.webhooks.get(session_id, {})
    db.refresh(row)
    assert "webhook_id" not in (ConnectorCredentialService(db).get_sync_state(row) or {})

    reinstalled = client.post(
        "/api/apps/whatsapp/install",
        headers=_ws_headers(owner, ws),
    )
    assert reinstalled.status_code == 201, reinstalled.text
    db.refresh(row)
    sync_after = ConnectorCredentialService(db).get_sync_state(row) or {}
    new_webhook_id = str(sync_after.get("webhook_id") or "")
    assert new_webhook_id
    assert new_webhook_id in FakeOpenWAClient.webhooks.get(session_id, {})
