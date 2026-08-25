"""Phase 14 paid Agent admission transaction tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.agent.admission as admission_module
from app.apps_catalog.access import RuntimeAppAccessSnapshot
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENT_REQUESTS_USAGE_METRIC,
    AGENTS_AI_APP_SLUG,
)
from app.apps_catalog.agent_usage import AgentRequestQuotaReceipt
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.quota import AiTokenLimits
from app.usage.attribution import GenerationUsageContext


class _RowResult:
    def __init__(self, row) -> None:
        self.row = row

    def one_or_none(self):
        return self.row


class _AdmissionDb:
    def __init__(self, events: list[str], row) -> None:
        self.events = events
        self.row = row
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def execute(self, _statement):
        self.events.append("expert_lock")
        return _RowResult(self.row)

    def commit(self) -> None:
        self.events.append("commit")
        self.commits += 1

    def rollback(self) -> None:
        self.events.append("rollback")
        self.rollbacks += 1

    def close(self) -> None:
        self.events.append("close")
        self.closes += 1


class _Meter:
    def __init__(
        self,
        events: list[str],
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        api_key_id: uuid.UUID,
        request_id: str,
    ) -> None:
        self.events = events
        self.request_id = request_id
        self._context = GenerationUsageContext(
            workspace_id=workspace_id,
            expert_id=expert_id,
            api_key_id=api_key_id,
            request_id=request_id,
        )
        self.settled = False
        self.released = False

    def reserve_in_transaction(self, limits: AiTokenLimits):
        assert limits == AiTokenLimits(daily=100, weekly=500, monthly=2_000)
        self.events.append("ai_reserve")
        return self._context

    def context(self) -> GenerationUsageContext:
        return self._context

    def settle(self, _payload) -> None:
        self.events.append("ai_settle")
        self.settled = True

    def release(self) -> None:
        self.events.append("ai_release")
        self.released = True


def _snapshot(workspace_id: uuid.UUID) -> RuntimeAppAccessSnapshot:
    now = datetime.now(timezone.utc)
    return RuntimeAppAccessSnapshot(
        decision_at=now,
        workspace_id=workspace_id,
        app_id=uuid.uuid4(),
        app_slug=AGENTS_AI_APP_SLUG,
        installation_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        plan_code="fixture",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
        entitlements=MappingProxyType({AGENT_REQUESTS_DAILY_ENTITLEMENT: 5}),
    )


def _receipt(request_id: str, limit: int = 5) -> AgentRequestQuotaReceipt:
    now = datetime.now(timezone.utc)
    return AgentRequestQuotaReceipt(
        request_id=request_id,
        metric=AGENT_REQUESTS_USAGE_METRIC,
        period_start=now,
        period_end=now + timedelta(days=1),
        counter_id=uuid.uuid4(),
        used=1,
        limit=limit,
    )


def _patch_successful_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
    db: _AdmissionDb,
    access: RuntimeAppAccessSnapshot,
    knowledge,
    quota_error: AppError | None = None,
) -> dict[str, _Meter]:
    meter_holder: dict[str, _Meter] = {}
    monkeypatch.setattr(admission_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        admission_module,
        "begin_runtime_admission_transaction",
        lambda session: events.append("begin"),
    )
    monkeypatch.setattr(
        admission_module,
        "acquire_runtime_admission_fences",
        lambda session, **kwargs: events.append("fences"),
    )

    class AccessService:
        def __init__(self, _db) -> None:
            pass

        def require_runtime_active(self, workspace_id, **kwargs):
            assert workspace_id == access.workspace_id
            assert kwargs == {
                "app_slug": AGENTS_AI_APP_SLUG,
                "entitlement_keys": (AGENT_REQUESTS_DAILY_ENTITLEMENT,),
            }
            events.append("app_access")
            return access

    class QueryService:
        def __init__(self, _db, _settings) -> None:
            pass

        def _finish_prepare(self, authorized, **kwargs):
            assert authorized.ownership == "workspace"
            assert authorized.membership is None
            events.append("knowledge")
            return knowledge

    class QuotaService:
        def __init__(self, _db, _settings) -> None:
            pass

        def get_ai_limits_db_only(self, workspace_id):
            assert workspace_id == access.workspace_id
            events.append("ai_limits")
            return AiTokenLimits(daily=100, weekly=500, monthly=2_000)

    class AppQuotaService:
        def __init__(self, _db) -> None:
            pass

        def consume_in_transaction(self, **kwargs):
            events.append("app_quota")
            if quota_error is not None:
                raise quota_error
            return _receipt(kwargs["request_id"])

    def build_meter(
        _db,
        *,
        workspace_id,
        expert_id,
        api_key_id,
        request_id,
        settings,
        **_kwargs,
    ):
        meter = _Meter(
            events,
            workspace_id=workspace_id,
            expert_id=expert_id,
            api_key_id=api_key_id,
            request_id=request_id,
        )
        meter_holder["meter"] = meter
        return meter

    monkeypatch.setattr(admission_module, "AppAccessService", AccessService)
    monkeypatch.setattr(admission_module, "ExpertQueryService", QueryService)
    monkeypatch.setattr(admission_module, "QuotaService", QuotaService)
    monkeypatch.setattr(
        admission_module, "AgentsAiRequestQuotaService", AppQuotaService
    )
    monkeypatch.setattr(admission_module, "MeteredWorkspaceGeneration", build_meter)
    return meter_holder


def test_completion_admission_commits_after_every_authority_and_quota_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    request_id = "agent-ordered-admission"
    access = _snapshot(workspace_id)
    expert = SimpleNamespace(
        id=expert_id,
        workspace_id=workspace_id,
        rag_config={"client_agent": {"enabled": True}},
    )
    workspace = SimpleNamespace(id=workspace_id)
    knowledge = SimpleNamespace(authorized=SimpleNamespace(expert=expert))
    db = _AdmissionDb(events, (expert, workspace))
    meter_holder = _patch_successful_dependencies(
        monkeypatch,
        events=events,
        db=db,
        access=access,
        knowledge=knowledge,
    )

    admitted = admission_module.admit_agent_completion(
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        expert_id=expert_id,
        request_id=request_id,
        settings=Settings(_env_file=None),
    )

    assert events == [
        "begin",
        "fences",
        "app_access",
        "expert_lock",
        "knowledge",
        "ai_limits",
        "ai_reserve",
        "app_quota",
        "commit",
    ]
    assert admitted.request_id == request_id
    assert admitted.access is access
    assert admitted.knowledge is knowledge
    assert admitted.quota.used == 1
    assert admitted.usage_context().api_key_id == api_key_id
    assert admitted.meter is meter_holder["meter"]
    assert db.rollbacks == 0 and db.closes == 0

    admitted.release()
    assert events[-2:] == ["ai_release", "close"]
    assert db.closes == 1


def test_daily_quota_failure_rolls_back_ai_hold_and_preserves_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    access = _snapshot(workspace_id)
    expert = SimpleNamespace(
        id=expert_id,
        workspace_id=workspace_id,
        rag_config={"client_agent": {"enabled": True}},
    )
    db = _AdmissionDb(events, (expert, SimpleNamespace(id=workspace_id)))
    quota_error = AppError(
        ErrorCategory.AGENT_REQUEST_QUOTA_EXCEEDED,
        "daily limit",
        headers={"Retry-After": "30"},
    )
    _patch_successful_dependencies(
        monkeypatch,
        events=events,
        db=db,
        access=access,
        knowledge=SimpleNamespace(authorized=SimpleNamespace(expert=expert)),
        quota_error=quota_error,
    )

    with pytest.raises(AppError) as raised:
        admission_module.admit_agent_completion(
            workspace_id=workspace_id,
            api_key_id=uuid.uuid4(),
            expert_id=expert_id,
            request_id="over-limit",
            settings=Settings(_env_file=None),
        )

    assert raised.value is quota_error
    assert events[-4:] == ["ai_reserve", "app_quota", "rollback", "close"]
    assert db.commits == 0 and db.rollbacks == 1 and db.closes == 1


def test_missing_or_non_workspace_expert_fails_before_any_usage_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    workspace_id = uuid.uuid4()
    db = _AdmissionDb(events, None)
    access = _snapshot(workspace_id)
    monkeypatch.setattr(admission_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        admission_module,
        "begin_runtime_admission_transaction",
        lambda _db: events.append("begin"),
    )
    monkeypatch.setattr(
        admission_module,
        "acquire_runtime_admission_fences",
        lambda _db, **kwargs: events.append("fences"),
    )

    class AccessService:
        def __init__(self, _db) -> None:
            pass

        def require_runtime_active(self, *_args, **_kwargs):
            events.append("app_access")
            return access

    monkeypatch.setattr(admission_module, "AppAccessService", AccessService)

    with pytest.raises(AppError) as raised:
        admission_module.admit_agent_completion(
            workspace_id=workspace_id,
            api_key_id=uuid.uuid4(),
            expert_id=uuid.uuid4(),
            request_id="missing-expert",
            settings=Settings(_env_file=None),
        )

    assert raised.value.category == ErrorCategory.EXPERT_NOT_FOUND
    assert events == [
        "begin",
        "fences",
        "app_access",
        "expert_lock",
        "rollback",
        "close",
    ]


def test_sqlalchemy_admission_failure_is_fail_closed_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    workspace_id = uuid.uuid4()
    db = _AdmissionDb(events, None)
    monkeypatch.setattr(admission_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        admission_module,
        "begin_runtime_admission_transaction",
        lambda _db: (_ for _ in ()).throw(SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(AppError) as raised:
        admission_module.admit_agent_completion(
            workspace_id=workspace_id,
            api_key_id=uuid.uuid4(),
            expert_id=uuid.uuid4(),
            settings=Settings(_env_file=None),
        )

    assert raised.value.category == ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE
    assert raised.value.retryable is True
    assert events == ["rollback", "close"]


def test_models_access_uses_only_fences_and_paid_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    workspace_id = uuid.uuid4()
    db = _AdmissionDb(events, None)
    access = _snapshot(workspace_id)
    monkeypatch.setattr(admission_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        admission_module,
        "begin_runtime_admission_transaction",
        lambda _db: events.append("begin"),
    )
    monkeypatch.setattr(
        admission_module,
        "acquire_runtime_admission_fences",
        lambda _db, **kwargs: events.append("fences"),
    )

    class AccessService:
        def __init__(self, _db) -> None:
            pass

        def require_runtime_active(self, workspace, **kwargs):
            assert workspace == workspace_id
            events.append("app_access")
            return access

    monkeypatch.setattr(admission_module, "AppAccessService", AccessService)

    result = admission_module.require_agent_models_access(workspace_id)

    assert result is access
    assert events == ["begin", "fences", "app_access", "commit", "close"]


def test_models_commit_failure_is_fail_closed_without_rollback_masking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    workspace_id = uuid.uuid4()
    access = _snapshot(workspace_id)

    class FailingDb(_AdmissionDb):
        def commit(self) -> None:
            self.events.append("commit")
            raise SQLAlchemyError("commit unavailable")

        def rollback(self) -> None:
            self.events.append("rollback")
            raise SQLAlchemyError("rollback unavailable")

    db = FailingDb(events, None)
    monkeypatch.setattr(admission_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        admission_module,
        "begin_runtime_admission_transaction",
        lambda _db: events.append("begin"),
    )
    monkeypatch.setattr(
        admission_module,
        "acquire_runtime_admission_fences",
        lambda _db, **kwargs: events.append("fences"),
    )

    class AccessService:
        def __init__(self, _db) -> None:
            pass

        def require_runtime_active(self, workspace, **kwargs):
            assert workspace == workspace_id
            events.append("app_access")
            return access

    monkeypatch.setattr(admission_module, "AppAccessService", AccessService)

    with pytest.raises(AppError) as raised:
        admission_module.require_agent_models_access(workspace_id)

    assert raised.value.category == ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE
    assert raised.value.retryable is True
    assert isinstance(raised.value.__cause__, SQLAlchemyError)
    assert events == [
        "begin",
        "fences",
        "app_access",
        "commit",
        "rollback",
        "close",
    ]
