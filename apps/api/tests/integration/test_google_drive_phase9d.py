"""Phase 9D — Google Drive connector integration tests (mocked Google HTTP)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest

from app.apps_catalog.seed import ensure_app_catalog
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection, ConnectorItem
from app.connectors.oauth_state import ConnectorOAuthStateService, clear_oauth_memory_store
from app.connectors.providers.google_drive import register_google_drive_connector
from app.connectors.providers.google_drive.adapter import GoogleDriveConnector
from app.connectors.registry import connector_registry
from app.connectors.service import ConnectorConnectionService
from app.connectors.sync import ConnectorSyncService
from app.connectors.types import ConnectionStatus
from app.core.config import get_settings
from app.core.errors import ErrorCategory
from app.experts.models import ExpertSource, ExpertSourceStatus, ExpertSourceType
from app.workspaces.models import Workspace
from tests.support.fake_google_drive import FakeGoogleDriveClient, patch_google_drive_client


@pytest.fixture(autouse=True)
def _reset_google_drive_settings_cache():
    """Prevent GOOGLE_DRIVE_* env from leaking via cached Settings across tests."""
    yield
    get_settings.cache_clear()
    # Ensure adapter reflects unset credentials for subsequent 9C tests.
    register_google_drive_connector()


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
        json={"name": "Drive", "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _seed(db: Session) -> None:
    ensure_app_catalog(db)
    db.commit()


def _enable_drive(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "test-drive-client-id")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "test-drive-client-secret")
    monkeypatch.setenv("GOOGLE_DRIVE_APP_ID", "123456789")
    get_settings.cache_clear()
    register_google_drive_connector()
    assert connector_registry.is_available("google_drive")


def _disable_drive(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
    get_settings.cache_clear()
    register_google_drive_connector()
    assert not connector_registry.is_available("google_drive")


def _install_and_connect(
    client, db, user, ws, *, fake: FakeGoogleDriveClient
) -> dict:
    assert (
        client.post(
            "/api/apps/google-drive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        "/api/apps/google-drive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/google-drive"},
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["authorization_url"]
    assert "accounts.google.com" in body["authorization_url"]

    # Complete OAuth via callback with stored state.
    clear_oauth_memory_store()
    # Re-start to get a fresh state bound to this connection.
    # Extract state from authorization_url is hard; create state + complete via service.
    svc = ConnectorConnectionService(db)
    row = db.get(AppConnection, uuid.UUID(body["id"]))
    assert row is not None
    result = fake.exchange_code(code="x", redirect_uri="http://localhost/cb")
    from app.connectors.providers.google_drive.token import apply_token_response

    creds = apply_token_response({}, result)
    creds["google_sub"] = fake.userinfo["sub"]
    creds["email"] = fake.userinfo["email"]
    svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=row.id,
        credentials=creds,
        actor_id=uuid.UUID(user["user"]["id"]),
        external_account_id=fake.userinfo["sub"],
        external_account_name=fake.userinfo["email"],
        display_name=fake.userinfo["email"],
    )
    db.commit()
    return body


def test_registry_unavailable_without_config(monkeypatch) -> None:
    _disable_drive(monkeypatch)
    assert connector_registry.has("google_drive")
    assert not connector_registry.is_available("google_drive")
    desc = connector_registry.describe("google_drive")
    assert desc is not None
    assert desc["available"] is False
    assert desc["unavailable_reason"] == ErrorCategory.GOOGLE_DRIVE_NOT_CONFIGURED.value


def test_catalog_available_when_configured(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    user = register_user(email="gd-meta@example.com")
    ws = _create_workspace(client, user, "gd-meta")
    res = client.get("/api/apps/google-drive", headers=_ws_headers(user, ws))
    assert res.status_code == 200
    assert res.json()["connector"]["available"] is True
    assert res.json()["connector"]["can_connect"] is True


def test_oauth_start_returns_authorization_url(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    user = register_user(email="gd-oauth@example.com")
    ws = _create_workspace(client, user, "gd-oauth")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    assert conn.status == ConnectionStatus.ACTIVE.value
    creds = ConnectorCredentialService(db).get_credentials(conn)
    assert creds is not None
    assert creds.get("access_token")
    assert creds.get("refresh_token")
    assert "access_token" not in body


def test_oauth_callback_roundtrip(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    user = register_user(email="gd-cb@example.com")
    ws = _create_workspace(client, user, "gd-cb")
    assert (
        client.post(
            "/api/apps/google-drive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        "/api/apps/google-drive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/google-drive"},
    ).json()
    # Pull state from OAuth store by creating a known state for the connection.
    clear_oauth_memory_store()
    oauth = ConnectorOAuthStateService(allow_memory_fallback=True)
    installation_id = uuid.UUID(started["app_installation_id"])
    payload = oauth.create(
        workspace_id=uuid.UUID(ws["id"]),
        actor_id=uuid.UUID(user["user"]["id"]),
        app_installation_id=installation_id,
        connector_key="google_drive",
        connection_id=uuid.UUID(started["id"]),
        return_path="/apps/google-drive",
        include_pkce=True,
    )
    res = client.get(
        f"/api/connectors/oauth/google_drive/callback"
        f"?code=auth-code&state={payload.state}",
        follow_redirects=False,
    )
    assert res.status_code in {302, 307}
    assert "oauth=success" in res.headers["location"]
    conn = db.get(AppConnection, uuid.UUID(started["id"]))
    assert conn is not None
    assert conn.status == ConnectionStatus.ACTIVE.value
    _ = fake


def test_picker_session_no_refresh_token(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    user = register_user(email="gd-picker@example.com")
    ws = _create_workspace(client, user, "gd-picker")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    res = client.post(
        f"/api/apps/google-drive/connections/{body['id']}/picker-session",
        headers=_ws_headers(user, ws),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["access_token"]
    assert "refresh_token" not in data
    assert data.get("app_id") == "123456789"


def test_add_connector_sources_and_sync(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    fake.add_file(
        "file-1",
        name="notes.txt",
        mime_type="text/plain",
        content=b"hello geem drive",
    )
    user = register_user(email="gd-src@example.com")
    ws = _create_workspace(client, user, "gd-src")
    body = _install_and_connect(client, db, user, ws, fake=fake)

    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Drive Expert"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
        "app.documents.service.MinioObjectStorage"
    ) as storage_cls, patch(
        "app.worker.tasks.enqueue_ingest", return_value="task-drive-1"
    ):
        storage = storage_cls.return_value

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage.ensure_bucket.return_value = None

        res = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [{"external_id": "file-1"}],
            },
        )
        assert res.status_code == 201, res.text
        payload = res.json()
        assert payload["status"] == "processing"
        assert payload["sync_run_id"]
        assert len(payload["sources"]) == 1
        assert payload["sources"][0]["type"] == ExpertSourceType.CONNECTOR.value

        # Pending connector sources must appear in knowledge list before Document exists.
        docs = client.get(
            f"/api/experts/{expert['id']}/documents",
            headers=_ws_headers(user, ws),
        )
        assert docs.status_code == 200, docs.text
        rows = docs.json()
        assert len(rows) == 1
        assert rows[0]["source_type"] == ExpertSourceType.CONNECTOR.value
        assert rows[0]["document_id"] is None
        assert rows[0]["status"] == "processing"
        assert rows[0]["title"]

        # Run sync inline (storage still mocked).
        sync = ConnectorSyncService(db)
        run = sync.execute_sync_run(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(body["id"]),
            sync_run_id=uuid.UUID(payload["sync_run_id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
        )
        db.commit()
        assert run.status in {"succeeded", "partial"}, (
            run.status,
            run.error_code,
            run.error_message,
        )
        assert run.items_created + run.items_updated >= 1

        conn = db.get(AppConnection, uuid.UUID(body["id"]))
        assert conn is not None
        state = ConnectorCredentialService(db).get_sync_state(conn)
        assert state and state.get("start_page_token")


def test_unsupported_mime_rejected(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    fake.add_file(
        "sheet-1",
        name="book.xlsx",
        mime_type="application/vnd.google-apps.spreadsheet",
        content=b"noop",
    )
    user = register_user(email="gd-mime@example.com")
    ws = _create_workspace(client, user, "gd-mime")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Mime"}
    ).json()
    res = client.post(
        f"/api/experts/{expert['id']}/connector-sources",
        headers=_ws_headers(user, ws),
        json={
            "connection_id": body["id"],
            "items": [{"external_id": "sheet-1"}],
        },
    )
    assert res.status_code == 422
    assert res.json()["error"] == "google_drive_file_type_unsupported"


def test_webhook_enqueues_sync(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    user = register_user(email="gd-wh@example.com")
    ws = _create_workspace(client, user, "gd-wh")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    cred_svc = ConnectorCredentialService(db)
    from app.common.crypto import decrypt_secret

    routing = decrypt_secret(conn.webhook_routing_token_encrypted)
    cred_svc.set_sync_state(
        conn,
        {
            "start_page_token": "t1",
            "watch_channel_id": "channel-1",
            "watch_resource_id": "resource-1",
            "watch_channel_token": "tok-1",
            "watch_expiration": str(
                int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp() * 1000)
            ),
        },
    )
    db.commit()

    with patch(
        "app.connectors.tasks.enqueue_connector_webhook_work"
    ) as enqueue_wh, patch(
        "app.connectors.tasks.enqueue_connector_sync"
    ):
        res = client.post(
            f"/api/connectors/webhooks/google_drive/{routing}",
            headers={
                "X-Goog-Channel-ID": "channel-1",
                "X-Goog-Channel-Token": "tok-1",
                "X-Goog-Resource-ID": "resource-1",
                "X-Goog-Resource-State": "change",
                "X-Goog-Message-Number": "42",
            },
            content=b"",
        )
        assert res.status_code == 200
        assert enqueue_wh.called

    # Process webhook task inline.
    from app.connectors.tasks import process_connector_webhook_event

    call_payload = enqueue_wh.call_args[0][0]
    with patch("app.connectors.tasks.enqueue_connector_sync") as enq:
        out = process_connector_webhook_event.run(call_payload)
    assert out["status"] == "processed"
    assert enq.called or out.get("sync_run_id") is None  # coalesce ok


def test_disconnect_marks_sources_unavailable(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    fake.add_file(
        "file-2",
        name="a.txt",
        mime_type="text/plain",
        content=b"content",
    )
    user = register_user(email="gd-disc@example.com")
    ws = _create_workspace(client, user, "gd-disc")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Disc"}
    ).json()
    with patch("app.connectors.tasks.enqueue_connector_sync"):
        add = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [{"external_id": "file-2"}],
            },
        )
    assert add.status_code == 201, add.text
    source_id = add.json()["sources"][0]["id"]

    res = client.delete(
        f"/api/apps/google-drive/connections/{body['id']}",
        headers=_ws_headers(user, ws),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "disconnected"
    source = db.get(ExpertSource, uuid.UUID(source_id))
    assert source is not None
    assert source.status == ExpertSourceStatus.UNAVAILABLE.value


def test_disconnect_reconnect_readd_revives_source(
    client, register_user, db, monkeypatch
) -> None:
    """P1: after disconnect, re-picking the same file must re-queue ingest."""
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    fake.add_file(
        "file-revive",
        name="revive.txt",
        mime_type="text/plain",
        content=b"revive me",
    )
    user = register_user(email="gd-revive@example.com")
    ws = _create_workspace(client, user, "gd-revive")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Revive"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"):
        add = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [{"external_id": "file-revive"}],
            },
        )
    assert add.status_code == 201, add.text
    source_id = add.json()["sources"][0]["id"]
    sync_run_id = add.json()["sync_run_id"]

    with patch("app.documents.service.MinioObjectStorage") as storage_cls, patch(
        "app.worker.tasks.enqueue_ingest", return_value="task-revive-1"
    ):
        storage = storage_cls.return_value

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage.ensure_bucket.return_value = None
        run = ConnectorSyncService(db).execute_sync_run(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(body["id"]),
            sync_run_id=uuid.UUID(sync_run_id),
            actor_id=uuid.UUID(user["user"]["id"]),
        )
        db.commit()
    assert run.status in {"succeeded", "partial"}, (run.status, run.error_message)

    item = db.execute(
        select(ConnectorItem).where(
            ConnectorItem.app_connection_id == uuid.UUID(body["id"]),
            ConnectorItem.external_id == "file-revive",
        )
    ).scalar_one()
    assert item.current_document_id is not None

    assert (
        client.delete(
            f"/api/apps/google-drive/connections/{body['id']}",
            headers=_ws_headers(user, ws),
        ).status_code
        == 200
    )
    db.refresh(item)
    assert item.current_document_id is None
    source = db.get(ExpertSource, uuid.UUID(source_id))
    assert source is not None
    assert source.status == ExpertSourceStatus.UNAVAILABLE.value

    # Reconnect — authorization URL must request consent (refresh token).
    reconnect = client.post(
        "/api/apps/google-drive/connections",
        headers=_ws_headers(user, ws),
        json={"connection_id": body["id"], "return_path": "/apps/google-drive"},
    )
    assert reconnect.status_code == 201, reconnect.text
    assert "prompt=consent" in reconnect.json()["authorization_url"]
    assert "select_account" in reconnect.json()["authorization_url"]

    auth = GoogleDriveConnector().build_authorization_request(
        state="s",
        redirect_uri="http://localhost/cb",
        reconnect=True,
    )
    assert "prompt=consent" in auth.authorization_url
    assert "select_account" in auth.authorization_url

    # Simulate OAuth complete again.
    svc = ConnectorConnectionService(db)
    row = db.get(AppConnection, uuid.UUID(body["id"]))
    assert row is not None
    result = fake.exchange_code(code="reconnect", redirect_uri="http://localhost/cb")
    from app.connectors.providers.google_drive.token import apply_token_response

    creds = apply_token_response({}, result)
    creds["google_sub"] = fake.userinfo["sub"]
    creds["email"] = fake.userinfo["email"]
    svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=row.id,
        credentials=creds,
        actor_id=uuid.UUID(user["user"]["id"]),
        external_account_id=fake.userinfo["sub"],
        external_account_name=fake.userinfo["email"],
        display_name=fake.userinfo["email"],
    )
    db.commit()

    with patch("app.connectors.tasks.enqueue_connector_sync"):
        readd = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [{"external_id": "file-revive"}],
            },
        )
    assert readd.status_code == 201, readd.text
    revived = readd.json()["sources"][0]
    assert revived["id"] == source_id
    assert revived["status"] == ExpertSourceStatus.PROCESSING.value
    assert readd.json()["sync_run_id"]


def test_oauth_callback_redirects_to_spa_not_api(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    monkeypatch.setenv("WORKSPACE_WEB_URL", "http://app.geem.dm:5174")
    monkeypatch.setenv("APP_URL", "http://api.geem.dm:8000")
    get_settings.cache_clear()
    register_google_drive_connector()

    user = register_user(email="gd-spa@example.com")
    ws = _create_workspace(client, user, "gd-spa")
    assert (
        client.post(
            "/api/apps/google-drive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        "/api/apps/google-drive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/google-drive"},
    ).json()
    clear_oauth_memory_store()
    oauth = ConnectorOAuthStateService(allow_memory_fallback=True)
    payload = oauth.create(
        workspace_id=uuid.UUID(ws["id"]),
        actor_id=uuid.UUID(user["user"]["id"]),
        app_installation_id=uuid.UUID(started["app_installation_id"]),
        connector_key="google_drive",
        connection_id=uuid.UUID(started["id"]),
        return_path="/apps/google-drive",
        include_pkce=True,
    )
    res = client.get(
        f"/api/connectors/oauth/google_drive/callback"
        f"?code=auth-code&state={payload.state}",
        follow_redirects=False,
    )
    assert res.status_code in {302, 307}
    location = res.headers["location"]
    assert location.startswith("http://app.geem.dm:5174/apps/google-drive")
    assert "oauth=success" in location
    assert not location.startswith("http://api.geem.dm:8000")
    _ = fake


def test_workspace_isolation_connection(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_drive(monkeypatch)
    fake = patch_google_drive_client(monkeypatch)
    a = register_user(email="gd-iso-a@example.com")
    b = register_user(email="gd-iso-b@example.com")
    ws_a = _create_workspace(client, a, "gd-iso-a")
    ws_b = _create_workspace(client, b, "gd-iso-b")
    body = _install_and_connect(client, db, a, ws_a, fake=fake)
    leak = client.get(
        f"/api/apps/google-drive/connections/{body['id']}",
        headers=_ws_headers(b, ws_b),
    )
    assert leak.status_code == 404
