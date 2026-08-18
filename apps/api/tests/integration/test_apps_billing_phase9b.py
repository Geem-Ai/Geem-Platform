"""Phase 9B — App billing: licenses, subscriptions, access, fulfillment."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.apps_catalog.access import AppAccessService, AppAccessStatus
from app.apps_catalog.calendar import add_calendar_months, compute_renewal_period
from app.apps_catalog.entitlements import AppEntitlementService
from app.apps_catalog.models import (
    AppBillingType,
    AppCategory,
    AppInstallation,
    AppInstallationStatus,
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
from app.billing.models import Purchase, PurchaseKind
from app.workspaces.models import WorkspaceMembership, WorkspaceRole


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client, user: dict, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _ws_headers(user: dict, workspace: dict) -> dict[str, str]:
    return _auth(user["access_token"], **{"X-Workspace-Id": workspace["id"]})


def _return_token(redirect_url: str) -> str:
    return parse_qs(urlparse(redirect_url).query)["rt"][0]


def _as_test_path(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _add_member(db, workspace_id: str, user_id: str, role=WorkspaceRole.MEMBER) -> None:
    from tests.support.rbac import add_workspace_member
    key = role.value if hasattr(role, "value") else role
    add_workspace_member(db, workspace_id, user_id, key)



def _seed_paid_apps(db) -> tuple[CatalogApp, CatalogApp, AppPlan, list[AppPlan]]:
    """Test-only catalog fixtures — never production seed."""
    ensure_app_catalog(db)
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

    one_time = CatalogApp(
        slug=f"test-analytics-{uuid.uuid4().hex[:8]}",
        name="Test Analytics",
        short_description="Test one-time app",
        description="Test fixture only",
        category_id=cat.id,
        billing_type=AppBillingType.ONE_TIME.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=False,
        sort_order=90,
        icon_url=None,
        extra={"test_fixture": True},
    )
    db.add(one_time)
    db.flush()
    one_plan = AppPlan(
        app_id=one_time.id,
        code="lifetime",
        name="Lifetime",
        billing_interval=AppPlanBillingInterval.NONE.value,
        price_amount=Decimal("79.00"),
        currency="SAR",
        is_default=True,
        is_active=True,
        sort_order=0,
    )
    db.add(one_plan)
    db.flush()

    sub_app = CatalogApp(
        slug=f"test-messenger-{uuid.uuid4().hex[:8]}",
        name="Test Messenger",
        short_description="Test subscription app",
        description="Test fixture only",
        category_id=cat.id,
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.PUBLISHED.value,
        is_featured=False,
        sort_order=91,
        icon_url=None,
        extra={"test_fixture": True},
    )
    db.add(sub_app)
    db.flush()
    plans: list[AppPlan] = []
    for code, name, price, order in [
        ("starter", "Starter", "49.00", 0),
        ("pro", "Pro", "149.00", 1),
        ("business", "Business", "299.00", 2),
    ]:
        plan = AppPlan(
            app_id=sub_app.id,
            code=code,
            name=name,
            billing_interval=AppPlanBillingInterval.MONTHLY.value,
            price_amount=Decimal(price),
            currency="SAR",
            is_default=code == "pro",
            is_active=True,
            sort_order=order,
        )
        db.add(plan)
        db.flush()
        db.add(
            AppPlanEntitlement(
                app_plan_id=plan.id,
                key="whatsapp_sessions",
                value=1 if code == "starter" else (3 if code == "pro" else 10),
            )
        )
        plans.append(plan)
    db.commit()
    db.refresh(one_time)
    db.refresh(sub_app)
    db.refresh(one_plan)
    for p in plans:
        db.refresh(p)
    return one_time, sub_app, one_plan, plans


def _complete_noop(client, checkout: dict) -> dict:
    rt = _return_token(checkout["redirect_url"])
    res = client.get(
        f"/api/billing/return/noop/{checkout['purchase_id']}",
        params={"rt": rt},
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def owner_ws(client, register_user):
    user = register_user(email="owner9b@example.com")
    ws = _create_workspace(client, user, "Acme 9B", f"acme-9b-{uuid.uuid4().hex[:6]}")
    return user, ws


class TestAppCalendar:
    def test_add_calendar_months_clamps_day(self):
        start = datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)
        assert add_calendar_months(start, 1) == datetime(
            2026, 2, 28, 12, 0, tzinfo=timezone.utc
        )

    def test_active_renewal_extends_from_end(self):
        start = datetime(2026, 8, 17, tzinfo=timezone.utc)
        end = datetime(2026, 9, 17, tzinfo=timezone.utc)
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        new_start, new_end = compute_renewal_period(
            current_period_start=start, current_period_end=end, now=now
        )
        assert new_start == start
        assert new_end == datetime(2026, 10, 17, tzinfo=timezone.utc)

    def test_expired_renewal_starts_now(self):
        start = datetime(2026, 7, 17, tzinfo=timezone.utc)
        end = datetime(2026, 8, 17, tzinfo=timezone.utc)
        now = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
        new_start, new_end = compute_renewal_period(
            current_period_start=start, current_period_end=end, now=now
        )
        assert new_start == now
        assert new_end == datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)


class TestAppOneTimeBilling:
    def test_owner_checkout_amount_from_plan(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        res = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["kind"] == PurchaseKind.APP_ONE_TIME.value
        assert body["amount"] == "79.00"
        assert body["currency"] == "SAR"
        assert body["redirect_url"]

    def test_member_cannot_purchase(self, client, owner_ws, db, register_user):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        member = register_user(email="member9b@example.com")
        _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
        res = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(member, ws),
            json={"plan_id": str(plan.id)},
        )
        assert res.status_code == 403

    def test_admin_can_purchase(self, client, owner_ws, db, register_user):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        admin = register_user(email="admin9b@example.com")
        _add_member(db, ws["id"], admin["user"]["id"], WorkspaceRole.ADMIN)
        res = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(admin, ws),
            json={"plan_id": str(plan.id)},
        )
        assert res.status_code == 200, res.text

    def test_noop_grants_license_and_install(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        paid = _complete_noop(client, checkout)
        assert paid["status"] == "paid"

        detail = client.get(
            f"/api/apps/{one_time.slug}", headers=_ws_headers(user, ws)
        ).json()
        assert detail["access"]["status"] == "active"
        assert detail["installation_status"] == "active"
        assert detail["can_install"] is False

        lic = db.scalar(
            select(AppLicense).where(
                AppLicense.workspace_id == uuid.UUID(ws["id"]),
                AppLicense.app_id == one_time.id,
            )
        )
        assert lic is not None
        assert lic.status == AppLicenseStatus.ACTIVE.value
        assert lic.purchase_id == uuid.UUID(paid["id"])

    def test_duplicate_return_idempotent(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)
        _complete_noop(client, checkout)
        count = len(
            list(
                db.scalars(
                    select(AppLicense).where(
                        AppLicense.workspace_id == uuid.UUID(ws["id"]),
                        AppLicense.app_id == one_time.id,
                    )
                )
            )
        )
        assert count == 1

    def test_second_checkout_while_licensed_rejected(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)
        again = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        )
        assert again.status_code == 409
        assert again.json()["code"] == "app_already_licensed"

    def test_uninstall_preserves_license_reinstall_free(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)

        un = client.delete(
            f"/api/apps/{one_time.slug}/install", headers=_ws_headers(user, ws)
        )
        assert un.status_code == 200
        detail = client.get(
            f"/api/apps/{one_time.slug}", headers=_ws_headers(user, ws)
        ).json()
        assert detail["access"]["status"] == "entitled_not_installed"
        assert detail["can_install"] is True
        assert detail["access"]["can_purchase"] is False

        rein = client.post(
            f"/api/apps/{one_time.slug}/install", headers=_ws_headers(user, ws)
        )
        assert rein.status_code == 201
        lic = db.scalar(
            select(AppLicense).where(
                AppLicense.workspace_id == uuid.UUID(ws["id"]),
                AppLicense.app_id == one_time.id,
            )
        )
        assert lic.status == AppLicenseStatus.ACTIVE.value

    def test_price_snapshot_immutable(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        assert checkout["amount"] == "79.00"
        plan.price_amount = Decimal("199.00")
        db.commit()
        paid = _complete_noop(client, checkout)
        assert paid["amount"] == "79.00"
        purchase = db.get(Purchase, uuid.UUID(paid["id"]))
        assert purchase is not None
        assert purchase.amount == Decimal("79.00")

    def test_plan_must_belong_to_app(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, _plan, sub_plans = _seed_paid_apps(db)
        res = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(sub_plans[0].id)},
        )
        assert res.status_code == 404
        assert res.json()["code"] == "app_plan_not_found"

    def test_workspace_isolation(self, client, owner_ws, db, register_user):
        user_a, ws_a = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user_a, ws_a),
            json={"plan_id": str(plan.id)},
        ).json()
        paid = _complete_noop(client, checkout)

        user_b = register_user(email="other9b@example.com")
        ws_b = _create_workspace(client, user_b, "Other", f"other-9b-{uuid.uuid4().hex[:6]}")
        detail_b = client.get(
            f"/api/apps/{one_time.slug}", headers=_ws_headers(user_b, ws_b)
        ).json()
        assert detail_b["access"]["status"] == "not_entitled"
        hist = client.get(
            f"/api/billing/purchases/{paid['id']}",
            headers=_ws_headers(user_b, ws_b),
        )
        assert hist.status_code == 404


class TestAppSubscriptionBilling:
    def test_initial_subscribe_and_period(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        pro = next(p for p in plans if p.code == "pro")
        before = datetime.now(timezone.utc)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(pro.id)},
        ).json()
        assert checkout["amount"] == "149.00"
        paid = _complete_noop(client, checkout)
        assert paid["status"] == "paid"
        assert paid["kind"] == PurchaseKind.APP_SUBSCRIPTION.value

        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        assert sub.status == AppSubscriptionStatus.ACTIVE.value
        assert sub.app_plan_id == pro.id
        assert sub.current_period_end > before
        assert abs(
            (sub.current_period_end - add_calendar_months(sub.current_period_start, 1)).total_seconds()
        ) < 2

        detail = client.get(
            f"/api/apps/{sub_app.slug}", headers=_ws_headers(user, ws)
        ).json()
        assert detail["access"]["status"] == "active"
        assert detail["access"]["plan_code"] == "pro"
        assert detail["access"]["can_renew"] is True
        assert detail["installation_status"] == "active"

    def test_member_cannot_subscribe(self, client, owner_ws, db, register_user):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        member = register_user(email="mem-sub9b@example.com")
        _add_member(db, ws["id"], member["user"]["id"], WorkspaceRole.MEMBER)
        res = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(member, ws),
            json={"plan_id": str(plans[1].id)},
        )
        assert res.status_code == 403

    def test_expiration_by_time_without_status_cleanup(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)
        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        sub.current_period_end = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()

        access = AppAccessService(db).resolve(
            uuid.UUID(ws["id"]), app_slug=sub_app.slug, can_manage=True
        )
        assert access.status == AppAccessStatus.EXPIRED
        assert access.commercially_entitled is False

        client.delete(
            f"/api/apps/{sub_app.slug}/install", headers=_ws_headers(user, ws)
        )
        rein = client.post(
            f"/api/apps/{sub_app.slug}/install", headers=_ws_headers(user, ws)
        )
        assert rein.status_code == 402
        assert rein.json()["code"] == "app_subscription_expired"

    def test_active_renewal_extends_end(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)
        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        old_end = sub.current_period_end
        old_start = sub.current_period_start

        renew = client.post(
            f"/api/apps/{sub_app.slug}/renew",
            headers=_ws_headers(user, ws),
            json={},
        ).json()
        assert renew["kind"] == PurchaseKind.APP_SUBSCRIPTION_RENEWAL.value
        _complete_noop(client, renew)
        db.refresh(sub)
        assert sub.current_period_start == old_start
        assert sub.current_period_end == add_calendar_months(old_end, 1)

    def test_same_purchase_replay_adds_zero(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)
        renew = client.post(
            f"/api/apps/{sub_app.slug}/renew",
            headers=_ws_headers(user, ws),
            json={},
        ).json()
        _complete_noop(client, renew)
        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        end_after = sub.current_period_end
        _complete_noop(client, renew)
        db.refresh(sub)
        assert sub.current_period_end == end_after

    def test_conflicting_plan_renewal_rejected(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)
        res = client.post(
            f"/api/apps/{sub_app.slug}/renew",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[2].id)},
        )
        assert res.status_code == 409
        assert res.json()["code"] == "app_plan_mismatch"

    def test_plan_entitlements_resolve(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)
        value = AppEntitlementService(db).get(
            uuid.UUID(ws["id"]),
            app_slug=sub_app.slug,
            key="whatsapp_sessions",
        )
        assert value == 3

    def test_valid_subscription_can_reinstall(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[0].id)},
        ).json()
        _complete_noop(client, checkout)
        client.delete(
            f"/api/apps/{sub_app.slug}/install", headers=_ws_headers(user, ws)
        )
        rein = client.post(
            f"/api/apps/{sub_app.slug}/install", headers=_ws_headers(user, ws)
        )
        assert rein.status_code == 201

    def test_separate_renewals_grant_two_months(self, client, owner_ws, db):
        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)
        renew_a = client.post(
            f"/api/apps/{sub_app.slug}/renew",
            headers=_ws_headers(user, ws),
            json={},
        ).json()
        renew_b = client.post(
            f"/api/apps/{sub_app.slug}/renew",
            headers=_ws_headers(user, ws),
            json={},
        ).json()
        _complete_noop(client, renew_a)
        _complete_noop(client, renew_b)
        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        # initial + 2 renewals = 3 months from start
        expected = add_calendar_months(sub.current_period_start, 3)
        assert abs((sub.current_period_end - expected).total_seconds()) < 2

    def test_concurrent_fulfill_does_not_lose_month(self, client, owner_ws, db):
        """Two distinct purchases fulfilled under row locks each add one month."""
        from app.apps_catalog.commerce import AppCommerceService
        from app.billing.models import Purchase, PurchaseStatus
        from tests.conftest import TestingSessionLocal

        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)

        renew_ids: list[uuid.UUID] = []
        for _ in range(2):
            renew = client.post(
                f"/api/apps/{sub_app.slug}/renew",
                headers=_ws_headers(user, ws),
                json={},
            ).json()
            renew_ids.append(uuid.UUID(renew["purchase_id"]))

        barrier = threading.Barrier(2, timeout=10)
        errors: list[BaseException] = []

        def worker(purchase_id: uuid.UUID) -> None:
            session = TestingSessionLocal()
            try:
                purchase = session.get(Purchase, purchase_id)
                assert purchase is not None
                barrier.wait()
                AppCommerceService(session, billing=False).fulfill_subscription_purchase(
                    purchase
                )
                purchase.status = PurchaseStatus.PAID.value
                session.commit()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
                session.rollback()
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(pid,)) for pid in renew_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        db.expire_all()
        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        expected = add_calendar_months(sub.current_period_start, 3)
        assert abs((sub.current_period_end - expected).total_seconds()) < 2


class TestAppAccessResolver:
    def test_matrix(self, client, owner_ws, db):
        user, ws = owner_ws
        ensure_app_catalog(db)
        one_time, sub_app, one_plan, plans = _seed_paid_apps(db)
        ws_id = uuid.UUID(ws["id"])
        access = AppAccessService(db)

        # free + uninstalled
        drive = access.resolve(ws_id, app_slug="google-drive", can_manage=True)
        assert drive.status == AppAccessStatus.ENTITLED_NOT_INSTALLED
        client.post("/api/apps/google-drive/install", headers=_ws_headers(user, ws))
        drive2 = access.resolve(ws_id, app_slug="google-drive", can_manage=True)
        assert drive2.status == AppAccessStatus.ACTIVE

        # one_time no license
        ot = access.resolve(ws_id, app_slug=one_time.slug, can_manage=True)
        assert ot.status == AppAccessStatus.NOT_ENTITLED

        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(one_plan.id)},
        ).json()
        _complete_noop(client, checkout)
        ot_inst = access.resolve(ws_id, app_slug=one_time.slug, can_manage=True)
        assert ot_inst.status == AppAccessStatus.ACTIVE
        client.delete(
            f"/api/apps/{one_time.slug}/install", headers=_ws_headers(user, ws)
        )
        ot_unin = access.resolve(ws_id, app_slug=one_time.slug, can_manage=True)
        assert ot_unin.status == AppAccessStatus.ENTITLED_NOT_INSTALLED

        # subscription
        checkout2 = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[0].id)},
        ).json()
        _complete_noop(client, checkout2)
        sub_a = access.resolve(ws_id, app_slug=sub_app.slug, can_manage=True)
        assert sub_a.status == AppAccessStatus.ACTIVE
        client.delete(
            f"/api/apps/{sub_app.slug}/install", headers=_ws_headers(user, ws)
        )
        sub_u = access.resolve(ws_id, app_slug=sub_app.slug, can_manage=True)
        assert sub_u.status == AppAccessStatus.ENTITLED_NOT_INSTALLED

        row = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == ws_id,
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert row is not None
        row.current_period_end = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        # still installed? reinstall was undone — install while expired blocked;
        # force install row active for matrix
        
        inst = db.scalar(
            select(AppInstallation).where(
                AppInstallation.workspace_id == ws_id,
                AppInstallation.app_id == sub_app.id,
            )
        )
        assert inst is not None
        inst.status = AppInstallationStatus.ACTIVE.value
        db.commit()
        expired_installed = access.resolve(ws_id, app_slug=sub_app.slug, can_manage=True)
        assert expired_installed.status == AppAccessStatus.EXPIRED
        inst.status = AppInstallationStatus.UNINSTALLED.value
        db.commit()
        expired_unin = access.resolve(ws_id, app_slug=sub_app.slug, can_manage=True)
        assert expired_unin.status == AppAccessStatus.EXPIRED


class TestFreeAppsRegression:
    def test_free_install_no_purchase(self, client, owner_ws, db):
        user, ws = owner_ws
        ensure_app_catalog(db)
        before = len(
            list(
                db.scalars(
                    select(Purchase).where(Purchase.workspace_id == uuid.UUID(ws["id"]))
                )
            )
        )
        res = client.post(
            "/api/apps/google-drive/install", headers=_ws_headers(user, ws)
        )
        assert res.status_code == 201
        after = len(
            list(
                db.scalars(
                    select(Purchase).where(Purchase.workspace_id == uuid.UUID(ws["id"]))
                )
            )
        )
        assert after == before


class TestBillingHistoryAppKinds:
    def test_history_labels(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, sub_app, plan, plans = _seed_paid_apps(db)
        c1 = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, c1)
        c2 = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, c2)
        hist = client.get(
            "/api/billing/purchases", headers=_ws_headers(user, ws)
        ).json()
        kinds = {item["kind"] for item in hist["items"]}
        assert PurchaseKind.APP_ONE_TIME.value in kinds
        assert PurchaseKind.APP_SUBSCRIPTION.value in kinds
        names = [item["item_name"] for item in hist["items"]]
        assert any(n and "Test Analytics" in n for n in names)
        assert any(n and "Test Messenger" in n for n in names)


class TestAppCommerceHardening:
    """P1–P3 audit fixes: open checkout guard, period stack, revoke, unpublished reinstall."""

    def test_second_checkout_while_pending_rejected(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        first = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        )
        assert first.status_code == 200, first.text
        second = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        )
        assert second.status_code == 409
        assert second.json()["code"] == "app_checkout_in_progress"

    def test_subscribe_while_active_period_extends(
        self, client, owner_ws, db
    ):
        from app.apps_catalog.commerce import AppCommerceService
        from app.billing.models import PurchaseStatus
        from tests.conftest import TestingSessionLocal

        user, ws = owner_ws
        _one, sub_app, _op, plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{sub_app.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plans[1].id)},
        ).json()
        _complete_noop(client, checkout)

        sub = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub is not None
        original_start = sub.current_period_start
        original_end = sub.current_period_end

        # Simulate a second verified initial subscribe (race survivor).
        purchase = Purchase(
            workspace_id=uuid.UUID(ws["id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
            kind=PurchaseKind.APP_SUBSCRIPTION.value,
            status=PurchaseStatus.REDIRECTED.value,
            amount=Decimal("149.00"),
            currency="SAR",
            payment_gateway_config_id=db.scalar(
                select(Purchase.payment_gateway_config_id).where(
                    Purchase.id == uuid.UUID(checkout["purchase_id"])
                )
            ),
            cart_id=f"race-{uuid.uuid4().hex[:10]}",
            return_token_hash="x" * 64,
            payload={
                "kind": PurchaseKind.APP_SUBSCRIPTION.value,
                "commercial_action": "subscribe",
                "app_id": str(sub_app.id),
                "app_slug": sub_app.slug,
                "app_plan_id": str(plans[1].id),
                "plan_id": str(plans[1].id),
            },
        )
        db.add(purchase)
        db.commit()
        db.refresh(purchase)

        session = TestingSessionLocal()
        try:
            row = session.get(Purchase, purchase.id)
            assert row is not None
            AppCommerceService(session, billing=False).fulfill_subscription_purchase(row)
            session.commit()
        finally:
            session.close()

        db.expire_all()
        sub2 = db.scalar(
            select(AppSubscription).where(
                AppSubscription.workspace_id == uuid.UUID(ws["id"]),
                AppSubscription.app_id == sub_app.id,
            )
        )
        assert sub2 is not None
        assert sub2.current_period_start == original_start
        assert abs(
            (sub2.current_period_end - add_calendar_months(original_end, 1)).total_seconds()
        ) < 2

    def test_revoked_license_reactivated_on_fulfill(self, client, owner_ws, db):
        from app.apps_catalog.commerce import AppCommerceService
        from app.billing.models import PurchaseStatus
        from tests.conftest import TestingSessionLocal

        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        paid = _complete_noop(client, checkout)

        lic = db.scalar(
            select(AppLicense).where(
                AppLicense.workspace_id == uuid.UUID(ws["id"]),
                AppLicense.app_id == one_time.id,
            )
        )
        assert lic is not None
        lic.status = AppLicenseStatus.REVOKED.value
        lic.revoked_at = datetime.now(timezone.utc)
        db.commit()

        # New purchase after revoke
        gateway_id = db.scalar(
            select(Purchase.payment_gateway_config_id).where(
                Purchase.id == uuid.UUID(paid["id"])
            )
        )
        purchase = Purchase(
            workspace_id=uuid.UUID(ws["id"]),
            actor_id=uuid.UUID(user["user"]["id"]),
            kind=PurchaseKind.APP_ONE_TIME.value,
            status=PurchaseStatus.REDIRECTED.value,
            amount=Decimal("79.00"),
            currency="SAR",
            payment_gateway_config_id=gateway_id,
            cart_id=f"rev-{uuid.uuid4().hex[:10]}",
            return_token_hash="y" * 64,
            payload={
                "kind": PurchaseKind.APP_ONE_TIME.value,
                "commercial_action": "purchase",
                "app_id": str(one_time.id),
                "app_slug": one_time.slug,
                "app_plan_id": str(plan.id),
                "plan_id": str(plan.id),
            },
        )
        db.add(purchase)
        db.commit()
        db.refresh(purchase)

        session = TestingSessionLocal()
        try:
            row = session.get(Purchase, purchase.id)
            assert row is not None
            AppCommerceService(session, billing=False).fulfill_one_time_purchase(row)
            session.commit()
        finally:
            session.close()

        db.expire_all()
        licenses = list(
            db.scalars(
                select(AppLicense).where(
                    AppLicense.workspace_id == uuid.UUID(ws["id"]),
                    AppLicense.app_id == one_time.id,
                )
            )
        )
        assert len(licenses) == 1
        assert licenses[0].status == AppLicenseStatus.ACTIVE.value
        assert licenses[0].purchase_id == purchase.id
        assert licenses[0].revoked_at is None

    def test_licensed_reinstall_when_unpublished(self, client, owner_ws, db):
        user, ws = owner_ws
        one_time, _sub, plan, _plans = _seed_paid_apps(db)
        checkout = client.post(
            f"/api/apps/{one_time.slug}/checkout",
            headers=_ws_headers(user, ws),
            json={"plan_id": str(plan.id)},
        ).json()
        _complete_noop(client, checkout)
        un = client.delete(
            f"/api/apps/{one_time.slug}/install", headers=_ws_headers(user, ws)
        )
        assert un.status_code == 200

        one_time.status = AppStatus.COMING_SOON.value
        db.commit()

        rein = client.post(
            f"/api/apps/{one_time.slug}/install", headers=_ws_headers(user, ws)
        )
        assert rein.status_code == 201, rein.text
        assert rein.json()["status"] == "active"
