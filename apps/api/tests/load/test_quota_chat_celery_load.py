"""Phase 11D — quota, credit, chat ContextVar, Celery tenant, usage-write concurrency."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.service import PlanService, SubscriptionService
from app.common.request_context import clear_request_context, get_request_context
from app.common.tenant_context import tenant_context
from app.conversations.invocation import ChatInvocationContext
from app.conversations.turn import ChatTurnExecutor
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.entitlements.cache import invalidate_entitlements
from app.entitlements.keys import EntitlementKey
from app.usage.ai_usage import AiUsageService
from app.usage.credits import CreditService
from app.usage.metered import MeteredWorkspaceGeneration
from app.usage.metrics import CreditLedgerEntryType, UsageMetric
from app.usage.models import CreditLedgerEntry, UsagePeriodCounter
from app.usage.periods import PeriodType
from tests.conftest import TestingSessionLocal


def _auth(token: str, workspace: dict | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace is not None:
        headers["X-Workspace-Id"] = workspace["id"]
    return headers


def _workspace(client, user, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(user["access_token"]),
        json={"name": slug, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _assign_plan(db: Session, workspace_id: uuid.UUID, *, daily: int, weekly: int, monthly: int, code: str) -> None:
    plan = PlanService(db).create_plan(
        code=code,
        name=code,
        description="test",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: daily,
            EntitlementKey.AI_TOKENS_WEEKLY.value: weekly,
            EntitlementKey.AI_TOKENS_MONTHLY.value: monthly,
            EntitlementKey.EXPERTS_LIMIT.value: 10,
            EntitlementKey.STORAGE_BYTES.value: 10_000_000,
        },
        extra={"kind": "test", "commercial": False},
    )
    SubscriptionService(db).assign_plan(workspace_id, plan.id)
    db.commit()
    invalidate_entitlements(workspace_id)


@pytest.mark.load
def test_quota_reservation_concurrency_cannot_overspend(client, register_user, db) -> None:
    user = register_user(email="load-quota@example.com")
    ws = _workspace(client, user, "load-quota-ws")
    wid = uuid.UUID(ws["id"])
    _assign_plan(db, wid, daily=1000, weekly=10_000, monthly=10_000, code="load_quota")

    n = 20
    tokens = 100
    barrier = threading.Barrier(n, timeout=15)
    results: list[tuple[str, Any]] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            try:
                dto = AiUsageService(session).reserve_ai_usage(
                    wid, f"load-{i}-{uuid.uuid4()}", tokens
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
        t.join(timeout=40)
        assert not t.is_alive()

    oks = [r for r in results if r[0] == "ok"]
    fails = [r for r in results if r[0] == "fail"]
    assert len(oks) == 10
    assert len(fails) == 10
    assert all(f[1] == ErrorCategory.QUOTA_EXCEEDED for f in fails)

    db.expire_all()
    row = db.scalar(
        select(UsagePeriodCounter).where(
            UsagePeriodCounter.workspace_id == wid,
            UsagePeriodCounter.metric == UsageMetric.AI_TOKENS.value,
            UsagePeriodCounter.period_type == PeriodType.DAILY.value,
        )
    )
    assert row is not None
    assert row.reserved + row.used <= 1000
    assert row.reserved == 1000


@pytest.mark.load
def test_duplicate_request_id_does_not_double_charge(client, register_user, db) -> None:
    user = register_user(email="load-idem@example.com")
    ws = _workspace(client, user, "load-idem-ws")
    wid = uuid.UUID(ws["id"])
    _assign_plan(db, wid, daily=500, weekly=5000, monthly=5000, code="load_idem")
    rid = "same-request-id-11d"
    barrier = threading.Barrier(8, timeout=15)
    oks = []
    lock = threading.Lock()

    def worker() -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            dto = AiUsageService(session).reserve_ai_usage(wid, rid, 100)
            session.commit()
            with lock:
                oks.append(dto)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)
        assert not t.is_alive()
    assert len(oks) == 8
    db.expire_all()
    row = db.scalar(
        select(UsagePeriodCounter).where(
            UsagePeriodCounter.workspace_id == wid,
            UsagePeriodCounter.metric == UsageMetric.AI_TOKENS.value,
            UsagePeriodCounter.period_type == PeriodType.DAILY.value,
        )
    )
    assert row.reserved == 100


@pytest.mark.load
def test_purchased_credit_fifo_concurrency_stays_non_negative(client, register_user, db) -> None:
    user = register_user(email="load-credit@example.com")
    ws = _workspace(client, user, "load-credit-ws")
    wid = uuid.UUID(ws["id"])
    _assign_plan(db, wid, daily=0, weekly=0, monthly=0, code="load_credit")
    CreditService(db).append(
        wid,
        entry_type=CreditLedgerEntryType.GRANT,
        amount=300,
        request_id="grant-11d",
        source_type="test",
        source_id="pack",
    )
    db.commit()

    n = 10
    barrier = threading.Barrier(n, timeout=15)
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        session = TestingSessionLocal()
        try:
            barrier.wait()
            try:
                AiUsageService(session).reserve_ai_usage(wid, f"cr-{i}-{uuid.uuid4()}", 100)
                session.commit()
                with lock:
                    results.append("ok")
            except AppError:
                session.rollback()
                with lock:
                    results.append("fail")
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)
        assert not t.is_alive()
    assert results.count("ok") == 3
    assert results.count("fail") == 7
    grants = list(
        db.scalars(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.workspace_id == wid,
                CreditLedgerEntry.entry_type == CreditLedgerEntryType.GRANT.value,
            )
        )
    )
    for grant in grants:
        assert grant.remaining_amount is None or grant.remaining_amount >= 0


@pytest.mark.load
def test_chat_turn_contextvar_does_not_bleed(client, register_user, db) -> None:
    user_a = register_user(email="load-chat-a@example.com")
    user_b = register_user(email="load-chat-b@example.com")
    ws_a = _workspace(client, user_a, "load-chat-a")
    ws_b = _workspace(client, user_b, "load-chat-b")
    captured: list[tuple[uuid.UUID | None, uuid.UUID]] = []
    lock = threading.Lock()

    class _Query:
        def query_for_workspace(self, *, workspace, expert_id, question, **kwargs):
            with lock:
                captured.append((get_request_context().workspace_id, workspace.id))
            return {"answer": f"ok-{workspace.id}", "citations": [], "usage": {}}

    barrier = threading.Barrier(12, timeout=15)

    def worker(ws: dict, expert: uuid.UUID) -> None:
        wid = uuid.UUID(ws["id"])
        session = TestingSessionLocal()
        try:
            barrier.wait()
            with tenant_context(workspace_id=wid):
                meter = MagicMock()
                meter.closed = False
                meter.context.return_value = MagicMock(extra_billed_tokens=0)
                meter.settle = MagicMock()
                invocation = ChatInvocationContext.workspace_user(
                    workspace_id=wid,
                    user_id=uuid.uuid4(),
                    expert_id=expert,
                    conversation_id=uuid.uuid4(),
                    message_id=uuid.uuid4(),
                    request_id=str(uuid.uuid4()),
                )
                ChatTurnExecutor(session, expert_query=_Query()).execute(
                    workspace=MagicMock(id=wid),
                    expert_id=expert,
                    question="q",
                    invocation=invocation,
                    meter=meter,
                )
        finally:
            session.close()

    ea, eb = uuid.uuid4(), uuid.uuid4()
    threads = [threading.Thread(target=worker, args=(ws_a, ea)) for _ in range(6)]
    threads += [threading.Thread(target=worker, args=(ws_b, eb)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)
        assert not t.is_alive()
    assert len(captured) == 12
    for ctx_ws, arg_ws in captured:
        assert ctx_ws == arg_ws
    assert {row[1] for row in captured} == {uuid.UUID(ws_a["id"]), uuid.UUID(ws_b["id"])}
    clear_request_context()
    assert get_request_context().workspace_id is None


@pytest.mark.load
def test_celery_tenant_context_cleared_between_tasks() -> None:
    seen: list[uuid.UUID | None] = []
    a = uuid.uuid4()
    b = uuid.uuid4()

    def _task(wid: uuid.UUID) -> None:
        with tenant_context(workspace_id=wid, request_id=str(wid)):
            seen.append(get_request_context().workspace_id)
        seen.append(get_request_context().workspace_id)

    _task(a)
    _task(b)
    assert seen == [a, None, b, None]


@pytest.mark.load
def test_usage_partition_concurrent_writes_keep_workspace(client, register_user, db) -> None:
    user_a = register_user(email="load-ue-a@example.com")
    user_b = register_user(email="load-ue-b@example.com")
    ws_a = _workspace(client, user_a, "load-ue-a")
    ws_b = _workspace(client, user_b, "load-ue-b")
    wa, wb = uuid.UUID(ws_a["id"]), uuid.UUID(ws_b["id"])

    def _write(wid: uuid.UUID, n: int) -> None:
        session = TestingSessionLocal()
        try:
            for _ in range(n):
                session.add(
                    UsageEvent(
                        operation_type="chat",
                        workspace_id=wid,
                        input_tokens=1,
                        output_tokens=1,
                    )
                )
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_write, wa, 25) for _ in range(4)]
        futs += [pool.submit(_write, wb, 25) for _ in range(4)]
        for fut in futs:
            fut.result(timeout=30)

    count_a = db.scalar(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.workspace_id == wa)
    )
    count_b = db.scalar(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.workspace_id == wb)
    )
    assert count_a == 100
    assert count_b == 100
