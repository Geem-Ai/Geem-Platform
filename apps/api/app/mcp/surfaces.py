"""Exact default-off MCP surface bindings, approval views, and outbox state."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.mcp_product import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTORS_APP_SLUG,
    MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
    MCP_TOOL_CALLS_USAGE_METRIC,
)
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    acquire_surface_target_runtime_mutation_fences,
    begin_runtime_admission_transaction,
)
from app.audit import AuditAction, AuditEntityType, record_audit
from app.common.crypto import decrypt_json, encrypt_json
from app.connectors.models import (
    AppConnection,
    ChannelBinding,
    ChannelConversationBinding,
)
from app.connectors.types import CONNECTION_USABLE_STATUSES, ConnectionHealth
from app.conversations.invocation import (
    SOURCE_CHANNEL,
    SOURCE_WIDGET,
    ChatInvocationContext,
)
from app.conversations.models import Conversation
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.mcp.approvals import McpApprovalService, PendingDecision
from app.mcp.access_policy import is_mcp_access_denial
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.public_tokens import (
    channel_external_principal_fingerprint,
    widget_external_principal_fingerprint,
)
from app.mcp.resolver import ResolvedMcpTool
from app.mcp.runtime_models import (
    McpPendingToolCall,
    McpSurfaceDelivery,
    McpToolSurfaceBinding,
)
from app.mcp.types import (
    McpCompatibilityStatus,
    McpGrantState,
    McpToolClassification,
    McpToolStatus,
    annotations_forbid_read_only,
)
from app.usage.models import UsagePeriodCounter
from app.usage.periods import PeriodType, period_containing
from app.widgets.models import (
    WidgetConversationBinding,
    WidgetInstance,
    WidgetInstanceStatus,
)
from app.widgets.origins import normalize_origin


CHAT_WIDGET_APP_SLUG = "chat-widget"
WHATSAPP_APP_SLUG = "whatsapp"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class McpSurfaceBindingCreateIn(_StrictModel):
    mcp_tool_grant_id: uuid.UUID
    surface_kind: Literal["chat_widget", "whatsapp_openwa"]
    widget_instance_id: uuid.UUID | None = None
    channel_binding_id: uuid.UUID | None = None
    write_policy: Literal["deny", "workspace_operator_approval"] = "deny"
    public_risk_acknowledged: bool = False
    outbound_data_acknowledged: bool = False

    @model_validator(mode="after")
    def exact_target(self) -> "McpSurfaceBindingCreateIn":
        widget = self.widget_instance_id is not None
        channel = self.channel_binding_id is not None
        if widget == channel or (self.surface_kind == "chat_widget") != widget:
            raise ValueError("Exactly one matching MCP surface target is required.")
        if not self.public_risk_acknowledged or not self.outbound_data_acknowledged:
            raise ValueError("Both MCP external-surface risk acknowledgements are required.")
        return self


class McpSurfaceBindingOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    expert_id: uuid.UUID
    mcp_tool_grant_id: uuid.UUID
    surface_kind: str
    widget_instance_id: uuid.UUID | None
    channel_binding_id: uuid.UUID | None
    state: str
    write_policy: str
    public_risk_acknowledged_at: datetime
    outbound_data_acknowledged_at: datetime
    target_label: str | None = None


class McpDecisionIn(_StrictModel):
    decision: Literal["approve", "deny"]


class McpApprovalOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    status: str
    surface_kind: str
    surface_label: str
    sender_label: str | None = None
    connection_name: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None = None
    outcome_message: str | None = None


class McpApprovalListOut(BaseModel):
    items: list[McpApprovalOut]
    total: int
    limit: int
    offset: int


class McpDeliveryOut(BaseModel):
    id: uuid.UUID
    status: str
    surface_kind: str
    surface_label: str
    sequence: int
    segment_index: int
    provider_message_id: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class McpDeliveryListOut(BaseModel):
    items: list[McpDeliveryOut]
    total: int
    limit: int
    offset: int


class McpDeliveryReconcileIn(_StrictModel):
    resolution: Literal["confirmed_sent", "cancelled"]


class McpUsageOut(BaseModel):
    access: dict[str, Any]
    connections: dict[str, int]
    tool_calls_daily: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResolvedSurfaceMcpTool:
    grant: McpToolGrant
    tool: McpServerTool
    connection: AppConnection
    provider_tool_schema: dict[str, Any]
    surface_binding: McpToolSurfaceBinding
    source_app_slug: str
    surface_target_key: str
    external_principal_fingerprint: str


class McpSurfaceBindingService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        session_factory=SessionLocal,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    def list_bindings(
        self, *, workspace_id: uuid.UUID, expert_id: uuid.UUID
    ) -> list[McpSurfaceBindingOut]:
        rows = self.db.scalars(
            select(McpToolSurfaceBinding)
            .where(
                McpToolSurfaceBinding.workspace_id == workspace_id,
                McpToolSurfaceBinding.expert_id == expert_id,
            )
            .order_by(McpToolSurfaceBinding.created_at, McpToolSurfaceBinding.id)
        ).all()
        return [self._out(row, db=self.db) for row in rows]

    def create_binding(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: McpSurfaceBindingCreateIn,
    ) -> McpSurfaceBindingOut:
        channel_connection_id = None
        if body.channel_binding_id is not None:
            channel_connection_id = self.db.scalar(
                select(ChannelBinding.app_connection_id).where(
                    ChannelBinding.workspace_id == workspace_id,
                    ChannelBinding.id == body.channel_binding_id,
                )
            )
            if channel_connection_id is None:
                raise AppError(ErrorCategory.NOT_FOUND, "WhatsApp target not found.")
        gate = self.session_factory()
        try:
            begin_runtime_admission_transaction(gate)
            source_slug = _source_app_slug(body.surface_kind)
            target_key = _target_key(
                body.surface_kind,
                body.widget_instance_id,
                body.channel_binding_id,
                channel_connection_id=channel_connection_id,
            )
            acquire_runtime_admission_fences(
                gate,
                workspace_id=workspace_id,
                app_slugs=(MCP_CONNECTORS_APP_SLUG, source_slug),
            )
            acquire_surface_target_runtime_mutation_fences(
                gate,
                workspace_id=workspace_id,
                surface_target_keys=(target_key,),
            )
            access = AppAccessService(gate).require_runtime_active_set(
                workspace_id,
                requirements_by_app_slug={
                    MCP_CONNECTORS_APP_SLUG: (MCP_CONNECTIONS_ENTITLEMENT,),
                    source_slug: (),
                },
            )
            grant, tool, connection = _lock_exact_grant(
                gate, workspace_id, expert_id, body.mcp_tool_grant_id
            )
            if not _grant_is_current(
                grant,
                tool,
                connection,
                now=access.decision_at,
                settings=self.settings,
            ):
                raise AppError(
                    ErrorCategory.MCP_TOOL_NOT_GRANTED,
                    "The MCP tool grant is not current.",
                )
            if connection.app_installation_id != access.require(
                MCP_CONNECTORS_APP_SLUG
            ).installation_id:
                raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "The MCP grant is invalid.")

            now = access.decision_at
            if body.surface_kind == "chat_widget":
                assert body.widget_instance_id is not None
                source = gate.scalar(
                    select(WidgetInstance)
                    .where(
                        WidgetInstance.workspace_id == workspace_id,
                        WidgetInstance.id == body.widget_instance_id,
                        WidgetInstance.expert_id == expert_id,
                    )
                    .with_for_update()
                )
                if source is None or source.status != WidgetInstanceStatus.ACTIVE.value:
                    raise AppError(ErrorCategory.NOT_FOUND, "Chat Widget target not found.")
                origins = _widget_origins(source)
                if not origins:
                    raise AppError(
                        ErrorCategory.VALIDATION,
                        "MCP-enabled widgets require a non-empty exact HTTPS origin allowlist.",
                    )
                if source.app_installation_id != access.require(source_slug).installation_id:
                    raise AppError(ErrorCategory.APP_NOT_INSTALLED, "Chat Widget is not active.")
                config_hash = _widget_config_hash(source)
                source_fingerprint = _widget_source_fingerprint(source)
                source.mcp_source_principal_fingerprint = source_fingerprint
                target_label = source.title
            else:
                assert body.channel_binding_id is not None
                source = gate.scalar(
                    select(ChannelBinding)
                    .where(
                        ChannelBinding.workspace_id == workspace_id,
                        ChannelBinding.id == body.channel_binding_id,
                        ChannelBinding.expert_id == expert_id,
                    )
                    .with_for_update()
                )
                if (
                    source is None
                    or not source.enabled
                    or not source.auto_reply_enabled
                    or source.respond_to_groups
                ):
                    raise AppError(
                        ErrorCategory.NOT_FOUND,
                        "WhatsApp direct-chat target not found.",
                    )
                channel_connection = gate.scalar(
                    select(AppConnection)
                    .where(
                        AppConnection.workspace_id == workspace_id,
                        AppConnection.id == source.app_connection_id,
                    )
                    .with_for_update()
                )
                if (
                    channel_connection is None
                    or channel_connection.app_installation_id
                    != access.require(source_slug).installation_id
                    or channel_connection.status not in CONNECTION_USABLE_STATUSES
                ):
                    raise AppError(ErrorCategory.CONNECTOR_NOT_CONNECTED, "WhatsApp is not active.")
                config_hash = _channel_config_hash(source, channel_connection)
                source_fingerprint = _channel_source_fingerprint(source, channel_connection)
                source.mcp_source_principal_fingerprint = source_fingerprint
                target_label = channel_connection.display_name

            existing = gate.scalar(
                select(McpToolSurfaceBinding)
                .where(
                    McpToolSurfaceBinding.workspace_id == workspace_id,
                    McpToolSurfaceBinding.expert_id == expert_id,
                    McpToolSurfaceBinding.mcp_tool_grant_id == grant.id,
                    (
                        McpToolSurfaceBinding.widget_instance_id
                        == body.widget_instance_id
                        if body.widget_instance_id is not None
                        else McpToolSurfaceBinding.channel_binding_id
                        == body.channel_binding_id
                    ),
                )
                .with_for_update()
            )
            if existing is None:
                existing = McpToolSurfaceBinding(
                    workspace_id=workspace_id,
                    expert_id=expert_id,
                    mcp_tool_grant_id=grant.id,
                    surface_kind=body.surface_kind,
                    widget_instance_id=body.widget_instance_id,
                    channel_binding_id=body.channel_binding_id,
                    state="active",
                    write_policy=body.write_policy,
                    approved_surface_config_hash=config_hash,
                    approved_source_principal_fingerprint=source_fingerprint,
                    approved_source_epoch=source.mcp_source_epoch,
                    public_risk_acknowledged_at=now,
                    outbound_data_acknowledged_at=now,
                    approved_by_user_id=actor_id,
                    approved_at=now,
                )
                gate.add(existing)
            else:
                existing.state = "active"
                existing.write_policy = body.write_policy
                existing.approved_surface_config_hash = config_hash
                existing.approved_source_principal_fingerprint = source_fingerprint
                existing.approved_source_epoch = source.mcp_source_epoch
                existing.public_risk_acknowledged_at = now
                existing.outbound_data_acknowledged_at = now
                existing.approved_by_user_id = actor_id
                existing.approved_at = now
            gate.flush()
            record_audit(
                gate,
                action=AuditAction.APP_MCP_SURFACE_BOUND,
                entity_type=AuditEntityType.MCP_TOOL_SURFACE_BINDING,
                entity_id=existing.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={
                    "expert_id": str(expert_id),
                    "grant_id": str(grant.id),
                    "surface_binding_id": str(existing.id),
                    "surface_kind": existing.surface_kind,
                },
                allowlist=frozenset(
                    {
                        "expert_id",
                        "grant_id",
                        "surface_binding_id",
                        "surface_kind",
                    }
                ),
            )
            output = self._out(existing, db=gate, target_label=target_label)
            gate.commit()
            return output
        except AppError:
            gate.rollback()
            raise
        except SQLAlchemyError as exc:
            gate.rollback()
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "The MCP surface binding could not be updated.",
                retryable=True,
            ) from exc
        finally:
            gate.close()

    def revoke_binding(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        binding_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        snapshot = self.db.execute(
            select(
                McpToolSurfaceBinding.surface_kind,
                McpToolSurfaceBinding.widget_instance_id,
                McpToolSurfaceBinding.channel_binding_id,
                ChannelBinding.app_connection_id,
            )
            .outerjoin(
                ChannelBinding,
                ChannelBinding.id == McpToolSurfaceBinding.channel_binding_id,
            )
            .where(
                McpToolSurfaceBinding.workspace_id == workspace_id,
                McpToolSurfaceBinding.expert_id == expert_id,
                McpToolSurfaceBinding.id == binding_id,
            )
        ).one_or_none()
        if snapshot is None:
            raise AppError(ErrorCategory.NOT_FOUND, "MCP surface binding not found.")
        target_key = _target_key(
            snapshot.surface_kind,
            snapshot.widget_instance_id,
            snapshot.channel_binding_id,
            channel_connection_id=snapshot.app_connection_id,
        )
        # Admission takes this fence before any surface/source row lock. Keep
        # the restrictive path in the same canonical order to avoid a
        # row-lock/advisory-lock cycle under concurrent dispatch and revoke.
        acquire_surface_target_runtime_mutation_fences(
            self.db,
            workspace_id=workspace_id,
            surface_target_keys=(target_key,),
        )
        row = self.db.scalar(
            select(McpToolSurfaceBinding)
            .where(
                McpToolSurfaceBinding.workspace_id == workspace_id,
                McpToolSurfaceBinding.expert_id == expert_id,
                McpToolSurfaceBinding.id == binding_id,
            )
            .with_for_update()
        )
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "MCP surface binding not found.")
        current_connection_id = (
            self.db.scalar(
                select(ChannelBinding.app_connection_id).where(
                    ChannelBinding.id == row.channel_binding_id,
                    ChannelBinding.workspace_id == workspace_id,
                )
            )
            if row.channel_binding_id is not None
            else None
        )
        if (
            _target_key(
                row.surface_kind,
                row.widget_instance_id,
                row.channel_binding_id,
                channel_connection_id=current_connection_id,
            )
            != target_key
        ):
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "The MCP surface binding changed during revocation.",
                retryable=True,
            )
        row.state = "revoked"
        record_audit(
            self.db,
            action=AuditAction.APP_MCP_SURFACE_UNBOUND,
            entity_type=AuditEntityType.MCP_TOOL_SURFACE_BINDING,
            entity_id=binding_id,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            metadata={
                "expert_id": str(expert_id),
                "surface_binding_id": str(binding_id),
                "surface_kind": row.surface_kind,
            },
            allowlist=frozenset(
                {"expert_id", "surface_binding_id", "surface_kind"}
            ),
        )
        self.db.commit()

    @staticmethod
    def _out(
        row: McpToolSurfaceBinding,
        *,
        db: Session,
        target_label: str | None = None,
    ) -> McpSurfaceBindingOut:
        if target_label is None and row.widget_instance_id:
            target_label = db.scalar(
                select(WidgetInstance.title).where(WidgetInstance.id == row.widget_instance_id)
            )
        if target_label is None and row.channel_binding_id:
            target_label = db.scalar(
                select(AppConnection.display_name)
                .join(ChannelBinding, ChannelBinding.app_connection_id == AppConnection.id)
                .where(ChannelBinding.id == row.channel_binding_id)
            )
        return McpSurfaceBindingOut(
            id=row.id,
            workspace_id=row.workspace_id,
            expert_id=row.expert_id,
            mcp_tool_grant_id=row.mcp_tool_grant_id,
            surface_kind=row.surface_kind,
            widget_instance_id=row.widget_instance_id,
            channel_binding_id=row.channel_binding_id,
            state=row.state,
            write_policy=row.write_policy,
            public_risk_acknowledged_at=row.public_risk_acknowledged_at,
            outbound_data_acknowledged_at=row.outbound_data_acknowledged_at,
            target_label=target_label,
        )


class McpSurfaceResolver:
    """Resolve only exact external bindings; absence returns before paid lookup."""

    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        session_factory=SessionLocal,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    def resolve(
        self, invocation: ChatInvocationContext, expert_id: uuid.UUID
    ) -> list[ResolvedSurfaceMcpTool]:
        if not self.settings.mcp_connector_enabled:
            return []
        if invocation.source not in {SOURCE_WIDGET, SOURCE_CHANNEL}:
            return []
        if (
            invocation.expert_id not in {None, expert_id}
            or invocation.source_binding_id is None
            or not invocation.external_principal_fingerprint
            or invocation.conversation_id is None
        ):
            return []
        target_id = invocation.widget_id
        if invocation.source == SOURCE_CHANNEL:
            target_id = _channel_binding_id_for_connection(
                self.db, invocation.workspace_id, invocation.connection_id
            )
        if target_id is None:
            return []
        target_column = (
            McpToolSurfaceBinding.widget_instance_id
            if invocation.source == SOURCE_WIDGET
            else McpToolSurfaceBinding.channel_binding_id
        )
        # Exact-binding preflight is intentionally free: no candidate means no
        # MCP or companion-App access query and the legacy path stays unchanged.
        if not self.db.scalar(
            select(McpToolSurfaceBinding.id)
            .where(
                McpToolSurfaceBinding.workspace_id == invocation.workspace_id,
                McpToolSurfaceBinding.expert_id == expert_id,
                McpToolSurfaceBinding.state == "active",
                target_column == target_id,
            )
            .limit(1)
        ):
            return []
        preflight_rows = self.db.execute(
            select(
                McpToolSurfaceBinding,
                McpToolGrant,
                McpServerTool,
                AppConnection,
            )
            .join(
                McpToolGrant,
                (McpToolGrant.workspace_id == McpToolSurfaceBinding.workspace_id)
                & (McpToolGrant.id == McpToolSurfaceBinding.mcp_tool_grant_id),
            )
            .join(
                McpServerTool,
                (McpServerTool.workspace_id == McpToolGrant.workspace_id)
                & (McpServerTool.id == McpToolGrant.mcp_server_tool_id),
            )
            .join(
                AppConnection,
                (AppConnection.workspace_id == McpToolGrant.workspace_id)
                & (AppConnection.id == McpToolGrant.app_connection_id),
            )
            .where(
                McpToolSurfaceBinding.workspace_id == invocation.workspace_id,
                McpToolSurfaceBinding.expert_id == expert_id,
                McpToolSurfaceBinding.state == "active",
                target_column == target_id,
            )
        ).all()
        preflight_now = datetime.now(timezone.utc)
        if not self._source_is_locally_eligible(
            self.db,
            invocation=invocation,
            expert_id=expert_id,
        ) or not any(
            _grant_is_current(
                grant,
                tool,
                connection,
                now=preflight_now,
                settings=self.settings,
            )
            and _surface_allows_tool(surface, tool)
            and self._surface_is_current(
                self.db,
                surface,
                invocation=invocation,
            )
            for surface, grant, tool, connection in preflight_rows
        ):
            return []

        gate = self.session_factory()
        try:
            begin_runtime_admission_transaction(gate)
            surface_kind = (
                "chat_widget" if invocation.source == SOURCE_WIDGET else "whatsapp_openwa"
            )
            source_slug = _source_app_slug(surface_kind)
            target_key = _target_key(
                surface_kind,
                invocation.widget_id,
                (
                    _channel_binding_id_for_connection(
                        gate, invocation.workspace_id, invocation.connection_id
                    )
                    if invocation.source == SOURCE_CHANNEL
                    else None
                ),
                channel_connection_id=invocation.connection_id,
            )
            acquire_runtime_admission_fences(
                gate,
                workspace_id=invocation.workspace_id,
                app_slugs=(MCP_CONNECTORS_APP_SLUG, source_slug),
                surface_target_keys=(target_key,),
            )
            access = AppAccessService(gate).require_runtime_active_set(
                invocation.workspace_id,
                requirements_by_app_slug={
                    MCP_CONNECTORS_APP_SLUG: (MCP_CONNECTIONS_ENTITLEMENT,),
                    source_slug: (),
                },
            )
            rows = gate.execute(
                select(
                    McpToolSurfaceBinding,
                    McpToolGrant,
                    McpServerTool,
                    AppConnection,
                )
                .join(
                    McpToolGrant,
                    (McpToolGrant.workspace_id == McpToolSurfaceBinding.workspace_id)
                    & (McpToolGrant.id == McpToolSurfaceBinding.mcp_tool_grant_id),
                )
                .join(
                    McpServerTool,
                    (McpServerTool.workspace_id == McpToolGrant.workspace_id)
                    & (McpServerTool.id == McpToolGrant.mcp_server_tool_id),
                )
                .join(
                    AppConnection,
                    (AppConnection.workspace_id == McpToolGrant.workspace_id)
                    & (AppConnection.id == McpToolGrant.app_connection_id),
                )
                .where(
                    McpToolSurfaceBinding.workspace_id == invocation.workspace_id,
                    McpToolSurfaceBinding.expert_id == expert_id,
                    McpToolSurfaceBinding.state == "active",
                    target_column == target_id,
                )
                .order_by(McpServerTool.llm_tool_name)
                .with_for_update(read=True)
            ).all()
            source_ok = self._source_is_current(
                gate,
                invocation=invocation,
                expert_id=expert_id,
                source_installation_id=access.require(source_slug).installation_id,
            )
            if not source_ok:
                gate.commit()
                return []
            result: list[ResolvedSurfaceMcpTool] = []
            for surface, grant, tool, connection in rows:
                if (
                    connection.app_installation_id
                    != access.require(MCP_CONNECTORS_APP_SLUG).installation_id
                    or not _grant_is_current(
                        grant,
                        tool,
                        connection,
                        now=access.decision_at,
                        settings=self.settings,
                    )
                    or not self._surface_is_current(
                        gate, surface, invocation=invocation
                    )
                ):
                    continue
                if not _surface_allows_tool(surface, tool):
                    continue
                result.append(
                    ResolvedSurfaceMcpTool(
                        grant=grant,
                        tool=tool,
                        connection=connection,
                        provider_tool_schema=_provider_schema(tool),
                        surface_binding=surface,
                        source_app_slug=source_slug,
                        surface_target_key=target_key,
                        external_principal_fingerprint=invocation.external_principal_fingerprint,
                    )
                )
                if len(result) >= self.settings.mcp_max_tools_per_expert:
                    break
            gate.commit()
            return result
        except AppError as exc:
            gate.rollback()
            if is_mcp_access_denial(exc):
                return []
            raise
        except SQLAlchemyError as exc:
            gate.rollback()
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "MCP surface access is temporarily unavailable.",
                retryable=True,
            ) from exc
        finally:
            gate.close()

    def _source_is_locally_eligible(
        self,
        db: Session,
        *,
        invocation: ChatInvocationContext,
        expert_id: uuid.UUID,
    ) -> bool:
        """Cheap source/binding preflight with no paid-App decision or row lock."""

        if invocation.source == SOURCE_WIDGET:
            if not invocation.initiating_origin or invocation.widget_id is None:
                return False
            widget = db.scalar(
                select(WidgetInstance).where(
                    WidgetInstance.workspace_id == invocation.workspace_id,
                    WidgetInstance.id == invocation.widget_id,
                    WidgetInstance.expert_id == expert_id,
                )
            )
            conv = db.scalar(
                select(WidgetConversationBinding).where(
                    WidgetConversationBinding.id == invocation.source_binding_id,
                    WidgetConversationBinding.workspace_id == invocation.workspace_id,
                    WidgetConversationBinding.widget_instance_id == invocation.widget_id,
                    WidgetConversationBinding.conversation_id == invocation.conversation_id,
                    WidgetConversationBinding.expert_id == expert_id,
                )
            )
            if (
                widget is None
                or conv is None
                or widget.status != WidgetInstanceStatus.ACTIVE.value
            ):
                return False
            try:
                origin = normalize_origin(invocation.initiating_origin)
            except ValueError:
                return False
            return origin in _widget_origins(widget) and _widget_principal_matches(
                invocation,
                widget,
                conv,
                settings=self.settings,
            )

        if invocation.connection_id is None:
            return False
        channel = db.scalar(
            select(ChannelBinding).where(
                ChannelBinding.workspace_id == invocation.workspace_id,
                ChannelBinding.app_connection_id == invocation.connection_id,
                ChannelBinding.expert_id == expert_id,
            )
        )
        conv = db.scalar(
            select(ChannelConversationBinding).where(
                ChannelConversationBinding.id == invocation.source_binding_id,
                ChannelConversationBinding.workspace_id == invocation.workspace_id,
                ChannelConversationBinding.app_connection_id == invocation.connection_id,
                ChannelConversationBinding.conversation_id == invocation.conversation_id,
                ChannelConversationBinding.expert_id == expert_id,
            )
        )
        source_connection = db.scalar(
            select(AppConnection).where(
                AppConnection.workspace_id == invocation.workspace_id,
                AppConnection.id == invocation.connection_id,
            )
        )
        return bool(
            channel
            and conv
            and source_connection
            and channel.enabled
            and channel.auto_reply_enabled
            and not channel.respond_to_groups
            and source_connection.status in CONNECTION_USABLE_STATUSES
            and _channel_principal_matches(
                invocation,
                conv,
                settings=self.settings,
            )
        )

    def _source_is_current(
        self,
        db: Session,
        *,
        invocation: ChatInvocationContext,
        expert_id: uuid.UUID,
        source_installation_id: uuid.UUID,
    ) -> bool:
        if invocation.source == SOURCE_WIDGET:
            if not invocation.initiating_origin or invocation.widget_id is None:
                return False
            widget = db.scalar(
                select(WidgetInstance)
                .where(
                    WidgetInstance.workspace_id == invocation.workspace_id,
                    WidgetInstance.id == invocation.widget_id,
                    WidgetInstance.expert_id == expert_id,
                )
                .with_for_update(read=True)
            )
            conv = db.scalar(
                select(WidgetConversationBinding)
                .where(
                    WidgetConversationBinding.id == invocation.source_binding_id,
                    WidgetConversationBinding.workspace_id == invocation.workspace_id,
                    WidgetConversationBinding.widget_instance_id == invocation.widget_id,
                    WidgetConversationBinding.conversation_id == invocation.conversation_id,
                    WidgetConversationBinding.expert_id == expert_id,
                )
                .with_for_update(read=True)
            )
            if (
                widget is None
                or conv is None
                or widget.status != WidgetInstanceStatus.ACTIVE.value
                or widget.app_installation_id != source_installation_id
            ):
                return False
            try:
                origin = normalize_origin(invocation.initiating_origin)
            except ValueError:
                return False
            return origin in _widget_origins(widget) and _widget_principal_matches(
                invocation,
                widget,
                conv,
                settings=self.settings,
            )

        if invocation.connection_id is None:
            return False
        channel = db.scalar(
            select(ChannelBinding)
            .where(
                ChannelBinding.workspace_id == invocation.workspace_id,
                ChannelBinding.app_connection_id == invocation.connection_id,
                ChannelBinding.expert_id == expert_id,
            )
            .with_for_update(read=True)
        )
        conv = db.scalar(
            select(ChannelConversationBinding)
            .where(
                ChannelConversationBinding.id == invocation.source_binding_id,
                ChannelConversationBinding.workspace_id == invocation.workspace_id,
                ChannelConversationBinding.app_connection_id == invocation.connection_id,
                ChannelConversationBinding.conversation_id == invocation.conversation_id,
                ChannelConversationBinding.expert_id == expert_id,
            )
            .with_for_update(read=True)
        )
        source_connection = db.scalar(
            select(AppConnection)
            .where(
                AppConnection.workspace_id == invocation.workspace_id,
                AppConnection.id == invocation.connection_id,
            )
            .with_for_update(read=True)
        )
        return bool(
            channel
            and conv
            and source_connection
            and channel.enabled
            and channel.auto_reply_enabled
            and not channel.respond_to_groups
            and source_connection.app_installation_id == source_installation_id
            and source_connection.status in CONNECTION_USABLE_STATUSES
            and _channel_principal_matches(
                invocation,
                conv,
                settings=self.settings,
            )
        )

    def _surface_is_current(
        self,
        db: Session,
        surface: McpToolSurfaceBinding,
        *,
        invocation: ChatInvocationContext,
    ) -> bool:
        if invocation.source == SOURCE_WIDGET:
            widget = db.get(WidgetInstance, surface.widget_instance_id)
            return bool(
                widget
                and surface.approved_source_epoch == widget.mcp_source_epoch
                and surface.approved_surface_config_hash == _widget_config_hash(widget)
                and surface.approved_source_principal_fingerprint
                == _widget_source_fingerprint(widget)
            )
        channel = db.get(ChannelBinding, surface.channel_binding_id)
        source_connection = (
            db.get(AppConnection, channel.app_connection_id) if channel else None
        )
        return bool(
            channel
            and source_connection
            and surface.approved_source_epoch == channel.mcp_source_epoch
            and surface.approved_surface_config_hash
            == _channel_config_hash(channel, source_connection)
            and surface.approved_source_principal_fingerprint
            == _channel_source_fingerprint(channel, source_connection)
        )


class McpExternalOperationsService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def list_approvals(
        self,
        *,
        workspace_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> McpApprovalListOut:
        where = (
            McpPendingToolCall.workspace_id == workspace_id,
            McpPendingToolCall.mcp_tool_surface_binding_id.is_not(None),
        )
        total = int(
            self.db.scalar(select(func.count()).select_from(McpPendingToolCall).where(*where))
            or 0
        )
        rows = self.db.execute(
            select(
                McpPendingToolCall,
                McpToolSurfaceBinding,
                McpServerTool,
                AppConnection,
            )
            .join(
                McpToolSurfaceBinding,
                McpToolSurfaceBinding.id
                == McpPendingToolCall.mcp_tool_surface_binding_id,
            )
            .join(
                McpToolGrant,
                McpToolGrant.id == McpPendingToolCall.mcp_tool_grant_id,
            )
            .join(McpServerTool, McpServerTool.id == McpToolGrant.mcp_server_tool_id)
            .join(AppConnection, AppConnection.id == McpToolGrant.app_connection_id)
            .where(*where)
            .order_by(McpPendingToolCall.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return McpApprovalListOut(
            items=[self._approval_out(*row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def decide_external(
        self,
        *,
        workspace_id: uuid.UUID,
        approval_id: uuid.UUID,
        operator_user_id: uuid.UUID,
        decision: str,
    ) -> McpApprovalOut:
        result = McpApprovalService(self.db, self.settings).decide_external(
            workspace_id=workspace_id,
            pending_id=approval_id,
            operator_user_id=operator_user_id,
            decision=decision,
        )
        record_audit(
            self.db,
            action=AuditAction.APP_MCP_TOOL_APPROVAL_DECIDED,
            entity_type=AuditEntityType.MCP_PENDING_TOOL_CALL,
            entity_id=approval_id,
            workspace_id=workspace_id,
            actor_user_id=operator_user_id,
            metadata={
                "approval_id": str(approval_id),
                "decision": decision,
                "status": result.status,
                "surface_kind": "external",
            },
            allowlist=frozenset(
                {"approval_id", "decision", "status", "surface_kind"}
            ),
        )
        self.db.commit()
        if result.enqueue_resume:
            _enqueue_resume_after_commit(approval_id)
        elif result.status in {"denied", "expired", "outcome_unknown"}:
            from app.mcp.resume import McpPendingResumeService

            McpPendingResumeService(self.db, self.settings).finalize_terminal(
                approval_id
            )
        row = self.db.execute(
            select(
                McpPendingToolCall,
                McpToolSurfaceBinding,
                McpServerTool,
                AppConnection,
            )
            .join(
                McpToolSurfaceBinding,
                McpToolSurfaceBinding.id
                == McpPendingToolCall.mcp_tool_surface_binding_id,
            )
            .join(McpToolGrant, McpToolGrant.id == McpPendingToolCall.mcp_tool_grant_id)
            .join(McpServerTool, McpServerTool.id == McpToolGrant.mcp_server_tool_id)
            .join(AppConnection, AppConnection.id == McpToolGrant.app_connection_id)
            .where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.id == approval_id,
            )
        ).one()
        return self._approval_out(*row)

    def decide_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        approval_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        decision: str,
    ) -> PendingDecision:
        result = McpApprovalService(self.db, self.settings).decide_workspace_chat(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            pending_id=approval_id,
            actor_user_id=actor_user_id,
            decision=decision,
        )
        record_audit(
            self.db,
            action=AuditAction.APP_MCP_TOOL_APPROVAL_DECIDED,
            entity_type=AuditEntityType.MCP_PENDING_TOOL_CALL,
            entity_id=approval_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            metadata={
                "approval_id": str(approval_id),
                "decision": decision,
                "status": result.status,
                "surface_kind": "workspace",
            },
            allowlist=frozenset(
                {"approval_id", "decision", "status", "surface_kind"}
            ),
        )
        self.db.commit()
        if result.enqueue_resume:
            _enqueue_resume_after_commit(approval_id)
        elif result.status in {"denied", "expired", "outcome_unknown"}:
            from app.mcp.resume import McpPendingResumeService

            McpPendingResumeService(self.db, self.settings).finalize_terminal(
                approval_id
            )
        return result

    def list_deliveries(
        self,
        *,
        workspace_id: uuid.UUID,
        status: str | None,
        limit: int,
        offset: int,
    ) -> McpDeliveryListOut:
        predicates = [McpSurfaceDelivery.workspace_id == workspace_id]
        if status:
            predicates.append(McpSurfaceDelivery.status == status)
        total = int(
            self.db.scalar(select(func.count()).select_from(McpSurfaceDelivery).where(*predicates))
            or 0
        )
        rows = self.db.execute(
            select(McpSurfaceDelivery, McpToolSurfaceBinding)
            .join(
                McpToolSurfaceBinding,
                McpToolSurfaceBinding.id == McpSurfaceDelivery.mcp_tool_surface_binding_id,
            )
            .where(*predicates)
            .order_by(McpSurfaceDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return McpDeliveryListOut(
            items=[self._delivery_out(delivery, surface) for delivery, surface in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def reconcile_delivery(
        self,
        *,
        workspace_id: uuid.UUID,
        delivery_id: uuid.UUID,
        operator_user_id: uuid.UUID,
        resolution: str,
    ) -> McpDeliveryOut:
        row = self.db.scalar(
            select(McpSurfaceDelivery)
            .where(
                McpSurfaceDelivery.workspace_id == workspace_id,
                McpSurfaceDelivery.id == delivery_id,
            )
            .with_for_update()
        )
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "MCP delivery not found.")
        if row.status != "delivery_unknown":
            raise AppError(ErrorCategory.CONFLICT, "Only an unknown delivery can be reconciled.")
        if resolution not in {"confirmed_sent", "cancelled"}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid delivery resolution.")
        row.status = "sent" if resolution == "confirmed_sent" else "cancelled"
        row.reconciliation_resolution = (
            "delivered" if resolution == "confirmed_sent" else "not_delivered"
        )
        row.reconciled_by_user_id = operator_user_id
        row.reconciled_at = datetime.now(timezone.utc)
        row.version += 1
        record_audit(
            self.db,
            action=AuditAction.APP_MCP_EXTERNAL_DELIVERY_CHANGED,
            entity_type=AuditEntityType.MCP_SURFACE_DELIVERY,
            entity_id=row.id,
            workspace_id=workspace_id,
            actor_user_id=operator_user_id,
            metadata={
                "delivery_id": str(row.id),
                "resolution": resolution,
                "status": row.status,
            },
            allowlist=frozenset({"delivery_id", "resolution", "status"}),
        )
        self.db.commit()
        surface = self.db.get(McpToolSurfaceBinding, row.mcp_tool_surface_binding_id)
        assert surface is not None
        return self._delivery_out(row, surface)

    def usage(self, *, workspace_id: uuid.UUID) -> McpUsageOut:
        gate = SessionLocal()
        try:
            begin_runtime_admission_transaction(gate)
            acquire_runtime_admission_fences(
                gate,
                workspace_id=workspace_id,
                app_slugs=(MCP_CONNECTORS_APP_SLUG,),
            )
            access = AppAccessService(gate).require_runtime_active(
                workspace_id,
                app_slug=MCP_CONNECTORS_APP_SLUG,
                entitlement_keys=(
                    MCP_CONNECTIONS_ENTITLEMENT,
                    MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
                ),
            )
            window = period_containing(access.decision_at, PeriodType.DAILY)
            used_connections = int(
                gate.scalar(
                    select(func.count())
                    .select_from(AppConnection)
                    .where(
                        AppConnection.workspace_id == workspace_id,
                        AppConnection.app_installation_id == access.installation_id,
                        AppConnection.status.in_(CONNECTION_USABLE_STATUSES),
                    )
                )
                or 0
            )
            calls = gate.scalar(
                select(UsagePeriodCounter.used).where(
                    UsagePeriodCounter.workspace_id == workspace_id,
                    UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
                    UsagePeriodCounter.period_type == PeriodType.DAILY.value,
                    UsagePeriodCounter.period_start == window.start,
                    UsagePeriodCounter.period_end == window.end,
                )
            )
            output = McpUsageOut(
                access={
                    "status": "active",
                    "plan_code": access.plan_code,
                    "current_period_start": access.current_period_start,
                    "current_period_end": access.current_period_end,
                    "installed": True,
                },
                connections={
                    "used": used_connections,
                    "limit": access.entitlement(MCP_CONNECTIONS_ENTITLEMENT),
                },
                tool_calls_daily={
                    "used": int(calls or 0),
                    "limit": access.entitlement(MCP_TOOL_CALLS_DAILY_ENTITLEMENT),
                    "reset_at": window.end.isoformat(),
                },
            )
            gate.commit()
            return output
        finally:
            gate.close()

    def _approval_out(
        self,
        pending: McpPendingToolCall,
        surface: McpToolSurfaceBinding,
        tool: McpServerTool,
        connection: AppConnection,
    ) -> McpApprovalOut:
        arguments = None
        if pending.arguments_encrypted:
            arguments = decrypt_json(pending.arguments_encrypted, settings=self.settings)
        return McpApprovalOut(
            id=pending.id,
            conversation_id=pending.conversation_id,
            message_id=pending.message_id,
            status=pending.status,
            surface_kind=surface.surface_kind,
            surface_label=_surface_label(self.db, surface),
            sender_label=_safe_external_sender_label(pending, surface),
            connection_name=connection.display_name,
            tool_name=tool.tool_name,
            arguments=arguments,
            expires_at=pending.expires_at,
            created_at=pending.created_at,
            decided_at=pending.decided_at,
            outcome_message=(
                "outcome_unknown" if pending.status == "outcome_unknown" else None
            ),
        )

    def _delivery_out(
        self, delivery: McpSurfaceDelivery, surface: McpToolSurfaceBinding
    ) -> McpDeliveryOut:
        return McpDeliveryOut(
            id=delivery.id,
            status=delivery.status,
            surface_kind=surface.surface_kind,
            surface_label=_surface_label(self.db, surface),
            sequence=delivery.conversation_sequence,
            segment_index=delivery.segment_index,
            provider_message_id=delivery.provider_message_id,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
            resolved_at=delivery.reconciled_at,
        )


class McpSurfaceOutboxService:
    """Immutable segment outbox with CAS/lease and ambiguity boundaries."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def enqueue(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        surface_binding_id: uuid.UUID,
        rendered_segments: list[str],
        pending_id: uuid.UUID | None = None,
        widget_instance_id: uuid.UUID | None = None,
        initiating_origin_digest: str | None = None,
        external_turn_handle_digest: str | None = None,
        external_principal_fingerprint: str | None = None,
        response_revision: int = 1,
        ttl_seconds: int = 900,
    ) -> list[McpSurfaceDelivery]:
        if not rendered_segments:
            return []
        if len(rendered_segments) > 64:
            raise AppError(
                ErrorCategory.VALIDATION,
                "An MCP external response has too many delivery segments.",
            )
        if response_revision < 1:
            raise AppError(
                ErrorCategory.VALIDATION,
                "An MCP external response revision must be positive.",
            )
        widget_receipt = widget_instance_id is not None
        if (
            (initiating_origin_digest is not None) != widget_receipt
            or (external_turn_handle_digest is not None) != widget_receipt
        ):
            raise AppError(
                ErrorCategory.VALIDATION,
                "A complete Widget MCP turn receipt is required.",
            )
        if widget_receipt:
            initiating_origin_digest = _require_sha256_digest(
                initiating_origin_digest, "Widget origin"
            )
            external_turn_handle_digest = _require_sha256_digest(
                external_turn_handle_digest, "Widget turn handle"
            )
            if external_principal_fingerprint is not None:
                external_principal_fingerprint = _require_sha256_digest(
                    external_principal_fingerprint,
                    "external principal",
                )
        else:
            # WhatsApp delivery must carry the keyed conversation/sender
            # fingerprint captured at turn admission.  The raw chat/sender IDs
            # remain only in ChannelConversationBinding and are re-digested at
            # delivery time; they are never copied into this outbox.
            external_principal_fingerprint = _require_sha256_digest(
                external_principal_fingerprint,
                "external principal",
            )
        bounded_segments = [str(segment)[:16_000] for segment in rendered_segments]
        conversation = self.db.scalar(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.id == conversation_id,
            )
            .with_for_update()
        )
        if conversation is None:
            raise AppError(ErrorCategory.CONVERSATION_NOT_FOUND, "Conversation not found.")
        existing = self._existing_enqueue(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            surface_binding_id=surface_binding_id,
            pending_id=pending_id,
            widget_instance_id=widget_instance_id,
            initiating_origin_digest=initiating_origin_digest,
            external_turn_handle_digest=external_turn_handle_digest,
            external_principal_fingerprint=external_principal_fingerprint,
            response_revision=response_revision,
            bounded_segments=bounded_segments,
        )
        if existing:
            return existing
        sequence = int(
            self.db.scalar(
                select(func.coalesce(func.max(McpSurfaceDelivery.conversation_sequence), 0))
                .where(McpSurfaceDelivery.conversation_id == conversation_id)
            )
            or 0
        ) + 1
        deadline = datetime.now(timezone.utc) + timedelta(seconds=max(1, ttl_seconds))
        rows: list[McpSurfaceDelivery] = []
        for index, bounded in enumerate(bounded_segments):
            row = McpSurfaceDelivery(
                workspace_id=workspace_id,
                mcp_pending_tool_call_id=pending_id,
                assistant_message_id=assistant_message_id,
                conversation_id=conversation_id,
                mcp_tool_surface_binding_id=surface_binding_id,
                widget_instance_id=widget_instance_id,
                initiating_origin_digest=initiating_origin_digest,
                external_turn_handle_digest=external_turn_handle_digest,
                response_revision=response_revision,
                conversation_sequence=sequence,
                segment_index=index,
                rendered_segment_encrypted=encrypt_json(
                    {
                        "text": bounded,
                        "external_principal_fingerprint": (
                            external_principal_fingerprint
                        ),
                    },
                    settings=self.settings,
                ),
                content_hash=_delivery_content_hash(
                    bounded,
                    external_principal_fingerprint,
                ),
                status="pending",
                version=1,
                attempts=0,
                delivery_deadline=deadline,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def claim(
        self,
        delivery_id: uuid.UUID,
        *,
        lease_seconds: int = 60,
        max_attempts: int = 3,
    ) -> McpSurfaceDelivery | None:
        now = datetime.now(timezone.utc)
        row = self.db.scalar(
            select(McpSurfaceDelivery)
            .where(McpSurfaceDelivery.id == delivery_id)
            .with_for_update()
        )
        if row is None or row.status != "pending":
            return None
        if row.delivery_deadline <= now:
            row.status = "expired"
            row.version += 1
            return None
        if row.attempts >= max(1, max_attempts):
            row.status = "cancelled"
            row.version += 1
            return None
        earlier = self.db.scalar(
            select(McpSurfaceDelivery.id)
            .where(
                McpSurfaceDelivery.conversation_id == row.conversation_id,
                (
                    (McpSurfaceDelivery.conversation_sequence < row.conversation_sequence)
                    | (
                        (McpSurfaceDelivery.conversation_sequence == row.conversation_sequence)
                        & (McpSurfaceDelivery.segment_index < row.segment_index)
                    )
                ),
                McpSurfaceDelivery.status.in_(("pending", "dispatching", "delivery_unknown")),
            )
            .limit(1)
        )
        if earlier is not None:
            return None
        row.status = "dispatching"
        row.claimed_at = now
        row.claim_lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
        row.attempts += 1
        row.version += 1
        self.db.flush()
        return row

    def rendered_payload(self, row: McpSurfaceDelivery) -> tuple[str, str | None]:
        payload = decrypt_json(row.rendered_segment_encrypted, settings=self.settings)
        text = str(payload.get("text") or "")
        raw_fingerprint = payload.get("external_principal_fingerprint")
        fingerprint = None
        if raw_fingerprint is not None:
            fingerprint = _require_sha256_digest(
                str(raw_fingerprint),
                "external principal",
            )
        expected_hash = _delivery_content_hash(text, fingerprint)
        if not hmac.compare_digest(expected_hash, row.content_hash):
            raise AppError(
                ErrorCategory.CONFLICT,
                "The MCP external delivery content failed integrity validation.",
            )
        return text, fingerprint

    def rendered_text(self, row: McpSurfaceDelivery) -> str:
        text, _fingerprint = self.rendered_payload(row)
        return text

    def cancel_before_send(self, delivery_id: uuid.UUID) -> bool:
        """Permanently cancel work that is proven not to have reached OpenWA."""

        row = self._lock(delivery_id)
        if row.status not in {"pending", "dispatching"}:
            return False
        row.status = "cancelled"
        row.claim_lease_expires_at = None
        row.version += 1
        return True

    def mark_sent(self, delivery_id: uuid.UUID, *, provider_message_id: str | None) -> None:
        row = self._lock(delivery_id)
        if row.status != "dispatching":
            return
        row.status = "sent"
        row.provider_message_id = (provider_message_id or "")[:256] or None
        row.claim_lease_expires_at = None
        row.version += 1

    def mark_unknown(self, delivery_id: uuid.UUID) -> None:
        row = self._lock(delivery_id)
        if row.status != "dispatching":
            return
        row.status = "delivery_unknown"
        row.claim_lease_expires_at = None
        row.version += 1

    def release_definite_pre_send_failure(
        self,
        delivery_id: uuid.UUID,
        *,
        max_attempts: int = 3,
    ) -> None:
        """Release only a sender-confirmed failure before provider dispatch."""

        row = self._lock(delivery_id)
        if row.status != "dispatching":
            return
        row.status = (
            "cancelled" if row.attempts >= max(1, max_attempts) else "pending"
        )
        row.claim_lease_expires_at = None
        row.claimed_at = None
        row.version += 1

    def recover_pre_send_claims(self, *, limit: int = 100) -> int:
        now = datetime.now(timezone.utc)
        rows = self.db.scalars(
            select(McpSurfaceDelivery)
            .where(
                McpSurfaceDelivery.status == "dispatching",
                McpSurfaceDelivery.claim_lease_expires_at < now,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        # Once a dispatching row may have reached the provider, retry is
        # ambiguous. The sender must explicitly return a definite pre-send
        # failure to reset it; a stale generic lease is always unknown.
        for row in rows:
            row.status = "delivery_unknown"
            row.claim_lease_expires_at = None
            row.version += 1
        return len(rows)

    def purge_terminal(self, *, limit: int = 100) -> int:
        """Hard-purge terminal encrypted segments after their bounded TTL.

        Ambiguous deliveries are deliberately retained until an operator
        reconciles them; once reconciled they become ``sent`` or ``cancelled``
        and are eligible on the next sweep. Pending-call revisions are retained
        as finalization proof and purged with their parent approval instead.
        """

        now = datetime.now(timezone.utc)
        ids = list(
            self.db.scalars(
                select(McpSurfaceDelivery.id)
                .where(
                    McpSurfaceDelivery.status.in_(("sent", "cancelled", "expired")),
                    McpSurfaceDelivery.delivery_deadline <= now,
                    # Pending-linked revisions are the durable proof that
                    # terminal approval finalization ran. Approval recovery
                    # removes both sides atomically after its longer TTL.
                    McpSurfaceDelivery.mcp_pending_tool_call_id.is_(None),
                )
                .order_by(McpSurfaceDelivery.delivery_deadline)
                .limit(max(1, min(int(limit), 500)))
                .with_for_update(skip_locked=True)
            ).all()
        )
        if not ids:
            return 0
        result = self.db.execute(
            delete(McpSurfaceDelivery).where(McpSurfaceDelivery.id.in_(ids))
        )
        return int(result.rowcount or 0)

    def _lock(self, delivery_id: uuid.UUID) -> McpSurfaceDelivery:
        row = self.db.scalar(
            select(McpSurfaceDelivery)
            .where(McpSurfaceDelivery.id == delivery_id)
            .with_for_update()
        )
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "MCP delivery not found.")
        return row

    def _existing_enqueue(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        surface_binding_id: uuid.UUID,
        pending_id: uuid.UUID | None,
        widget_instance_id: uuid.UUID | None,
        initiating_origin_digest: str | None,
        external_turn_handle_digest: str | None,
        external_principal_fingerprint: str | None,
        response_revision: int,
        bounded_segments: list[str],
    ) -> list[McpSurfaceDelivery]:
        identities = [
            McpSurfaceDelivery.assistant_message_id == assistant_message_id
        ]
        if widget_instance_id is not None:
            identities.append(
                (McpSurfaceDelivery.widget_instance_id == widget_instance_id)
                & (
                    McpSurfaceDelivery.initiating_origin_digest
                    == initiating_origin_digest
                )
                & (
                    McpSurfaceDelivery.external_turn_handle_digest
                    == external_turn_handle_digest
                )
            )
        rows = list(
            self.db.scalars(
                select(McpSurfaceDelivery)
                .where(
                    McpSurfaceDelivery.workspace_id == workspace_id,
                    McpSurfaceDelivery.response_revision == response_revision,
                    or_(*identities),
                )
                .order_by(McpSurfaceDelivery.segment_index)
                .with_for_update()
            ).all()
        )
        if not rows:
            return []
        if len(rows) != len(bounded_segments):
            raise AppError(
                ErrorCategory.CONFLICT,
                "The MCP external delivery identity already has different content.",
            )
        for index, (row, segment) in enumerate(zip(rows, bounded_segments, strict=True)):
            expected_hash = _delivery_content_hash(
                segment,
                external_principal_fingerprint,
            )
            try:
                _persisted_text, persisted_fingerprint = self.rendered_payload(row)
            except (AppError, TypeError, ValueError) as exc:
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "The MCP external delivery identity already has different content.",
                ) from exc
            if (
                row.conversation_id != conversation_id
                or row.assistant_message_id != assistant_message_id
                or row.mcp_tool_surface_binding_id != surface_binding_id
                or row.mcp_pending_tool_call_id != pending_id
                or row.widget_instance_id != widget_instance_id
                or row.initiating_origin_digest != initiating_origin_digest
                or row.external_turn_handle_digest != external_turn_handle_digest
                or persisted_fingerprint != external_principal_fingerprint
                or row.segment_index != index
                or row.content_hash != expected_hash
            ):
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "The MCP external delivery identity already has different content.",
                )
        return rows


def stale_widget_surface_bindings(db: Session, widget: WidgetInstance) -> None:
    acquire_surface_target_runtime_mutation_fences(
        db,
        workspace_id=widget.workspace_id,
        surface_target_keys=(f"widget:{widget.id}",),
    )
    locked_widget = db.scalar(
        select(WidgetInstance)
        .where(
            WidgetInstance.workspace_id == widget.workspace_id,
            WidgetInstance.id == widget.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_widget is None:
        raise AppError(ErrorCategory.NOT_FOUND, "Chat Widget target not found.")
    widget = locked_widget
    widget.mcp_source_epoch += 1
    widget.mcp_source_principal_fingerprint = _widget_source_fingerprint(widget)
    rows = db.scalars(
        select(McpToolSurfaceBinding)
        .where(
            McpToolSurfaceBinding.workspace_id == widget.workspace_id,
            McpToolSurfaceBinding.widget_instance_id == widget.id,
            McpToolSurfaceBinding.state == "active",
        )
        .with_for_update()
    ).all()
    for row in rows:
        row.state = "stale_source"


def stale_channel_surface_bindings(
    db: Session,
    channel: ChannelBinding,
    connection: AppConnection,
) -> None:
    acquire_surface_target_runtime_mutation_fences(
        db,
        workspace_id=channel.workspace_id,
        surface_target_keys=(f"whatsapp:{connection.id}:{channel.id}",),
    )
    locked_channel = db.scalar(
        select(ChannelBinding)
        .where(
            ChannelBinding.workspace_id == channel.workspace_id,
            ChannelBinding.id == channel.id,
            ChannelBinding.app_connection_id == connection.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked_connection = db.scalar(
        select(AppConnection)
        .where(
            AppConnection.workspace_id == channel.workspace_id,
            AppConnection.id == connection.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_channel is None or locked_connection is None:
        raise AppError(ErrorCategory.NOT_FOUND, "WhatsApp target not found.")
    channel = locked_channel
    connection = locked_connection
    channel.mcp_source_epoch += 1
    channel.mcp_source_principal_fingerprint = _channel_source_fingerprint(
        channel, connection
    )
    rows = db.scalars(
        select(McpToolSurfaceBinding)
        .where(
            McpToolSurfaceBinding.workspace_id == channel.workspace_id,
            McpToolSurfaceBinding.channel_binding_id == channel.id,
            McpToolSurfaceBinding.state == "active",
        )
        .with_for_update()
    ).all()
    for row in rows:
        row.state = "stale_source"


def _lock_exact_grant(
    db: Session,
    workspace_id: uuid.UUID,
    expert_id: uuid.UUID,
    grant_id: uuid.UUID,
) -> tuple[McpToolGrant, McpServerTool, AppConnection]:
    row = db.execute(
        select(McpToolGrant, McpServerTool, AppConnection)
        .join(
            McpServerTool,
            (McpServerTool.workspace_id == McpToolGrant.workspace_id)
            & (McpServerTool.id == McpToolGrant.mcp_server_tool_id)
            & (McpServerTool.app_connection_id == McpToolGrant.app_connection_id),
        )
        .join(
            AppConnection,
            (AppConnection.workspace_id == McpToolGrant.workspace_id)
            & (AppConnection.id == McpToolGrant.app_connection_id),
        )
        .where(
            McpToolGrant.workspace_id == workspace_id,
            McpToolGrant.expert_id == expert_id,
            McpToolGrant.id == grant_id,
        )
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "MCP tool grant not found.")
    return row


def _grant_is_current(
    grant: McpToolGrant,
    tool: McpServerTool,
    connection: AppConnection,
    *,
    now: datetime,
    settings: Settings,
) -> bool:
    refreshed_at = connection.mcp_inventory_refreshed_at
    return bool(
        grant.state == McpGrantState.ACTIVE.value
        and tool.status == McpToolStatus.ACTIVE.value
        and tool.compatibility_status == McpCompatibilityStatus.COMPATIBLE.value
        and tool.classification
        in {McpToolClassification.READ_ONLY.value, McpToolClassification.WRITE.value}
        and not (
            tool.classification == McpToolClassification.READ_ONLY.value
            and annotations_forbid_read_only(getattr(tool, "annotations", None))
        )
        and grant.approved_definition_hash == tool.definition_hash
        and grant.approved_classification == tool.classification
        and grant.approved_principal_fingerprint
        == connection.mcp_principal_fingerprint
        and grant.approved_credential_epoch == connection.mcp_credential_epoch
        and connection.status in CONNECTION_USABLE_STATUSES
        and connection.health != ConnectionHealth.FAILED.value
        and not connection.mcp_reauthorization_required
        and refreshed_at is not None
        and refreshed_at
        >= now
        - timedelta(seconds=int(settings.mcp_tool_inventory_ttl_seconds))
    )


def _surface_allows_tool(
    surface: McpToolSurfaceBinding, tool: McpServerTool
) -> bool:
    return bool(
        tool.classification != McpToolClassification.WRITE.value
        or surface.write_policy == "workspace_operator_approval"
    )


def _widget_principal_matches(
    invocation: ChatInvocationContext,
    widget: WidgetInstance,
    binding: WidgetConversationBinding,
    *,
    settings: Settings,
) -> bool:
    supplied = invocation.external_principal_fingerprint or ""
    try:
        expected = widget_external_principal_fingerprint(
            binding.session_id,
            widget_id=widget.id,
            secret=settings.jwt_secret,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(supplied, expected)


def _channel_principal_matches(
    invocation: ChatInvocationContext,
    binding: ChannelConversationBinding,
    *,
    settings: Settings,
) -> bool:
    if invocation.connection_id is None:
        return False
    supplied = invocation.external_principal_fingerprint or ""
    try:
        expected = channel_external_principal_fingerprint(
            external_chat_id=binding.external_chat_id,
            external_sender_id=binding.external_sender_id,
            workspace_id=invocation.workspace_id,
            connection_id=invocation.connection_id,
            binding_id=binding.id,
            secret=settings.jwt_secret,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(supplied, expected)


def _provider_schema(tool: McpServerTool) -> dict[str, Any]:
    function: dict[str, Any] = {
        "name": tool.llm_tool_name,
        "parameters": dict(tool.input_schema or {}),
    }
    description = (tool.description or tool.title or "").strip()
    if tool.classification == McpToolClassification.WRITE.value:
        guidance = (
            "WRITE TOOL. Select only when the latest user request explicitly "
            "asks to change external data; never use it to gather evidence."
        )
    else:
        guidance = "READ-ONLY TOOL. Use only to retrieve evidence."
    function["description"] = f"{guidance} {description}".strip()
    return {"type": "function", "function": function}


def _source_app_slug(surface_kind: str) -> str:
    return CHAT_WIDGET_APP_SLUG if surface_kind == "chat_widget" else WHATSAPP_APP_SLUG


def _target_key(
    surface_kind: str,
    widget_id: uuid.UUID | None,
    channel_binding_id: uuid.UUID | None,
    *,
    channel_connection_id: uuid.UUID | None = None,
) -> str:
    if surface_kind == "chat_widget" and widget_id:
        return f"widget:{widget_id}"
    if (
        surface_kind == "whatsapp_openwa"
        and channel_binding_id
        and channel_connection_id
    ):
        return f"whatsapp:{channel_connection_id}:{channel_binding_id}"
    raise AppError(ErrorCategory.VALIDATION, "An exact MCP surface target is required.")


def _channel_binding_id_for_connection(
    db: Session, workspace_id: uuid.UUID, connection_id: uuid.UUID | None
) -> uuid.UUID | None:
    if connection_id is None:
        return None
    return db.scalar(
        select(ChannelBinding.id).where(
            ChannelBinding.workspace_id == workspace_id,
            ChannelBinding.app_connection_id == connection_id,
        )
    )


def _widget_origins(widget: WidgetInstance) -> list[str]:
    raw = widget.allowed_origins if isinstance(widget.allowed_origins, list) else []
    result: list[str] = []
    for value in raw:
        try:
            origin = normalize_origin(str(value))
        except ValueError:
            continue
        if origin.startswith("https://") and origin not in result:
            result.append(origin)
    return sorted(result)


def _widget_config_hash(widget: WidgetInstance) -> str:
    return _digest_json(
        {
            "widget_id": str(widget.id),
            "expert_id": str(widget.expert_id) if widget.expert_id else None,
            "status": widget.status,
            "allowed_origins": _widget_origins(widget),
        }
    )


def _widget_source_fingerprint(widget: WidgetInstance) -> str:
    return _digest_json(
        {"widget_id": str(widget.id), "audience": _widget_config_hash(widget)}
    )


def _channel_config_hash(channel: ChannelBinding, connection: AppConnection) -> str:
    return _digest_json(
        {
            "channel_binding_id": str(channel.id),
            "connection_id": str(connection.id),
            "expert_id": str(channel.expert_id) if channel.expert_id else None,
            "enabled": bool(channel.enabled),
            "auto_reply_enabled": bool(channel.auto_reply_enabled),
            "respond_to_groups": bool(channel.respond_to_groups),
            "connection_status": connection.status,
        }
    )


def _channel_source_fingerprint(
    channel: ChannelBinding, connection: AppConnection
) -> str:
    return _digest_json(
        {
            "connection_id": str(connection.id),
            "external_account_id": connection.external_account_id,
            "channel": _channel_config_hash(channel, connection),
        }
    )


def _digest_json(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _delivery_content_hash(
    text: str,
    external_principal_fingerprint: str | None,
) -> str:
    """Bind immutable rendered bytes to their server-keyed recipient digest."""

    encoded = json.dumps(
        {
            "external_principal_fingerprint": external_principal_fingerprint,
            "text": text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256_digest(value: str | None, label: str) -> str:
    normalized = (value or "").strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise AppError(
            ErrorCategory.VALIDATION,
            f"A valid {label} digest is required.",
        )
    return normalized


def _surface_label(db: Session, surface: McpToolSurfaceBinding) -> str:
    if surface.widget_instance_id:
        return str(
            db.scalar(
                select(WidgetInstance.title).where(
                    WidgetInstance.id == surface.widget_instance_id
                )
            )
            or "Chat Widget"
        )
    return str(
        db.scalar(
            select(AppConnection.display_name)
            .join(ChannelBinding, ChannelBinding.app_connection_id == AppConnection.id)
            .where(ChannelBinding.id == surface.channel_binding_id)
        )
        or "WhatsApp"
    )


def _safe_external_sender_label(
    pending: McpPendingToolCall,
    surface: McpToolSurfaceBinding,
) -> str:
    """Return stable operator context without exposing a raw external identity.

    ``external_principal_fingerprint`` is the immutable server-keyed digest
    bound to the originating Widget audience/session or WhatsApp chat/sender.
    A short alias is safe to correlate in the approval queue and cannot be
    reversed without Geem's secret.  Never consult the mutable channel sender
    row here: after a sender/session change that could label an old approval as
    belonging to a different current principal (the resume gate rejects it).
    """

    prefix = (
        "Widget visitor"
        if surface.surface_kind == "chat_widget"
        else "WhatsApp sender"
    )
    fingerprint = str(pending.external_principal_fingerprint or "").strip().lower()
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        return prefix
    return f"{prefix} · {fingerprint[:8]}"


def _enqueue_resume_after_commit(pending_id: uuid.UUID) -> None:
    try:
        from app.worker.tasks import resume_mcp_pending_tool_call

        resume_mcp_pending_tool_call.delay(str(pending_id))
    except Exception:
        # The committed approved row is authoritative; the recovery sweep will
        # enqueue the same ID-only task. Never roll back a human decision.
        return


__all__ = [
    "McpApprovalListOut",
    "McpDecisionIn",
    "McpDeliveryListOut",
    "McpDeliveryReconcileIn",
    "McpExternalOperationsService",
    "McpSurfaceBindingCreateIn",
    "McpSurfaceBindingOut",
    "McpSurfaceBindingService",
    "McpSurfaceOutboxService",
    "McpSurfaceResolver",
    "McpUsageOut",
    "ResolvedSurfaceMcpTool",
    "stale_channel_surface_bindings",
    "stale_widget_surface_bindings",
]
