"""Phase 9C — Connector foundation integration tests."""

from __future__ import annotations

import hashlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.models import (
    AppBillingType,
    AppInstallationStatus,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.seed import ensure_app_catalog
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.items import ConnectorItemService
from app.connectors.models import AppConnection, ConnectorWebhookEvent
from app.connectors.oauth_state import (
    ConnectorOAuthStateService,
    clear_oauth_memory_store,
    validate_oauth_return_path,
)
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.service import ConnectorConnectionService
from app.connectors.sync import ConnectorSyncService
from app.connectors.types import ConnectionStatus, ConnectorItemType
from app.connectors.webhooks import ConnectorWebhookDispatcher
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from tests.support.fake_connectors import FakeKnowledgeConnector


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
        json={"name": "Conn", "slug": slug},
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


def _register_fake(registry: ConnectorRegistry | None = None) -> FakeKnowledgeConnector:
    reg = registry or connector_registry
    fake = FakeKnowledgeConnector()
    if reg.has(fake.key):
        reg.unregister(fake.key)
    reg.register(fake)
    return fake


def _seed_fake_app(db: Session, *, connections_limit: int = 1) -> CatalogApp:
    from app.apps_catalog.repository import AppCatalogRepository

    repo = AppCatalogRepository(db)
    cat = repo.get_category_by_slug("knowledge")
    assert cat is not None
    slug = f"fake-connector-{uuid.uuid4().hex[:8]}"
    app = CatalogApp(
        slug=slug,
        name="Fake Connector",
        short_description="Test only",
        description="Test only",
        category_id=cat.id,
        billing_type=AppBillingType.FREE.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=False,
        sort_order=99,
        connector_key="fake_knowledge",
        connector_kind="knowledge_source",
        extra={"test": True},
    )
    repo.upsert_app(app)
    plan = AppPlan(
        app_id=app.id,
        code="free",
        name="Free",
        billing_interval=AppPlanBillingInterval.NONE.value,
        price_amount=0,
        currency="SAR",
        is_default=True,
        is_active=True,
        extra={},
    )
    repo.upsert_plan(plan)
    repo.upsert_entitlement(
        AppPlanEntitlement(
            app_plan_id=plan.id, key="connections", value=connections_limit
        )
    )
    db.commit()
    db.refresh(app)
    return app


# --- registry ---


def test_registry_register_and_duplicate() -> None:
    reg = ConnectorRegistry()
    fake = FakeKnowledgeConnector()
    reg.register(fake)
    assert reg.is_available("fake_knowledge")
    assert reg.get("fake_knowledge").key == "fake_knowledge"
    try:
        reg.register(FakeKnowledgeConnector())
        assert False, "expected duplicate rejection"
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_ALREADY_REGISTERED


def test_registry_unknown_and_production_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
    from app.core.config import get_settings
    from app.connectors.providers.google_drive import register_google_drive_connector

    get_settings.cache_clear()
    register_google_drive_connector()

    reg = ConnectorRegistry()
    try:
        reg.get("google_drive")
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_NOT_AVAILABLE
    # Global registry may have google_drive registered (Phase 9D) but still
    # unavailable when OAuth env is unset.
    desc = connector_registry.describe("google_drive")
    assert desc is not None
    assert desc["available"] is False
    assert desc["can_connect"] is False
    if connector_registry.has("google_drive"):
        assert desc.get("unavailable_reason") == "google_drive_not_configured"
        assert not connector_registry.is_available("google_drive")


def test_catalog_connector_metadata(client, register_user, db, monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
    from app.core.config import get_settings
    from app.connectors.providers.google_drive import register_google_drive_connector

    get_settings.cache_clear()
    register_google_drive_connector()

    _seed(db)
    user = register_user(email="conn-meta@example.com")
    ws = _create_workspace(client, user, "conn-meta")
    res = client.get("/api/apps/google-drive", headers=_ws_headers(user, ws))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["connector"]["key"] == "google_drive"
    assert body["connector"]["kind"] == "knowledge_source"
    assert body["connector"]["available"] is False
    assert body["connector"]["can_connect"] is False
    assert body["has_active_connection"] is False
    assert "credentials_encrypted" not in body


# --- connection lifecycle ---


def test_owner_can_connect_fake_and_member_cannot(client, register_user, db) -> None:
    _seed(db)
    fake = _register_fake()
    app = _seed_fake_app(db)
    owner = register_user(email="conn-owner@example.com")
    member = register_user(email="conn-member@example.com")
    ws = _create_workspace(client, owner, "conn-owner")
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)

    install = client.post(
        f"/api/apps/{app.slug}/install", headers=_ws_headers(owner, ws)
    )
    assert install.status_code == 201, install.text

    denied = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(member, ws),
        json={"display_name": "Nope"},
    )
    assert denied.status_code == 403

    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(owner, ws),
        json={"display_name": "Work"},
    )
    assert started.status_code == 201, started.text
    conn = started.json()
    assert conn["status"] == "connecting"
    assert "credentials_encrypted" not in conn
    assert "sync_state_encrypted" not in conn

    # Activate via service (provider complete path)
    svc = ConnectorConnectionService(db, registry=connector_registry)
    activated = svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(conn["id"]),
        credentials={"access_token": "tok", "refresh_token": "ref"},
        actor_id=uuid.UUID(owner["user"]["id"]),
        external_account_name="Fake",
    )
    db.commit()
    assert activated.status == ConnectionStatus.ACTIVE.value
    assert activated.credentials_encrypted
    assert "tok" not in (activated.credentials_encrypted or "")

    listed = client.get(
        f"/api/apps/{app.slug}/connections", headers=_ws_headers(member, ws)
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert "credentials" not in listed.json()["items"][0]

    health = client.post(
        f"/api/apps/{app.slug}/connections/{conn['id']}/health-check",
        headers=_ws_headers(owner, ws),
    )
    assert health.status_code == 200, health.text
    assert health.json()["health"] == "healthy"

    disc = client.delete(
        f"/api/apps/{app.slug}/connections/{conn['id']}",
        headers=_ws_headers(owner, ws),
    )
    assert disc.status_code == 200, disc.text
    assert disc.json()["status"] == "disconnected"
    db.refresh(activated)
    assert activated.credentials_encrypted is None
    assert activated.sync_state_encrypted is None
    assert fake.disconnect_calls == 1

    sync_denied = client.post(
        f"/api/apps/{app.slug}/connections/{conn['id']}/sync",
        headers=_ws_headers(owner, ws),
        json={},
    )
    assert sync_denied.status_code == 409
    assert sync_denied.json()["error"] == "connector_already_disconnected"


def test_health_check_restores_degraded_to_active(client, register_user, db) -> None:
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db)
    owner = register_user(email="conn-heal@example.com")
    ws = _create_workspace(client, owner, "conn-heal")
    client.post(f"/api/apps/{app.slug}/install", headers=_ws_headers(owner, ws))

    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(owner, ws),
        json={"display_name": "Heal"},
    )
    assert started.status_code == 201, started.text
    conn = started.json()
    svc = ConnectorConnectionService(db, registry=connector_registry)
    row = svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(conn["id"]),
        credentials={"access_token": "tok", "refresh_token": "ref"},
        actor_id=uuid.UUID(owner["user"]["id"]),
        external_account_name="Heal Me",
    )
    db.commit()
    svc.record_error(
        row,
        error_code="connector_sync_failed",
        error_message="transient provider blip",
        degrade=True,
    )
    db.commit()
    db.refresh(row)
    assert row.status == ConnectionStatus.DEGRADED.value

    health = client.post(
        f"/api/apps/{app.slug}/connections/{conn['id']}/health-check",
        headers=_ws_headers(owner, ws),
    )
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["health"] == "healthy"
    assert body["status"] == ConnectionStatus.ACTIVE.value
    db.refresh(row)
    assert row.status == ConnectionStatus.ACTIVE.value
    assert row.last_error_code is None


def test_must_install_before_connect(client, register_user, db) -> None:
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-noinst@example.com")
    ws = _create_workspace(client, user, "conn-noinst")
    res = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    )
    assert res.status_code in {402, 409}
    assert res.json()["error"] in {
        "app_not_installed",
        "connector_installation_required",
    }


def test_connection_limit_and_concurrency(client, register_user, db) -> None:
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db, connections_limit=1)
    user = register_user(email="conn-limit@example.com")
    ws = _create_workspace(client, user, "conn-limit")
    assert (
        client.post(
            f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )

    first = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={"display_name": "A"},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={"display_name": "B"},
    )
    assert second.status_code == 429, second.text
    body = second.json()
    assert body["error"] == "connector_limit_reached"
    assert body["details"]["metric"] == "connections"
    assert body["details"]["limit"] == 1

    # Concurrent final slot: limit=1, disconnect first, then race two creates
    assert (
        client.delete(
            f"/api/apps/{app.slug}/connections/{first.json()['id']}",
            headers=_ws_headers(user, ws),
        ).status_code
        == 200
    )

    # Raise limit to 1 still — race two at once on empty
    results: list[int] = []
    barrier = threading.Barrier(2)

    def _create() -> None:
        local = SessionLocal()
        try:
            from app.apps_catalog.repository import AppCatalogRepository

            workspace = local.get(Workspace, uuid.UUID(ws["id"]))
            assert workspace is not None
            membership = local.execute(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == workspace.id,
                    WorkspaceMembership.user_id == uuid.UUID(user["user"]["id"]),
                )
            ).scalar_one()
            barrier.wait(timeout=5)
            try:
                ConnectorConnectionService(local, registry=connector_registry).start_connection(
                    workspace=workspace,
                    role=membership.role,
                    actor_id=uuid.UUID(user["user"]["id"]),
                    app_slug=app.slug,
                    display_name="race",
                )
                local.commit()
                results.append(201)
            except AppError as exc:
                local.rollback()
                if exc.category == ErrorCategory.CONNECTOR_LIMIT_REACHED:
                    results.append(429)
                else:
                    results.append(500)
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_create), pool.submit(_create)]
        for f in futs:
            f.result(timeout=10)
    assert sorted(results) == [201, 429]


def test_workspace_isolation_connections(client, register_user, db) -> None:
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db)
    a = register_user(email="conn-iso-a@example.com")
    b = register_user(email="conn-iso-b@example.com")
    ws_a = _create_workspace(client, a, "conn-iso-a")
    ws_b = _create_workspace(client, b, "conn-iso-b")
    for user, ws in ((a, ws_a), (b, ws_b)):
        assert (
            client.post(
                f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
            ).status_code
            == 201
        )
    created = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(a, ws_a),
        json={},
    ).json()
    leak = client.get(
        f"/api/apps/{app.slug}/connections/{created['id']}",
        headers=_ws_headers(b, ws_b),
    )
    assert leak.status_code == 404


def test_production_sync_unavailable(client, register_user, db, monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
    from app.core.config import get_settings
    from app.connectors.providers.google_drive import register_google_drive_connector

    get_settings.cache_clear()
    register_google_drive_connector()

    _seed(db)
    user = register_user(email="conn-prod@example.com")
    ws = _create_workspace(client, user, "conn-prod")
    assert (
        client.post(
            "/api/apps/google-drive/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    res = client.post(
        "/api/apps/google-drive/connections",
        headers=_ws_headers(user, ws),
        json={},
    )
    assert res.status_code == 409
    assert res.json()["error"] == "connector_not_available"


# --- oauth state ---


def test_oauth_state_security(db) -> None:
    clear_oauth_memory_store()
    svc = ConnectorOAuthStateService(allow_memory_fallback=True, ttl_seconds=600)
    ws = uuid.uuid4()
    actor = uuid.uuid4()
    inst = uuid.uuid4()
    payload = svc.create(
        workspace_id=ws,
        actor_id=actor,
        app_installation_id=inst,
        connector_key="fake_knowledge",
        return_path="/apps/fake-connector",
        include_pkce=True,
    )
    assert payload.code_verifier
    public = svc.peek_public(payload.state)
    assert public is not None
    assert "code_verifier" not in public

    try:
        validate_oauth_return_path("https://evil.example/x")
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_OAUTH_RETURN_PATH_INVALID

    try:
        validate_oauth_return_path("//evil.example/x")
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_OAUTH_RETURN_PATH_INVALID

    assert validate_oauth_return_path("/apps/google-drive") == "/apps/google-drive"

    consumed = svc.consume(
        payload.state,
        workspace_id=ws,
        actor_id=actor,
        connector_key="fake_knowledge",
        app_installation_id=inst,
    )
    assert consumed.code_verifier == payload.code_verifier

    try:
        svc.consume(
            payload.state,
            workspace_id=ws,
            actor_id=actor,
            connector_key="fake_knowledge",
        )
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID

    # Binding checks
    p2 = svc.create(
        workspace_id=ws,
        actor_id=actor,
        app_installation_id=inst,
        connector_key="fake_knowledge",
    )
    try:
        svc.consume(
            p2.state,
            workspace_id=uuid.uuid4(),
            actor_id=actor,
            connector_key="fake_knowledge",
        )
        assert False
    except AppError:
        pass

    p3 = svc.create(
        workspace_id=ws,
        actor_id=actor,
        app_installation_id=inst,
        connector_key="fake_knowledge",
    )
    try:
        svc.consume(
            p3.state,
            workspace_id=ws,
            actor_id=uuid.uuid4(),
            connector_key="fake_knowledge",
        )
        assert False
    except AppError:
        pass

    p4 = svc.create(
        workspace_id=ws,
        actor_id=actor,
        app_installation_id=inst,
        connector_key="fake_knowledge",
    )
    try:
        svc.consume(
            p4.state,
            workspace_id=ws,
            actor_id=actor,
            connector_key="other",
        )
        assert False
    except AppError:
        pass


def test_oauth_callback_unavailable(client, monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
    from app.core.config import get_settings
    from app.connectors.providers.google_drive import register_google_drive_connector

    get_settings.cache_clear()
    register_google_drive_connector()
    res = client.get(
        "/api/connectors/oauth/google_drive/callback?code=x&state=y",
        follow_redirects=False,
    )
    assert res.status_code == 409
    assert res.json()["error"] == "connector_not_available"


# --- webhooks ---


def test_webhook_dispatch_and_idempotency(client, register_user, db) -> None:
    _seed(db)
    fake = _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-wh@example.com")
    ws = _create_workspace(client, user, "conn-wh")
    assert (
        client.post(
            f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    ).json()
    svc = ConnectorConnectionService(db)
    conn = svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        credentials={"access_token": "t"},
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()
    from app.common.crypto import decrypt_secret
    from app.core.config import get_settings

    token = decrypt_secret(conn.webhook_routing_token_encrypted, settings=get_settings())
    body = b'{"change":1}'
    sig = hashlib.sha256(fake.webhook_secret.encode() + body).hexdigest()
    enqueued: list[dict] = []

    def _enqueue(payload: dict) -> None:
        enqueued.append(payload)

    dispatcher = ConnectorWebhookDispatcher(db, enqueue_fn=_enqueue)
    status, resp, _ = dispatcher.dispatch(
        connector_key="fake_knowledge",
        routing_token=token,
        raw_body=body,
        headers={"x-fake-signature": sig, "x-fake-event-id": "evt-1"},
        query_params={},
    )
    db.commit()
    assert status == 200
    assert enqueued
    assert len(enqueued) == 1
    envelope = enqueued[0]
    assert envelope["workspace_id"] == ws["id"]
    assert envelope["connection_id"] == started["id"]
    assert envelope["connector_key"] == "fake_knowledge"
    assert envelope["adapter_payload"] == {"kind": "fake_change"}
    assert "kind" not in envelope
    assert len(db.query(ConnectorWebhookEvent).all()) == 1
    # No raw body stored
    event = db.query(ConnectorWebhookEvent).one()
    assert event.payload_hash
    assert not hasattr(event, "raw_body")

    # Duplicate
    status2, _, _ = dispatcher.dispatch(
        connector_key="fake_knowledge",
        routing_token=token,
        raw_body=body,
        headers={"x-fake-signature": sig, "x-fake-event-id": "evt-1"},
        query_params={},
    )
    assert status2 == 200
    assert db.query(ConnectorWebhookEvent).count() == 1

    # Bad token
    try:
        dispatcher.dispatch(
            connector_key="fake_knowledge",
            routing_token="not-a-real-token-xxxxxx",
            raw_body=body,
            headers={"x-fake-signature": sig},
            query_params={},
        )
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED


# --- sync ---


def test_sync_run_lifecycle(client, register_user, db) -> None:
    _seed(db)
    fake = _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-sync@example.com")
    ws = _create_workspace(client, user, "conn-sync")
    assert (
        client.post(
            f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    ).json()
    ConnectorConnectionService(db).activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        credentials={"access_token": "t"},
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()

    sync_svc = ConnectorSyncService(db)
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    run_out = sync_svc.request_manual_sync(
        workspace=workspace,
        role=WorkspaceRole.OWNER.value,
        actor_id=uuid.UUID(user["user"]["id"]),
        app_slug=app.slug,
        connection_id=uuid.UUID(started["id"]),
        idempotency_key="sync-1",
        enqueue=False,
    )
    db.commit()
    run = sync_svc.execute_sync_run(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        sync_run_id=run_out.id,
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()
    assert run.status == "succeeded"
    assert run.items_seen >= 1

    conn = db.get(AppConnection, uuid.UUID(started["id"]))
    assert conn is not None
    assert conn.sync_state_encrypted
    state = ConnectorCredentialService(db).get_sync_state(conn)
    assert state == {"cursor": 1}

    # Idempotent request
    again = sync_svc.request_manual_sync(
        workspace=workspace,
        role=WorkspaceRole.OWNER.value,
        actor_id=uuid.UUID(user["user"]["id"]),
        app_slug=app.slug,
        connection_id=uuid.UUID(started["id"]),
        idempotency_key="sync-1",
        enqueue=False,
    )
    assert again.id == run_out.id

    # Concurrent sync blocked
    pending = sync_svc.request_manual_sync(
        workspace=workspace,
        role=WorkspaceRole.OWNER.value,
        actor_id=uuid.UUID(user["user"]["id"]),
        app_slug=app.slug,
        connection_id=uuid.UUID(started["id"]),
        idempotency_key="sync-2",
        enqueue=False,
    )
    db.commit()
    try:
        sync_svc.request_manual_sync(
            workspace=workspace,
            role=WorkspaceRole.OWNER.value,
            actor_id=uuid.UUID(user["user"]["id"]),
            app_slug=app.slug,
            connection_id=uuid.UUID(started["id"]),
            idempotency_key="sync-3",
            enqueue=False,
        )
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.CONNECTOR_SYNC_IN_PROGRESS

    # Finish pending so disconnect tests can proceed
    sync_svc.execute_sync_run(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        sync_run_id=pending.id,
    )
    db.commit()
    _ = fake


# --- items ---


def test_connector_items(client, register_user, db) -> None:
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-items@example.com")
    ws = _create_workspace(client, user, "conn-items")
    assert (
        client.post(
            f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    ).json()
    ConnectorConnectionService(db).activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        credentials={"access_token": "t"},
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()

    items = ConnectorItemService(db)
    a = items.upsert_item(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        external_id="file-1",
        name="Report.pdf",
        item_type=ConnectorItemType.FILE.value,
        path="/foo/Report.pdf",
    )
    db.commit()
    renamed = items.upsert_item(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        external_id="file-1",
        name="Renamed.pdf",
        item_type=ConnectorItemType.FILE.value,
        path="/bar/Renamed.pdf",
    )
    db.commit()
    assert renamed.id == a.id
    assert renamed.name == "Renamed.pdf"
    assert renamed.external_id == "file-1"

    # Second connection can reuse same external id
    started2 = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    )
    # limit 1 — disconnect first
    client.delete(
        f"/api/apps/{app.slug}/connections/{started['id']}",
        headers=_ws_headers(user, ws),
    )
    started2 = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    ).json()
    ConnectorConnectionService(db).activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started2["id"]),
        credentials={"access_token": "t2"},
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()
    other = items.upsert_item(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started2["id"]),
        external_id="file-1",
        name="Other.pdf",
    )
    db.commit()
    assert other.id != a.id

    try:
        items.upsert_item(
            workspace_id=uuid.UUID(ws["id"]),
            connection_id=uuid.UUID(started2["id"]),
            external_id="bad",
            name="x",
            metadata={"access_token": "nope"},
        )
        assert False
    except AppError as exc:
        assert exc.category == ErrorCategory.VALIDATION


# --- app access ---


def test_expired_subscription_blocks_connector(client, register_user, db) -> None:
    """Subscription expired + installed → connector ops blocked."""
    from datetime import datetime, timedelta, timezone

    from app.apps_catalog.models import AppInstallation, AppSubscription, AppSubscriptionStatus
    from app.apps_catalog.repository import AppCatalogRepository

    _seed(db)
    _register_fake()
    repo = AppCatalogRepository(db)
    cat = repo.get_category_by_slug("communication")
    assert cat is not None
    slug = f"fake-sub-{uuid.uuid4().hex[:8]}"
    app = CatalogApp(
        slug=slug,
        name="Fake Sub",
        short_description="t",
        description="t",
        category_id=cat.id,
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.PUBLISHED.value,
        connector_key="fake_knowledge",
        connector_kind="knowledge_source",
        extra={},
    )
    repo.upsert_app(app)
    plan = AppPlan(
        app_id=app.id,
        code="monthly",
        name="Monthly",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=10,
        currency="SAR",
        is_default=True,
        is_active=True,
        extra={},
    )
    repo.upsert_plan(plan)
    repo.upsert_entitlement(
        AppPlanEntitlement(app_plan_id=plan.id, key="connections", value=1)
    )
    db.commit()

    user = register_user(email="conn-exp@example.com")
    ws = _create_workspace(client, user, "conn-exp")
    ws_id = uuid.UUID(ws["id"])

    inst = AppInstallation(
        workspace_id=ws_id,
        app_id=app.id,
        status=AppInstallationStatus.ACTIVE.value,
        installed_by_user_id=uuid.UUID(user["user"]["id"]),
    )
    db.add(inst)
    now = datetime.now(timezone.utc)
    sub = AppSubscription(
        workspace_id=ws_id,
        app_id=app.id,
        app_plan_id=plan.id,
        status=AppSubscriptionStatus.ACTIVE.value,
        current_period_start=now - timedelta(days=40),
        current_period_end=now - timedelta(days=1),
    )
    db.add(sub)
    db.commit()

    res = client.post(
        f"/api/apps/{slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    )
    assert res.status_code == 402, res.text
    assert res.json()["error"] == "app_subscription_expired"


def test_seed_connections_entitlement(db) -> None:
    _seed(db)
    from app.apps_catalog.repository import AppCatalogRepository

    repo = AppCatalogRepository(db)
    drive = repo.get_app_by_slug("google-drive")
    assert drive is not None
    assert drive.connector_key == "google_drive"
    plan = next(p for p in drive.plans if p.code == "free")
    ent = repo.get_entitlement(plan.id, "connections")
    assert ent is not None
    assert ent.value == 1


# --- audit regressions (P1–P3) ---


def test_failed_celery_sync_finalizes_pending_run(client, register_user, db) -> None:
    """P1: orphaned pending/running runs must be finalized so sync is not blocked forever."""
    from app.connectors.models import ConnectorSyncRun
    from app.connectors.tasks import _mark_sync_run_failed

    _seed(db)
    _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-p1@example.com")
    ws = _create_workspace(client, user, "conn-p1")
    assert (
        client.post(
            f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    ).json()
    ConnectorConnectionService(db).activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        credentials={"access_token": "t"},
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    assert workspace is not None
    sync_svc = ConnectorSyncService(db)
    run_out = sync_svc.request_manual_sync(
        workspace=workspace,
        role=WorkspaceRole.OWNER.value,
        actor_id=uuid.UUID(user["user"]["id"]),
        app_slug=app.slug,
        connection_id=uuid.UUID(started["id"]),
        idempotency_key="p1-sync",
        enqueue=False,
    )
    db.commit()
    assert run_out.status == "pending"

    # Simulate Celery's last-retry finalize path (worker crash before execute completes).
    _mark_sync_run_failed(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        sync_run_id=run_out.id,
        error_code="connector_connection_failed",
        error_message="worker boom",
    )

    db.expire_all()
    run_row = db.get(ConnectorSyncRun, run_out.id)
    assert run_row is not None
    assert run_row.status == "failed"
    assert run_row.error_code == "connector_connection_failed"
    assert run_row.completed_at is not None

    # Slot cleared — another sync request must succeed.
    next_run = sync_svc.request_manual_sync(
        workspace=workspace,
        role=WorkspaceRole.OWNER.value,
        actor_id=uuid.UUID(user["user"]["id"]),
        app_slug=app.slug,
        connection_id=uuid.UUID(started["id"]),
        idempotency_key="p1-sync-2",
        enqueue=False,
    )
    db.commit()
    assert next_run.status == "pending"
    assert next_run.id != run_out.id

    # Idempotent on already-failed runs.
    _mark_sync_run_failed(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        sync_run_id=run_out.id,
        error_code="connector_connection_failed",
        error_message="already failed",
    )
    db.expire_all()
    assert db.get(ConnectorSyncRun, run_out.id).status == "failed"


def test_get_connection_requires_active_installation(
    client, register_user, db
) -> None:
    """P2: get_connection must not leak rows after uninstall."""
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-p2-get@example.com")
    ws = _create_workspace(client, user, "conn-p2-get")
    headers = _ws_headers(user, ws)
    assert client.post(f"/api/apps/{app.slug}/install", headers=headers).status_code == 201
    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=headers,
        json={},
    ).json()
    ok = client.get(
        f"/api/apps/{app.slug}/connections/{started['id']}",
        headers=headers,
    )
    assert ok.status_code == 200, ok.text

    uninstalled = client.delete(f"/api/apps/{app.slug}/install", headers=headers)
    assert uninstalled.status_code == 200, uninstalled.text

    missing = client.get(
        f"/api/apps/{app.slug}/connections/{started['id']}",
        headers=headers,
    )
    assert missing.status_code == 404
    assert missing.json()["error"] == "connector_not_found"


def test_reconnect_respects_connection_limit(client, register_user, db) -> None:
    """P2: reconnecting a disconnected row must respect connections entitlement."""
    _seed(db)
    _register_fake()
    app = _seed_fake_app(db, connections_limit=1)
    user = register_user(email="conn-p2-re@example.com")
    ws = _create_workspace(client, user, "conn-p2-re")
    headers = _ws_headers(user, ws)
    assert client.post(f"/api/apps/{app.slug}/install", headers=headers).status_code == 201

    first = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=headers,
        json={"display_name": "A"},
    ).json()
    assert (
        client.delete(
            f"/api/apps/{app.slug}/connections/{first['id']}",
            headers=headers,
        ).status_code
        == 200
    )

    second = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=headers,
        json={"display_name": "B"},
    )
    assert second.status_code == 201, second.text

    # Slot is filled by B — reconnecting A must be rejected.
    re = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=headers,
        json={"connection_id": first["id"], "display_name": "A again"},
    )
    assert re.status_code == 429, re.text
    assert re.json()["error"] == "connector_limit_reached"


def test_webhook_envelope_nests_adapter_payload(
    client, register_user, db
) -> None:
    """P3: adapter enqueue_payload must not overwrite tenant envelope fields."""
    _seed(db)
    fake = _register_fake()
    app = _seed_fake_app(db)
    user = register_user(email="conn-p3@example.com")
    ws = _create_workspace(client, user, "conn-p3")
    assert (
        client.post(
            f"/api/apps/{app.slug}/install", headers=_ws_headers(user, ws)
        ).status_code
        == 201
    )
    started = client.post(
        f"/api/apps/{app.slug}/connections",
        headers=_ws_headers(user, ws),
        json={},
    ).json()
    svc = ConnectorConnectionService(db)
    conn = svc.activate_connection(
        workspace_id=uuid.UUID(ws["id"]),
        connection_id=uuid.UUID(started["id"]),
        credentials={"access_token": "t"},
        actor_id=uuid.UUID(user["user"]["id"]),
    )
    db.commit()
    from app.common.crypto import decrypt_secret
    from app.connectors.adapters import WebhookHandleResult
    from app.core.config import get_settings

    token = decrypt_secret(conn.webhook_routing_token_encrypted, settings=get_settings())
    body = b'{"change":2}'
    sig = hashlib.sha256(fake.webhook_secret.encode() + body).hexdigest()

    def _malicious_webhook(*, request, credentials):  # noqa: ANN001
        _ = credentials
        event_id = request.headers.get("x-fake-event-id")
        return WebhookHandleResult(
            accepted=True,
            provider_event_id=event_id,
            idempotency_key=event_id,
            enqueue=True,
            enqueue_payload={
                "workspace_id": "attacker-ws",
                "connection_id": "attacker-conn",
                "webhook_event_id": "attacker-evt",
                "connector_key": "evil",
                "kind": "spoof",
            },
            http_status=200,
            response_body=b'{"ok":true}',
        )

    fake.verify_and_handle_webhook = _malicious_webhook  # type: ignore[method-assign]
    enqueued: list[dict] = []
    dispatcher = ConnectorWebhookDispatcher(db, enqueue_fn=enqueued.append)
    status, _, _ = dispatcher.dispatch(
        connector_key="fake_knowledge",
        routing_token=token,
        raw_body=body,
        headers={"x-fake-signature": sig, "x-fake-event-id": "evt-p3"},
        query_params={},
    )
    db.commit()
    assert status == 200
    assert len(enqueued) == 1
    payload = enqueued[0]
    assert payload["workspace_id"] == ws["id"]
    assert payload["connection_id"] == started["id"]
    assert payload["connector_key"] == "fake_knowledge"
    assert payload["adapter_payload"]["workspace_id"] == "attacker-ws"
    assert payload["adapter_payload"]["kind"] == "spoof"
