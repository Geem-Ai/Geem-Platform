from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.mcp.resolver as resolver_module
import app.mcp.services as services_module
from app.connectors.types import ConnectionHealth, ConnectionStatus
from app.conversations.invocation import ChatInvocationContext
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.repository import McpGrantRecord
from app.mcp.resolver import McpGrantResolver
from app.mcp.services import McpServerService
from app.mcp.surfaces import (
    _grant_is_current as _surface_grant_is_current,
    _provider_schema as _surface_provider_schema,
)
from app.mcp.types import (
    McpCompatibilityStatus,
    McpGrantState,
    McpToolClassification,
    McpToolStatus,
    annotations_forbid_read_only,
)


def _enabled_settings():
    return get_settings().model_copy(update={"mcp_connector_enabled": True})


def test_zero_source_grant_returns_before_paid_lookup(monkeypatch) -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    events: list[str] = []

    class _Repo:
        def __init__(self, _db) -> None:
            pass

        def has_eligible_source_grant(self, *args, **kwargs) -> bool:
            events.append("preflight")
            return False

    monkeypatch.setattr(resolver_module, "McpRepository", _Repo)
    resolver = McpGrantResolver(
        SimpleNamespace(),
        settings=_enabled_settings(),
        session_factory=lambda: (_ for _ in ()).throw(
            AssertionError("paid lookup must not start")
        ),
    )
    invocation = ChatInvocationContext.workspace_user(
        workspace_id=workspace_id,
        user_id=uuid.uuid4(),
        expert_id=expert_id,
    )

    assert resolver.resolve(invocation, expert_id) == []
    assert events == ["preflight"]


def test_expired_paid_access_before_first_call_falls_back_to_rag(monkeypatch) -> None:
    workspace_id = uuid.uuid4()
    expert_id = uuid.uuid4()

    class _Repo:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def has_eligible_source_grant(*_args, **_kwargs) -> bool:
            return True

    class _Gate:
        rolled_back = False
        closed = False

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    class _Access:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def require_runtime_active(*_args, **_kwargs):
            raise AppError(
                ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
                "MCP subscription expired.",
            )

    gate = _Gate()
    monkeypatch.setattr(resolver_module, "McpRepository", _Repo)
    monkeypatch.setattr(resolver_module, "AppAccessService", _Access)
    monkeypatch.setattr(
        resolver_module, "begin_runtime_admission_transaction", lambda _db: None
    )
    monkeypatch.setattr(
        resolver_module, "acquire_runtime_admission_fences", lambda *_args, **_kwargs: None
    )
    resolver = McpGrantResolver(
        SimpleNamespace(),
        settings=_enabled_settings(),
        session_factory=lambda: gate,  # type: ignore[arg-type]
    )
    invocation = ChatInvocationContext.workspace_user(
        workspace_id=workspace_id,
        user_id=uuid.uuid4(),
        expert_id=expert_id,
    )

    assert resolver.resolve(invocation, expert_id) == []
    assert gate.rolled_back is True
    assert gate.closed is True


def _current_record() -> McpGrantRecord:
    definition_hash = "a" * 64
    principal = "b" * 64
    grant = SimpleNamespace(
        state=McpGrantState.ACTIVE.value,
        approved_definition_hash=definition_hash,
        approved_classification=McpToolClassification.READ_ONLY.value,
        approved_principal_fingerprint=principal,
        approved_credential_epoch=3,
        unattended_write_allowed=False,
    )
    tool = SimpleNamespace(
        status=McpToolStatus.ACTIVE.value,
        compatibility_status=McpCompatibilityStatus.COMPATIBLE.value,
        classification=McpToolClassification.READ_ONLY.value,
        definition_hash=definition_hash,
        annotations={"readOnlyHint": True},
        llm_tool_name="mcp_lookup",
        input_schema={"type": "object"},
        description="Look up a record",
        title="Lookup",
    )
    connection = SimpleNamespace(
        status=ConnectionStatus.ACTIVE.value,
        health=ConnectionHealth.HEALTHY.value,
        mcp_reauthorization_required=False,
        mcp_principal_fingerprint=principal,
        mcp_credential_epoch=3,
        mcp_inventory_refreshed_at=datetime.now(timezone.utc),
    )
    return McpGrantRecord(grant, tool, connection)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("grant", "state", McpGrantState.STALE_DEFINITION.value),
        ("grant", "approved_definition_hash", "c" * 64),
        ("grant", "approved_classification", McpToolClassification.WRITE.value),
        ("grant", "approved_principal_fingerprint", "d" * 64),
        ("grant", "approved_credential_epoch", 2),
        ("tool", "status", McpToolStatus.WITHDRAWN.value),
        (
            "tool",
            "compatibility_status",
            McpCompatibilityStatus.UNSUPPORTED_SCHEMA.value,
        ),
        ("connection", "mcp_principal_fingerprint", "e" * 64),
        ("connection", "mcp_credential_epoch", 4),
    ],
)
def test_stale_or_changed_pin_never_resolves(target, field, value) -> None:
    record = _current_record()
    setattr(getattr(record, target), field, value)
    resolver = McpGrantResolver(SimpleNamespace(), settings=get_settings())

    assert not resolver._record_is_current(
        record,
        source="workspace",
        decision_at=datetime.now(timezone.utc),
    )


def test_exact_current_pins_resolve() -> None:
    resolver = McpGrantResolver(SimpleNamespace(), settings=get_settings())
    assert resolver._record_is_current(
        _current_record(),
        source="workspace",
        decision_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    "annotations",
    [
        {"readOnlyHint": False},
        {"destructiveHint": True},
        {"readOnlyHint": False, "destructiveHint": False},
        {"readOnlyHint": "false"},
        {"destructiveHint": 1},
    ],
)
def test_mutating_annotation_never_resolves_as_read_only(annotations) -> None:
    record = _current_record()
    record.tool.annotations = annotations
    resolver = McpGrantResolver(SimpleNamespace(), settings=get_settings())

    assert annotations_forbid_read_only(annotations)
    assert not resolver._record_is_current(
        record,
        source="workspace",
        decision_at=datetime.now(timezone.utc),
    )


def test_provider_schema_labels_write_tools_for_explicit_mutation_only() -> None:
    record = _current_record()
    record.tool.classification = McpToolClassification.WRITE.value

    schema = McpGrantResolver._provider_schema(record.tool)

    description = schema["function"]["description"]
    assert description.startswith("WRITE TOOL.")
    assert "latest user request explicitly asks" in description
    assert description.endswith("Look up a record")


def test_external_surface_rejects_contradictory_read_only_tool() -> None:
    record = _current_record()
    record.tool.annotations = {"readOnlyHint": False}

    assert not _surface_grant_is_current(
        record.grant,
        record.tool,
        record.connection,
        now=datetime.now(timezone.utc),
        settings=get_settings(),
    )


def test_external_surface_schema_labels_write_tool() -> None:
    record = _current_record()
    record.tool.classification = McpToolClassification.WRITE.value

    schema = _surface_provider_schema(record.tool)

    assert schema["function"]["description"].startswith("WRITE TOOL.")


def test_classification_rejects_explicit_mutator_as_read_only(monkeypatch) -> None:
    tool = SimpleNamespace(
        annotations={"readOnlyHint": False},
        classification=McpToolClassification.UNKNOWN.value,
    )

    class _Repo:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def get_tool(*_args, **_kwargs):
            return tool

    class _Gate:
        rolled_back = False
        closed = False

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    gate = _Gate()
    monkeypatch.setattr(services_module, "_begin_paid_access", lambda *_a, **_k: None)
    monkeypatch.setattr(services_module, "McpRepository", _Repo)
    service = McpServerService(
        SimpleNamespace(),  # type: ignore[arg-type]
        session_factory=lambda: gate,  # type: ignore[arg-type]
        gateway=SimpleNamespace(),  # type: ignore[arg-type]
        oauth=SimpleNamespace(),  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as raised:
        service.classify_tool(
            workspace_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            tool_id=uuid.uuid4(),
            classification=McpToolClassification.READ_ONLY.value,
        )

    assert raised.value.category == ErrorCategory.VALIDATION
    assert "must be reviewed as a write tool" in raised.value.message
    assert gate.rolled_back is True
    assert gate.closed is True


def test_public_api_write_requires_unattended_opt_in() -> None:
    record = _current_record()
    record.tool.classification = McpToolClassification.WRITE.value
    record.grant.approved_classification = McpToolClassification.WRITE.value
    resolver = McpGrantResolver(SimpleNamespace(), settings=get_settings())

    assert not resolver._record_is_current(
        record,
        source="api",
        decision_at=datetime.now(timezone.utc),
    )
    record.grant.unattended_write_allowed = True
    assert resolver._record_is_current(
        record,
        source="api",
        decision_at=datetime.now(timezone.utc),
    )
