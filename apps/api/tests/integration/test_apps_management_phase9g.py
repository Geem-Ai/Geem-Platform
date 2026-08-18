"""Phase 9G — App management polish, secrecy, isolation, role matrix, E2E gates."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessStatus
from app.apps_catalog.models import (
    AppBillingType,
    AppCategory,
    AppLicense,
    AppLicenseStatus,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.apps_catalog.seed import ensure_app_catalog
from app.connectors.models import AppConnection
from app.connectors.providers.google_drive import register_google_drive_connector
from app.connectors.providers.openwa import register_openwa_connector
from app.connectors.registry import connector_registry
from app.connectors.schemas import assert_no_secrets
from app.connectors.service import ConnectorConnectionService
from app.connectors.sync import ConnectorSyncService
from app.connectors.types import ConnectionStatus
from app.core.config import get_settings
from app.experts.models import ExpertSourceType
from app.workspaces.models import WorkspaceMembership, WorkspaceRole
from tests.integration.test_openwa_phase9f import FakeOpenWAClient
from tests.support.fake_google_drive import patch_google_drive_client


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


def _add_member(db, workspace_id: str, user_id: str, role=WorkspaceRole.MEMBER) -> None:
    from tests.support.rbac import add_workspace_member
    key = role.value if hasattr(role, "value") else role
    add_workspace_member(db, workspace_id, user_id, key)



def _return_token(redirect_url: str) -> str:
    return parse_qs(urlparse(redirect_url).query)["rt"][0]


def _complete_noop(client: TestClient, checkout: dict) -> dict:
    rt = _return_token(checkout["redirect_url"])
    res = client.get(
        f"/api/billing/return/noop/{checkout['purchase_id']}",
        params={"rt": rt},
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _seed(db: Session) -> None:
    ensure_app_catalog(db)
    db.commit()


def _seed_coming_soon(db: Session) -> CatalogApp:
    cat = db.scalar(select(AppCategory).where(AppCategory.slug == "productivity"))
    assert cat is not None
    app = CatalogApp(
        slug=f"soon-{uuid.uuid4().hex[:8]}",
        name="Coming Soon Tool",
        short_description="Discoverable but unavailable",
        description="Test fixture",
        category_id=cat.id,
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.COMING_SOON.value,
        is_featured=False,
        sort_order=99,
    )
    db.add(app)
    db.flush()
    plan = AppPlan(
        app_id=app.id,
        code="soon",
        name="Soon",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=Decimal("10.00"),
        currency="SAR",
        is_default=True,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(app)
    return app


def _seed_one_time(db: Session) -> tuple[CatalogApp, AppPlan]:
    cat = db.scalar(select(AppCategory).where(AppCategory.slug == "analytics"))
    if cat is None:
        cat = AppCategory(
            slug="analytics",
            name_key="apps.categories.analytics",
            description_key="apps.categories.analyticsHint",
            sort_order=40,
            is_active=True,
        )
        db.add(cat)
        db.flush()
    app = CatalogApp(
        slug=f"ot-{uuid.uuid4().hex[:8]}",
        name="One Time Tool",
        short_description="Test one-time",
        description="Test fixture only",
        category_id=cat.id,
        billing_type=AppBillingType.ONE_TIME.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=False,
        sort_order=50,
    )
    db.add(app)
    db.flush()
    plan = AppPlan(
        app_id=app.id,
        code="buy",
        name="Buy Once",
        billing_interval=AppPlanBillingInterval.NONE.value,
        price_amount=Decimal("49.00"),
        currency="SAR",
        is_default=True,
        is_active=True,
    )
    db.add(plan)
    db.flush()
    db.add(AppPlanEntitlement(app_plan_id=plan.id, key="connections", value=1))
    db.commit()
    db.refresh(app)
    db.refresh(plan)
    return app, plan


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    get_settings.cache_clear()
    register_google_drive_connector()
    register_openwa_connector()


def _enable_drive(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_ID", "test-drive-client-id")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "test-drive-client-secret")
    monkeypatch.setenv("GOOGLE_DRIVE_APP_ID", "123456789")
    get_settings.cache_clear()
    register_google_drive_connector()
    assert connector_registry.is_available("google_drive")


def _enable_openwa(monkeypatch) -> None:
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
        "app.connectors.providers.openwa.adapter.OpenWAClient",
        FakeOpenWAClient,
    )
    register_openwa_connector(client_factory=FakeOpenWAClient)


def _whatsapp_plan(db: Session, code: str = "line") -> tuple[CatalogApp, AppPlan]:
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert app is not None
    plan = db.scalar(
        select(AppPlan).where(AppPlan.app_id == app.id, AppPlan.code == code)
    )
    assert plan is not None
    return app, plan


class TestDtoSecrecy:
    def test_catalog_and_installations_omit_secrets(
        self, client, register_user, db
    ) -> None:
        _seed(db)
        user = register_user(email="9g-secrets@example.com")
        ws = _create_workspace(client, user, "Sec", f"sec-{uuid.uuid4().hex[:6]}")
        headers = _ws_headers(user, ws)

        assert (
            client.post("/api/apps/google-drive/install", headers=headers).status_code
            == 201
        )

        for path in (
            "/api/apps",
            "/api/apps/google-drive",
            "/api/apps/installations",
            "/api/apps/google-drive/connections",
        ):
            res = client.get(path, headers=headers)
            assert res.status_code == 200, res.text
            assert_no_secrets(res.json())

    def test_whatsapp_connection_detail_omits_secrets(
        self, client, register_user, db, monkeypatch
    ) -> None:
        _seed(db)
        _enable_openwa(monkeypatch)
        user = register_user(email="9g-wa-secrets@example.com")
        ws = _create_workspace(client, user, "WA", f"wa-sec-{uuid.uuid4().hex[:6]}")
        headers = _ws_headers(user, ws)
        _, plan = _whatsapp_plan(db)

        checkout = client.post(
            "/api/apps/whatsapp/checkout",
            headers=headers,
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)
        detail = client.get("/api/apps/whatsapp", headers=headers).json()
        if detail["access"]["status"] != AppAccessStatus.ACTIVE.value:
            assert (
                client.post("/api/apps/whatsapp/install", headers=headers).status_code
                == 201
            )
        started = client.post(
            "/api/apps/whatsapp/connections",
            headers=headers,
            json={"connect_mode": "qr"},
        )
        assert started.status_code == 201, started.text
        conn_id = started.json()["id"]
        detail = client.get(
            f"/api/apps/whatsapp/connections/{conn_id}",
            headers=headers,
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert_no_secrets(body)
        assert "credentials_encrypted" not in body
        assert "session_id" not in body


class TestConnectionUsageDto:
    def test_installations_include_usage_and_summaries(
        self, client, register_user, db, monkeypatch
    ) -> None:
        _seed(db)
        _enable_openwa(monkeypatch)
        user = register_user(email="9g-usage@example.com")
        ws = _create_workspace(client, user, "Usage", f"usage-{uuid.uuid4().hex[:6]}")
        headers = _ws_headers(user, ws)
        _, plan = _whatsapp_plan(db, code="desk")

        checkout = client.post(
            "/api/apps/whatsapp/checkout",
            headers=headers,
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)
        detail = client.get("/api/apps/whatsapp", headers=headers).json()
        if detail["access"]["status"] != AppAccessStatus.ACTIVE.value:
            assert (
                client.post("/api/apps/whatsapp/install", headers=headers).status_code
                == 201
            )
        started = client.post(
            "/api/apps/whatsapp/connections",
            headers=headers,
            json={"connect_mode": "qr", "display_name": "Sales"},
        )
        assert started.status_code == 201, started.text

        inst = client.get("/api/apps/installations", headers=headers)
        assert inst.status_code == 200, inst.text
        wa = next(i for i in inst.json()["items"] if i["app"]["slug"] == "whatsapp")
        usage = wa["app"]["connection_usage"]
        assert usage is not None
        assert usage["used"] == 1
        assert usage["limit"] == 3
        assert len(wa["app"]["connections"]) == 1
        assert wa["app"]["connections"][0]["id"] == started.json()["id"]
        assert wa["app"]["connections"][0]["status"]

        conns = client.get("/api/apps/whatsapp/connections", headers=headers)
        assert conns.status_code == 200, conns.text
        assert conns.json()["used"] == 1
        assert conns.json()["connection_limit"] == 3


class TestRoleMatrix:
    def test_member_mutations_forbidden_owner_admin_ok(
        self, client, register_user, db
    ) -> None:
        _seed(db)
        owner = register_user(email="9g-owner@example.com")
        admin = register_user(email="9g-admin@example.com")
        member = register_user(email="9g-member@example.com")
        ws = _create_workspace(
            client, owner, "Roles", f"roles-{uuid.uuid4().hex[:6]}"
        )
        _add_member(db, ws["id"], admin["user"]["id"], WorkspaceRole.ADMIN)
        _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)

        browse = client.get("/api/apps", headers=_ws_headers(member, ws))
        assert browse.status_code == 200
        drive = next(a for a in browse.json()["items"] if a["slug"] == "google-drive")
        assert drive["access"]["can_install"] is False

        assert (
            client.post(
                "/api/apps/google-drive/install",
                headers=_ws_headers(member, ws),
            ).status_code
            == 403
        )

        assert (
            client.post(
                "/api/apps/google-drive/install",
                headers=_ws_headers(admin, ws),
            ).status_code
            == 201
        )

        assert (
            client.delete(
                "/api/apps/google-drive/install",
                headers=_ws_headers(member, ws),
            ).status_code
            == 403
        )
        assert (
            client.delete(
                "/api/apps/google-drive/install",
                headers=_ws_headers(admin, ws),
            ).status_code
            == 200
        )


class TestCatalogEdgeCases:
    def test_free_install_uninstall_reinstall_no_purchase(
        self, client, register_user, db
    ) -> None:
        _seed(db)
        user = register_user(email="9g-free@example.com")
        ws = _create_workspace(client, user, "Free", f"free-{uuid.uuid4().hex[:6]}")
        headers = _ws_headers(user, ws)

        assert (
            client.post("/api/apps/google-drive/install", headers=headers).status_code
            == 201
        )
        detail = client.get("/api/apps/google-drive", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.ACTIVE.value

        assert (
            client.delete("/api/apps/google-drive/install", headers=headers).status_code
            == 200
        )
        detail = client.get("/api/apps/google-drive", headers=headers).json()
        assert detail["access"]["can_install"] is True

        assert (
            client.post("/api/apps/google-drive/install", headers=headers).status_code
            == 201
        )
        history = client.get("/api/billing/purchases", headers=headers)
        assert history.status_code == 200
        assert all(
            p["kind"] not in {"app_one_time", "app_subscription"}
            for p in history.json().get("items", [])
        )

    def test_one_time_license_survives_uninstall(
        self, client, register_user, db
    ) -> None:
        _seed(db)
        app, plan = _seed_one_time(db)
        user = register_user(email="9g-ot@example.com")
        ws = _create_workspace(client, user, "OT", f"ot-{uuid.uuid4().hex[:6]}")
        headers = _ws_headers(user, ws)

        checkout = client.post(
            f"/api/apps/{app.slug}/checkout",
            headers=headers,
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)

        detail = client.get(f"/api/apps/{app.slug}", headers=headers).json()
        if detail["access"]["status"] == AppAccessStatus.ENTITLED_NOT_INSTALLED.value:
            assert (
                client.post(
                    f"/api/apps/{app.slug}/install", headers=headers
                ).status_code
                == 201
            )

        detail = client.get(f"/api/apps/{app.slug}", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.ACTIVE.value

        assert (
            client.delete(
                f"/api/apps/{app.slug}/install", headers=headers
            ).status_code
            == 200
        )
        detail = client.get(f"/api/apps/{app.slug}", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.ENTITLED_NOT_INSTALLED.value
        assert detail["access"]["can_install"] is True
        assert detail["access"]["can_purchase"] is False

        assert (
            client.post(f"/api/apps/{app.slug}/install", headers=headers).status_code
            == 201
        )
        licenses = db.scalars(
            select(AppLicense).where(
                AppLicense.workspace_id == uuid.UUID(ws["id"]),
                AppLicense.app_id == app.id,
                AppLicense.status == AppLicenseStatus.ACTIVE.value,
            )
        ).all()
        assert len(licenses) == 1

    def test_coming_soon_checkout_and_install_rejected(
        self, client, register_user, db
    ) -> None:
        _seed(db)
        app = _seed_coming_soon(db)
        user = register_user(email="9g-soon@example.com")
        ws = _create_workspace(client, user, "Soon", f"soon-{uuid.uuid4().hex[:6]}")
        headers = _ws_headers(user, ws)

        detail = client.get(f"/api/apps/{app.slug}", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.UNAVAILABLE.value
        assert detail["access"]["can_purchase"] is False
        assert detail["access"]["can_install"] is False

        plan = db.scalar(select(AppPlan).where(AppPlan.app_id == app.id))
        assert plan is not None
        checkout = client.post(
            f"/api/apps/{app.slug}/checkout",
            headers=headers,
            json={"plan_id": str(plan.id)},
        )
        assert checkout.status_code in {403, 404, 409, 422}
        install = client.post(f"/api/apps/{app.slug}/install", headers=headers)
        assert install.status_code in {403, 404, 409, 422}


class TestWorkspaceIsolation:
    def test_whatsapp_connection_isolated(
        self, client, register_user, db, monkeypatch
    ) -> None:
        _seed(db)
        _enable_openwa(monkeypatch)
        owner_a = register_user(email="9g-iso-a@example.com")
        owner_b = register_user(email="9g-iso-b@example.com")
        ws_a = _create_workspace(client, owner_a, "A", f"iso-a-{uuid.uuid4().hex[:6]}")
        ws_b = _create_workspace(client, owner_b, "B", f"iso-b-{uuid.uuid4().hex[:6]}")
        _, plan = _whatsapp_plan(db)

        for user, ws in ((owner_a, ws_a), (owner_b, ws_b)):
            headers = _ws_headers(user, ws)
            checkout = client.post(
                "/api/apps/whatsapp/checkout",
                headers=headers,
                json={"plan_id": str(plan.id)},
            ).json()
            _complete_noop(client, checkout)
            detail = client.get("/api/apps/whatsapp", headers=headers).json()
            if detail["access"]["status"] != AppAccessStatus.ACTIVE.value:
                assert (
                    client.post("/api/apps/whatsapp/install", headers=headers).status_code
                    == 201
                )

        started = client.post(
            "/api/apps/whatsapp/connections",
            headers=_ws_headers(owner_a, ws_a),
            json={"connect_mode": "qr"},
        )
        assert started.status_code == 201, started.text
        conn_id = started.json()["id"]

        leak = client.get(
            f"/api/apps/whatsapp/connections/{conn_id}",
            headers=_ws_headers(owner_b, ws_b),
        )
        assert leak.status_code == 404

        disc = client.post(
            f"/api/apps/whatsapp/connections/{conn_id}/disconnect",
            headers=_ws_headers(owner_b, ws_b),
        )
        assert disc.status_code == 404


class TestE2EFreeDrive:
    def test_install_connect_expert_source(
        self, client, register_user, db, monkeypatch
    ) -> None:
        _seed(db)
        _enable_drive(monkeypatch)
        fake = patch_google_drive_client(monkeypatch)
        fake.add_file(
            "file-9g",
            name="phase9g.txt",
            mime_type="text/plain",
            content=b"phase 9g free path",
        )
        user = register_user(email="9g-drive-e2e@example.com")
        ws = _create_workspace(
            client, user, "DriveE2E", f"drive-e2e-{uuid.uuid4().hex[:6]}"
        )
        headers = _ws_headers(user, ws)

        catalog = client.get("/api/apps/google-drive", headers=headers).json()
        assert catalog["access"]["can_install"] is True

        assert (
            client.post("/api/apps/google-drive/install", headers=headers).status_code
            == 201
        )
        started = client.post(
            "/api/apps/google-drive/connections",
            headers=headers,
            json={"return_path": "/apps/google-drive"},
        )
        assert started.status_code == 201, started.text
        body = started.json()
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
        )
        db.commit()

        detail = client.get("/api/apps/google-drive", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.ACTIVE.value
        assert detail["has_active_connection"] is True
        assert detail["connection_usage"]["used"] == 1

        expert = client.post(
            "/api/experts", headers=headers, json={"name": "9G Expert"}
        ).json()
        with patch("app.connectors.tasks.enqueue_connector_sync"), patch(
            "app.documents.service.MinioObjectStorage"
        ) as storage_cls, patch(
            "app.worker.tasks.enqueue_ingest", return_value="task-9g"
        ):
            storage = storage_cls.return_value

            def _put(**kw):
                from app.storage.document_keys import resolve_document_storage_key

                return resolve_document_storage_key(
                    kw["document_id"], kw.get("workspace_id")
                )

            storage.put_document_bytes.side_effect = _put
            storage.ensure_bucket.return_value = None

            res = client.post(
                f"/api/experts/{expert['id']}/connector-sources",
                headers=headers,
                json={
                    "connection_id": body["id"],
                    "items": [{"external_id": "file-9g"}],
                },
            )
            assert res.status_code == 201, res.text
            payload = res.json()
            assert payload["sources"][0]["type"] == ExpertSourceType.CONNECTOR.value

            sync = ConnectorSyncService(db)
            sync.execute_sync_run(
                workspace_id=uuid.UUID(ws["id"]),
                connection_id=uuid.UUID(body["id"]),
                sync_run_id=uuid.UUID(payload["sync_run_id"]),
                actor_id=uuid.UUID(user["user"]["id"]),
            )
            db.commit()

        docs = client.get(
            f"/api/experts/{expert['id']}/documents",
            headers=headers,
        )
        assert docs.status_code == 200
        assert len(docs.json()) >= 1


class TestE2EWhatsAppPaid:
    def test_subscribe_install_connect(
        self, client, register_user, db, monkeypatch
    ) -> None:
        _seed(db)
        _enable_openwa(monkeypatch)
        user = register_user(email="9g-wa-e2e@example.com")
        ws = _create_workspace(
            client, user, "WAE2E", f"wa-e2e-{uuid.uuid4().hex[:6]}"
        )
        headers = _ws_headers(user, ws)
        _, plan = _whatsapp_plan(db, code="line")

        detail = client.get("/api/apps/whatsapp", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.NOT_ENTITLED.value
        assert detail["access"]["can_purchase"] is True
        assert any(p["code"] == "line" for p in detail["plans"])

        checkout = client.post(
            "/api/apps/whatsapp/checkout",
            headers=headers,
            json={"plan_id": str(plan.id)},
        )
        assert checkout.status_code == 200, checkout.text
        paid = _complete_noop(client, checkout.json())
        assert paid["status"] == "paid"

        detail = client.get("/api/apps/whatsapp", headers=headers).json()
        if detail["access"]["status"] == AppAccessStatus.ENTITLED_NOT_INSTALLED.value:
            assert (
                client.post("/api/apps/whatsapp/install", headers=headers).status_code
                == 201
            )
            detail = client.get("/api/apps/whatsapp", headers=headers).json()

        assert detail["access"]["status"] == AppAccessStatus.ACTIVE.value
        assert detail["access"]["plan_code"] == "line"

        started = client.post(
            "/api/apps/whatsapp/connections",
            headers=headers,
            json={"connect_mode": "qr"},
        )
        assert started.status_code == 201, started.text
        conn = started.json()
        assert conn["status"] in {
            ConnectionStatus.CONNECTING.value,
            ConnectionStatus.PENDING.value,
            ConnectionStatus.ACTIVE.value,
        }
        assert_no_secrets(conn)

        usage = client.get("/api/apps/whatsapp/connections", headers=headers).json()
        assert usage["used"] == 1
        assert usage["connection_limit"] == 1


class TestWhatsAppExpireRenew:
    def test_expire_blocks_then_renew_restores(
        self, client, register_user, db, monkeypatch
    ) -> None:
        _seed(db)
        _enable_openwa(monkeypatch)
        owner = register_user(email="9g-expire-owner@example.com")
        member = register_user(email="9g-expire-member@example.com")
        ws = _create_workspace(
            client, owner, "Expire", f"expire-{uuid.uuid4().hex[:6]}"
        )
        _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
        headers = _ws_headers(owner, ws)
        app, plan = _whatsapp_plan(db, code="line")

        checkout = client.post(
            "/api/apps/whatsapp/checkout",
            headers=headers,
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)
        if (
            client.get("/api/apps/whatsapp", headers=headers).json()["access"]["status"]
            != AppAccessStatus.ACTIVE.value
        ):
            assert (
                client.post("/api/apps/whatsapp/install", headers=headers).status_code
                == 201
            )

        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == app.id,
            )
        )
        assert sub is not None
        now = datetime.now(timezone.utc)
        sub.current_period_start = now - timedelta(days=40)
        sub.current_period_end = now - timedelta(days=1)
        sub.status = AppSubscriptionStatus.EXPIRED.value
        db.commit()

        detail = client.get("/api/apps/whatsapp", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.EXPIRED.value
        assert detail["access"]["can_renew"] is True

        blocked = client.post(
            "/api/apps/whatsapp/connections",
            headers=headers,
            json={"connect_mode": "qr"},
        )
        assert blocked.status_code in {402, 403, 409, 422}

        member_renew = client.post(
            "/api/apps/whatsapp/renew",
            headers=_ws_headers(member, ws),
            json={},
        )
        assert member_renew.status_code == 403

        renew = client.post("/api/apps/whatsapp/renew", headers=headers, json={})
        assert renew.status_code == 200, renew.text
        paid = _complete_noop(client, renew.json())
        assert paid["status"] == "paid"
        paid2 = _complete_noop(client, renew.json())
        assert paid2["status"] == "paid"

        detail = client.get("/api/apps/whatsapp", headers=headers).json()
        assert detail["access"]["status"] == AppAccessStatus.ACTIVE.value

        started = client.post(
            "/api/apps/whatsapp/connections",
            headers=headers,
            json={"connect_mode": "qr"},
        )
        assert started.status_code == 201, started.text
