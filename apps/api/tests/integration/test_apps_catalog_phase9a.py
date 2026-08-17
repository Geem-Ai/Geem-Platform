"""Phase 9A — App Store catalog + free install lifecycle."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.apps_catalog.models import (
    AppBillingType,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.seed import ensure_app_catalog, seed_app_catalog
from app.apps_catalog.service import AppInstallationService
from app.workspaces.models import WorkspaceMembership, WorkspaceRole


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _create_workspace(client: TestClient, user: dict, slug: str, name: str = "Apps") -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_member(db, workspace_id: str, user_id: str, role: WorkspaceRole) -> None:
    db.add(
        WorkspaceMembership(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id),
            role=role.value,
        )
    )
    db.commit()


def _seed(db) -> None:
    ensure_app_catalog(db)
    db.commit()


# --- catalog ---


def test_list_published_and_coming_soon_apps(client, register_user, db) -> None:
    _seed(db)
    user = register_user(email="apps-list@example.com")
    ws = _create_workspace(client, user, "apps-list")

    res = client.get("/api/apps", headers=_ws_headers(user, ws))
    assert res.status_code == 200, res.text
    body = res.json()
    slugs = {item["slug"] for item in body["items"]}
    assert "google-drive" in slugs
    assert "microsoft-onedrive" in slugs
    assert "whatsapp" in slugs
    assert "openwa" not in slugs
    assert body["total"] >= 3

    drive = next(i for i in body["items"] if i["slug"] == "google-drive")
    assert drive["billing_type"] == "free"
    assert drive["status"] == "published"
    assert drive["can_install"] is True
    assert drive["access_requirement"] == "free"
    assert drive["plans"][0]["price_amount"] == "0.00"
    assert drive["plans"][0]["currency"] == "SAR"
    assert "config_encrypted" not in drive
    assert "metadata" not in drive

    whatsapp = next(i for i in body["items"] if i["slug"] == "whatsapp")
    assert whatsapp["name"] == "WhatsApp"
    assert whatsapp["billing_type"] == "subscription"
    assert whatsapp["status"] == "coming_soon"
    assert whatsapp["can_install"] is False
    assert whatsapp["access_requirement"] == "unavailable"


def test_draft_and_disabled_apps_hidden(client, register_user, db) -> None:
    _seed(db)
    from app.apps_catalog.repository import AppCatalogRepository

    cat = AppCatalogRepository(db).get_category_by_slug("knowledge")
    assert cat is not None
    db.add(
        CatalogApp(
            slug="secret-draft",
            name="Draft",
            short_description="hidden",
            description=None,
            category_id=cat.id,
            billing_type=AppBillingType.FREE.value,
            status=AppStatus.DRAFT.value,
            is_featured=False,
            sort_order=99,
            extra={},
        )
    )
    db.add(
        CatalogApp(
            slug="disabled-app",
            name="Disabled",
            short_description="hidden",
            description=None,
            category_id=cat.id,
            billing_type=AppBillingType.FREE.value,
            status=AppStatus.DISABLED.value,
            is_featured=False,
            sort_order=100,
            extra={},
        )
    )
    db.commit()

    user = register_user(email="apps-hidden@example.com")
    ws = _create_workspace(client, user, "apps-hidden")
    res = client.get("/api/apps", headers=_ws_headers(user, ws))
    slugs = {i["slug"] for i in res.json()["items"]}
    assert "secret-draft" not in slugs
    assert "disabled-app" not in slugs

    assert (
        client.get("/api/apps/secret-draft", headers=_ws_headers(user, ws)).status_code
        == 404
    )


def test_get_app_by_slug_and_category_filter(client, register_user, db) -> None:
    _seed(db)
    user = register_user(email="apps-detail@example.com")
    ws = _create_workspace(client, user, "apps-detail")

    detail = client.get("/api/apps/google-drive", headers=_ws_headers(user, ws))
    assert detail.status_code == 200
    body = detail.json()
    assert body["slug"] == "google-drive"
    assert body["category"]["slug"] == "knowledge"
    assert body["description"]
    assert body["plans"][0]["code"] == "free"

    cats = client.get("/api/apps/categories", headers=_ws_headers(user, ws))
    assert cats.status_code == 200
    assert any(c["slug"] == "knowledge" for c in cats.json())

    filtered = client.get(
        "/api/apps",
        headers=_ws_headers(user, ws),
        params={"category": "communication"},
    )
    assert filtered.status_code == 200
    assert all(i["category"]["slug"] == "communication" for i in filtered.json()["items"])
    assert any(i["slug"] == "whatsapp" for i in filtered.json()["items"])

    billing = client.get(
        "/api/apps",
        headers=_ws_headers(user, ws),
        params={"billing_type": "free"},
    )
    assert all(i["billing_type"] == "free" for i in billing.json()["items"])


def test_seed_is_idempotent(db) -> None:
    first_cats, first_apps = seed_app_catalog(db)
    db.commit()
    second_cats, second_apps = seed_app_catalog(db)
    db.commit()
    assert {c.slug for c in first_cats} == {c.slug for c in second_cats}
    assert {a.slug for a in first_apps} == {a.slug for a in second_apps}
    assert len(second_apps) == len(first_apps)


# --- installation ---


def test_owner_installs_and_uninstalls_free_app(client, register_user, db) -> None:
    _seed(db)
    user = register_user(email="apps-owner@example.com")
    ws = _create_workspace(client, user, "apps-owner")
    headers = _ws_headers(user, ws)

    install = client.post("/api/apps/google-drive/install", headers=headers)
    assert install.status_code == 201, install.text
    body = install.json()
    assert body["status"] == "active"
    assert body["app"]["slug"] == "google-drive"
    assert "config_encrypted" not in body
    installation_id = body["id"]

    listed = client.get("/api/apps/installations", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == installation_id

    detail = client.get("/api/apps/google-drive", headers=headers)
    assert detail.json()["can_install"] is False
    assert detail.json()["can_uninstall"] is True
    assert detail.json()["installation_status"] == "active"

    # Duplicate install → conflict
    again = client.post("/api/apps/google-drive/install", headers=headers)
    assert again.status_code == 409
    assert again.json()["code"] == "app_already_installed"

    uninstall = client.delete("/api/apps/google-drive/install", headers=headers)
    assert uninstall.status_code == 200
    assert uninstall.json()["status"] == "uninstalled"

    empty = client.get("/api/apps/installations", headers=headers)
    assert empty.json()["total"] == 0

    # Reinstall reuses lifecycle row
    reinstall = client.post("/api/apps/google-drive/install", headers=headers)
    assert reinstall.status_code == 201
    assert reinstall.json()["id"] == installation_id
    assert reinstall.json()["status"] == "active"


def test_admin_can_install_member_cannot(client, register_user, db) -> None:
    _seed(db)
    owner = register_user(email="apps-admin-owner@example.com")
    admin = register_user(email="apps-admin@example.com")
    member = register_user(email="apps-member@example.com")
    ws = _create_workspace(client, owner, "apps-roles")
    _add_member(db, ws["id"], admin["user"]["id"], WorkspaceRole.ADMIN)
    _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)

    ok = client.post(
        "/api/apps/microsoft-onedrive/install",
        headers=_ws_headers(admin, ws),
    )
    assert ok.status_code == 201, ok.text

    denied = client.post(
        "/api/apps/google-drive/install",
        headers=_ws_headers(member, ws),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "insufficient_workspace_role"

    # Member can browse
    browse = client.get("/api/apps", headers=_ws_headers(member, ws))
    assert browse.status_code == 200
    drive = next(i for i in browse.json()["items"] if i["slug"] == "google-drive")
    assert drive["can_install"] is False

    uninstall_denied = client.delete(
        "/api/apps/microsoft-onedrive/install",
        headers=_ws_headers(member, ws),
    )
    assert uninstall_denied.status_code == 403


def test_paid_and_coming_soon_cannot_install(client, register_user, db) -> None:
    _seed(db)
    user = register_user(email="apps-paid@example.com")
    ws = _create_workspace(client, user, "apps-paid")
    headers = _ws_headers(user, ws)

    coming = client.post("/api/apps/whatsapp/install", headers=headers)
    assert coming.status_code == 409
    assert coming.json()["code"] == "app_not_available"

    # Inject a published subscription app without inventing WhatsApp prices
    from app.apps_catalog.repository import AppCatalogRepository

    cat = AppCatalogRepository(db).get_category_by_slug("communication")
    assert cat is not None
    paid = CatalogApp(
        slug="paid-demo",
        name="Paid Demo",
        short_description="requires purchase",
        description=None,
        category_id=cat.id,
        billing_type=AppBillingType.ONE_TIME.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=False,
        sort_order=90,
        extra={},
    )
    db.add(paid)
    db.commit()

    billing = client.post("/api/apps/paid-demo/install", headers=headers)
    assert billing.status_code == 402
    assert billing.json()["code"] == "app_billing_required"


def test_cross_workspace_isolation(client, register_user, db) -> None:
    _seed(db)
    user_a = register_user(email="apps-a@example.com")
    user_b = register_user(email="apps-b@example.com")
    ws_a = _create_workspace(client, user_a, "apps-iso-a")
    ws_b = _create_workspace(client, user_b, "apps-iso-b")

    installed = client.post(
        "/api/apps/google-drive/install",
        headers=_ws_headers(user_a, ws_a),
    )
    assert installed.status_code == 201
    installation_id = installed.json()["id"]

    # B cannot read A's installation by id
    leak = client.get(
        f"/api/apps/installations/{installation_id}",
        headers=_ws_headers(user_b, ws_b),
    )
    assert leak.status_code == 404
    assert leak.json()["code"] == "app_installation_not_found"

    # B list does not include A's install
    listed_b = client.get("/api/apps/installations", headers=_ws_headers(user_b, ws_b))
    assert listed_b.json()["total"] == 0

    # B cannot uninstall via slug in B context (not installed there)
    un = client.delete(
        "/api/apps/google-drive/install",
        headers=_ws_headers(user_b, ws_b),
    )
    assert un.status_code == 409
    assert un.json()["code"] == "app_not_installed"

    # A still has it
    listed_a = client.get("/api/apps/installations", headers=_ws_headers(user_a, ws_a))
    assert listed_a.json()["total"] == 1


def test_installation_config_encrypted_not_in_api(client, register_user, db) -> None:
    _seed(db)
    user = register_user(email="apps-crypto@example.com")
    ws = _create_workspace(client, user, "apps-crypto")
    headers = _ws_headers(user, ws)

    installed = client.post("/api/apps/google-drive/install", headers=headers)
    installation_id = uuid.UUID(installed.json()["id"])

    svc = AppInstallationService(db)
    svc.set_encrypted_config(
        workspace_id=uuid.UUID(ws["id"]),
        installation_id=installation_id,
        payload={"future_token": "super-secret-value"},
    )
    db.commit()

    raw = svc.repo.get_installation_for_workspace(uuid.UUID(ws["id"]), installation_id)
    assert raw is not None
    assert raw.config_encrypted is not None
    assert "super-secret-value" not in raw.config_encrypted

    decrypted = svc.get_decrypted_config(
        workspace_id=uuid.UUID(ws["id"]),
        installation_id=installation_id,
    )
    assert decrypted == {"future_token": "super-secret-value"}

    api = client.get(f"/api/apps/installations/{installation_id}", headers=headers)
    assert api.status_code == 200
    assert "config_encrypted" not in api.text
    assert "super-secret-value" not in api.text

    catalog = client.get("/api/apps/google-drive", headers=headers)
    assert "config_encrypted" not in catalog.text
    assert "super-secret-value" not in catalog.text


def test_installed_filter(client, register_user, db) -> None:
    _seed(db)
    user = register_user(email="apps-filter@example.com")
    ws = _create_workspace(client, user, "apps-filter")
    headers = _ws_headers(user, ws)
    client.post("/api/apps/google-drive/install", headers=headers)

    only = client.get("/api/apps", headers=headers, params={"installed": True})
    assert only.status_code == 200
    assert {i["slug"] for i in only.json()["items"]} == {"google-drive"}

    not_inst = client.get("/api/apps", headers=headers, params={"installed": False})
    slugs = {i["slug"] for i in not_inst.json()["items"]}
    assert "google-drive" not in slugs
    assert "microsoft-onedrive" in slugs
