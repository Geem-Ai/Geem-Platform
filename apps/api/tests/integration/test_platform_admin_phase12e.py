"""Phase 12E — Platform Admin App Store management."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.apps_catalog.access import AppAccessService, AppAccessStatus
from app.apps_catalog.models import (
    AppBillingType,
    AppCategory,
    AppCommercialSource,
    AppLicense,
    AppLicenseStatus,
    AppPlan,
    AppPlanEntitlement,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.apps_catalog.seed import ensure_app_catalog
from app.audit.models import AuditLog
from app.billing.models import Purchase
from app.identity.models import PlatformRole, User
from tests.integration.test_apps_billing_phase9b import _seed_paid_apps


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _promote_platform_admin(db, user_id: str) -> User:
    user = db.get(User, uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _create_workspace(client, token: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def test_unauthenticated_platform_apps_401(client) -> None:
    assert client.get("/api/platform/apps").status_code == 401


def test_normal_user_platform_apps_403(client, register_user) -> None:
    user = register_user(email="normal-12e@example.com")
    res = client.get("/api/platform/apps", headers=_auth(user["access_token"]))
    assert res.status_code == 403
    assert res.json()["code"] == "platform_admin_required"


def test_platform_admin_lists_all_statuses(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-list@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])

    cat = db.scalar(select(AppCategory).where(AppCategory.slug == "analytics"))
    assert cat is not None
    draft = CatalogApp(
        slug=f"draft-fixture-{uuid.uuid4().hex[:8]}",
        name="Draft Fixture",
        short_description="draft",
        description="draft",
        category_id=cat.id,
        billing_type=AppBillingType.FREE.value,
        status=AppStatus.DRAFT.value,
        is_featured=False,
        sort_order=99,
    )
    db.add(draft)
    db.commit()

    res = client.get(
        "/api/platform/apps",
        headers=_auth(admin_user["access_token"]),
        params={"status": "draft", "search": "Draft Fixture"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    assert any(item["slug"] == draft.slug for item in body["items"])


def test_create_draft_app_and_publish(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-create@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    cat = db.scalar(select(AppCategory).where(AppCategory.slug == "productivity"))
    assert cat is not None

    slug = f"fixture-app-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/platform/apps",
        headers=_auth(admin_user["access_token"]),
        json={
            "slug": slug,
            "name": "Fixture App",
            "short_description": "Fixture",
            "description": "Fixture description",
            "category_id": str(cat.id),
            "billing_type": "free",
        },
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    plan = client.post(
        f"/api/platform/apps/{app_id}/plans",
        headers=_auth(admin_user["access_token"]),
        json={
            "code": "free",
            "name": "Free",
            "price_amount": "0.00",
            "billing_interval": "none",
            "is_default": True,
        },
    )
    assert plan.status_code == 201, plan.text

    pub = client.post(
        f"/api/platform/apps/{app_id}/publish",
        headers=_auth(admin_user["access_token"]),
        json={"reason": "Ready for tenants"},
    )
    assert pub.status_code == 200, pub.text
    assert pub.json()["status"] == "published"


def test_manual_license_grant_no_purchase(client, register_user, db) -> None:
    one_time, _sub_app, one_plan, _ = _seed_paid_apps(db)
    db.commit()
    admin_user = register_user(email="admin-12e-license@example.com")
    owner = register_user(email="owner-12e-license@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], f"ws-lic-{uuid.uuid4().hex[:6]}")

    idem = f"lic-grant-{uuid.uuid4()}"
    grant = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{one_time.id}/license/grant",
        headers=_auth(admin_user["access_token"]),
        json={
            "app_plan_id": str(one_plan.id),
            "reason": "Partner grant",
            "idempotency_key": idem,
        },
    )
    assert grant.status_code == 200, grant.text
    body = grant.json()
    assert body["access_status"] in {"entitled_not_installed", "active"}
    assert body["license_id"]

    lic = db.get(AppLicense, uuid.UUID(body["license_id"]))
    assert lic is not None
    assert lic.purchase_id is None
    assert lic.source == AppCommercialSource.PLATFORM_ADMIN.value
    assert lic.status == AppLicenseStatus.ACTIVE.value

    purchases = db.scalars(
        select(Purchase).where(Purchase.workspace_id == uuid.UUID(ws["id"]))
    ).all()
    assert purchases == []

    replay = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{one_time.id}/license/grant",
        headers=_auth(admin_user["access_token"]),
        json={
            "app_plan_id": str(one_plan.id),
            "reason": "Partner grant",
            "idempotency_key": idem,
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"] is True

    access = AppAccessService(db).resolve(uuid.UUID(ws["id"]), app_slug=one_time.slug)
    assert access.commercially_entitled


def test_manual_subscription_grant_and_revoke(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    whatsapp = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert whatsapp is not None
    plan = db.scalar(
        select(AppPlan).where(AppPlan.app_id == whatsapp.id, AppPlan.code == "line")
    )
    assert plan is not None

    admin_user = register_user(email="admin-12e-sub@example.com")
    owner = register_user(email="owner-12e-sub@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], f"ws-sub-{uuid.uuid4().hex[:6]}")

    idem = f"sub-grant-{uuid.uuid4()}"
    grant = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{whatsapp.id}/subscription/grant",
        headers=_auth(admin_user["access_token"]),
        json={
            "app_plan_id": str(plan.id),
            "reason": "Trial partner",
            "idempotency_key": idem,
        },
    )
    assert grant.status_code == 200, grant.text
    sub_id = grant.json()["subscription_id"]
    assert sub_id

    sub = db.get(AppSubscription, uuid.UUID(sub_id))
    assert sub is not None
    assert sub.latest_purchase_id is None
    assert sub.source == AppCommercialSource.PLATFORM_ADMIN.value

    access = AppAccessService(db).resolve(uuid.UUID(ws["id"]), app_slug=whatsapp.slug)
    assert access.commercially_entitled

    revoke = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{whatsapp.id}/subscription/revoke",
        headers=_auth(admin_user["access_token"]),
        json={"reason": "End trial"},
    )
    assert revoke.status_code == 200, revoke.text
    db.refresh(sub)
    assert sub.status == AppSubscriptionStatus.CANCELLED.value
    access_after = AppAccessService(db).resolve(uuid.UUID(ws["id"]), app_slug=whatsapp.slug)
    assert access_after.status == AppAccessStatus.EXPIRED


def test_workspace_apps_list(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-wsapps@example.com")
    owner = register_user(email="owner-12e-wsapps@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], f"ws-apps-{uuid.uuid4().hex[:6]}")

    res = client.get(
        f"/api/platform/workspaces/{ws['id']}/apps",
        headers=_auth(admin_user["access_token"]),
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) >= 4
    gdrive = next(i for i in items if i["app_slug"] == "google-drive")
    assert gdrive["billing_type"] == "free"
    assert "credentials" not in str(items).lower()


def test_app_detail_no_secrets(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-detail@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert app is not None

    res = client.get(
        f"/api/platform/apps/{app.id}",
        headers=_auth(admin_user["access_token"]),
    )
    assert res.status_code == 200, res.text
    text = res.text.lower()
    for secret in (
        "credentials_encrypted",
        "refresh_token",
        "access_token",
        "api_key",
    ):
        assert secret not in text


def test_license_grant_audit(client, register_user, db) -> None:
    one_time, _sub_app, one_plan, _ = _seed_paid_apps(db)
    db.commit()
    admin_user = register_user(email="admin-12e-audit@example.com")
    owner = register_user(email="owner-12e-audit@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], f"ws-audit-{uuid.uuid4().hex[:6]}")

    client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{one_time.id}/license/grant",
        headers=_auth(admin_user["access_token"]),
        json={
            "app_plan_id": str(one_plan.id),
            "reason": "Audit test",
            "idempotency_key": f"audit-{uuid.uuid4()}",
        },
    )
    db.commit()
    audits = db.scalars(
        select(AuditLog).where(AuditLog.action == "app_license.grant")
    ).all()
    assert len(audits) >= 1


def test_seeded_app_disable_forbidden(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-seeded@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "google-drive"))
    assert app is not None

    detail = client.get(
        f"/api/platform/apps/{app.id}",
        headers=_auth(admin_user["access_token"]),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["is_seeded"] is True
    assert body["disable_allowed"] is False

    disable = client.post(
        f"/api/platform/apps/{app.id}/disable",
        headers=_auth(admin_user["access_token"]),
        json={"reason": "Should not work"},
    )
    assert disable.status_code == 422, disable.text
    assert "cannot be disabled" in disable.json()["message"].lower()


def test_seeded_app_billing_type_can_change(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-seeded-bill@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "google-drive"))
    assert app is not None
    assert app.billing_type == AppBillingType.FREE.value

    updated = client.patch(
        f"/api/platform/apps/{app.id}",
        headers=_auth(admin_user["access_token"]),
        json={"billing_type": "subscription"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["billing_type"] == "subscription"
    assert body["is_seeded"] is True
    assert body["disable_allowed"] is False
    assert body["billing_type_locked"] is False

    db.refresh(app)
    assert app.billing_type == AppBillingType.SUBSCRIPTION.value


def test_subscription_extend(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    whatsapp = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert whatsapp is not None
    plan = db.scalar(
        select(AppPlan).where(AppPlan.app_id == whatsapp.id, AppPlan.code == "line")
    )
    assert plan is not None

    admin_user = register_user(email="admin-12e-extend@example.com")
    owner = register_user(email="owner-12e-extend@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    ws = _create_workspace(client, owner["access_token"], f"ws-ext-{uuid.uuid4().hex[:6]}")

    grant = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{whatsapp.id}/subscription/grant",
        headers=_auth(admin_user["access_token"]),
        json={
            "app_plan_id": str(plan.id),
            "reason": "Initial grant",
            "idempotency_key": f"sub-grant-{uuid.uuid4()}",
        },
    )
    assert grant.status_code == 200, grant.text
    sub = db.get(AppSubscription, uuid.UUID(grant.json()["subscription_id"]))
    assert sub is not None
    before_end = sub.current_period_end

    idem = f"sub-extend-{uuid.uuid4()}"
    extend = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{whatsapp.id}/subscription/extend",
        headers=_auth(admin_user["access_token"]),
        json={"reason": "Partner extension", "idempotency_key": idem},
    )
    assert extend.status_code == 200, extend.text
    db.refresh(sub)
    assert sub.current_period_end > before_end

    replay = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{whatsapp.id}/subscription/extend",
        headers=_auth(admin_user["access_token"]),
        json={"reason": "Partner extension", "idempotency_key": idem},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"] is True


def test_plan_entitlement_removal_on_update(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-ent@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    cat = db.scalar(select(AppCategory).where(AppCategory.slug == "communication"))
    assert cat is not None

    slug = f"ent-fixture-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/platform/apps",
        headers=_auth(admin_user["access_token"]),
        json={
            "slug": slug,
            "name": "Entitlement Fixture",
            "short_description": "Fixture",
            "category_id": str(cat.id),
            "billing_type": "subscription",
            "connector_key": "whatsapp",
            "connector_kind": "connector",
        },
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]

    plan_res = client.post(
        f"/api/platform/apps/{app_id}/plans",
        headers=_auth(admin_user["access_token"]),
        json={
            "code": "pro",
            "name": "Pro",
            "price_amount": "10.00",
            "billing_interval": "monthly",
            "is_default": True,
            "entitlements": [{"key": "connections", "value": 3}],
        },
    )
    assert plan_res.status_code == 201, plan_res.text
    plan_id = plan_res.json()["id"]

    ent = db.scalar(
        select(AppPlanEntitlement).where(
            AppPlanEntitlement.app_plan_id == uuid.UUID(plan_id),
            AppPlanEntitlement.key == "connections",
        )
    )
    assert ent is not None

    updated = client.patch(
        f"/api/platform/apps/{app_id}/plans/{plan_id}",
        headers=_auth(admin_user["access_token"]),
        json={"entitlements": [], "reason": "Remove limits"},
    )
    assert updated.status_code == 200, updated.text
    ent_after = db.scalar(
        select(AppPlanEntitlement).where(
            AppPlanEntitlement.app_plan_id == uuid.UUID(plan_id),
            AppPlanEntitlement.key == "connections",
        )
    )
    assert ent_after is None


def test_plan_code_can_be_updated(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-plan-code@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert app is not None
    plan = db.scalar(
        select(AppPlan).where(AppPlan.app_id == app.id, AppPlan.code == "line")
    )
    assert plan is not None

    updated = client.patch(
        f"/api/platform/apps/{app.id}/plans/{plan.id}",
        headers=_auth(admin_user["access_token"]),
        json={"code": "line-renamed"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["code"] == "line-renamed"

    db.refresh(plan)
    assert plan.code == "line-renamed"


def test_plan_update_without_entitlement_change_no_reason(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-plan-save@example.com")
    owner = register_user(email="owner-12e-plan-save@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert app is not None
    plan = db.scalar(
        select(AppPlan).where(AppPlan.app_id == app.id, AppPlan.code == "line")
    )
    assert plan is not None
    ws = _create_workspace(client, owner["access_token"], f"ws-plan-{uuid.uuid4().hex[:6]}")
    grant = client.post(
        f"/api/platform/workspaces/{ws['id']}/apps/{app.id}/subscription/grant",
        headers=_auth(admin_user["access_token"]),
        json={
            "app_plan_id": str(plan.id),
            "reason": "Seed commercial history",
            "idempotency_key": f"plan-save-{uuid.uuid4()}",
        },
    )
    assert grant.status_code == 200, grant.text

    updated = client.patch(
        f"/api/platform/apps/{app.id}/plans/{plan.id}",
        headers=_auth(admin_user["access_token"]),
        json={
            "name": "WhatsApp Line Updated",
            "entitlements": [{"key": "connections", "value": 1}],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "WhatsApp Line Updated"


def test_billing_type_change_to_free_normalizes_plans(client, register_user, db) -> None:
    ensure_app_catalog(db)
    db.commit()
    admin_user = register_user(email="admin-12e-free-plans@example.com")
    _promote_platform_admin(db, admin_user["user"]["id"])
    app = db.scalar(select(CatalogApp).where(CatalogApp.slug == "whatsapp"))
    assert app is not None
    plans = db.scalars(select(AppPlan).where(AppPlan.app_id == app.id)).all()
    assert plans
    assert any(p.billing_interval == "monthly" for p in plans)

    updated = client.patch(
        f"/api/platform/apps/{app.id}",
        headers=_auth(admin_user["access_token"]),
        json={"billing_type": "free"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["billing_type"] == "free"

    for plan in db.scalars(select(AppPlan).where(AppPlan.app_id == app.id)):
        db.refresh(plan)
        assert plan.price_amount == Decimal("0.00")
        assert plan.billing_interval == "none"
