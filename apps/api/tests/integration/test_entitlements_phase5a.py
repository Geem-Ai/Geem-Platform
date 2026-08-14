"""Phase 5A — plans, entitlements, subscriptions, credits, usage isolation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.billing.models import PlanStatus, SubscriptionStatus
from app.billing.service import PlanService, SubscriptionService
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.entitlements.keys import EntitlementKey
from app.entitlements.quota import QuotaService
from app.entitlements.service import EntitlementService
from app.usage.credits import CreditService
from app.usage.meters import StorageUsageService, UsageMeterService
from app.usage.metrics import CreditLedgerEntryType, StorageUsageReason, UsageMetric
from app.usage.periods import PeriodType
from app.usage.repository import CreditRepository, StorageUsageRepository
from app.usage.summary import UsageSummaryService
from app.workspaces.models import WorkspaceKind


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client, token: str, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _ws_headers(token: str, workspace: dict) -> dict[str, str]:
    return _auth(token, **{"X-Workspace-Id": workspace["id"]})


def _create_limited_plan(db, *, code: str, tokens_daily: int, experts: int, storage: int):
    return PlanService(db).create_plan(
        code=code,
        name=f"Test {code}",
        description="Test-only plan — not Geem product pricing.",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: tokens_daily,
            EntitlementKey.AI_TOKENS_WEEKLY.value: tokens_daily * 7,
            EntitlementKey.AI_TOKENS_MONTHLY.value: tokens_daily * 30,
            EntitlementKey.EXPERTS_LIMIT.value: experts,
            EntitlementKey.STORAGE_BYTES.value: storage,
        },
        extra={"kind": "test", "commercial": False},
    )


# ---------------------------------------------------------------------------
# Bootstrap / entitlement resolution
# ---------------------------------------------------------------------------


def test_new_workspace_gets_bootstrap_entitlements(client, register_user, db) -> None:
    user = register_user(email="ent-boot@example.com")
    ws = _create_workspace(client, user["access_token"], "Boot WS", "ent-boot-ws")
    headers = _ws_headers(user["access_token"], ws)

    sub = client.get("/api/subscription", headers=headers)
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["status"] == "active"
    assert body["plan"]["code"] == "bootstrap_dev"
    assert "pro" not in body["plan"]["code"]
    assert body["ends_at"] is None

    ents = client.get("/api/entitlements", headers=headers)
    assert ents.status_code == 200, ents.text
    items = {row["key"]: row for row in ents.json()["items"]}
    assert items[EntitlementKey.AI_TOKENS_DAILY.value]["value"] == 1_000_000
    assert items[EntitlementKey.AI_TOKENS_DAILY.value]["value_type"] == "integer"
    assert items[EntitlementKey.EXPERTS_LIMIT.value]["value"] == 100
    assert items[EntitlementKey.STORAGE_BYTES.value]["value"] == 10 * 1024 * 1024 * 1024
    assert items[EntitlementKey.API_REQUESTS_PER_MINUTE.value]["value"] == 60

    resolved = EntitlementService(db).get_effective_entitlements(uuid.UUID(ws["id"]))
    assert resolved.plan_code == "bootstrap_dev"
    assert resolved.get(EntitlementKey.AI_TOKENS_WEEKLY).as_int() == 5_000_000
    assert EntitlementService(db).get_int(uuid.UUID(ws["id"]), EntitlementKey.EXPERTS_LIMIT) == 100


def test_quota_service_reads_entitlement_keys_not_plan_name(client, register_user, db) -> None:
    user = register_user(email="ent-quota@example.com")
    ws = _create_workspace(client, user["access_token"], "Quota WS", "ent-quota-ws")
    workspace_id = uuid.UUID(ws["id"])
    quota = QuotaService(db)
    limits = quota.get_ai_limits(workspace_id)
    assert limits.daily == 1_000_000
    assert limits.weekly == 5_000_000
    assert limits.monthly == 20_000_000
    assert quota.get_expert_limit(workspace_id) == 100
    assert quota.get_storage_limit(workspace_id) == 10 * 1024 * 1024 * 1024
    assert quota.get_api_requests_per_minute(workspace_id) == 60
    assert quota.get_credit_balance(workspace_id) == 0


def test_workspaces_on_different_plans_resolve_independently(client, register_user, db) -> None:
    user_a = register_user(email="ent-a@example.com")
    user_b = register_user(email="ent-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "A", "ent-plan-a")
    ws_b = _create_workspace(client, user_b["access_token"], "B", "ent-plan-b")

    limited = _create_limited_plan(db, code="test_limited_a", tokens_daily=100, experts=2, storage=50)
    generous = _create_limited_plan(
        db, code="test_limited_b", tokens_daily=9000, experts=9, storage=999
    )
    SubscriptionService(db).assign_plan(uuid.UUID(ws_a["id"]), limited.id)
    SubscriptionService(db).assign_plan(uuid.UUID(ws_b["id"]), generous.id)
    db.commit()

    assert EntitlementService(db).get_int(uuid.UUID(ws_a["id"]), EntitlementKey.AI_TOKENS_DAILY) == 100
    assert EntitlementService(db).get_int(uuid.UUID(ws_b["id"]), EntitlementKey.AI_TOKENS_DAILY) == 9000
    assert QuotaService(db).get_expert_limit(uuid.UUID(ws_a["id"])) == 2
    assert QuotaService(db).get_expert_limit(uuid.UUID(ws_b["id"])) == 9

    headers_a = _ws_headers(user_a["access_token"], ws_a)
    headers_b = _ws_headers(user_b["access_token"], ws_b)
    assert client.get("/api/subscription", headers=headers_a).json()["plan"]["code"] == "test_limited_a"
    assert client.get("/api/subscription", headers=headers_b).json()["plan"]["code"] == "test_limited_b"


def test_missing_entitlement_get_int_raises_quota_fails_closed(client, register_user, db) -> None:
    user = register_user(email="ent-missing@example.com")
    ws = _create_workspace(client, user["access_token"], "Missing", "ent-missing-ws")
    plan = PlanService(db).create_plan(
        code="sparse_test",
        name="Sparse test",
        entitlements={EntitlementKey.EXPERTS_LIMIT.value: 3},
        extra={"kind": "test"},
    )
    SubscriptionService(db).assign_plan(uuid.UUID(ws["id"]), plan.id)
    db.commit()

    with pytest.raises(AppError) as exc:
        EntitlementService(db).get_int(uuid.UUID(ws["id"]), EntitlementKey.AI_TOKENS_DAILY)
    assert exc.value.category == ErrorCategory.ENTITLEMENT_NOT_FOUND
    assert EntitlementService(db).get_entitlement(
        uuid.UUID(ws["id"]), EntitlementKey.AI_TOKENS_DAILY
    ) is None
    assert QuotaService(db).get_ai_limits(uuid.UUID(ws["id"])).daily == 0
    assert QuotaService(db).get_expert_limit(uuid.UUID(ws["id"])) == 3


def test_invalid_integer_entitlement_rejected_on_read(client, register_user, db) -> None:
    user = register_user(email="ent-badint@example.com")
    ws = _create_workspace(client, user["access_token"], "BadInt", "ent-badint-ws")
    plan = PlanService(db).create_plan(code="bad_int_plan", name="Bad int")
    from app.billing.models import PlanEntitlement
    from app.entitlements.keys import EntitlementValueType

    db.add(
        PlanEntitlement(
            plan_id=plan.id,
            key=EntitlementKey.EXPERTS_LIMIT.value,
            value="not-a-number",
            value_type=EntitlementValueType.INTEGER.value,
        )
    )
    SubscriptionService(db).assign_plan(uuid.UUID(ws["id"]), plan.id)
    db.commit()

    with pytest.raises(AppError) as exc:
        EntitlementService(db).get_int(uuid.UUID(ws["id"]), EntitlementKey.EXPERTS_LIMIT)
    assert exc.value.category == ErrorCategory.ENTITLEMENT_INVALID


def test_boolean_entitlement_get_bool(client, register_user, db) -> None:
    user = register_user(email="ent-bool@example.com")
    ws = _create_workspace(client, user["access_token"], "Bool", "ent-bool-ws")
    plan = PlanService(db).create_plan(
        code="bool_plan",
        name="Bool plan",
        entitlements={"feature_flag_example": True},
    )
    SubscriptionService(db).assign_plan(uuid.UUID(ws["id"]), plan.id)
    db.commit()
    assert EntitlementService(db).get_bool(uuid.UUID(ws["id"]), "feature_flag_example") is True


# ---------------------------------------------------------------------------
# Subscription resolution
# ---------------------------------------------------------------------------


def test_assign_plan_cancels_previous_active_subscription(client, register_user, db) -> None:
    user = register_user(email="ent-sub@example.com")
    ws = _create_workspace(client, user["access_token"], "Sub", "ent-sub-ws")
    workspace_id = uuid.UUID(ws["id"])
    first = SubscriptionService(db).get_current(workspace_id)
    assert first is not None
    other = _create_limited_plan(db, code="replacement_test", tokens_daily=5, experts=1, storage=10)
    second = SubscriptionService(db).assign_plan(workspace_id, other.id)
    db.commit()

    db.refresh(first)
    assert first.status == SubscriptionStatus.CANCELED.value
    assert first.ends_at is not None
    current = SubscriptionService(db).get_current(workspace_id)
    assert current is not None
    assert current.id == second.id
    assert current.plan.code == "replacement_test"


def test_canceled_subscription_is_not_effective(client, register_user, db) -> None:
    user = register_user(email="ent-can@example.com")
    ws = _create_workspace(client, user["access_token"], "Can", "ent-can-ws")
    workspace_id = uuid.UUID(ws["id"])
    current = SubscriptionService(db).require_current(workspace_id)
    current.status = SubscriptionStatus.CANCELED.value
    current.ends_at = datetime.now(timezone.utc)
    db.commit()
    assert SubscriptionService(db).get_current(workspace_id) is None


def test_ensure_bootstrap_plan_is_idempotent(db) -> None:
    first = PlanService(db).ensure_bootstrap_plan()
    second = PlanService(db).ensure_bootstrap_plan()
    assert first.id == second.id
    keys = {row.key for row in PlanService(db).plans.list_entitlements(first.id)}
    assert EntitlementKey.AI_TOKENS_DAILY.value in keys
    assert EntitlementKey.EXPERTS_LIMIT.value in keys


def test_ensure_bootstrap_plan_recovers_when_code_lookup_loses_the_race(db) -> None:
    svc = PlanService(db)
    existing = svc.ensure_bootstrap_plan()
    db.commit()
    calls = {"n": 0}
    real = svc.plans.get_by_code

    def _miss_once(code: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real(code)

    svc.plans.get_by_code = _miss_once  # type: ignore[method-assign]
    recovered = svc.ensure_bootstrap_plan()
    assert recovered.id == existing.id


def test_assign_plan_recovers_when_active_row_appears_concurrently(client, register_user, db) -> None:
    user = register_user(email="ent-race@example.com")
    ws = _create_workspace(client, user["access_token"], "Race", "ent-race-ws")
    workspace_id = uuid.UUID(ws["id"])
    current = SubscriptionService(db).require_current(workspace_id)
    svc = SubscriptionService(db)
    calls = {"n": 0}
    real = svc.subscriptions.get_active_for_update

    def _none_once(ws_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real(ws_id)

    svc.subscriptions.get_active_for_update = _none_once  # type: ignore[method-assign]
    recovered = svc.assign_plan(workspace_id, current.plan_id)
    db.commit()
    assert recovered.plan_id == current.plan_id
    assert SubscriptionService(db).get_current(workspace_id) is not None


def test_entitlements_payload_uses_real_plan_status(client, register_user, db) -> None:
    user = register_user(email="ent-status@example.com")
    ws = _create_workspace(client, user["access_token"], "Status", "ent-status-ws")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_limited_plan(db, code="status_plan", tokens_daily=3, experts=1, storage=9)
    SubscriptionService(db).assign_plan(uuid.UUID(ws["id"]), plan.id)
    plan.status = PlanStatus.ARCHIVED.value
    db.commit()

    res = client.get("/api/entitlements", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["plan"]["code"] == "status_plan"
    assert body["plan"]["status"] == PlanStatus.ARCHIVED.value


# ---------------------------------------------------------------------------
# Credits / ledger
# ---------------------------------------------------------------------------


def test_credit_account_created_and_ledger_append_idempotent(client, register_user, db) -> None:
    user = register_user(email="ent-cred@example.com")
    ws = _create_workspace(client, user["access_token"], "Cred", "ent-cred-ws")
    workspace_id = uuid.UUID(ws["id"])
    credits = CreditService(db)
    account = credits.ensure_account(workspace_id)
    assert account.workspace_id == workspace_id
    assert account.balance == 0

    first = credits.append(
        workspace_id,
        entry_type=CreditLedgerEntryType.GRANT,
        amount=250,
        request_id="req-grant-1",
        source_type="manual",
        source_id="test",
    )
    db.commit()
    assert first.amount == 250
    assert first.remaining_amount == 250
    assert credits.get_balance(workspace_id) == 250

    replay = credits.append(
        workspace_id,
        entry_type=CreditLedgerEntryType.GRANT,
        amount=250,
        request_id="req-grant-1",
        source_type="manual",
        source_id="test",
    )
    db.commit()
    assert replay.id == first.id
    assert credits.get_balance(workspace_id) == 250
    assert len(credits.list_ledger(workspace_id)) == 1


def test_ledger_has_no_update_or_delete_api() -> None:
    assert not hasattr(CreditRepository, "update")
    assert not hasattr(CreditRepository, "delete")
    assert not hasattr(CreditRepository, "update_ledger")
    assert not hasattr(CreditService, "update_entry")
    assert not hasattr(CreditService, "delete_entry")


# ---------------------------------------------------------------------------
# Usage counters + storage events + summary
# ---------------------------------------------------------------------------


def test_usage_summary_and_storage_events(client, register_user, db) -> None:
    user = register_user(email="ent-sum@example.com")
    ws = _create_workspace(client, user["access_token"], "Sum", "ent-sum-ws")
    workspace_id = uuid.UUID(ws["id"])
    headers = _ws_headers(user["access_token"], ws)

    StorageUsageService(db).record_delta(
        workspace_id,
        delta_bytes=4096,
        reason=StorageUsageReason.UPLOAD,
        extra={"test": True},
    )
    meter = UsageMeterService(db)
    daily = meter.get_or_create_window(
        workspace_id, metric=UsageMetric.AI_TOKENS, period_type=PeriodType.DAILY
    )
    daily.used = 12
    daily.reserved = 3
    db.commit()

    res = client.get("/api/usage/summary", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ai_tokens"]["daily"]["limit"] == 1_000_000
    assert body["ai_tokens"]["daily"]["used"] == 12
    assert body["ai_tokens"]["daily"]["reserved"] == 3
    assert body["ai_tokens"]["daily"]["remaining"] == 1_000_000 - 12 - 3
    assert body["ai"]["daily"]["remaining"] == body["ai_tokens"]["daily"]["remaining"]
    assert body["ai_tokens"]["daily"]["period_start"] is not None
    assert body["experts"]["used"] == 0
    assert body["credits"]["balance"] == 0
    # Live storage is summed from documents (none yet), not from events.
    assert body["storage_bytes"]["used"] == 0

    events = StorageUsageRepository(db).list_for_workspace(workspace_id)
    assert len(events) == 1
    assert events[0].delta_bytes == 4096


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_cross_workspace_isolation_of_billing_and_usage(client, register_user, db) -> None:
    user_a = register_user(email="iso-a@example.com")
    user_b = register_user(email="iso-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "IsoA", "ent-iso-a")
    ws_b = _create_workspace(client, user_b["access_token"], "IsoB", "ent-iso-b")
    id_a = uuid.UUID(ws_a["id"])
    id_b = uuid.UUID(ws_b["id"])

    limited = _create_limited_plan(db, code="iso_plan_a", tokens_daily=11, experts=1, storage=11)
    SubscriptionService(db).assign_plan(id_a, limited.id)
    CreditService(db).append(
        id_a, entry_type=CreditLedgerEntryType.GRANT, amount=80, request_id="iso-a-1"
    )
    CreditService(db).append(
        id_b, entry_type=CreditLedgerEntryType.GRANT, amount=15, request_id="iso-b-1"
    )
    StorageUsageService(db).record_delta(id_a, delta_bytes=100, reason=StorageUsageReason.UPLOAD)
    StorageUsageService(db).record_delta(id_b, delta_bytes=5, reason=StorageUsageReason.UPLOAD)
    UsageMeterService(db).get_or_create_window(id_a, period_type=PeriodType.DAILY).used = 7
    db.commit()

    # API: A cannot use B's workspace id as the authz boundary.
    stolen = client.get("/api/subscription", headers=_ws_headers(user_a["access_token"], ws_b))
    assert stolen.status_code in {403, 404}, stolen.text

    # Query-string workspace ids must be ignored (context comes from headers).
    headers_a = _ws_headers(user_a["access_token"], ws_a)
    listed = client.get(f"/api/entitlements?workspace_id={ws_b['id']}", headers=headers_a)
    assert listed.status_code == 200
    assert listed.json()["plan"]["code"] == "iso_plan_a"

    credits = CreditRepository(db)
    assert [e.amount for e in credits.list_ledger(id_a)] == [80]
    assert [e.amount for e in credits.list_ledger(id_b)] == [15]
    assert credits.get_ledger_by_request_id(id_a, "iso-b-1") is None
    assert credits.get_account(id_a).balance == 80
    assert credits.get_account(id_b).balance == 15

    storage = StorageUsageRepository(db)
    assert [e.delta_bytes for e in storage.list_for_workspace(id_a)] == [100]
    assert [e.delta_bytes for e in storage.list_for_workspace(id_b)] == [5]

    assert UsageSummaryService(db).summarize(id_a).ai_daily.used == 7
    assert UsageSummaryService(db).summarize(id_b).ai_daily.used == 0


def test_usage_history_is_workspace_scoped(client, register_user, db) -> None:
    user_a = register_user(email="hist-a@example.com")
    user_b = register_user(email="hist-b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "HistA", "hist-a")
    ws_b = _create_workspace(client, user_b["access_token"], "HistB", "hist-b")
    id_a = uuid.UUID(ws_a["id"])
    id_b = uuid.UUID(ws_b["id"])

    CreditService(db).append(
        id_a, entry_type=CreditLedgerEntryType.GRANT, amount=40, request_id="hist-a-grant"
    )
    CreditService(db).append(
        id_a, entry_type=CreditLedgerEntryType.CONSUME, amount=5, request_id="hist-a-use"
    )
    CreditService(db).append(
        id_b, entry_type=CreditLedgerEntryType.GRANT, amount=99, request_id="hist-b-grant"
    )
    db.add(
        UsageEvent(
            operation_type="chat",
            input_tokens=12,
            output_tokens=8,
            workspace_id=id_a,
        )
    )
    db.add(
        UsageEvent(
            operation_type="chat",
            input_tokens=3,
            output_tokens=1,
            workspace_id=id_b,
        )
    )
    db.commit()

    listed = client.get(
        "/api/usage/history", headers=_ws_headers(user_a["access_token"], ws_a)
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    kinds = {row["kind"] for row in items}
    assert "credit_grant" in kinds
    assert "credit_consume" in kinds
    assert "chat_tokens" in kinds
    assert all(row["kind"] != "credit_reserve" for row in items)
    assert not any(row.get("credits") == 99 for row in items)
    stolen = client.get(
        "/api/usage/history", headers=_ws_headers(user_a["access_token"], ws_b)
    )
    assert stolen.status_code in {403, 404}, stolen.text

    listed_b = client.get(
        "/api/usage/history", headers=_ws_headers(user_b["access_token"], ws_b)
    )
    assert listed_b.status_code == 200
    credits_b = {row.get("credits") for row in listed_b.json()["items"]}
    assert 99 in credits_b
    assert 40 not in credits_b


def test_usage_history_filters_by_kind_and_returns_counts(client, register_user, db) -> None:
    user = register_user(email="hist-kind@example.com")
    ws = _create_workspace(client, user["access_token"], "HistK", "hist-k")
    workspace_id = uuid.UUID(ws["id"])
    CreditService(db).append(
        workspace_id,
        entry_type=CreditLedgerEntryType.GRANT,
        amount=40,
        request_id="hist-k-grant",
        source_type="manual",
    )
    db.add(
        UsageEvent(
            operation_type="chat",
            model="test-model",
            input_tokens=10,
            output_tokens=5,
            workspace_id=workspace_id,
            request_id="hist-k-ai",
        )
    )
    db.commit()

    headers = _ws_headers(user["access_token"], ws)
    listed = client.get("/api/usage/history", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["counts"]["all"] >= 2
    assert body["counts"]["ai"] >= 1
    assert body["counts"]["credits"] >= 1
    ai_row = next(row for row in body["items"] if row["kind"] == "chat_tokens")
    assert ai_row["operation_type"] == "chat"
    assert ai_row["model"] == "dalseen/geem-1.0"
    assert ai_row["input_tokens"] == 10
    assert ai_row["output_tokens"] == 5

    ai_only = client.get("/api/usage/history?kind=ai", headers=headers)
    assert ai_only.status_code == 200, ai_only.text
    ai_body = ai_only.json()
    assert ai_body["total"] == ai_body["counts"]["ai"]
    assert all(row["kind"] == "chat_tokens" for row in ai_body["items"])

    credits_only = client.get("/api/usage/history?kind=credits", headers=headers)
    assert credits_only.status_code == 200, credits_only.text
    credit_body = credits_only.json()
    assert credit_body["total"] == credit_body["counts"]["credits"]
    assert all(
        row["kind"]
        not in {
            "ai_tokens",
            "chat_tokens",
            "embed_tokens",
            "rerank_tokens",
            "ocr_tokens",
            "title_tokens",
        }
        for row in credit_body["items"]
    )
    grant = next(row for row in credit_body["items"] if row["kind"] == "credit_grant")
    assert grant["source_type"] == "manual"
    assert grant["credits"] == 40
    assert listed.json()["tokens"]["input"] >= 10
    assert listed.json()["tokens"]["output"] >= 5
    assert listed.json()["tokens"]["total"] >= 15
    assert ai_body["tokens"]["total"] >= 15
    assert credit_body["tokens"]["total"] == 0


def test_usage_history_splits_openrouter_families(client, register_user, db) -> None:
    user = register_user(email="hist-fam@example.com")
    ws = _create_workspace(client, user["access_token"], "HistF", "hist-f")
    workspace_id = uuid.UUID(ws["id"])
    db.add_all(
        [
            UsageEvent(
                operation_type="generation",
                input_tokens=10,
                output_tokens=2,
                workspace_id=workspace_id,
            ),
            UsageEvent(
                operation_type="embed_query",
                input_tokens=8,
                output_tokens=0,
                workspace_id=workspace_id,
            ),
            UsageEvent(
                operation_type="rerank",
                input_tokens=4,
                output_tokens=0,
                workspace_id=workspace_id,
            ),
            UsageEvent(
                operation_type="pdf_parse",
                input_tokens=30,
                output_tokens=0,
                workspace_id=workspace_id,
            ),
            UsageEvent(
                operation_type="title",
                input_tokens=3,
                output_tokens=1,
                workspace_id=workspace_id,
            ),
        ]
    )
    db.commit()

    headers = _ws_headers(user["access_token"], ws)
    listed = client.get("/api/usage/history?kind=ai", headers=headers)
    assert listed.status_code == 200, listed.text
    kinds = {row["kind"] for row in listed.json()["items"]}
    assert kinds == {
        "chat_tokens",
        "embed_tokens",
        "rerank_tokens",
        "ocr_tokens",
        "title_tokens",
    }
    assert listed.json()["counts"]["ai"] == 5


def test_usage_history_filters_by_date_and_returns_token_totals(
    client, register_user, db
) -> None:
    user = register_user(email="hist-date@example.com")
    ws = _create_workspace(client, user["access_token"], "HistD", "hist-d")
    workspace_id = uuid.UUID(ws["id"])
    db.add(
        UsageEvent(
            operation_type="chat",
            input_tokens=10,
            output_tokens=5,
            workspace_id=workspace_id,
            created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        UsageEvent(
            operation_type="chat",
            input_tokens=100,
            output_tokens=50,
            workspace_id=workspace_id,
            created_at=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    headers = _ws_headers(user["access_token"], ws)
    window = client.get(
        "/api/usage/history?from=2026-08-01T00:00:00Z&to=2026-08-14T00:00:00Z",
        headers=headers,
    )
    assert window.status_code == 200, window.text
    body = window.json()
    assert body["counts"]["ai"] == 1
    assert body["tokens"]["input"] == 100
    assert body["tokens"]["output"] == 50
    assert body["tokens"]["total"] == 150
    assert len(body["items"]) == 1
    assert body["items"][0]["input_tokens"] == 100


def test_usage_history_paginates_with_total(client, register_user, db) -> None:
    user = register_user(email="hist-page@example.com")
    ws = _create_workspace(client, user["access_token"], "HistP", "hist-p")
    workspace_id = uuid.UUID(ws["id"])
    for i in range(15):
        db.add(
            UsageEvent(
                operation_type="chat",
                input_tokens=i + 1,
                output_tokens=0,
                workspace_id=workspace_id,
            )
        )
    db.commit()

    headers = _ws_headers(user["access_token"], ws)
    first = client.get("/api/usage/history?limit=10&offset=0", headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] >= 15
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["items"]) == 10

    second = client.get("/api/usage/history?limit=10&offset=10", headers=headers)
    assert second.status_code == 200, second.text
    page_two = second.json()
    assert page_two["offset"] == 10
    ids_first = {row["id"] for row in body["items"]}
    ids_second = {row["id"] for row in page_two["items"]}
    assert ids_first.isdisjoint(ids_second)
    assert len(page_two["items"]) >= 5


def test_usage_history_skips_internal_credit_reserve_rows(client, register_user, db) -> None:
    user = register_user(email="hist-reserve@example.com")
    ws = _create_workspace(client, user["access_token"], "HistR", "hist-r")
    workspace_id = uuid.UUID(ws["id"])
    CreditService(db).append(
        workspace_id,
        entry_type=CreditLedgerEntryType.GRANT,
        amount=100,
        request_id="hist-r-grant",
    )
    for i in range(60):
        CreditService(db).append(
            workspace_id,
            entry_type=CreditLedgerEntryType.RESERVE,
            amount=1,
            request_id=f"hist-r-res-{i}",
        )
    db.commit()

    listed = client.get(
        "/api/usage/history?limit=50",
        headers=_ws_headers(user["access_token"], ws),
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    kinds = {row["kind"] for row in items}
    assert "credit_reserve" not in kinds
    assert any(row.get("credits") == 100 and row["kind"] == "credit_grant" for row in items)


def test_unauthenticated_entitlement_routes_rejected(client) -> None:
    assert client.get("/api/subscription").status_code == 401
    assert client.get("/api/entitlements").status_code == 401
    assert client.get("/api/usage/summary").status_code == 401
    assert client.get("/api/usage/history").status_code == 401


def test_system_workspace_is_not_provisioned(db) -> None:
    from app.workspaces.service import WorkspaceService

    system = WorkspaceService(db).ensure_platform_knowledge_workspace()
    assert system.kind == WorkspaceKind.SYSTEM.value
    assert SubscriptionService(db).get_current(system.id) is None
    assert CreditService(db).get_balance(system.id) == 0


# ---------------------------------------------------------------------------
# Existing Phase 4 / Expert behavior
# ---------------------------------------------------------------------------


def test_phase4_conversation_still_creates_after_entitlements(client, register_user) -> None:
    user = register_user(email="ent-chat@example.com")
    ws = _create_workspace(client, user["access_token"], "Chat", "ent-chat-ws")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "Still Works"})
    assert expert.status_code == 201, expert.text
    created = client.post(
        "/api/conversations",
        headers=headers,
        json={"expert_id": expert.json()["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["expert"]["name"] == "Still Works"

    summary = client.get("/api/usage/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["experts"]["used"] == 1


def test_phase3_expert_list_still_works(client, register_user) -> None:
    user = register_user(email="ent-exp@example.com")
    ws = _create_workspace(client, user["access_token"], "Exp", "ent-exp-ws")
    headers = _ws_headers(user["access_token"], ws)
    created = client.post("/api/experts", headers=headers, json={"name": "Alpha"})
    assert created.status_code == 201, created.text
    listed = client.get("/api/experts", headers=headers)
    assert listed.status_code == 200
    names = {row["name"] for row in listed.json() if row["ownership"] == "workspace"}
    assert "Alpha" in names
