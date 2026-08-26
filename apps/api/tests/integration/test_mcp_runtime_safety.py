from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.api_keys.models import ApiKey
from app.apps_catalog.access import RuntimeAppAccessSnapshot
from app.apps_catalog.mcp_product import (
    MCP_CONNECTORS_APP_SLUG,
    MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
    MCP_TOOL_CALLS_USAGE_METRIC,
)
from app.apps_catalog.models import (
    AppCategory,
    AppInstallation,
    AppInstallationStatus,
    CatalogApp,
)
from app.apps_catalog.service import AppInstallationService
from app.audit import AuditEntityType, AuditLog, record_audit
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.types import (
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
)
from app.conversations.models import Conversation, Message, MessageRole
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import Expert, ExpertType
from app.identity.models import User
from app.mcp.approvals import McpApprovalService
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.quota import McpToolQuotaService
from app.mcp.runtime_models import (
    McpPendingToolCall,
    McpSurfaceDelivery,
    McpToolInvocation,
    McpToolSurfaceBinding,
    McpWidgetTurnReceipt,
)
from app.mcp.services import McpServerService
from app.mcp.surfaces import McpSurfaceOutboxService, stale_widget_surface_bindings
from app.mcp.types import (
    McpCompatibilityStatus,
    McpGrantState,
    McpToolClassification,
    McpToolStatus,
)
from app.retention.service import RetentionPurgeService
from app.usage.models import UsagePeriodCounter
from app.widgets.models import WidgetConversationBinding, WidgetInstance
from app.workspaces.models import Workspace
from app.workspaces.service import WorkspaceService
from tests.support.rbac import add_workspace_member


def _runtime_chain(db) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    user = User(
        email=f"mcp-{uuid.uuid4().hex}@example.com",
        password_hash="not-used",
        email_verified_at=now,
    )
    workspace = Workspace(name="MCP Runtime", slug=f"mcp-{uuid.uuid4().hex[:12]}")
    category = AppCategory(slug=f"mcp-{uuid.uuid4().hex[:12]}", name_key="mcp")
    db.add_all([user, workspace, category])
    db.flush()
    app = CatalogApp(
        slug=f"mcp-runtime-{uuid.uuid4().hex[:12]}",
        name="MCP Runtime",
        short_description="MCP Runtime",
        category_id=category.id,
        connector_key="mcp_remote",
        connector_kind="tool_source",
    )
    db.add(app)
    db.flush()
    installation = AppInstallation(workspace_id=workspace.id, app_id=app.id)
    expert = Expert(
        workspace_id=workspace.id,
        type=ExpertType.WORKSPACE.value,
        name="MCP Expert",
        system_instructions="",
        created_by=user.id,
    )
    api_key = ApiKey(
        workspace_id=workspace.id,
        name="MCP test",
        key_prefix="geem_test",
        last_four="test",
        secret_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        created_by=user.id,
    )
    db.add_all([installation, expert, api_key])
    db.flush()
    principal = "b" * 64
    connection = AppConnection(
        workspace_id=workspace.id,
        app_installation_id=installation.id,
        connector_key="mcp_remote",
        auth_mode=ConnectorAuthMode.NONE.value,
        status=ConnectionStatus.ACTIVE.value,
        health=ConnectionHealth.HEALTHY.value,
        mcp_credential_epoch=1,
        mcp_principal_fingerprint=principal,
        mcp_discovery_generation=1,
        mcp_inventory_refreshed_at=now,
    )
    db.add(connection)
    db.flush()
    tool = McpServerTool(
        workspace_id=workspace.id,
        app_connection_id=connection.id,
        tool_name="lookup",
        llm_tool_name=f"mcp_lookup_{uuid.uuid4().hex[:12]}",
        title="Lookup",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={"readOnlyHint": True},
        raw_definition={"name": "lookup", "inputSchema": {"type": "object"}},
        normalization_version="test-v1",
        protocol_version="2026-07-28",
        compatibility_status=McpCompatibilityStatus.COMPATIBLE.value,
        classification=McpToolClassification.READ_ONLY.value,
        definition_hash="a" * 64,
        status=McpToolStatus.ACTIVE.value,
        discovery_generation=1,
    )
    db.add(tool)
    db.flush()
    grant = McpToolGrant(
        workspace_id=workspace.id,
        expert_id=expert.id,
        app_connection_id=connection.id,
        mcp_server_tool_id=tool.id,
        approved_definition_hash=tool.definition_hash,
        approved_classification=tool.classification,
        approved_principal_fingerprint=principal,
        approved_credential_epoch=1,
        state=McpGrantState.ACTIVE.value,
        allow_workspace_chat=True,
        allow_public_api=True,
        approved_by_user_id=user.id,
        approved_at=now,
        outbound_data_acknowledged_at=now,
    )
    db.add(grant)
    db.commit()
    return SimpleNamespace(
        now=now,
        user=user,
        workspace=workspace,
        app=app,
        installation=installation,
        expert=expert,
        api_key=api_key,
        connection=connection,
        tool=tool,
        grant=grant,
    )


def _access(chain: SimpleNamespace, *, limit: int) -> RuntimeAppAccessSnapshot:
    start = chain.now.replace(hour=0, minute=0, second=0, microsecond=0)
    return RuntimeAppAccessSnapshot(
        decision_at=chain.now,
        workspace_id=chain.workspace.id,
        app_id=chain.app.id,
        app_slug=MCP_CONNECTORS_APP_SLUG,
        installation_id=chain.installation.id,
        subscription_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        plan_code="mcp-test",
        current_period_start=start,
        current_period_end=start + timedelta(days=30),
        entitlements=MappingProxyType({MCP_TOOL_CALLS_DAILY_ENTITLEMENT: limit}),
    )


def _admit(db, chain: SimpleNamespace, *, admission_id: str, arguments: dict, limit: int):
    return McpToolQuotaService(db).admit_in_transaction(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        grant_id=chain.grant.id,
        tool_id=chain.tool.id,
        connection_id=chain.connection.id,
        invocation_source="api",
        model_tool_call_id="call-1",
        request_id="request-1",
        admission_id=admission_id,
        arguments=arguments,
        access=_access(chain, limit=limit),
        api_key_id=chain.api_key.id,
    )


def _external_runtime_chain(db, chain: SimpleNamespace) -> SimpleNamespace:
    """Create every RESTRICT-linked external MCP runtime row."""

    conversation = Conversation(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        user_id=None,
        source="widget",
        title="retained MCP turn",
    )
    widget = WidgetInstance(
        workspace_id=chain.workspace.id,
        app_installation_id=chain.installation.id,
        expert_id=chain.expert.id,
        title="Retained Widget",
        allowed_origins=["https://example.com"],
        mcp_source_epoch=1,
        mcp_source_principal_fingerprint="c" * 64,
    )
    db.add_all([conversation, widget])
    db.flush()
    conversation_binding = WidgetConversationBinding(
        workspace_id=chain.workspace.id,
        widget_instance_id=widget.id,
        conversation_id=conversation.id,
        session_id=f"session-{uuid.uuid4().hex}",
        expert_id=chain.expert.id,
    )
    user_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER.value,
        content="run a retained write",
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT.value,
        content="pending",
    )
    surface = McpToolSurfaceBinding(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        mcp_tool_grant_id=chain.grant.id,
        surface_kind="chat_widget",
        widget_instance_id=widget.id,
        channel_binding_id=None,
        state="active",
        write_policy="workspace_operator_approval",
        approved_surface_config_hash="d" * 64,
        approved_source_principal_fingerprint="c" * 64,
        approved_source_epoch=1,
        public_risk_acknowledged_at=chain.now,
        outbound_data_acknowledged_at=chain.now,
        approved_by_user_id=chain.user.id,
        approved_at=chain.now,
    )
    db.add_all(
        [conversation_binding, user_message, assistant_message, surface]
    )
    db.flush()
    receipt = McpWidgetTurnReceipt(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        widget_instance_id=widget.id,
        widget_conversation_binding_id=conversation_binding.id,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        request_content_hash="1" * 64,
        client_turn_id_digest="2" * 64,
        session_id_digest="3" * 64,
        initiating_origin_digest="4" * 64,
        external_turn_handle_digest="5" * 64,
        status="pending",
    )
    db.add(receipt)
    db.flush()
    admission = McpToolQuotaService(db).admit_in_transaction(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        grant_id=chain.grant.id,
        tool_id=chain.tool.id,
        connection_id=chain.connection.id,
        invocation_source="widget",
        model_tool_call_id=f"external-call-{uuid.uuid4().hex}",
        request_id=f"external-request-{uuid.uuid4().hex}",
        admission_id=f"external-admission-{uuid.uuid4().hex}",
        arguments={"id": 1},
        access=_access(chain, limit=100),
        conversation_id=conversation.id,
        message_id=user_message.id,
        surface_binding_id=surface.id,
        external_principal_fingerprint="c" * 64,
    )
    invocation = db.get(McpToolInvocation, admission.invocation_id)
    assert invocation is not None
    invocation.status = "dispatching"
    invocation.gateway_dispatch_started_at = chain.now
    approvals = McpApprovalService(db, get_settings())
    pending = approvals.create_pending(
        workspace_id=chain.workspace.id,
        conversation_id=conversation.id,
        message_id=user_message.id,
        grant_id=chain.grant.id,
        model_tool_call_id=f"write-{uuid.uuid4().hex}",
        idempotency_key=f"pending-{uuid.uuid4().hex}",
        arguments={"id": 1},
        loop_state={"v": 1, "messages": []},
        surface_binding_id=surface.id,
        external_principal_fingerprint="c" * 64,
        initiating_origin_digest=receipt.initiating_origin_digest,
        external_turn_handle_digest=receipt.external_turn_handle_digest,
    )
    delivery = McpSurfaceOutboxService(db, get_settings()).enqueue(
        workspace_id=chain.workspace.id,
        conversation_id=conversation.id,
        assistant_message_id=assistant_message.id,
        surface_binding_id=surface.id,
        rendered_segments=["pending result"],
        pending_id=pending.id,
        widget_instance_id=widget.id,
        initiating_origin_digest=receipt.initiating_origin_digest,
        external_turn_handle_digest=receipt.external_turn_handle_digest,
        external_principal_fingerprint="c" * 64,
    )[0]
    approvals.decide_external(
        workspace_id=chain.workspace.id,
        pending_id=pending.id,
        operator_user_id=chain.user.id,
        decision="approve",
    )
    assert approvals.claim_resume(
        workspace_id=chain.workspace.id,
        pending_id=pending.id,
    ) is not None
    approvals.mark_gateway_dispatch_started(
        workspace_id=chain.workspace.id,
        pending_id=pending.id,
    )
    assert McpSurfaceOutboxService(db, get_settings()).claim(delivery.id) is not None
    db.commit()
    return SimpleNamespace(
        conversation=conversation,
        widget=widget,
        conversation_binding=conversation_binding,
        user_message=user_message,
        assistant_message=assistant_message,
        surface=surface,
        receipt=receipt,
        invocation=invocation,
        pending=pending,
        delivery=delivery,
    )


@pytest.mark.parametrize("remote_failure", [False, True])
def test_oauth_disconnect_commits_local_deny_before_best_effort_revocation(
    db, remote_failure: bool
) -> None:
    chain = _runtime_chain(db)
    runtime = _external_runtime_chain(db, chain)
    chain.connection.auth_mode = ConnectorAuthMode.OAUTH2.value
    ConnectorCredentialService(db).set_credentials(
        chain.connection,
        {
            "mcp": {
                "server_url": "https://mcp.example.com/mcp",
                "resource_uri": "https://mcp.example.com/mcp",
                "auth": {
                    "mode": "oauth",
                    "revocation_endpoint": "https://auth.example.com/revoke",
                    "client_id": "client-id",
                    "token_endpoint_auth_method": "none",
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                },
            }
        },
        merge_refresh=False,
    )
    db.commit()

    class _RevocationProbe:
        called = False

        def revoke_best_effort(self, *, connection_id, auth) -> bool:
            # The service must finish its restrictive transaction before this
            # callback can perform any network operation.
            assert not db.in_transaction()
            assert connection_id == chain.connection.id
            assert chain.connection.status == ConnectionStatus.DISCONNECTED.value
            assert chain.connection.credentials_encrypted is None
            assert chain.grant.state == McpGrantState.REVOKED.value
            assert chain.tool.status == McpToolStatus.WITHDRAWN.value
            assert runtime.invocation.status == "outcome_unknown"
            assert runtime.invocation.error_code == "MCP_CONNECTION_RETIRED"
            assert runtime.pending.status == "outcome_unknown"
            assert runtime.pending.arguments_encrypted is None
            assert runtime.pending.loop_state_encrypted is None
            assert runtime.delivery.status == "delivery_unknown"
            assert runtime.receipt.status == "outcome_unknown"
            assert runtime.surface.state == "revoked"
            assert auth["refresh_token"] == "refresh-token"
            self.called = True
            if remote_failure:
                raise RuntimeError("simulated revocation outage")
            return True

    probe = _RevocationProbe()
    McpServerService(db, oauth=probe).delete_server(  # type: ignore[arg-type]
        workspace_id=chain.workspace.id,
        actor_id=chain.user.id,
        connection_id=chain.connection.id,
    )

    assert probe.called is True
    assert chain.connection.credentials_encrypted is None
    assert chain.connection.mcp_principal_fingerprint is None
    assert chain.connection.mcp_reauthorization_required is False
    assert db.get(McpToolInvocation, runtime.invocation.id) is not None
    assert db.get(McpPendingToolCall, runtime.pending.id) is not None
    assert db.get(McpSurfaceDelivery, runtime.delivery.id) is not None


@pytest.mark.parametrize("remote_failure", [False, True])
def test_mcp_uninstall_commits_local_deny_before_oauth_revocation(
    db,
    monkeypatch: pytest.MonkeyPatch,
    remote_failure: bool,
) -> None:
    chain = _runtime_chain(db)
    chain.connection.auth_mode = ConnectorAuthMode.OAUTH2.value
    ConnectorCredentialService(db).set_credentials(
        chain.connection,
        {
            "mcp": {
                "server_url": "https://mcp.example.com/mcp",
                "resource_uri": "https://mcp.example.com/mcp",
                "auth": {
                    "mode": "oauth",
                    "revocation_endpoint": "https://auth.example.com/revoke",
                    "client_id": "client-id",
                    "token_endpoint_auth_method": "none",
                    "refresh_token": "refresh-token",
                },
            }
        },
        merge_refresh=False,
    )
    db.commit()
    calls: list[uuid.UUID] = []

    def _revoke(_self, *, connection_id, auth) -> bool:
        assert not db.in_transaction()
        assert chain.installation.status == AppInstallationStatus.UNINSTALLED.value
        assert chain.connection.status == ConnectionStatus.REVOKED.value
        assert chain.connection.credentials_encrypted is None
        assert chain.grant.state == McpGrantState.REVOKED.value
        assert chain.tool.status == McpToolStatus.WITHDRAWN.value
        assert auth["refresh_token"] == "refresh-token"
        calls.append(connection_id)
        if remote_failure:
            raise RuntimeError("simulated revocation outage")
        return True

    monkeypatch.setattr("app.mcp.oauth.McpOAuthService.revoke_best_effort", _revoke)
    result = AppInstallationService(db).uninstall_app(
        workspace=chain.workspace,
        actor_id=chain.user.id,
        slug=chain.app.slug,
    )

    assert result.status == AppInstallationStatus.UNINSTALLED.value
    assert calls == [chain.connection.id]
    assert chain.connection.mcp_principal_fingerprint is None


def test_workspace_delete_revokes_mcp_only_after_local_deny_commit(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _runtime_chain(db)
    add_workspace_member(db, chain.workspace.id, chain.user.id, "owner")
    chain.connection.auth_mode = ConnectorAuthMode.OAUTH2.value
    ConnectorCredentialService(db).set_credentials(
        chain.connection,
        {
            "mcp": {
                "server_url": "https://mcp.example.com/mcp",
                "resource_uri": "https://mcp.example.com/mcp",
                "auth": {
                    "mode": "oauth",
                    "revocation_endpoint": "https://auth.example.com/revoke",
                    "client_id": "client-id",
                    "token_endpoint_auth_method": "none",
                    "refresh_token": "refresh-token",
                },
            }
        },
        merge_refresh=False,
    )
    db.commit()
    calls: list[uuid.UUID] = []

    def _revoke(_self, *, connection_id, auth) -> bool:
        assert not db.in_transaction()
        assert chain.workspace.deleted_at is not None
        assert chain.connection.status == ConnectionStatus.REVOKED.value
        assert chain.connection.credentials_encrypted is None
        assert chain.connection.mcp_principal_fingerprint is None
        assert chain.grant.state == McpGrantState.REVOKED.value
        assert chain.tool.status == McpToolStatus.WITHDRAWN.value
        assert auth["refresh_token"] == "refresh-token"
        calls.append(connection_id)
        raise RuntimeError("simulated revocation outage")

    monkeypatch.setattr("app.mcp.oauth.McpOAuthService.revoke_best_effort", _revoke)
    WorkspaceService(db).soft_delete_workspace(
        workspace_id=chain.workspace.id,
        actor_id=chain.user.id,
    )

    assert calls == [chain.connection.id]
    assert chain.connection.credentials_encrypted is None


def test_conversation_retention_purges_mcp_children_before_parent_and_keeps_proof(
    db,
) -> None:
    chain = _runtime_chain(db)
    runtime = _external_runtime_chain(db, chain)
    proof = record_audit(
        db,
        action="test.mcp.retention_proof",
        entity_type=AuditEntityType.CONVERSATION,
        entity_id=runtime.conversation.id,
        workspace_id=chain.workspace.id,
        required=True,
    )
    assert proof is not None
    runtime.conversation.deleted_at = chain.now - timedelta(days=31)
    db.commit()

    assert RetentionPurgeService(db).purge_conversation(runtime.conversation.id) is True

    assert db.get(Conversation, runtime.conversation.id) is None
    assert db.get(McpSurfaceDelivery, runtime.delivery.id) is None
    assert db.get(McpWidgetTurnReceipt, runtime.receipt.id) is None
    assert db.get(McpPendingToolCall, runtime.pending.id) is None
    assert db.get(McpToolInvocation, runtime.invocation.id) is None
    assert db.get(McpToolSurfaceBinding, runtime.surface.id) is not None
    assert db.get(McpToolGrant, chain.grant.id) is not None
    assert db.get(McpServerTool, chain.tool.id) is not None
    assert db.get(AppConnection, chain.connection.id) is not None
    assert db.get(AuditLog, proof.id) is not None
    assert (
        db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == chain.workspace.id,
                UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
            )
        )
        == 1
    )


def test_expert_retention_purges_mcp_grant_chain_before_parent_and_keeps_proof(
    db,
) -> None:
    chain = _runtime_chain(db)
    runtime = _external_runtime_chain(db, chain)
    proof = record_audit(
        db,
        action="test.mcp.retention_proof",
        entity_type=AuditEntityType.EXPERT,
        entity_id=chain.expert.id,
        workspace_id=chain.workspace.id,
        required=True,
    )
    assert proof is not None
    chain.expert.deleted_at = chain.now - timedelta(days=31)
    db.commit()

    assert RetentionPurgeService(db).purge_expert(chain.expert.id) is True

    assert db.get(Expert, chain.expert.id) is None
    assert db.get(Conversation, runtime.conversation.id) is None
    assert db.get(McpSurfaceDelivery, runtime.delivery.id) is None
    assert db.get(McpWidgetTurnReceipt, runtime.receipt.id) is None
    assert db.get(McpPendingToolCall, runtime.pending.id) is None
    assert db.get(McpToolInvocation, runtime.invocation.id) is None
    assert db.get(McpToolSurfaceBinding, runtime.surface.id) is None
    assert db.get(McpToolGrant, chain.grant.id) is None
    assert db.get(McpServerTool, chain.tool.id) is not None
    assert db.get(AppConnection, chain.connection.id) is not None
    assert db.get(AuditLog, proof.id) is not None
    assert (
        db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == chain.workspace.id,
                UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
            )
        )
        == 1
    )


def test_workspace_retention_purges_mcp_graph_in_fk_order_and_keeps_proof(
    db,
) -> None:
    chain = _runtime_chain(db)
    runtime = _external_runtime_chain(db, chain)
    proof = record_audit(
        db,
        action="test.mcp.retention_proof",
        entity_type=AuditEntityType.WORKSPACE,
        entity_id=chain.workspace.id,
        workspace_id=chain.workspace.id,
        required=True,
    )
    assert proof is not None
    chain.workspace.deleted_at = chain.now - timedelta(days=31)
    chain.workspace.status = "archived"
    db.commit()

    assert RetentionPurgeService(db).purge_workspace(chain.workspace.id) is True

    workspace = db.get(Workspace, chain.workspace.id)
    assert workspace is not None and workspace.purged_at is not None
    assert db.get(Conversation, runtime.conversation.id) is None
    assert db.get(Expert, chain.expert.id) is None
    assert db.get(McpSurfaceDelivery, runtime.delivery.id) is None
    assert db.get(McpWidgetTurnReceipt, runtime.receipt.id) is None
    assert db.get(McpPendingToolCall, runtime.pending.id) is None
    assert db.get(McpToolInvocation, runtime.invocation.id) is None
    assert db.get(McpToolSurfaceBinding, runtime.surface.id) is None
    assert db.get(McpToolGrant, chain.grant.id) is None
    assert db.get(McpServerTool, chain.tool.id) is None
    assert db.get(AppConnection, chain.connection.id) is None
    assert db.get(AuditLog, proof.id) is not None
    assert (
        db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == chain.workspace.id,
                UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
            )
        )
        == 1
    )


def test_atomic_tool_quota_is_idempotent_and_tamper_resistant(db) -> None:
    chain = _runtime_chain(db)
    first = _admit(db, chain, admission_id="admission-1", arguments={"q": "one"}, limit=1)
    db.commit()
    assert first.should_dispatch is True

    duplicate = _admit(
        db, chain, admission_id="admission-1", arguments={"q": "one"}, limit=1
    )
    assert duplicate.invocation_id == first.invocation_id
    assert duplicate.should_dispatch is False
    assert db.scalar(select(func.count()).select_from(McpToolInvocation)) == 1
    assert (
        db.scalar(
            select(UsagePeriodCounter.used).where(
                UsagePeriodCounter.workspace_id == chain.workspace.id,
                UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
            )
        )
        == 1
    )

    with pytest.raises(AppError) as tampered:
        _admit(
            db,
            chain,
            admission_id="admission-1",
            arguments={"q": "changed"},
            limit=1,
        )
    assert tampered.value.category == ErrorCategory.CONFLICT
    db.rollback()

    with pytest.raises(AppError) as exhausted:
        McpToolQuotaService(db).admit_in_transaction(
            workspace_id=chain.workspace.id,
            expert_id=chain.expert.id,
            grant_id=chain.grant.id,
            tool_id=chain.tool.id,
            connection_id=chain.connection.id,
            invocation_source="api",
            model_tool_call_id="call-2",
            request_id="request-2",
            admission_id="admission-2",
            arguments={},
            access=_access(chain, limit=1),
            api_key_id=chain.api_key.id,
        )
    assert exhausted.value.category == ErrorCategory.MCP_TOOL_LIMIT_REACHED
    db.rollback()
    assert db.scalar(select(func.count()).select_from(McpToolInvocation)) == 1


def test_approval_decision_claim_and_scrub_are_idempotent(db) -> None:
    chain = _runtime_chain(db)
    conversation = Conversation(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        user_id=chain.user.id,
        title="approval",
    )
    db.add(conversation)
    db.flush()
    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER.value,
        content="write",
    )
    db.add(message)
    db.commit()

    service = McpApprovalService(db, get_settings())
    pending = service.create_pending(
        workspace_id=chain.workspace.id,
        conversation_id=conversation.id,
        message_id=message.id,
        grant_id=chain.grant.id,
        model_tool_call_id="write-call",
        idempotency_key="write-admission",
        arguments={"id": 1},
        loop_state={"v": 1, "messages": []},
        initiated_by_user_id=chain.user.id,
    )
    duplicate = service.create_pending(
        workspace_id=chain.workspace.id,
        conversation_id=conversation.id,
        message_id=message.id,
        grant_id=chain.grant.id,
        model_tool_call_id="write-call",
        idempotency_key="write-admission",
        arguments={"id": 1},
        loop_state={"v": 1, "messages": []},
        initiated_by_user_id=chain.user.id,
    )
    assert duplicate.id == pending.id

    with pytest.raises(AppError) as changed_arguments:
        service.create_pending(
            workspace_id=chain.workspace.id,
            conversation_id=conversation.id,
            message_id=message.id,
            grant_id=chain.grant.id,
            model_tool_call_id="write-call",
            idempotency_key="write-admission",
            arguments={"id": 2},
            loop_state={"v": 1, "messages": []},
            initiated_by_user_id=chain.user.id,
        )
    assert changed_arguments.value.category == ErrorCategory.CONFLICT

    with pytest.raises(AppError) as wrong_actor:
        service.decide_workspace_chat(
            workspace_id=chain.workspace.id,
            conversation_id=conversation.id,
            pending_id=pending.id,
            actor_user_id=uuid.uuid4(),
            decision="approve",
        )
    assert wrong_actor.value.category == ErrorCategory.MCP_TOOL_NOT_GRANTED

    decision = service.decide_workspace_chat(
        workspace_id=chain.workspace.id,
        conversation_id=conversation.id,
        pending_id=pending.id,
        actor_user_id=chain.user.id,
        decision="approve",
    )
    repeated = service.decide_workspace_chat(
        workspace_id=chain.workspace.id,
        conversation_id=conversation.id,
        pending_id=pending.id,
        actor_user_id=chain.user.id,
        decision="approve",
    )
    assert decision.enqueue_resume is True
    assert repeated.enqueue_resume is False
    claimed = service.claim_resume(
        workspace_id=chain.workspace.id,
        pending_id=pending.id,
        lease_seconds=30,
    )
    assert claimed is not None and claimed.execution_deadline is not None
    with pytest.raises(AppError) as missing_dispatch_marker:
        service.finish_execution(
            workspace_id=chain.workspace.id,
            pending_id=pending.id,
        )
    assert missing_dispatch_marker.value.category == ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
    service.mark_gateway_dispatch_started(
        workspace_id=chain.workspace.id,
        pending_id=pending.id,
    )
    service.finish_execution(
        workspace_id=chain.workspace.id,
        pending_id=pending.id,
    )
    db.commit()
    db.refresh(pending)
    assert pending.status == "executed"
    assert pending.arguments_encrypted is None
    assert pending.loop_state_encrypted is None
    assert pending.claim_lease_expires_at is None


def test_widget_outbox_enqueue_is_idempotent_and_ordered(db) -> None:
    chain = _runtime_chain(db)
    conversation = Conversation(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        user_id=None,
        source="widget",
        title="widget",
    )
    widget = WidgetInstance(
        workspace_id=chain.workspace.id,
        app_installation_id=chain.installation.id,
        expert_id=chain.expert.id,
        title="Widget",
        allowed_origins=["https://example.com"],
        mcp_source_epoch=1,
        mcp_source_principal_fingerprint="c" * 64,
    )
    db.add_all([conversation, widget])
    db.flush()
    assistant = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT.value,
        content="first\nsecond",
    )
    surface = McpToolSurfaceBinding(
        workspace_id=chain.workspace.id,
        expert_id=chain.expert.id,
        mcp_tool_grant_id=chain.grant.id,
        surface_kind="chat_widget",
        widget_instance_id=widget.id,
        channel_binding_id=None,
        state="active",
        write_policy="deny",
        approved_surface_config_hash="d" * 64,
        approved_source_principal_fingerprint="c" * 64,
        approved_source_epoch=1,
        public_risk_acknowledged_at=chain.now,
        outbound_data_acknowledged_at=chain.now,
        approved_by_user_id=chain.user.id,
        approved_at=chain.now,
    )
    db.add_all([assistant, surface])
    db.commit()

    outbox = McpSurfaceOutboxService(db, get_settings())
    kwargs = {
        "workspace_id": chain.workspace.id,
        "conversation_id": conversation.id,
        "assistant_message_id": assistant.id,
        "surface_binding_id": surface.id,
        "rendered_segments": ["first", "second"],
        "widget_instance_id": widget.id,
        "initiating_origin_digest": "e" * 64,
        "external_turn_handle_digest": "f" * 64,
    }
    first = outbox.enqueue(**kwargs)
    db.commit()
    repeated = outbox.enqueue(**kwargs)
    assert [row.id for row in repeated] == [row.id for row in first]

    claimed_first = outbox.claim(first[0].id)
    assert claimed_first is not None
    assert outbox.claim(first[1].id) is None
    outbox.mark_sent(first[0].id, provider_message_id="provider-1")
    db.commit()
    assert outbox.claim(first[1].id) is not None
    assert outbox.rendered_text(first[1]) == "second"
    db.rollback()

    with pytest.raises(AppError) as changed:
        outbox.enqueue(**{**kwargs, "rendered_segments": ["changed", "second"]})
    assert changed.value.category == ErrorCategory.CONFLICT

    with pytest.raises(AppError) as changed_count:
        outbox.enqueue(**{**kwargs, "rendered_segments": ["first"]})
    assert changed_count.value.category == ErrorCategory.CONFLICT
    assert isinstance(changed_count.value.message, str)

    with pytest.raises(AppError) as partial_receipt:
        outbox.enqueue(
            **{
                **kwargs,
                "widget_instance_id": None,
                "external_turn_handle_digest": None,
            }
        )
    assert partial_receipt.value.category == ErrorCategory.VALIDATION

    stale_widget_surface_bindings(db, widget)
    assert widget.mcp_source_epoch == 2
    assert surface.state == "stale_source"
