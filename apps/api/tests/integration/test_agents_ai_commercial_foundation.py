from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.orm import Session

import app.agent.router as agent_router
from app.agent.admission import admit_agent_completion, require_agent_models_access
from app.api_keys.scopes import SCOPE_AGENT_WRITE
from app.apps_catalog.access import AppAccessService
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENT_REQUESTS_USAGE_METRIC,
    AGENTS_AI_APP_SLUG,
)
from app.apps_catalog.agent_usage import AgentsAiRequestQuotaService
from app.apps_catalog.models import (
    AppInstallation,
    AppInstallationStatus,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
)
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    acquire_workspace_app_runtime_mutation_fence,
    begin_runtime_admission_transaction,
)
from app.apps_catalog.seed import ensure_app_catalog
from app.common.public_model import PUBLIC_MODEL_ID
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import Document
from app.db.session import engine as production_engine
from app.entitlements.quota import QuotaService
from app.experts.models import Expert, ExpertDocument, ExpertStatus, ExpertType
from app.usage.metered import MeteredWorkspaceGeneration
from app.usage.models import AiUsageReservation, UsagePeriodCounter
from tests.conftest import TestingSessionLocal, engine


def _auth(token: str, workspace_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Workspace-Id": workspace_id,
    }


def _workspace(client, register_user) -> tuple[dict, dict]:
    user = register_user(email=f"agents-{uuid.uuid4().hex[:8]}@example.com")
    response = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={"name": "Agents fixture", "slug": f"agents-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code in {200, 201}, response.text
    return user, response.json()


def _grant_agents_access(
    db: Session, workspace_id: uuid.UUID, *, limit: int
) -> AppPlan:
    ensure_app_catalog(db)
    catalog = AppAccessService(db).repo.get_app_by_slug(AGENTS_AI_APP_SLUG)
    assert catalog is not None
    catalog.status = AppStatus.PUBLISHED.value
    plan = AppPlan(
        app_id=catalog.id,
        code=f"fixture-{uuid.uuid4().hex[:8]}",
        name="Agents fixture plan",
        description="Isolated test fixture; not production pricing.",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=Decimal("1.00"),
        currency="SAR",
        sort_order=10,
        is_default=True,
        is_active=True,
    )
    db.add(plan)
    db.flush()
    db.add(
        AppPlanEntitlement(
            app_plan_id=plan.id,
            key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
            value=limit,
        )
    )
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            AppInstallation(
                workspace_id=workspace_id,
                app_id=catalog.id,
                status=AppInstallationStatus.ACTIVE.value,
                installed_at=now,
            ),
            AppSubscription(
                workspace_id=workspace_id,
                app_id=catalog.id,
                app_plan_id=plan.id,
                status=AppSubscriptionStatus.ACTIVE.value,
                current_period_start=now - timedelta(minutes=1),
                current_period_end=now + timedelta(days=30),
            ),
        ]
    )
    db.commit()
    return plan


def _create_admission_expert(db: Session, workspace_id: uuid.UUID) -> Expert:
    expert = Expert(
        workspace_id=workspace_id,
        type=ExpertType.WORKSPACE.value,
        name="Agent admission load fixture",
        status=ExpertStatus.READY.value,
        system_instructions="Answer from the authorized fixture.",
        rag_config={"client_agent": {"enabled": True}},
    )
    document = Document(
        workspace_id=workspace_id,
        title="Agent admission load source",
        original_filename="agent-admission-load.txt",
        storage_key=f"tests/{workspace_id}/agent-admission-load.txt",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        mime_type="text/plain",
        byte_size=20,
        page_count=1,
        status="ready",
        processing_version={"fixture": "phase14-admission-load"},
    )
    db.add_all([expert, document])
    db.flush()
    db.add(ExpertDocument(expert_id=expert.id, document_id=document.id))
    db.commit()
    return expert


def _production_admit(
    *,
    workspace_id: uuid.UUID,
    expert_id: uuid.UUID,
    api_key_id: uuid.UUID,
    request_id: str,
):
    return admit_agent_completion(
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        expert_id=expert_id,
        request_id=request_id,
        # Keep the load fixture small while executing the unchanged production
        # reservation path. The commercial daily counter is the boundary under
        # test, independent of the Workspace AI-token amount reserved here.
        settings=Settings(_env_file=None, ai_usage_reservation_tokens=1),
    )


def _admit(db: Session, workspace_id: uuid.UUID, request_id: str):
    begin_runtime_admission_transaction(db)
    acquire_runtime_admission_fences(
        db, workspace_id=workspace_id, app_slugs=(AGENTS_AI_APP_SLUG,)
    )
    access = AppAccessService(db).require_runtime_active(
        workspace_id,
        app_slug=AGENTS_AI_APP_SLUG,
        entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
    )
    limits = QuotaService(db).get_ai_limits_db_only(workspace_id)
    generation = MeteredWorkspaceGeneration(
        db, workspace_id=workspace_id, request_id=request_id
    )
    generation.reserve_in_transaction(limits)
    receipt = AgentsAiRequestQuotaService(db).consume_in_transaction(
        workspace_id=workspace_id, request_id=request_id, access=access
    )
    return access, receipt


def _runtime_access(db: Session, workspace_id: uuid.UUID):
    try:
        begin_runtime_admission_transaction(db)
        acquire_runtime_admission_fences(
            db, workspace_id=workspace_id, app_slugs=(AGENTS_AI_APP_SLUG,)
        )
        return AppAccessService(db).require_runtime_active(
            workspace_id,
            app_slug=AGENTS_AI_APP_SLUG,
            entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
        )
    finally:
        db.rollback()


def test_runtime_access_is_one_fresh_data_select(client, register_user, db) -> None:
    _user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    _grant_agents_access(db, workspace_id, limit=3)
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        if "runtime_clock" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        begin_runtime_admission_transaction(db)
        acquire_runtime_admission_fences(
            db, workspace_id=workspace_id, app_slugs=(AGENTS_AI_APP_SLUG,)
        )
        snapshot = AppAccessService(db).require_runtime_active(
            workspace_id,
            app_slug=AGENTS_AI_APP_SLUG,
            entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
        )
        assert snapshot.entitlement(AGENT_REQUESTS_DAILY_ENTITLEMENT) == 3
        assert snapshot.workspace_id == workspace_id
        assert len(statements) == 1
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        db.rollback()


def test_runtime_access_uses_database_time_same_app_plan_and_fresh_entitlement(
    client, register_user, db
) -> None:
    _user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    plan = _grant_agents_access(db, workspace_id, limit=3)
    subscription = db.scalar(
        select(AppSubscription).where(
            AppSubscription.workspace_id == workspace_id,
            AppSubscription.app_id == plan.app_id,
        )
    )
    assert subscription is not None

    # Both bounds are database-authored. A start at the previous statement's
    # timestamp is admitted, while an end at that timestamp is excluded by the
    # locked [period_start, period_end) contract.
    db.execute(
        update(AppSubscription)
        .where(AppSubscription.id == subscription.id)
        .values(
            status=AppSubscriptionStatus.ACTIVE.value,
            current_period_start=func.statement_timestamp(),
            current_period_end=func.statement_timestamp() + timedelta(days=1),
        )
    )
    db.commit()
    assert _runtime_access(db, workspace_id).plan_id == plan.id

    db.execute(
        update(AppSubscription)
        .where(AppSubscription.id == subscription.id)
        .values(current_period_end=func.statement_timestamp())
    )
    db.commit()
    with pytest.raises(AppError) as expired:
        _runtime_access(db, workspace_id)
    assert expired.value.category == ErrorCategory.APP_SUBSCRIPTION_EXPIRED

    # A subscription cannot borrow a plan (and entitlements) from another App.
    foreign_plan_id = db.scalar(
        select(AppPlan.id).where(AppPlan.app_id != plan.app_id).limit(1)
    )
    assert foreign_plan_id is not None
    db.execute(
        update(AppSubscription)
        .where(AppSubscription.id == subscription.id)
        .values(
            app_plan_id=foreign_plan_id,
            current_period_start=func.statement_timestamp() - timedelta(days=1),
            current_period_end=func.statement_timestamp() + timedelta(days=1),
        )
    )
    db.commit()
    with pytest.raises(AppError) as mismatched:
        _runtime_access(db, workspace_id)
    assert mismatched.value.category == ErrorCategory.ENTITLEMENT_INVALID

    # The authoritative SELECT observes entitlement deletion/reduction on the
    # next transaction; no positive cache or second resolver can mask it.
    db.execute(
        update(AppSubscription)
        .where(AppSubscription.id == subscription.id)
        .values(app_plan_id=plan.id)
    )
    db.execute(
        delete(AppPlanEntitlement).where(
            AppPlanEntitlement.app_plan_id == plan.id,
            AppPlanEntitlement.key == AGENT_REQUESTS_DAILY_ENTITLEMENT,
        )
    )
    db.commit()
    with pytest.raises(AppError) as missing:
        _runtime_access(db, workspace_id)
    assert missing.value.category == ErrorCategory.ENTITLEMENT_INVALID

    entitlement = AppPlanEntitlement(
        app_plan_id=plan.id,
        key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
        value=1,
    )
    db.add(entitlement)
    db.commit()
    assert _runtime_access(db, workspace_id).entitlement(
        AGENT_REQUESTS_DAILY_ENTITLEMENT
    ) == 1

    entitlement.value = 0
    db.commit()
    with pytest.raises(AppError) as non_positive:
        _runtime_access(db, workspace_id)
    assert non_positive.value.category == ErrorCategory.ENTITLEMENT_INVALID

    entitlement.value = "1"
    db.commit()
    with pytest.raises(AppError) as malformed:
        _runtime_access(db, workspace_id)
    assert malformed.value.category == ErrorCategory.ENTITLEMENT_INVALID


def test_waiting_admission_observes_restrictive_commit_before_access_select(
    client, register_user, db
) -> None:
    _user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    plan = _grant_agents_access(db, workspace_id, limit=3)
    writer = TestingSessionLocal()
    observer = TestingSessionLocal()
    pid_ready = threading.Event()
    access_select_started = threading.Event()
    waiter_pid: list[int] = []
    outcomes: list[str] = []
    thread: threading.Thread | None = None

    try:
        acquire_workspace_app_runtime_mutation_fence(
            writer,
            workspace_id=workspace_id,
            app_slug=AGENTS_AI_APP_SLUG,
        )
        writer.execute(
            update(AppInstallation)
            .where(
                AppInstallation.workspace_id == workspace_id,
                AppInstallation.app_id == plan.app_id,
            )
            .values(status=AppInstallationStatus.UNINSTALLED.value)
        )

        def wait_then_resolve() -> None:
            session = TestingSessionLocal()
            try:
                begin_runtime_admission_transaction(session)
                waiter_pid.append(int(session.scalar(text("SELECT pg_backend_pid()"))))
                pid_ready.set()
                acquire_runtime_admission_fences(
                    session,
                    workspace_id=workspace_id,
                    app_slugs=(AGENTS_AI_APP_SLUG,),
                )
                access_select_started.set()
                try:
                    AppAccessService(session).require_runtime_active(
                        workspace_id,
                        app_slug=AGENTS_AI_APP_SLUG,
                        entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
                    )
                    outcomes.append("unexpected-active")
                except AppError as exc:
                    outcomes.append(exc.category.value)
                finally:
                    session.rollback()
            finally:
                session.close()

        thread = threading.Thread(target=wait_then_resolve)
        thread.start()
        assert pid_ready.wait(timeout=5)

        deadline = time.monotonic() + 5
        waiting_on_fence = False
        while time.monotonic() < deadline:
            waiting_on_fence = bool(
                observer.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_locks "
                        "WHERE pid = :pid AND locktype = 'advisory' "
                        "AND granted = false)"
                    ),
                    {"pid": waiter_pid[0]},
                )
            )
            if waiting_on_fence:
                break
            time.sleep(0.01)
        assert waiting_on_fence is True
        assert access_select_started.is_set() is False

        writer.commit()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert access_select_started.is_set() is True
        assert outcomes == [ErrorCategory.APP_NOT_INSTALLED.value]
    finally:
        writer.rollback()
        if thread is not None:
            thread.join(timeout=10)
        writer.close()
        observer.rollback()
        observer.close()


def test_runtime_access_reviewed_plan_and_warm_p95(
    client, register_user, db
) -> None:
    _user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    _grant_agents_access(db, workspace_id, limit=3)
    durations_ms: list[float] = []
    transaction_durations_ms: list[float] = []
    started_at: dict[int, float] = {}
    captured: list[tuple[str, object]] = []

    def before(_conn, _cursor, statement, parameters, context, _many) -> None:
        if "runtime_clock" not in statement or statement.lstrip().startswith("EXPLAIN"):
            return
        started_at[id(context)] = time.perf_counter()
        if not captured:
            captured.append((statement, parameters))

    def after(_conn, _cursor, statement, _parameters, context, _many) -> None:
        if "runtime_clock" not in statement or id(context) not in started_at:
            return
        durations_ms.append(
            (time.perf_counter() - started_at.pop(id(context))) * 1_000
        )

    event.listen(production_engine, "before_cursor_execute", before)
    event.listen(production_engine, "after_cursor_execute", after)
    try:
        for _index in range(45):
            transaction_started = time.perf_counter()
            assert require_agent_models_access(workspace_id).entitlement(
                AGENT_REQUESTS_DAILY_ENTITLEMENT
            ) == 3
            transaction_durations_ms.append(
                (time.perf_counter() - transaction_started) * 1_000
            )
    finally:
        event.remove(production_engine, "before_cursor_execute", before)
        event.remove(production_engine, "after_cursor_execute", after)

    assert len(durations_ms) == 45
    warm = sorted(durations_ms[5:])
    p95 = warm[max(0, int(len(warm) * 0.95) - 1)]
    assert p95 <= 20.0, f"runtime access data SELECT p95 was {p95:.2f} ms"
    # This is the production Models authority path, timed outside SessionLocal:
    # fresh READ COMMITTED setup + verification, one shared fence statement,
    # one authoritative data SELECT, commit, and session/connection return.
    warm_transactions = sorted(transaction_durations_ms[5:])
    transaction_p95 = warm_transactions[
        max(0, int(len(warm_transactions) * 0.95) - 1)
    ]
    assert transaction_p95 <= 20.0, (
        "full runtime access transaction p95 was "
        f"{transaction_p95:.2f} ms"
    )

    statement, parameters = captured[0]
    explained = db.connection().exec_driver_sql(
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}",
        parameters,
    ).scalar_one()
    db.rollback()
    assert isinstance(explained, list) and len(explained) == 1
    report = explained[0]
    plan = report["Plan"]
    nodes = list(_walk_explain_nodes(plan))
    expected_relations = {
        "workspaces",
        "apps",
        "app_installations",
        "app_subscriptions",
        "app_plans",
        "app_plan_entitlements",
    }
    assert expected_relations <= {
        str(node["Relation Name"])
        for node in nodes
        if "Relation Name" in node
    }
    assert plan["Plan Rows"] == 1
    assert plan["Actual Rows"] == 1
    assert all(int(node.get("Temp Read Blocks", 0)) == 0 for node in nodes)
    assert all(int(node.get("Temp Written Blocks", 0)) == 0 for node in nodes)
    assert float(report["Execution Time"]) <= 20.0

    # The fixture is intentionally small, so PostgreSQL may rationally choose
    # sequential scans. A second planner-only review with seqscan disabled
    # proves every authority relation has a viable bounded index path; this
    # fails if a required production index is removed.
    db.execute(text("SET LOCAL enable_seqscan = off"))
    indexed = db.connection().exec_driver_sql(
        f"EXPLAIN (FORMAT JSON) {statement}",
        parameters,
    ).scalar_one()
    db.rollback()
    indexed_nodes = list(_walk_explain_nodes(indexed[0]["Plan"]))
    for relation in expected_relations:
        relation_nodes = [
            node
            for node in indexed_nodes
            if node.get("Relation Name") == relation
        ]
        assert relation_nodes, f"reviewed plan omitted {relation}"
        assert all(
            node["Node Type"] != "Seq Scan" for node in relation_nodes
        ), f"reviewed plan has no bounded index path for {relation}"


def test_atomic_daily_consume_receipt_and_n_plus_one(
    client, register_user, db
) -> None:
    _user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    _grant_agents_access(db, workspace_id, limit=1)
    expert = _create_admission_expert(db, workspace_id)
    api_key_id = uuid.uuid4()

    first_admission = _production_admit(
        workspace_id=workspace_id,
        expert_id=expert.id,
        api_key_id=api_key_id,
        request_id="agents-request-1",
    )
    first = first_admission.quota
    first_admission.release()
    assert first.used == 1

    replay_admission = _production_admit(
        workspace_id=workspace_id,
        expert_id=expert.id,
        api_key_id=api_key_id,
        request_id="agents-request-1",
    )
    replay = replay_admission.quota
    replay_admission.release()
    assert replay.counter_id == first.counter_id
    assert replay.used == 1

    with pytest.raises(AppError) as blocked:
        _production_admit(
            workspace_id=workspace_id,
            expert_id=expert.id,
            api_key_id=api_key_id,
            request_id="agents-request-2",
        )
    assert blocked.value.category == ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED
    assert blocked.value.headers["Retry-After"]
    assert blocked.value.details == {
        "metric": AGENT_REQUESTS_USAGE_METRIC,
        "limit": 1,
        "used": 1,
        "remaining": 0,
        "reset_at": first.period_end.isoformat(),
    }
    db.rollback()

    used = db.scalar(
        select(UsagePeriodCounter.used).where(
            UsagePeriodCounter.workspace_id == workspace_id,
            UsagePeriodCounter.metric == AGENT_REQUESTS_USAGE_METRIC,
        )
    )
    assert used == 1
    assert db.scalar(
        select(func.count())
        .select_from(AiUsageReservation)
        .where(
            AiUsageReservation.workspace_id == workspace_id,
            AiUsageReservation.request_id == "agents-request-2",
        )
    ) == 0


def test_concurrent_admission_allows_exactly_daily_limit(
    client, register_user, db
) -> None:
    _user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    limit = 3
    workers = 8
    _grant_agents_access(db, workspace_id, limit=limit)
    expert = _create_admission_expert(db, workspace_id)
    api_key_id = uuid.uuid4()
    barrier = threading.Barrier(workers, timeout=10)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    provider_starts = 0
    admission_sql: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        normalized = " ".join(statement.lower().split())
        with outcomes_lock:
            admission_sql.append(normalized)

    def run(index: int) -> None:
        nonlocal provider_starts
        try:
            barrier.wait()
            try:
                admitted = _production_admit(
                    workspace_id=workspace_id,
                    expert_id=expert.id,
                    api_key_id=api_key_id,
                    request_id=f"concurrent-agent-{index}",
                )
                # This marks the first expensive step after the production
                # coordinator returns a committed admission. Denied callers
                # must never reach it.
                with outcomes_lock:
                    provider_starts += 1
                admitted.release()
                outcome = "ok"
            except AppError as exc:
                outcome = exc.category.value
            except Exception as exc:  # pragma: no cover - assertion reports type
                outcome = f"unexpected:{type(exc).__name__}"
            with outcomes_lock:
                outcomes.append(outcome)
        except threading.BrokenBarrierError:  # pragma: no cover - diagnostic
            with outcomes_lock:
                outcomes.append("unexpected:BrokenBarrierError")

    threads = [threading.Thread(target=run, args=(index,)) for index in range(workers)]
    event.listen(production_engine, "before_cursor_execute", capture)
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
    finally:
        event.remove(production_engine, "before_cursor_execute", capture)

    assert outcomes.count("ok") == limit
    assert outcomes.count(ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED.value) == (
        workers - limit
    )
    assert provider_starts == limit

    access_selects = [sql for sql in admission_sql if "runtime_clock" in sql]
    shared_fences = [
        sql for sql in admission_sql if "pg_advisory_xact_lock_shared" in sql
    ]
    isolation_sets = [
        sql
        for sql in admission_sql
        if sql.startswith("set transaction isolation level read committed")
    ]
    isolation_checks = [
        sql for sql in admission_sql if sql.startswith("show transaction_isolation")
    ]
    app_entitlement_reads = [
        sql for sql in admission_sql if "app_plan_entitlements" in sql
    ]
    assert len(isolation_sets) == workers
    assert len(isolation_checks) == workers
    assert len(shared_fences) == workers
    assert len(access_selects) == workers
    assert app_entitlement_reads == access_selects


def test_protocol_reject_performs_zero_paid_admission_queries(
    client,
    register_user,
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, workspace = _workspace(client, register_user)
    _grant_agents_access(db, uuid.UUID(workspace["id"]), limit=2)
    created = client.post(
        "/api/api-keys",
        headers=_auth(user["access_token"], workspace["id"]),
        json={"name": "Agent query-count reject", "scopes": [SCOPE_AGENT_WRITE]},
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    monkeypatch.setattr(
        agent_router,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            client_agent_api_enabled=True,
            openrouter_api_key="test-openrouter-key",
        ),
    )
    admission_sql: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        normalized = " ".join(statement.lower().split())
        if (
            "runtime_clock" in normalized
            or "pg_advisory_xact_lock_shared" in normalized
            or "app_plan_entitlements" in normalized
        ):
            admission_sql.append(normalized)

    event.listen(production_engine, "before_cursor_execute", capture)
    try:
        rejected = client.post(
            "/api/v1/agent/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "X-Geem-Expert-Id": str(uuid.uuid4()),
            },
            json={
                "model": PUBLIC_MODEL_ID,
                "messages": [
                    {"role": "user", "content": "question"},
                    {"role": "assistant", "content": "unfinished answer"},
                ],
            },
        )
    finally:
        event.remove(production_engine, "before_cursor_execute", capture)

    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["error"]["code"] == "agent_invalid_tool_transcript"
    assert admission_sql == []


def _walk_explain_nodes(plan: dict):
    yield plan
    for child in plan.get("Plans", []):
        yield from _walk_explain_nodes(child)


def test_usage_endpoint_returns_authoritative_daily_snapshot(
    client, register_user, db
) -> None:
    user, workspace = _workspace(client, register_user)
    workspace_id = uuid.UUID(workspace["id"])
    plan = _grant_agents_access(db, workspace_id, limit=2)
    # Existing subscribers retain their current tier when it stops accepting
    # new sales; usage/UI still need its signed commercial display fields.
    plan.is_active = False
    db.commit()
    _admit(db, workspace_id, "agents-usage-route")
    db.commit()

    response = client.get(
        "/api/apps/agents-ai/usage",
        headers=_auth(user["access_token"], workspace["id"]),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["access"]["status"] == "active"
    assert payload["access"]["installed"] is True
    assert payload["access"]["plan_price_amount"] == "1.00"
    assert payload["access"]["plan_currency"] == "SAR"
    assert payload["access"]["plan_billing_interval"] == "monthly"
    assert payload["agent_requests_daily"]["used"] == 1
    assert payload["agent_requests_daily"]["limit"] == 2
    assert payload["base_url"].endswith("/api/v1/agent")
    assert payload["model"]


def test_agent_scope_issuance_requires_current_paid_access(
    client, register_user, db
) -> None:
    user, workspace = _workspace(client, register_user)
    ensure_app_catalog(db)
    db.commit()
    denied = client.post(
        "/api/api-keys",
        headers=_auth(user["access_token"], workspace["id"]),
        json={"name": "Agent denied", "scopes": [SCOPE_AGENT_WRITE]},
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["code"] == ErrorCategory.APP_NOT_AVAILABLE.value
    db.rollback()

    _grant_agents_access(db, uuid.UUID(workspace["id"]), limit=2)
    created = client.post(
        "/api/api-keys",
        headers=_auth(user["access_token"], workspace["id"]),
        json={"name": "Agent active", "scopes": [SCOPE_AGENT_WRITE]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["scopes"] == [SCOPE_AGENT_WRITE]
