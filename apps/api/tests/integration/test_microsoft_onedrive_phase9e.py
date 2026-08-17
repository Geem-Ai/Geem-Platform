"""Phase 9E — Microsoft OneDrive connector integration tests (mocked Graph)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.apps_catalog.seed import ensure_app_catalog
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection, ConnectorItem
from app.connectors.oauth_state import ConnectorOAuthStateService, clear_oauth_memory_store
from app.connectors.providers.google_drive import register_google_drive_connector
from app.connectors.providers.microsoft_onedrive import (
    register_microsoft_onedrive_connector,
)
from app.connectors.providers.microsoft_onedrive.scopes import ONEDRIVE_SCOPES
from app.connectors.providers.microsoft_onedrive.token import apply_token_response
from app.connectors.registry import connector_registry
from app.connectors.service import ConnectorConnectionService
from app.connectors.sync import ConnectorSyncService
from app.connectors.types import ConnectionStatus
from app.core.config import get_settings
from app.core.errors import ErrorCategory
from app.experts.models import ExpertSourceType
from tests.support.fake_google_drive import FakeGoogleDriveClient, patch_google_drive_client
from tests.support.fake_microsoft_onedrive import (
    FakeMicrosoftOneDriveClient,
    patch_microsoft_onedrive_client,
)

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
    b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
    b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
)


def _put_storage(**kw):
    from app.storage.document_keys import resolve_document_storage_key

    return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))


@pytest.fixture(autouse=True)
def _reset_onedrive_settings_cache():
    yield
    get_settings.cache_clear()
    register_microsoft_onedrive_connector()
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
        json={"name": "OneDrive", "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _seed(db: Session) -> None:
    ensure_app_catalog(db)
    db.commit()


def _enable_onedrive(monkeypatch) -> None:
    monkeypatch.setenv("MICROSOFT_ONEDRIVE_CLIENT_ID", "test-ms-client-id")
    monkeypatch.setenv("MICROSOFT_ONEDRIVE_CLIENT_SECRET", "test-ms-client-secret")
    monkeypatch.setenv("MICROSOFT_ONEDRIVE_TENANT", "organizations")
    get_settings.cache_clear()
    register_microsoft_onedrive_connector()
    assert connector_registry.is_available("microsoft_onedrive")


def _disable_onedrive(monkeypatch) -> None:
    monkeypatch.setenv("MICROSOFT_ONEDRIVE_CLIENT_ID", "")
    monkeypatch.setenv("MICROSOFT_ONEDRIVE_CLIENT_SECRET", "")
    get_settings.cache_clear()
    register_microsoft_onedrive_connector()
    assert not connector_registry.is_available("microsoft_onedrive")


def _install_and_connect(
    client, db, user, ws, *, fake: FakeMicrosoftOneDriveClient
) -> dict:
    assert (
        client.post(
            "/api/apps/microsoft-onedrive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        "/api/apps/microsoft-onedrive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/microsoft-onedrive"},
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["authorization_url"]
    assert "login.microsoftonline.com" in body["authorization_url"]
    parsed = urlparse(body["authorization_url"])
    qs = parse_qs(parsed.query)
    scopes = set((qs.get("scope") or [""])[0].split())
    assert "Files.Read" in scopes
    assert "offline_access" in scopes
    for forbidden in (
        "Files.ReadWrite",
        "Files.Read.All",
        "Sites.Read.All",
    ):
        assert forbidden not in scopes

    svc = ConnectorConnectionService(db)
    row = db.get(AppConnection, uuid.UUID(body["id"]))
    assert row is not None
    result = fake.exchange_code(code="x", redirect_uri="http://localhost/cb")
    creds = apply_token_response({}, result)
    creds["account_id"] = fake.me["id"]
    creds["upn"] = fake.me["userPrincipalName"]
    creds["tenant_id"] = "organizations"
    creds["drive_id"] = fake.drive["id"]
    creds["drive_type"] = fake.drive["driveType"]
    creds["drive_web_url"] = fake.drive["webUrl"]
    svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=row.id,
        credentials=creds,
        actor_id=uuid.UUID(user["user"]["id"]),
        external_account_id=fake.me["id"],
        external_account_name=fake.me["userPrincipalName"],
        display_name=fake.me["userPrincipalName"],
    )
    db.commit()
    return body


def test_adapter_registered_unavailable_without_config(monkeypatch) -> None:
    _disable_onedrive(monkeypatch)
    assert connector_registry.has("microsoft_onedrive")
    assert not connector_registry.is_available("microsoft_onedrive")
    desc = connector_registry.describe("microsoft_onedrive")
    assert desc is not None
    assert desc["available"] is False
    assert (
        desc["unavailable_reason"]
        == ErrorCategory.MICROSOFT_ONEDRIVE_NOT_CONFIGURED.value
    )


def test_catalog_available_when_configured(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    user = register_user(email="od-meta@example.com")
    ws = _create_workspace(client, user, "od-meta")
    res = client.get("/api/apps/microsoft-onedrive", headers=_ws_headers(user, ws))
    assert res.status_code == 200
    assert res.json()["connector"]["available"] is True
    assert res.json()["connector"]["key"] == "microsoft_onedrive"


def test_oauth_connect_encrypts_credentials(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-oauth@example.com")
    ws = _create_workspace(client, user, "od-oauth")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    assert conn.status == ConnectionStatus.ACTIVE.value
    assert conn.external_account_id == "ms-user-1"
    creds = ConnectorCredentialService(db).get_credentials(conn)
    assert creds is not None
    assert creds.get("access_token")
    assert creds.get("refresh_token")
    assert creds.get("drive_id") == "drive-1"
    assert "access_token" not in body
    state = ConnectorCredentialService(db).get_sync_state(conn) or {}
    assert state.get("drive_id") == "drive-1"


def test_oauth_callback_pkce_roundtrip(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-cb@example.com")
    ws = _create_workspace(client, user, "od-cb")
    assert (
        client.post(
            "/api/apps/microsoft-onedrive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        "/api/apps/microsoft-onedrive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/microsoft-onedrive"},
    ).json()
    clear_oauth_memory_store()
    oauth = ConnectorOAuthStateService(allow_memory_fallback=True)
    payload = oauth.create(
        workspace_id=uuid.UUID(ws["id"]),
        actor_id=uuid.UUID(user["user"]["id"]),
        app_installation_id=uuid.UUID(started["app_installation_id"]),
        connector_key="microsoft_onedrive",
        connection_id=uuid.UUID(started["id"]),
        return_path="/apps/microsoft-onedrive",
        include_pkce=True,
    )
    assert payload.code_verifier
    res = client.get(
        f"/api/connectors/oauth/microsoft_onedrive/callback"
        f"?code=auth-code&state={payload.state}",
        follow_redirects=False,
    )
    assert res.status_code in {302, 307}
    assert "oauth=success" in res.headers["location"]
    # Replay blocked.
    res2 = client.get(
        f"/api/connectors/oauth/microsoft_onedrive/callback"
        f"?code=auth-code&state={payload.state}",
        follow_redirects=False,
    )
    assert res2.status_code in {302, 307, 400}
    _ = fake


def test_oauth_callback_token_failure_marks_connection_error(
    client, register_user, db, monkeypatch
) -> None:
    """Token exchange 401 must leave the connection in error (not stuck connecting)."""
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    fake.fail_exchange = True
    user = register_user(email="od-oauth-fail@example.com")
    ws = _create_workspace(client, user, "od-oauth-fail")
    assert (
        client.post(
            "/api/apps/microsoft-onedrive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        "/api/apps/microsoft-onedrive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/microsoft-onedrive"},
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["status"] == ConnectionStatus.CONNECTING.value

    clear_oauth_memory_store()
    oauth = ConnectorOAuthStateService(allow_memory_fallback=True)
    payload = oauth.create(
        workspace_id=uuid.UUID(ws["id"]),
        actor_id=uuid.UUID(user["user"]["id"]),
        app_installation_id=uuid.UUID(body["app_installation_id"]),
        connector_key="microsoft_onedrive",
        connection_id=uuid.UUID(body["id"]),
        return_path="/apps/microsoft-onedrive",
        include_pkce=True,
    )
    res = client.get(
        f"/api/connectors/oauth/microsoft_onedrive/callback"
        f"?code=bad-code&state={payload.state}",
        follow_redirects=False,
    )
    assert res.status_code in {302, 307}
    location = res.headers["location"]
    assert "oauth=error" in location
    assert ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED.value in location

    listed = client.get(
        "/api/apps/microsoft-onedrive/connections",
        headers=_ws_headers(user, ws),
    )
    assert listed.status_code == 200, listed.text
    conn = listed.json()["items"][0]
    assert conn["id"] == body["id"]
    assert conn["status"] == ConnectionStatus.ERROR.value
    assert conn["health"] == "failed"
    assert (
        conn["last_error_code"]
        == ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED.value
    )
    assert conn["capabilities"]["can_reconnect"] is True
    assert conn["capabilities"]["can_disconnect"] is True



def test_member_cannot_connect(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    owner = register_user(email="od-owner@example.com")
    member = register_user(email="od-member@example.com")
    ws = _create_workspace(client, owner, "od-member-pol")
    assert (
        client.post(
            "/api/apps/microsoft-onedrive/install", headers=_ws_headers(owner, ws)
        ).status_code
        == 201
    )
    # Add member
    invite = client.post(
        f"/api/workspaces/{ws['id']}/members",
        headers=_ws_headers(owner, ws),
        json={"email": "od-member@example.com", "role": "member"},
    )
    # Some environments use invite flow; fall back to direct membership if available.
    if invite.status_code not in {200, 201}:
        from app.workspaces.models import WorkspaceMembership
        from app.identity.models import User

        u = db.query(User).filter(User.email == "od-member@example.com").one()
        db.add(
            WorkspaceMembership(
                workspace_id=uuid.UUID(ws["id"]),
                user_id=u.id,
                role="member",
            )
        )
        db.commit()

    res = client.post(
        "/api/apps/microsoft-onedrive/connections",
        headers=_ws_headers(member, ws),
        json={"return_path": "/apps/microsoft-onedrive"},
    )
    assert res.status_code in {403, 401}


def test_picker_session_and_token(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-picker@example.com")
    ws = _create_workspace(client, user, "od-picker")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    res = client.post(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}/picker-session",
        headers=_ws_headers(user, ws),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    # P0: session token must be SharePoint-audience, not Graph.
    assert data["access_token"].startswith("sp-token-for-")
    assert data["access_token"] != fake.token_response["access_token"]
    assert data["base_url"] == "https://contoso-my.sharepoint.com"
    assert "refresh_token" not in data
    assert data.get("drive_id") == "drive-1"

    token = client.post(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}/picker-token",
        headers=_ws_headers(user, ws),
        json={"resource": "https://contoso-my.sharepoint.com"},
    )
    assert token.status_code == 200, token.text
    assert token.json()["access_token"].startswith("sp-token-for-")
    assert "refresh_token" not in token.json()

    bad = client.post(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}/picker-token",
        headers=_ws_headers(user, ws),
        json={"resource": "https://other.sharepoint.com"},
    )
    assert bad.status_code in {422, 400, 403}


def test_picker_token_persists_rotated_refresh(
    client, register_user, db, monkeypatch
) -> None:
    """P1: Entra refresh rotation from picker mint must be persisted."""
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    fake.rotate_refresh = True
    user = register_user(email="od-picker-rt@example.com")
    ws = _create_workspace(client, user, "od-picker-rt")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    before = ConnectorCredentialService(db).get_credentials(conn) or {}
    graph_access = before["access_token"]
    assert before["refresh_token"] == "ms-refresh-token"

    token = client.post(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}/picker-token",
        headers=_ws_headers(user, ws),
        json={"resource": "https://contoso-my.sharepoint.com"},
    )
    assert token.status_code == 200, token.text
    assert token.json()["access_token"].startswith("sp-token-for-")

    db.refresh(conn)
    after = ConnectorCredentialService(db).get_credentials(conn) or {}
    assert after["refresh_token"] == "rotated-ms-refresh-token"
    # Graph access_token must not be overwritten by the SharePoint token.
    assert after["access_token"] == graph_access


def test_picker_fails_closed_without_drive_web_url(
    client, register_user, db, monkeypatch
) -> None:
    """P2: do not mint picker tokens when OneDrive host cannot be resolved."""
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-picker-host@example.com")
    ws = _create_workspace(client, user, "od-picker-host")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    cred_svc = ConnectorCredentialService(db)
    creds = dict(cred_svc.get_credentials(conn) or {})
    creds.pop("drive_web_url", None)
    cred_svc.set_credentials(conn, creds, expires_at=None, merge_refresh=True)
    state = dict(cred_svc.get_sync_state(conn) or {})
    state.pop("drive_web_url", None)
    cred_svc.set_sync_state(conn, state)
    fake.drive["webUrl"] = ""
    db.commit()

    res = client.post(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}/picker-session",
        headers=_ws_headers(user, ws),
    )
    assert res.status_code in {400, 422, 502}
    payload = res.json()
    detail = str(payload.get("detail") or payload).lower()
    assert "web url" in detail or "drive" in detail


def test_picker_rejects_personal_msa_drive(
    client, register_user, db, monkeypatch
) -> None:
    """Personal MSA hosts cannot mint SharePoint-audience picker tokens."""
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-picker-personal@example.com")
    ws = _create_workspace(client, user, "od-picker-personal")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    cred_svc = ConnectorCredentialService(db)
    personal_url = (
        "https://my.microsoftpersonalcontent.com/personal/abc/Documents"
    )
    creds = dict(cred_svc.get_credentials(conn) or {})
    creds["drive_type"] = "personal"
    creds["drive_web_url"] = personal_url
    cred_svc.set_credentials(conn, creds, expires_at=None, merge_refresh=True)
    state = dict(cred_svc.get_sync_state(conn) or {})
    state["drive_type"] = "personal"
    state["drive_web_url"] = personal_url
    cred_svc.set_sync_state(conn, state)
    db.commit()

    res = client.post(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}/picker-session",
        headers=_ws_headers(user, ws),
    )
    assert res.status_code == 422
    assert res.json()["error"] == "microsoft_onedrive_drive_not_supported"


def test_add_sources_pdf_txt_docx_and_reject_sharepoint(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    fake.add_file(
        item_id="pdf-1",
        name="a.pdf",
        mime_type="application/pdf",
        content=MINIMAL_PDF,
    )
    fake.add_file(
        item_id="txt-1",
        name="b.txt",
        mime_type="text/plain",
        content=b"hello onedrive",
    )
    fake.add_file(
        item_id="docx-1",
        name="c.docx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        content=b"PK fake docx",
    )
    fake.convert_bytes[("drive-1", "docx-1")] = MINIMAL_PDF
    fake.add_file(
        item_id="sp-1",
        name="sharepoint.pdf",
        mime_type="application/pdf",
        content=MINIMAL_PDF,
        drive_type="documentLibrary",
    )

    user = register_user(email="od-src@example.com")
    ws = _create_workspace(client, user, "od-src")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "OD Expert"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
        "app.documents.service.MinioObjectStorage"
    ) as storage_cls, patch(
        "app.worker.tasks.enqueue_ingest", return_value="task-od-1"
    ):
        storage = storage_cls.return_value

        storage.put_document_bytes.side_effect = _put_storage
        storage.ensure_bucket.return_value = None

        res = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [
                    {
                        "external_id": "drive-1:pdf-1",
                        "provider_locator": {"drive_id": "drive-1", "item_id": "pdf-1"},
                    },
                    {
                        "provider_locator": {"drive_id": "drive-1", "item_id": "txt-1"},
                    },
                    {
                        "provider_locator": {"drive_id": "drive-1", "item_id": "docx-1"},
                    },
                ],
            },
        )
        assert res.status_code == 201, res.text
        payload = res.json()
        assert payload["sync_run_id"]
        assert len(payload["sources"]) == 3

        # Fake frontend filename ignored — Graph name used.
        assert any(s["name"] == "a.pdf" for s in payload["sources"])

        sync = ConnectorSyncService(db)
        run = sync.execute_sync_run(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(body["id"]),
            sync_run_id=uuid.UUID(payload["sync_run_id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
        )
        db.commit()
        assert run.items_failed == 0
        assert run.items_created >= 1

        items = (
            db.query(ConnectorItem)
            .filter(ConnectorItem.app_connection_id == uuid.UUID(body["id"]))
            .all()
        )
        assert len(items) == 3
        assert all(i.current_document_id for i in items)

        # SharePoint library rejected.
        bad = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [
                    {
                        "provider_locator": {
                            "drive_id": "drive-1",
                            "item_id": "sp-1",
                        }
                    }
                ],
            },
        )
        assert bad.status_code == 422
        assert bad.json()["error"] == "microsoft_onedrive_drive_not_supported"

        # Duplicate selection reuses ConnectorItem.
        again = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [
                    {
                        "provider_locator": {
                            "drive_id": "drive-1",
                            "item_id": "pdf-1",
                        }
                    }
                ],
            },
        )
        assert again.status_code == 201
        assert (
            db.query(ConnectorItem)
            .filter(ConnectorItem.app_connection_id == uuid.UUID(body["id"]))
            .count()
            == 3
        )


def test_conversion_failure_marks_source(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    fake.add_file(
        item_id="pptx-1",
        name="deck.pptx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
    )
    fake.convert_fail.add(("drive-1", "pptx-1"))
    user = register_user(email="od-conv@example.com")
    ws = _create_workspace(client, user, "od-conv")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Conv"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
        "app.documents.service.MinioObjectStorage"
    ) as storage_cls, patch("app.worker.tasks.enqueue_ingest", return_value="t"):
        storage_cls.return_value.ensure_bucket.return_value = None
        storage_cls.return_value.put_document_bytes.side_effect = _put_storage
        res = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [
                    {
                        "provider_locator": {
                            "drive_id": "drive-1",
                            "item_id": "pptx-1",
                        }
                    }
                ],
            },
        )
        assert res.status_code == 201
        sync = ConnectorSyncService(db)
        run = sync.execute_sync_run(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(body["id"]),
            sync_run_id=uuid.UUID(res.json()["sync_run_id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
        )
        db.commit()
        assert run.items_failed >= 1


def test_delta_pagination_and_deletion(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    fake.add_file(item_id="d1", name="keep.txt", mime_type="text/plain", content=b"v1")
    # Baseline then working delta.
    fake.delta_pages = [
        {
            "value": [],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=base",
        },
        {
            "value": [
                {
                    "id": "d1",
                    "name": "renamed.txt",
                    "cTag": "c1",
                    "eTag": "e1",
                    "file": {"mimeType": "text/plain"},
                    "parentReference": {"driveId": "drive-1", "driveType": "business"},
                }
            ],
            "@odata.nextLink": "https://graph.microsoft.com/delta?token=page2",
        },
        {
            "value": [
                {
                    "id": "d1",
                    "deleted": {"state": "deleted"},
                    "parentReference": {"driveId": "drive-1"},
                },
                {
                    "id": "untracked",
                    "name": "ignore.pdf",
                    "file": {"mimeType": "application/pdf"},
                    "parentReference": {"driveId": "drive-1"},
                },
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=final",
        },
    ]
    user = register_user(email="od-delta@example.com")
    ws = _create_workspace(client, user, "od-delta")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Delta"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
        "app.documents.service.MinioObjectStorage"
    ) as storage_cls, patch("app.worker.tasks.enqueue_ingest", return_value="t"):
        storage_cls.return_value.ensure_bucket.return_value = None
        storage_cls.return_value.put_document_bytes.side_effect = _put_storage
        res = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [
                    {
                        "provider_locator": {
                            "drive_id": "drive-1",
                            "item_id": "d1",
                        }
                    }
                ],
            },
        )
        assert res.status_code == 201
        sync = ConnectorSyncService(db)
        run = sync.execute_sync_run(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(body["id"]),
            sync_run_id=uuid.UUID(res.json()["sync_run_id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
        )
        db.commit()
        assert run.items_deleted >= 1
        conn = db.get(AppConnection, uuid.UUID(body["id"]))
        state = ConnectorCredentialService(db).get_sync_state(conn) or {}
        assert "token=final" in (state.get("delta_link") or "")
        # deltaLink never exposed on connection DTO
        listed = client.get(
            f"/api/apps/microsoft-onedrive/connections/{body['id']}",
            headers=_ws_headers(user, ws),
        ).json()
        assert "delta_link" not in listed
        assert "sync_state" not in listed


def test_resync_410_recovers(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    fake.add_file(item_id="r1", name="x.txt", mime_type="text/plain", content=b"ok")

    calls = {"n": 0}
    original_delta = fake.delta

    def flaky_delta(**kwargs):
        calls["n"] += 1
        # First working delta after baseline → 410 once.
        if calls["n"] == 2:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_DELTA_RESYNC_REQUIRED,
                "resync",
            )
        return original_delta(**kwargs)

    fake.delta = flaky_delta  # type: ignore[method-assign]

    user = register_user(email="od-410@example.com")
    ws = _create_workspace(client, user, "od-410")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "R"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
        "app.documents.service.MinioObjectStorage"
    ) as storage_cls, patch("app.worker.tasks.enqueue_ingest", return_value="t"):
        storage_cls.return_value.ensure_bucket.return_value = None
        storage_cls.return_value.put_document_bytes.side_effect = _put_storage
        res = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": body["id"],
                "items": [
                    {
                        "provider_locator": {
                            "drive_id": "drive-1",
                            "item_id": "r1",
                        }
                    }
                ],
            },
        )
        sync = ConnectorSyncService(db)
        run = sync.execute_sync_run(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(body["id"]),
            sync_run_id=uuid.UUID(res.json()["sync_run_id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
        )
        db.commit()
        # Should complete without permanently breaking the connection.
        assert run is not None
        conn = db.get(AppConnection, uuid.UUID(body["id"]))
        assert conn is not None
        assert conn.status in {
            ConnectionStatus.ACTIVE.value,
            ConnectionStatus.DEGRADED.value,
        }


def test_webhook_validation_and_notifications(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-wh@example.com")
    ws = _create_workspace(client, user, "od-wh")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn is not None
    from app.common.crypto import decrypt_secret

    routing = decrypt_secret(
        conn.webhook_routing_token_encrypted, settings=get_settings()
    )
    # Seed subscription state.
    cred = ConnectorCredentialService(db)
    state = cred.get_sync_state(conn) or {}
    state["graph_subscription"] = {
        "id": "sub-1",
        "expiration": (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat(),
        "resource": "/drives/drive-1/root",
        "client_state": "secret-client-state",
    }
    state["drive_id"] = "drive-1"
    cred.set_sync_state(conn, state)
    db.commit()

    # Validation handshake — immediate plain text, no sync.
    with patch("app.connectors.tasks.enqueue_connector_webhook_work") as enq:
        val = client.post(
            f"/api/connectors/webhooks/microsoft_onedrive/{routing}"
            f"?validationToken=hello%20world",
        )
        assert val.status_code == 200
        assert val.text == "hello world"
        assert val.headers.get("content-type", "").startswith("text/plain")
        enq.assert_not_called()

    with patch("app.connectors.tasks.enqueue_connector_webhook_work") as enq:
        ok = client.post(
            f"/api/connectors/webhooks/microsoft_onedrive/{routing}",
            content=json.dumps(
                {
                    "value": [
                        {
                            "subscriptionId": "sub-1",
                            "clientState": "secret-client-state",
                            "resource": "/drives/drive-1/root",
                            "changeType": "updated",
                        },
                        {
                            "subscriptionId": "sub-1",
                            "clientState": "secret-client-state",
                            "changeType": "updated",
                        },
                    ]
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert ok.status_code == 202
        enq.assert_called_once()

    bad = client.post(
        f"/api/connectors/webhooks/microsoft_onedrive/{routing}",
        content=json.dumps(
            {
                "value": [
                    {
                        "subscriptionId": "sub-1",
                        "clientState": "wrong",
                        "changeType": "updated",
                    }
                ]
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code in {401, 403}


def test_disconnect_deletes_subscription(
    client, register_user, db, monkeypatch
) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    fake = patch_microsoft_onedrive_client(monkeypatch)
    user = register_user(email="od-disc@example.com")
    ws = _create_workspace(client, user, "od-disc")
    body = _install_and_connect(client, db, user, ws, fake=fake)
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    cred = ConnectorCredentialService(db)
    state = cred.get_sync_state(conn) or {}
    state["graph_subscription"] = {
        "id": "sub-delete-me",
        "expiration": (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat(),
        "client_state": "x",
        "resource": "/drives/drive-1/root",
    }
    cred.set_sync_state(conn, state)
    db.commit()

    res = client.delete(
        f"/api/apps/microsoft-onedrive/connections/{body['id']}",
        headers=_ws_headers(user, ws),
    )
    assert res.status_code == 200
    assert "sub-delete-me" in fake.deleted_subscriptions
    conn = db.get(AppConnection, uuid.UUID(body["id"]))
    assert conn.status == ConnectionStatus.DISCONNECTED.value
    assert ConnectorCredentialService(db).get_credentials(conn) is None


def test_cross_provider_coexistence(client, register_user, db, monkeypatch) -> None:
    _seed(db)
    _enable_onedrive(monkeypatch)
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "g-id")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "g-secret")
    get_settings.cache_clear()
    register_google_drive_connector()
    assert connector_registry.is_available("google_drive")
    assert connector_registry.is_available("microsoft_onedrive")
    assert set(connector_registry.keys()) >= {"google_drive", "microsoft_onedrive"}

    fake_od = patch_microsoft_onedrive_client(monkeypatch)
    fake_gd = patch_google_drive_client(monkeypatch)
    fake_gd.add_file("g1", name="g.txt", mime_type="text/plain", content=b"g")
    fake_od.add_file(
        item_id="o1", name="o.txt", mime_type="text/plain", content=b"o"
    )

    user = register_user(email="od-cross@example.com")
    ws = _create_workspace(client, user, "od-cross")
    od = _install_and_connect(client, db, user, ws, fake=fake_od)

    assert (
        client.post(
            "/api/apps/google-drive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    gd_started = client.post(
        "/api/apps/google-drive/connections",
        headers=_ws_headers(user, ws),
        json={"return_path": "/apps/google-drive"},
    ).json()
    svc = ConnectorConnectionService(db)
    row = db.get(AppConnection, uuid.UUID(gd_started["id"]))
    from app.connectors.providers.google_drive.token import (
        apply_token_response as gd_apply,
    )

    creds = gd_apply({}, fake_gd.exchange_code(code="c", redirect_uri="x"))
    creds["google_sub"] = fake_gd.userinfo["sub"]
    creds["email"] = fake_gd.userinfo["email"]
    svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=row.id,
        credentials=creds,
        actor_id=uuid.UUID(user["user"]["id"]),
        external_account_id=fake_gd.userinfo["sub"],
        external_account_name=fake_gd.userinfo["email"],
    )
    db.commit()

    expert = client.post(
        "/api/experts", headers=_ws_headers(user, ws), json={"name": "Both"}
    ).json()

    with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
        "app.documents.service.MinioObjectStorage"
    ) as storage_cls, patch("app.worker.tasks.enqueue_ingest", return_value="t"):
        storage_cls.return_value.ensure_bucket.return_value = None
        storage_cls.return_value.put_document_bytes.side_effect = _put_storage
        r1 = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": od["id"],
                "items": [
                    {
                        "provider_locator": {
                            "drive_id": "drive-1",
                            "item_id": "o1",
                        }
                    }
                ],
            },
        )
        r2 = client.post(
            f"/api/experts/{expert['id']}/connector-sources",
            headers=_ws_headers(user, ws),
            json={
                "connection_id": gd_started["id"],
                "items": [{"external_id": "g1"}],
            },
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        # External IDs do not collide across providers.
        items = db.query(ConnectorItem).all()
        ext = {(i.app_connection_id, i.external_id) for i in items}
        assert len(ext) >= 2


def test_scopes_least_privilege() -> None:
    assert "Files.Read" in ONEDRIVE_SCOPES
    assert "Files.ReadWrite" not in ONEDRIVE_SCOPES
    assert "Sites.Read.All" not in ONEDRIVE_SCOPES
