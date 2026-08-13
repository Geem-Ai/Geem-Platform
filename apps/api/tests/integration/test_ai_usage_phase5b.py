"""Phase 5B — atomic AI usage reservation, FIFO credits, Chat metering."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.service import PlanService, SubscriptionService
from app.core.errors import AppError, ErrorCategory
from app.entitlements.cache import invalidate_entitlements
from app.entitlements.keys import EntitlementKey
from app.usage.ai_usage import AiUsageService
from app.usage.credits import CreditService
from app.usage.metrics import AiUsageReservationStatus, CreditLedgerEntryType, UsageMetric
from app.usage.models import CreditLedgerEntry, UsagePeriodCounter
from app.usage.periods import PeriodType
from app.usage.repository import UsageCounterRepository
from app.usage.summary import UsageSummaryService
from app.conversations.models import MessageRole, MessageStatus
from app.conversations.title import persist_generated_conversation_title
from tests.conftest import TestingSessionLocal


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


def _create_ai_plan(
    db: Session,
    *,
    code: str,
    daily: int,
    weekly: int,
    monthly: int,
):
    return PlanService(db).create_plan(
        code=code,
        name=f"Test {code}",
        description="Test-only plan — not Geem product pricing.",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: daily,
            EntitlementKey.AI_TOKENS_WEEKLY.value: weekly,
            EntitlementKey.AI_TOKENS_MONTHLY.value: monthly,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
        },
        extra={"kind": "test", "commercial": False},
    )


def _assign_plan(db: Session, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> None:
    SubscriptionService(db).assign_plan(workspace_id, plan_id)
    db.commit()
    invalidate_entitlements(workspace_id)


def _grant_credits(db: Session, workspace_id: uuid.UUID, amount: int, request_id: str) -> None:
    CreditService(db).append(
        workspace_id,
        entry_type=CreditLedgerEntryType.GRANT,
        amount=amount,
        request_id=request_id,
        source_type="test",
    )
    db.commit()


def _counters(db: Session, workspace_id: uuid.UUID) -> dict[str, UsagePeriodCounter]:
    rows = UsageCounterRepository(db).list_for_workspace(
        workspace_id, metric=UsageMetric.AI_TOKENS.value
    )
    return {row.period_type: row for row in rows}


def _assert_non_negative(db: Session, workspace_id: uuid.UUID) -> None:
    for row in _counters(db, workspace_id).values():
        assert row.used >= 0
        assert row.reserved >= 0
    account = CreditService(db).repo.get_account(workspace_id)
    if account is not None:
        assert account.balance >= 0
    grants = db.scalars(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.workspace_id == workspace_id,
            CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
        )
    )
    for grant in grants:
        assert grant.remaining_amount is None or grant.remaining_amount >= 0


def _reserve(
    session: Session,
    workspace_id: uuid.UUID,
    request_id: str,
    tokens: int,
):
    dto = AiUsageService(session).reserve_ai_usage(workspace_id, request_id, tokens)
    session.commit()
    return dto


def _concurrent_reserve(
    workspace_id: uuid.UUID,
    tokens: int,
    n: int,
) -> list[tuple[str, Any]]:
    barrier = threading.Barrier(n, timeout=10)
    results: list[tuple[str, Any]] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            try:
                dto = AiUsageService(session).reserve_ai_usage(
                    workspace_id, f"req-{i}-{uuid.uuid4()}", tokens
                )
                session.commit()
                with lock:
                    results.append(("ok", dto))
            except AppError as exc:
                session.rollback()
                with lock:
                    results.append(("fail", exc.category))
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    return results


# ---------------------------------------------------------------------------
# Concurrent over-quota
# ---------------------------------------------------------------------------


def test_1_two_concurrent_requests_one_remaining_included(client, register_user, db) -> None:
    user = register_user(email="5b-1@example.com")
    ws = _create_workspace(client, user["access_token"], "T1", "p5b-t1")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t1", daily=100, weekly=10_000, monthly=10_000)
    _assign_plan(db, wid, plan.id)

    results = _concurrent_reserve(wid, 100, 2)
    oks = [r for r in results if r[0] == "ok"]
    fails = [r for r in results if r[0] == "fail"]
    assert len(oks) == 1
    assert len(fails) == 1
    assert fails[0][1] == ErrorCategory.QUOTA_EXCEEDED
    db.expire_all()
    daily = _counters(db, wid)[PeriodType.DAILY.value]
    assert daily.reserved == 100
    assert daily.used == 0
    _assert_non_negative(db, wid)


def test_2_two_concurrent_requests_one_credit_fits(client, register_user, db) -> None:
    user = register_user(email="5b-2@example.com")
    ws = _create_workspace(client, user["access_token"], "T2", "p5b-t2")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t2", daily=0, weekly=0, monthly=0)
    _assign_plan(db, wid, plan.id)
    _grant_credits(db, wid, 100, "grant-t2")

    results = _concurrent_reserve(wid, 100, 2)
    oks = [r for r in results if r[0] == "ok"]
    fails = [r for r in results if r[0] == "fail"]
    assert len(oks) == 1, results
    assert len(fails) == 1
    assert fails[0][1] == ErrorCategory.INSUFFICIENT_CREDITS
    db.expire_all()
    assert CreditService(db).get_balance(wid) == 0
    _assert_non_negative(db, wid)


def test_3_daily_blocks_when_weekly_monthly_remain(client, register_user, db) -> None:
    user = register_user(email="5b-3@example.com")
    ws = _create_workspace(client, user["access_token"], "T3", "p5b-t3")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t3", daily=100, weekly=10_000, monthly=10_000)
    _assign_plan(db, wid, plan.id)
    _reserve(db, wid, "t3-a", 100)
    AiUsageService(db).settle_ai_usage(wid, "t3-a", 100)
    db.commit()

    with pytest.raises(AppError) as exc:
        AiUsageService(db).reserve_ai_usage(wid, "t3-b", 1)
    assert exc.value.category == ErrorCategory.QUOTA_EXCEEDED
    db.rollback()
    summary = UsageSummaryService(db).summarize(wid)
    assert summary.ai_daily.used == 100
    assert summary.ai_weekly.remaining > 0
    assert summary.ai_monthly.remaining > 0


def test_4_weekly_counter_blocks(client, register_user, db) -> None:
    user = register_user(email="5b-4@example.com")
    ws = _create_workspace(client, user["access_token"], "T4", "p5b-t4")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t4", daily=10_000, weekly=50, monthly=10_000)
    _assign_plan(db, wid, plan.id)
    _reserve(db, wid, "t4-a", 50)
    AiUsageService(db).settle_ai_usage(wid, "t4-a", 50)
    db.commit()

    with pytest.raises(AppError) as exc:
        AiUsageService(db).reserve_ai_usage(wid, "t4-b", 1)
    assert exc.value.category == ErrorCategory.QUOTA_EXCEEDED
    db.rollback()
    assert UsageSummaryService(db).summarize(wid).ai_weekly.used == 50
    assert UsageSummaryService(db).summarize(wid).ai_daily.remaining > 0


def test_5_monthly_counter_blocks(client, register_user, db) -> None:
    user = register_user(email="5b-5@example.com")
    ws = _create_workspace(client, user["access_token"], "T5", "p5b-t5")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t5", daily=10_000, weekly=10_000, monthly=50)
    _assign_plan(db, wid, plan.id)
    _reserve(db, wid, "t5-a", 50)
    AiUsageService(db).settle_ai_usage(wid, "t5-a", 50)
    db.commit()

    with pytest.raises(AppError) as exc:
        AiUsageService(db).reserve_ai_usage(wid, "t5-b", 1)
    assert exc.value.category == ErrorCategory.QUOTA_EXCEEDED
    db.rollback()
    assert UsageSummaryService(db).summarize(wid).ai_monthly.used == 50


def test_6_and_7_included_then_credits_then_exhausted(client, register_user, db) -> None:
    user = register_user(email="5b-67@example.com")
    ws = _create_workspace(client, user["access_token"], "T67", "p5b-t67")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t67", daily=100, weekly=100, monthly=100)
    _assign_plan(db, wid, plan.id)
    _grant_credits(db, wid, 100, "grant-67")

    first = _reserve(db, wid, "t67-inc", 100)
    assert first.included_reserved == 100
    assert first.credit_reserved == 0
    AiUsageService(db).settle_ai_usage(wid, "t67-inc", 100)
    db.commit()

    second = _reserve(db, wid, "t67-cred", 100)
    assert second.included_reserved == 0
    assert second.credit_reserved == 100

    with pytest.raises(AppError) as exc:
        AiUsageService(db).reserve_ai_usage(wid, "t67-fail", 1)
    assert exc.value.category in {
        ErrorCategory.QUOTA_EXCEEDED,
        ErrorCategory.INSUFFICIENT_CREDITS,
    }
    db.rollback()


def test_8_failed_reservation_leaves_counters_unchanged(client, register_user, db) -> None:
    user = register_user(email="5b-8@example.com")
    ws = _create_workspace(client, user["access_token"], "T8", "p5b-t8")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t8", daily=10, weekly=10, monthly=10)
    _assign_plan(db, wid, plan.id)

    with pytest.raises(AppError):
        AiUsageService(db).reserve_ai_usage(wid, "t8-fail", 100)
    db.rollback()

    snaps = UsageSummaryService(db).summarize(wid)
    assert snaps.ai_daily.used == 0
    assert snaps.ai_daily.reserved == 0
    assert snaps.credit_balance == 0


def test_9_release_restores_reserved_capacity(client, register_user, db) -> None:
    user = register_user(email="5b-9@example.com")
    ws = _create_workspace(client, user["access_token"], "T9", "p5b-t9")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t9", daily=100, weekly=100, monthly=100)
    _assign_plan(db, wid, plan.id)
    _grant_credits(db, wid, 40, "grant-9")

    reserved = _reserve(db, wid, "t9-a", 100)
    assert reserved.included_reserved == 100
    AiUsageService(db).release_ai_usage(wid, "t9-a")
    db.commit()

    snaps = UsageSummaryService(db).summarize(wid)
    assert snaps.ai_daily.reserved == 0
    assert snaps.ai_daily.used == 0
    assert snaps.credit_balance == 40
    again = _reserve(db, wid, "t9-b", 100)
    assert again.status == AiUsageReservationStatus.RESERVED.value


def test_10_settle_charges_actual_amount(client, register_user, db) -> None:
    user = register_user(email="5b-10@example.com")
    ws = _create_workspace(client, user["access_token"], "T10", "p5b-t10")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t10", daily=100, weekly=100, monthly=100)
    _assign_plan(db, wid, plan.id)
    _reserve(db, wid, "t10-a", 100)
    settled = AiUsageService(db).settle_ai_usage(wid, "t10-a", 40)
    db.commit()
    assert settled.included_settled == 40
    assert settled.actual_tokens == 40
    snaps = UsageSummaryService(db).summarize(wid)
    assert snaps.ai_daily.used == 40
    assert snaps.ai_daily.reserved == 0
    assert snaps.ai_daily.remaining == 60


def test_11_settle_is_idempotent(client, register_user, db) -> None:
    user = register_user(email="5b-11@example.com")
    ws = _create_workspace(client, user["access_token"], "T11", "p5b-t11")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t11", daily=100, weekly=100, monthly=100)
    _assign_plan(db, wid, plan.id)
    _reserve(db, wid, "t11-a", 100)
    first = AiUsageService(db).settle_ai_usage(wid, "t11-a", 25)
    db.commit()
    second = AiUsageService(db).settle_ai_usage(wid, "t11-a", 99)
    db.commit()
    assert first.id == second.id
    assert second.actual_tokens == 25
    assert UsageSummaryService(db).summarize(wid).ai_daily.used == 25


def test_12_retry_same_request_id_does_not_double_charge(client, register_user, db) -> None:
    user = register_user(email="5b-12@example.com")
    ws = _create_workspace(client, user["access_token"], "T12", "p5b-t12")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t12", daily=100, weekly=100, monthly=100)
    _assign_plan(db, wid, plan.id)

    first = _reserve(db, wid, "same-req", 100)
    second = _reserve(db, wid, "same-req", 100)
    assert first.id == second.id
    db.expire_all()
    assert _counters(db, wid)[PeriodType.DAILY.value].reserved == 100

    AiUsageService(db).settle_ai_usage(wid, "same-req", 80)
    db.commit()
    AiUsageService(db).settle_ai_usage(wid, "same-req", 80)
    db.commit()
    assert UsageSummaryService(db).summarize(wid).ai_daily.used == 80
    assert UsageSummaryService(db).summarize(wid).ai_daily.reserved == 0


def test_13_workspace_isolation_under_concurrent_consumption(
    client, register_user, db
) -> None:
    user_a = register_user(email="5b-13a@example.com")
    user_b = register_user(email="5b-13b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "IsoA", "p5b-iso-a")
    ws_b = _create_workspace(client, user_b["access_token"], "IsoB", "p5b-iso-b")
    id_a = uuid.UUID(ws_a["id"])
    id_b = uuid.UUID(ws_b["id"])
    plan_a = _create_ai_plan(db, code="p5b_iso_a", daily=100, weekly=100, monthly=100)
    plan_b = _create_ai_plan(db, code="p5b_iso_b", daily=100, weekly=100, monthly=100)
    _assign_plan(db, id_a, plan_a.id)
    _assign_plan(db, id_b, plan_b.id)

    barrier = threading.Barrier(4, timeout=10)
    results: list[tuple[uuid.UUID, str]] = []
    lock = threading.Lock()

    def worker(workspace_id: uuid.UUID, i: int) -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            try:
                AiUsageService(session).reserve_ai_usage(
                    workspace_id, f"iso-{workspace_id}-{i}", 100
                )
                session.commit()
                with lock:
                    results.append((workspace_id, "ok"))
            except AppError:
                session.rollback()
                with lock:
                    results.append((workspace_id, "fail"))
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=(id_a, 0)),
        threading.Thread(target=worker, args=(id_a, 1)),
        threading.Thread(target=worker, args=(id_b, 0)),
        threading.Thread(target=worker, args=(id_b, 1)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    ok_a = sum(1 for wid, status in results if wid == id_a and status == "ok")
    ok_b = sum(1 for wid, status in results if wid == id_b and status == "ok")
    assert ok_a == 1
    assert ok_b == 1
    db.expire_all()
    _assert_non_negative(db, id_a)
    _assert_non_negative(db, id_b)


def test_14_concurrent_requests_never_go_negative(client, register_user, db) -> None:
    user = register_user(email="5b-14@example.com")
    ws = _create_workspace(client, user["access_token"], "T14", "p5b-t14")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_t14", daily=250, weekly=250, monthly=250)
    _assign_plan(db, wid, plan.id)

    results = _concurrent_reserve(wid, 100, 8)
    oks = [r for r in results if r[0] == "ok"]
    assert len(oks) == 2
    db.expire_all()
    daily = _counters(db, wid)[PeriodType.DAILY.value]
    assert daily.reserved == 200
    assert daily.used == 0
    _assert_non_negative(db, wid)


def test_fifo_consumes_oldest_grant_first(client, register_user, db) -> None:
    user = register_user(email="5b-fifo@example.com")
    ws = _create_workspace(client, user["access_token"], "Fifo", "p5b-fifo")
    wid = uuid.UUID(ws["id"])
    plan = _create_ai_plan(db, code="p5b_fifo", daily=0, weekly=0, monthly=0)
    _assign_plan(db, wid, plan.id)
    _grant_credits(db, wid, 40, "grant-old")
    _grant_credits(db, wid, 70, "grant-new")

    dto = _reserve(db, wid, "fifo-1", 50)
    assert dto.credit_reserved == 50
    db.expire_all()
    grants = list(
        db.scalars(
            select(CreditLedgerEntry)
            .where(
                CreditLedgerEntry.workspace_id == wid,
                CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
            )
            .order_by(CreditLedgerEntry.created_at.asc())
        )
    )
    assert grants[0].remaining_amount == 0
    assert grants[1].remaining_amount == 60


def test_usage_summary_includes_remaining_and_ai_alias(client, register_user, db) -> None:
    user = register_user(email="5b-sum@example.com")
    ws = _create_workspace(client, user["access_token"], "Sum", "p5b-sum")
    headers = _ws_headers(user["access_token"], ws)
    res = client.get("/api/usage/summary", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    daily = body["ai"]["daily"]
    assert set(daily) >= {
        "limit",
        "used",
        "reserved",
        "remaining",
        "period_start",
        "period_end",
    }
    assert daily["remaining"] == daily["limit"] - daily["used"] - daily["reserved"]
    assert body["credits"]["balance"] == 0
    assert "ledger" not in body["credits"]


# ---------------------------------------------------------------------------
# Chat integration
# ---------------------------------------------------------------------------


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    import json

    events: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        events.append((event, json.loads("\n".join(data_lines))))
    return events


def _fake_stream_success(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
    yield {"event": "status", "data": {"stage": "generating"}}
    yield {"event": "token", "data": {"text": "Hello world"}}
    yield {
        "event": "final",
        "data": {
            "answer": "Hello world",
            "insufficient_context": False,
            "citations": [],
            "model": "test-model",
            "usage": {
                "prompt_tokens": 4,
                "completion_tokens": 2,
                "total_tokens": 6,
                "source": "provider",
            },
        },
    }


def _fake_stream_fail(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
    yield {"event": "status", "data": {"stage": "generating"}}
    raise AppError(ErrorCategory.GENERATION_FAILED, "Provider down")


def _force_expert_ready(db, expert_id: str) -> None:
    from app.experts.models import Expert, ExpertStatus

    expert = db.get(Expert, uuid.UUID(expert_id))
    assert expert is not None
    expert.status = ExpertStatus.READY.value
    db.commit()


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
def test_chat_quota_exceeded_before_stream(
    _mock_resolve, client, register_user, db
) -> None:
    user = register_user(email="5b-chat-q@example.com")
    ws = _create_workspace(client, user["access_token"], "ChatQ", "p5b-chat-q")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "Q"}).json()
    _force_expert_ready(db, expert["id"])
    plan = _create_ai_plan(db, code="p5b_chat_q", daily=1, weekly=1, monthly=1)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=headers,
        json={"content": "Should be blocked"},
    ) as res:
        raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    assert any(n == "error" for n, _ in events)
    err = next(d for n, d in events if n == "error")
    assert err["error"] == "quota_exceeded"
    assert not any(n == "message_start" for n, _ in events)
    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    assert msgs == []


@patch(
    "app.conversations.title.generate_conversation_title_call",
    return_value=("Metered", None),
)
@patch(
    "app.conversations.chat_orchestrator.schedule_conversation_title",
    side_effect=persist_generated_conversation_title,
)
@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_chat_settle_uses_provider_tokens_and_retry_does_not_double_charge(
    _mock_stream, _mock_resolve, _mock_schedule, _mock_title, client, register_user, db
) -> None:
    user = register_user(email="5b-chat-s@example.com")
    ws = _create_workspace(client, user["access_token"], "ChatS", "p5b-chat-s")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "S"}).json()
    _force_expert_ready(db, expert["id"])
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    with patch(
        "app.experts.query_service.ExpertQueryService.query_stream",
        side_effect=_fake_stream_fail,
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/stream",
            headers=headers,
            json={"content": "First fails"},
        ) as res:
            "".join(res.iter_text())

    db.expire_all()
    snaps = UsageSummaryService(db).summarize(uuid.UUID(ws["id"]))
    assert snaps.ai_daily.used == 0
    assert snaps.ai_daily.reserved == 0

    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    failed_id = msgs[1]["id"]

    with patch(
        "app.experts.query_service.ExpertQueryService.query_stream",
        side_effect=_fake_stream_success,
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/{failed_id}/retry/stream",
            headers=headers,
            json={},
        ) as res:
            raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    assert any(n == "final" for n, _ in events)
    db.expire_all()
    snaps = UsageSummaryService(db).summarize(uuid.UUID(ws["id"]))
    assert snaps.ai_daily.used == 6
    assert snaps.ai_daily.reserved == 0

    msgs2 = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    users = [m for m in msgs2 if m["role"] == MessageRole.USER.value]
    assistants = [m for m in msgs2 if m["role"] == MessageRole.ASSISTANT.value]
    assert len(users) == 1
    assert assistants[0]["status"] == MessageStatus.FAILED.value
    assert assistants[1]["status"] == MessageStatus.COMPLETED.value


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_stale_generation_releases_ai_reservation(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    from datetime import datetime, timedelta, timezone

    from app.conversations.models import Message
    from app.conversations.repository import ConversationRepository

    user = register_user(email="5b-stale-res@example.com")
    ws = _create_workspace(client, user["access_token"], "StaleRes", "p5b-stale-res")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "Stale"}).json()
    _force_expert_ready(db, expert["id"])
    plan = _create_ai_plan(db, code="p5b_stale", daily=100_000, weekly=100_000, monthly=100_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    stale = Message(
        conversation_id=uuid.UUID(conv["id"]),
        role=MessageRole.ASSISTANT.value,
        content="orphaned",
        citations=[],
        status=MessageStatus.STREAMING.value,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    ConversationRepository(db).create_message(stale)
    db.commit()
    AiUsageService(db).reserve_ai_usage(uuid.UUID(ws["id"]), str(stale.id), 100)
    db.commit()
    assert UsageSummaryService(db).summarize(uuid.UUID(ws["id"])).ai_daily.reserved == 100

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages/stream",
        headers=headers,
        json={"content": "After crash"},
    ) as res:
        raw = "".join(res.iter_text())

    assert any(n == "final" for n, _ in _parse_sse(raw))
    db.expire_all()
    snaps = UsageSummaryService(db).summarize(uuid.UUID(ws["id"]))
    assert snaps.ai_daily.reserved == 0
    assert snaps.ai_daily.used == 6
    reservation = AiUsageService(db).reservations.get_by_request_id(
        uuid.UUID(ws["id"]), str(stale.id)
    )
    assert reservation is not None
    assert reservation.status == AiUsageReservationStatus.RELEASED.value


@patch("app.experts.query_service.ExpertQueryService.resolve_knowledge", return_value=MagicMock())
@patch(
    "app.experts.query_service.ExpertQueryService.query_stream",
    side_effect=_fake_stream_success,
)
def test_settle_failure_does_not_leave_reserved_hold(
    _mock_stream, _mock_resolve, client, register_user, db
) -> None:
    user = register_user(email="5b-settle-fail@example.com")
    ws = _create_workspace(client, user["access_token"], "SettleFail", "p5b-settle-fail")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "SF"}).json()
    _force_expert_ready(db, expert["id"])
    plan = _create_ai_plan(db, code="p5b_settle_fail", daily=100_000, weekly=100_000, monthly=100_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    ).json()

    with patch(
        "app.conversations.chat_orchestrator.AiUsageService.settle_ai_usage",
        side_effect=RuntimeError("settle boom"),
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conv['id']}/messages/stream",
            headers=headers,
            json={"content": "Will settle-fail"},
        ) as res:
            raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    assert any(n == "error" for n, _ in events)
    db.expire_all()
    snaps = UsageSummaryService(db).summarize(uuid.UUID(ws["id"]))
    assert snaps.ai_daily.reserved == 0
    assert snaps.ai_daily.used == 0
    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=headers).json()
    assert msgs[1]["status"] == MessageStatus.FAILED.value


@patch("app.experts.query_service.ExpertQueryService.query")
def test_api_query_is_metered_and_quota_blocked(
    mock_query, client, register_user, db
) -> None:
    mock_query.return_value = {
        "answer": "ok",
        "insufficient_context": False,
        "citations": [],
        "model": "test-model",
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 1,
            "total_tokens": 4,
            "source": "provider",
        },
    }
    user = register_user(email="5b-query-m@example.com")
    ws = _create_workspace(client, user["access_token"], "QueryM", "p5b-query-m")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "QM"}).json()
    _force_expert_ready(db, expert["id"])
    plan = _create_ai_plan(db, code="p5b_query_ok", daily=100_000, weekly=100_000, monthly=100_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    res = client.post(
        "/api/query",
        headers=headers,
        json={"expert_id": expert["id"], "question": "hello"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    snaps = UsageSummaryService(db).summarize(uuid.UUID(ws["id"]))
    assert snaps.ai_daily.used == 4
    assert snaps.ai_daily.reserved == 0

    tight = _create_ai_plan(db, code="p5b_query_block", daily=1, weekly=1, monthly=1)
    _assign_plan(db, uuid.UUID(ws["id"]), tight.id)
    blocked = client.post(
        "/api/query",
        headers=headers,
        json={"expert_id": expert["id"], "question": "blocked"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "quota_exceeded"
