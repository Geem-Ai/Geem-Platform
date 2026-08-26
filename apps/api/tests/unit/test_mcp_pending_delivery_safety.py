from __future__ import annotations

import uuid
from collections import namedtuple
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.db.models  # noqa: F401  # register relationship targets for isolated runs
from app.common.crypto import encrypt_json
from app.connectors.providers.openwa import channel as channel_module
from app.conversations.invocation import ChatInvocationContext
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp import delivery as delivery_module
from app.mcp import resume as resume_module
from app.mcp import surfaces as surfaces_module
from app.mcp.approvals import McpApprovalService
from app.mcp.delivery import McpWhatsAppDeliveryService
from app.mcp.surfaces import McpSurfaceOutboxService
from app.workspaces.permissions import WorkspacePermission


def _settings():
    return get_settings().model_copy(
        update={
            "jwt_secret": "phase-13-safety-tests",
            "mcp_egress_max_request_bytes": 65_536,
            "mcp_egress_max_response_bytes": 65_536,
        }
    )


def test_resume_rejects_removed_decision_actor_before_decrypt_or_egress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    pending_id = uuid.uuid4()
    claimed = SimpleNamespace(
        workspace_id=workspace_id,
        arguments_encrypted="must-not-decrypt",
        loop_state_encrypted="must-not-decrypt",
    )

    class _Identity:
        @staticmethod
        def scalar_one_or_none():
            return workspace_id

    class _Db:
        commits = 0

        @staticmethod
        def execute(_statement):
            return _Identity()

        def commit(self) -> None:
            self.commits += 1

        @staticmethod
        def get(_model, _row_id):
            return None

    class _Approvals:
        def __init__(self, _db, _settings) -> None:
            pass

        @staticmethod
        def claim_resume(**_kwargs):
            return claimed

    db = _Db()
    service = resume_module.McpPendingResumeService(db, _settings())  # type: ignore[arg-type]
    monkeypatch.setattr(resume_module, "McpApprovalService", _Approvals)
    monkeypatch.setattr(service, "_decision_actor_is_current", lambda _row: False)
    monkeypatch.setattr(
        service,
        "_cancel_pre_dispatch",
        lambda workspace, pending: {
            "status": "denied",
            "workspace": str(workspace),
            "pending": str(pending),
        },
    )
    monkeypatch.setattr(
        resume_module,
        "decrypt_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("authorization must precede encrypted state/model/gateway work")
        ),
    )

    result = service._resume_locked(pending_id)

    assert result["status"] == "denied"
    assert db.commits == 1


def test_resume_rechecks_external_operator_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = uuid.uuid4()
    membership = object()
    seen: list[tuple[object, WorkspacePermission]] = []

    class _Memberships:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def get(_workspace_id, user_id):
            return membership if user_id == actor_id else None

    monkeypatch.setattr(resume_module, "MembershipRepository", _Memberships)
    monkeypatch.setattr(
        resume_module,
        "has_permission",
        lambda current, permission: not seen.append((current, permission)),
    )
    service = resume_module.McpPendingResumeService(
        SimpleNamespace(),  # type: ignore[arg-type]
        _settings(),
    )
    pending = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        decided_by_user_id=actor_id,
        initiated_by_user_id=None,
        mcp_tool_surface_binding_id=uuid.uuid4(),
    )

    assert service._decision_actor_is_current(pending) is True
    assert seen == [
        (membership, WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL)
    ]


@pytest.mark.parametrize("source", ["workspace", "widget", "channel"])
def test_confirmed_write_synthesis_failure_stays_executed_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    workspace_id = uuid.uuid4()
    pending_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    surface_id = None if source == "workspace" else uuid.uuid4()
    claimed = SimpleNamespace(
        id=pending_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        message_id=message_id,
        status="executing",
        arguments_encrypted="arguments",
        loop_state_encrypted="loop-state",
        initiated_by_user_id=(actor_id if source == "workspace" else None),
        mcp_tool_surface_binding_id=surface_id,
        mcp_tool_grant_id=uuid.uuid4(),
        model_tool_call_id="approved-call",
        external_principal_fingerprint=(None if source == "workspace" else "e" * 64),
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        workspace_id=workspace_id,
        expert_id=expert_id,
        updated_at=None,
    )
    assistant = SimpleNamespace(
        id=message_id,
        conversation_id=conversation_id,
        content="awaiting approval",
        citations=[{"kind": "tool"}],
        status="pending",
        updated_at=None,
    )
    user_message = SimpleNamespace(id=uuid.uuid4(), content="do it")
    workspace = SimpleNamespace(id=workspace_id)
    surface = (
        None
        if source == "workspace"
        else SimpleNamespace(
            id=surface_id,
            surface_kind=("chat_widget" if source == "widget" else "whatsapp_openwa"),
        )
    )
    widget_receipt = SimpleNamespace(status="running")
    scalar_values = [conversation, assistant, claimed, assistant, conversation]
    if source == "widget":
        scalar_values.append(widget_receipt)

    class _Identity:
        @staticmethod
        def scalar_one_or_none():
            return workspace_id

    class _Db:
        commits = 0
        rollbacks = 0

        @staticmethod
        def execute(_statement):
            return _Identity()

        @staticmethod
        def scalar(_statement):
            assert scalar_values
            return scalar_values.pop(0)

        @staticmethod
        def get(model, _row_id):
            name = model.__name__
            if name == "Workspace":
                return workspace
            if name == "McpPendingToolCall":
                return claimed
            if name == "McpToolSurfaceBinding":
                return surface
            return None

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    db = _Db()
    decision_calls: list[bool] = []
    dispatch_markers: list[uuid.UUID] = []
    delivery_calls: list[dict] = []
    enqueued: list[uuid.UUID] = []
    loop_calls: list[str] = []
    meter_events: list[str] = []

    class _Approvals:
        def __init__(self, _db, _settings) -> None:
            pass

        @staticmethod
        def claim_resume(**_kwargs):
            return None if claimed.status == "executed" else claimed

    class _Conversations:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def find_preceding_user_message(*_args, **_kwargs):
            return user_message

        @staticmethod
        def list_history_for_rag(*_args, **_kwargs):
            return []

    class _Query:
        def __init__(self, _db, _settings) -> None:
            self._rag = SimpleNamespace()

        @staticmethod
        def resolve_knowledge_for_workspace(**_kwargs):
            return SimpleNamespace()

    resolved = SimpleNamespace(
        grant=SimpleNamespace(id=claimed.mcp_tool_grant_id),
        tool=SimpleNamespace(
            id=uuid.uuid4(),
            llm_tool_name="mcp_write",
            input_schema={"type": "object", "additionalProperties": False},
        ),
        connection=SimpleNamespace(id=uuid.uuid4()),
    )

    class _Resolver:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def resolve(*_args, **_kwargs):
            return [resolved]

    class _Meter:
        def __init__(self, *_args, **_kwargs) -> None:
            self.closed = False

        def reserve(self) -> None:
            meter_events.append("reserve")

        @staticmethod
        def context():
            return SimpleNamespace()

        def release(self) -> None:
            meter_events.append("release")
            self.closed = True

    class _Loop:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def resume_after_approved_write(**kwargs):
            loop_calls.append("resume")
            kwargs["before_gateway"]()
            kwargs["after_gateway"]()
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Final synthesis failed.",
            )

    class _Outbox:
        def __init__(self, _db, _settings) -> None:
            pass

        @staticmethod
        def enqueue(**kwargs):
            delivery_calls.append(kwargs)
            return [SimpleNamespace(id=uuid.uuid4())]

    if source == "workspace":
        invocation = ChatInvocationContext.workspace_user(
            workspace_id=workspace_id,
            user_id=actor_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
        )
    elif source == "widget":
        invocation = ChatInvocationContext.widget(
            workspace_id=workspace_id,
            widget_id=uuid.uuid4(),
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
            source_binding_id=uuid.uuid4(),
            external_principal_fingerprint="e" * 64,
            initiating_origin="https://widget.example",
        )
    else:
        invocation = ChatInvocationContext.channel(
            workspace_id=workspace_id,
            connection_id=uuid.uuid4(),
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(message_id),
            source_binding_id=uuid.uuid4(),
            external_principal_fingerprint="e" * 64,
        )

    monkeypatch.setattr(resume_module, "McpApprovalService", _Approvals)
    monkeypatch.setattr(resume_module, "ConversationRepository", _Conversations)
    monkeypatch.setattr(resume_module, "ExpertQueryService", _Query)
    monkeypatch.setattr(resume_module, "McpGrantResolver", _Resolver)
    monkeypatch.setattr(resume_module, "McpSurfaceResolver", _Resolver)
    monkeypatch.setattr(resume_module, "MeteredWorkspaceGeneration", _Meter)
    monkeypatch.setattr(resume_module, "ToolLoopTurnExecutor", _Loop)
    monkeypatch.setattr(resume_module, "McpSurfaceOutboxService", _Outbox)
    decrypt_values = iter(({}, {"v": 1}))
    monkeypatch.setattr(
        resume_module,
        "decrypt_json",
        lambda *_args, **_kwargs: next(decrypt_values),
    )
    service = resume_module.McpPendingResumeService(db, _settings())  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_decision_actor_is_current", lambda _row: True)
    monkeypatch.setattr(service, "_invocation", lambda *_args: invocation)
    monkeypatch.setattr(service, "_loop_state_matches", lambda *_args: True)
    monkeypatch.setattr(
        service,
        "_mark_dispatch",
        lambda _workspace_id, row_id: dispatch_markers.append(row_id),
    )

    def _finish(_workspace_id, _pending_id, *, outcome_unknown):
        decision_calls.append(outcome_unknown)
        claimed.status = "outcome_unknown" if outcome_unknown else "executed"

    monkeypatch.setattr(service, "_finish_approval", _finish)
    monkeypatch.setattr(
        service,
        "_enqueue_deliveries",
        lambda delivery_ids: enqueued.extend(delivery_ids),
    )

    first = service._resume_locked(pending_id)
    second = service._resume_locked(pending_id)

    assert first == {
        "status": "failed",
        "deliveries": (1 if source == "channel" else 0),
    }
    assert second == {"status": "executed"}
    assert claimed.status == "executed"
    assert decision_calls == [False]
    assert dispatch_markers == [pending_id]
    assert loop_calls == ["resume"]
    assert meter_events == ["reserve", "release"]
    assert db.rollbacks >= 1
    assert assistant.status == "failed"
    assert assistant.citations == []
    assert assistant.content == (
        "The approved tool completed, but a final answer could not be generated."
    )
    if source == "widget":
        assert widget_receipt.status == "failed"
    if source == "channel":
        assert len(delivery_calls) == 1
        assert delivery_calls[0]["response_revision"] == 2
        assert delivery_calls[0]["rendered_segments"] == [assistant.content]
        assert len(enqueued) == 1
    else:
        assert delivery_calls == []
        assert enqueued == []


def test_whatsapp_initial_pause_enqueues_one_generic_immutable_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_id = uuid.uuid4()
    surface_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    digest = "a" * 64
    pending = SimpleNamespace(
        id=pending_id,
        mcp_tool_surface_binding_id=surface_id,
        external_principal_fingerprint=digest,
    )
    captured: dict[str, object] = {}

    class _Db:
        @staticmethod
        def scalar(_statement):
            return pending

    class _Outbox:
        def __init__(self, _db, _settings) -> None:
            pass

        @staticmethod
        def enqueue(**kwargs):
            captured.update(kwargs)
            return [SimpleNamespace(id=delivery_id)]

    monkeypatch.setattr(channel_module, "McpSurfaceOutboxService", _Outbox)
    processor = object.__new__(channel_module.OpenWAChannelProcessor)
    processor.db = _Db()
    processor.settings = _settings()
    notice = "This request is awaiting approval from a workspace operator."

    ids = processor._create_initial_pending_notice(
        workspace_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        pending_payload={"id": str(pending_id)},
        external_principal_fingerprint=digest,
        notice=notice,
    )

    assert ids == [delivery_id]
    assert captured["rendered_segments"] == [notice]
    assert captured["pending_id"] == pending_id
    assert captured["surface_binding_id"] == surface_id
    assert captured["external_principal_fingerprint"] == digest
    assert captured["response_revision"] == 1


def test_outbox_payload_binds_text_to_immutable_principal_digest() -> None:
    settings = _settings()
    digest = "b" * 64
    text = "safe generic notice"
    row = SimpleNamespace(
        rendered_segment_encrypted=encrypt_json(
            {"text": text, "external_principal_fingerprint": digest},
            settings=settings,
        ),
        content_hash=surfaces_module._delivery_content_hash(text, digest),
    )
    outbox = McpSurfaceOutboxService(SimpleNamespace(), settings)  # type: ignore[arg-type]

    assert outbox.rendered_payload(row) == (text, digest)
    row.content_hash = surfaces_module._delivery_content_hash(text, "c" * 64)
    with pytest.raises(AppError) as caught:
        outbox.rendered_payload(row)
    assert caught.value.category == ErrorCategory.CONFLICT


def test_current_whatsapp_principal_changes_with_sender_or_chat() -> None:
    workspace_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    binding = SimpleNamespace(
        id=uuid.uuid4(),
        external_chat_id="chat-a",
        external_sender_id="sender-a",
    )
    original = delivery_module._channel_principal_fingerprint(
        binding,
        workspace_id=workspace_id,
        connection_id=connection_id,
        secret="principal-test",
    )
    binding.external_sender_id = "sender-b"
    changed_sender = delivery_module._channel_principal_fingerprint(
        binding,
        workspace_id=workspace_id,
        connection_id=connection_id,
        secret="principal-test",
    )
    binding.external_sender_id = "sender-a"
    binding.external_chat_id = "chat-b"
    changed_chat = delivery_module._channel_principal_fingerprint(
        binding,
        workspace_id=workspace_id,
        connection_id=connection_id,
        secret="principal-test",
    )

    assert original
    assert original != changed_sender
    assert original != changed_chat


@pytest.mark.parametrize(
    ("surface_kind", "expected_prefix"),
    (
        ("chat_widget", "Widget visitor"),
        ("whatsapp_openwa", "WhatsApp sender"),
    ),
)
def test_external_approval_sender_label_is_pseudonymous_and_surface_specific(
    surface_kind: str,
    expected_prefix: str,
) -> None:
    raw_phone = "+966501234567"
    raw_chat_id = "966501234567@c.us"
    fingerprint = "a1" * 32
    now = datetime.now(timezone.utc)
    pending = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        status="pending",
        arguments_encrypted=None,
        external_principal_fingerprint=fingerprint,
        expires_at=now,
        created_at=now,
        decided_at=None,
        # These attributes model the sensitive source values and prove the
        # response helper never reads or reflects them.
        external_sender_id=raw_phone,
        external_chat_id=raw_chat_id,
    )
    surface = SimpleNamespace(
        surface_kind=surface_kind,
        widget_instance_id=(uuid.uuid4() if surface_kind == "chat_widget" else None),
        channel_binding_id=(
            uuid.uuid4() if surface_kind == "whatsapp_openwa" else None
        ),
    )

    class _Db:
        @staticmethod
        def scalar(_statement):
            return "Reviewed surface"

    approval = surfaces_module.McpExternalOperationsService(
        _Db(),  # type: ignore[arg-type]
        _settings(),
    )._approval_out(
        pending,
        surface,
        SimpleNamespace(tool_name="reviewed_tool"),
        SimpleNamespace(display_name="Reviewed MCP server"),
    )
    label = approval.sender_label
    encoded = approval.model_dump_json()

    assert label == f"{expected_prefix} · {fingerprint[:8]}"
    assert raw_phone not in encoded
    assert raw_chat_id not in encoded


def test_external_approval_sender_label_never_reflects_malformed_fingerprint() -> None:
    hostile = "raw-phone-or-chat-id-must-not-leak"
    pending = SimpleNamespace(external_principal_fingerprint=hostile)
    surface = SimpleNamespace(surface_kind="whatsapp_openwa")

    label = surfaces_module._safe_external_sender_label(pending, surface)

    assert label == "WhatsApp sender"
    assert hostile not in label


def test_permanent_whatsapp_app_denial_cancels_instead_of_requeue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_id = uuid.uuid4()
    Identity = namedtuple(
        "Identity", "workspace_id channel_binding_id app_connection_id"
    )
    identity = Identity(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    events: list[str] = []

    class _LookupResult:
        @staticmethod
        def one_or_none():
            return identity

    class _Lookup:
        @staticmethod
        def execute(_statement):
            return _LookupResult()

        @staticmethod
        def close() -> None:
            events.append("lookup_close")

    class _Gate:
        @staticmethod
        def commit() -> None:
            events.append("commit")

        @staticmethod
        def rollback() -> None:
            events.append("rollback")

        @staticmethod
        def close() -> None:
            events.append("gate_close")

    sessions = iter((_Lookup(), _Gate()))
    monkeypatch.setattr(delivery_module, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(
        delivery_module, "begin_runtime_admission_transaction", lambda _db: None
    )
    monkeypatch.setattr(
        delivery_module,
        "acquire_runtime_admission_fences",
        lambda *_args, **_kwargs: None,
    )

    class _Access:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def require_runtime_active(*_args, **_kwargs):
            raise AppError(ErrorCategory.APP_NOT_INSTALLED, "not installed")

    class _Outbox:
        def __init__(self, _db, _settings) -> None:
            pass

        @staticmethod
        def cancel_before_send(row_id):
            assert row_id == delivery_id
            events.append("cancel")
            return True

    monkeypatch.setattr(delivery_module, "AppAccessService", _Access)
    monkeypatch.setattr(delivery_module, "McpSurfaceOutboxService", _Outbox)

    result = McpWhatsAppDeliveryService(settings=_settings())._claim_authorized(
        delivery_id
    )

    assert result is None
    assert events == ["lookup_close", "cancel", "commit", "gate_close"]


def test_approval_recovery_finalizes_before_purge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.mcp import approvals as approvals_module
    from app.worker import tasks

    pending_id = uuid.uuid4()
    events: list[str] = []

    class _Scalars:
        def __init__(self, values) -> None:
            self.values = values

        def all(self):
            return self.values

    class _Db:
        def __init__(self, kind: str) -> None:
            self.kind = kind
            self.scalar_calls = 0

        def scalars(self, _statement):
            self.scalar_calls += 1
            return _Scalars([] if self.scalar_calls == 1 else [pending_id])

        def commit(self) -> None:
            events.append(f"{self.kind}:commit")

        def close(self) -> None:
            events.append(f"{self.kind}:close")

    class _Approvals:
        def __init__(self, db, *_args) -> None:
            self.db = db

        @staticmethod
        def recover_stale_claims(**_kwargs):
            return 0, 0

        @staticmethod
        def expire_due(**_kwargs):
            return 0

        def purge_due(self, **_kwargs):
            events.append("purge")
            assert self.db.kind == "purge"
            return 1

    class _Resume:
        def __init__(self, db, *_args) -> None:
            assert db.kind == "terminal"

        @staticmethod
        def finalize_terminal(row_id):
            assert row_id == pending_id
            events.append("finalize")
            return True

    databases = iter((_Db("main"), _Db("terminal"), _Db("purge")))
    monkeypatch.setattr(tasks, "SessionLocal", lambda: next(databases))
    monkeypatch.setattr(approvals_module, "McpApprovalService", _Approvals)
    monkeypatch.setattr(resume_module, "McpPendingResumeService", _Resume)
    monkeypatch.setattr(
        tasks.resume_mcp_pending_tool_call,
        "delay",
        lambda _row_id: events.append("enqueue"),
    )

    result = tasks.recover_mcp_approval_state.run(limit=10)

    assert result["finalized"] == 1
    assert result["purged"] == 1
    assert events.index("finalize") < events.index("purge")


def test_delivery_sweep_retains_pending_linked_finalization_proof() -> None:
    statements: list[str] = []

    class _Rows:
        @staticmethod
        def all():
            return []

    class _Db:
        @staticmethod
        def scalars(statement):
            statements.append(str(statement))
            return _Rows()

    assert (
        McpSurfaceOutboxService(_Db(), _settings()).purge_terminal()  # type: ignore[arg-type]
        == 0
    )
    assert "mcp_surface_deliveries.mcp_pending_tool_call_id IS NULL" in statements[0]


def test_approval_purge_removes_linked_proof_before_parent_row() -> None:
    pending_id = uuid.uuid4()
    selected: list[str] = []
    deleted: list[str] = []

    class _Rows:
        @staticmethod
        def all():
            return [pending_id]

    class _Db:
        @staticmethod
        def scalars(statement):
            selected.append(str(statement))
            return _Rows()

        @staticmethod
        def execute(statement):
            deleted.append(str(statement))
            return SimpleNamespace()

    purged = McpApprovalService(_Db(), _settings()).purge_due(  # type: ignore[arg-type]
        finalized_terminal_ids=(pending_id,)
    )

    assert purged == 1
    assert "mcp_pending_tool_calls.status =" in selected[0]
    assert "mcp_pending_tool_calls.id IN" in selected[0]
    assert deleted[0].startswith("DELETE FROM mcp_surface_deliveries")
    assert deleted[1].startswith("DELETE FROM mcp_pending_tool_calls")
