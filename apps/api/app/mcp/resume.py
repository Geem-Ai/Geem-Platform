"""ID-only MCP approval resume and terminal external delivery orchestration."""

from __future__ import annotations

import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.schemas import AgentFunctionCall, AgentToolCall
from app.common.crypto import decrypt_json
from app.connectors.models import ChannelBinding, ChannelConversationBinding
from app.connectors.providers.openwa.text import split_whatsapp_text
from app.conversations.invocation import ChatInvocationContext
from app.conversations.locks import ConversationGenerationLock
from app.conversations.models import Conversation, Message, MessageStatus
from app.conversations.repository import ConversationRepository
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.experts.query_service import ExpertQueryService
from app.mcp.approvals import McpApprovalService
from app.mcp.executor import ToolLoopTurnExecutor, _validate_arguments
from app.mcp.public_tokens import origin_digest as keyed_origin_digest
from app.mcp.resolver import McpGrantResolver
from app.mcp.runtime_models import (
    McpPendingToolCall,
    McpSurfaceDelivery,
    McpToolSurfaceBinding,
    McpWidgetTurnReceipt,
)
from app.mcp.surfaces import McpSurfaceOutboxService, McpSurfaceResolver
from app.usage.metered import MeteredWorkspaceGeneration
from app.widgets.models import WidgetConversationBinding, WidgetInstance
from app.widgets.origins import normalize_origin
from app.workspaces.models import Workspace
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import has_permission
from app.workspaces.repository import MembershipRepository


class McpPendingResumeService:
    """Resume an approved row once, with a durable pre-dispatch marker."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def resume(self, pending_id: uuid.UUID) -> dict[str, Any]:
        """Re-acquire the originating conversation/surface lock before claiming.

        Human approval deliberately releases this lock.  Keeping the row in
        ``approved`` when the lock is busy lets the recovery sweep retry the
        stable ID without ever moving the approval into an executing state.
        """

        pending = self.db.get(McpPendingToolCall, pending_id)
        if pending is None:
            return {"status": "missing"}
        lock_id = self._resume_lock_id(pending)
        lock = ConversationGenerationLock(settings=self.settings)
        if not lock.acquire(lock_id):
            return {"status": "busy"}
        try:
            return self._resume_locked(pending_id)
        finally:
            lock.release(lock_id)

    def _resume_locked(self, pending_id: uuid.UUID) -> dict[str, Any]:
        identity = self.db.execute(
            select(McpPendingToolCall.workspace_id).where(
                McpPendingToolCall.id == pending_id
            )
        ).scalar_one_or_none()
        if identity is None:
            return {"status": "missing"}
        claimed = McpApprovalService(self.db, self.settings).claim_resume(
            workspace_id=identity,
            pending_id=pending_id,
        )
        self.db.commit()
        if claimed is None:
            current = self.db.get(McpPendingToolCall, pending_id)
            return {"status": current.status if current is not None else "missing"}
        if not claimed.arguments_encrypted or not claimed.loop_state_encrypted:
            return self._cancel_pre_dispatch(identity, pending_id)
        if not self._decision_actor_is_current(claimed):
            # Approval is authority at decision time, not a durable delegation.
            # Membership removal or permission downgrade during the human pause
            # must terminate the write before any model/provider/gateway egress.
            return self._cancel_pre_dispatch(identity, pending_id)

        arguments = decrypt_json(claimed.arguments_encrypted, settings=self.settings)
        loop_state = decrypt_json(claimed.loop_state_encrypted, settings=self.settings)
        if not isinstance(arguments, dict) or not isinstance(loop_state, dict):
            return self._cancel_pre_dispatch(identity, pending_id)
        conversation = self.db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == claimed.workspace_id,
                Conversation.id == claimed.conversation_id,
            )
        )
        assistant = self.db.scalar(
            select(Message).where(
                Message.conversation_id == claimed.conversation_id,
                Message.id == claimed.message_id,
            )
        )
        workspace = self.db.get(Workspace, claimed.workspace_id)
        if conversation is None or assistant is None or workspace is None:
            return self._cancel_pre_dispatch(identity, pending_id)
        user_message = ConversationRepository(self.db).find_preceding_user_message(
            conversation.id,
            assistant,
        )
        if user_message is None:
            return self._cancel_pre_dispatch(identity, pending_id)

        invocation = self._invocation(claimed, conversation)
        query = ExpertQueryService(self.db, self.settings)
        knowledge = query.resolve_knowledge_for_workspace(
            workspace=workspace,
            expert_id=conversation.expert_id,
            actor_id=claimed.initiated_by_user_id,
        )
        if claimed.mcp_tool_surface_binding_id is None:
            candidates = McpGrantResolver(self.db, settings=self.settings).resolve(
                invocation,
                conversation.expert_id,
            )
        else:
            candidates = McpSurfaceResolver(self.db, self.settings).resolve(
                invocation,
                conversation.expert_id,
            )
        resolved = next(
            (row for row in candidates if row.grant.id == claimed.mcp_tool_grant_id),
            None,
        )
        if resolved is None or not self._loop_state_matches(
            claimed, loop_state, resolved, invocation
        ):
            return self._cancel_pre_dispatch(identity, pending_id)
        validated_arguments = _validate_arguments(arguments, resolved.tool.input_schema)
        tool_call = AgentToolCall(
            id=claimed.model_tool_call_id,
            type="function",
            function=AgentFunctionCall(
                name=resolved.tool.llm_tool_name,
                arguments=json.dumps(
                    validated_arguments,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ),
            ),
        )
        history = [
            {"role": row.role, "content": row.content or ""}
            for row in ConversationRepository(self.db).list_history_for_rag(
                conversation.id,
                before_message_id=user_message.id,
                limit=max(0, int(self.settings.chat_history_max_messages)),
            )
            if (row.content or "").strip()
        ]
        meter = MeteredWorkspaceGeneration(
            self.db,
            workspace_id=claimed.workspace_id,
            user_id=claimed.initiated_by_user_id,
            expert_id=conversation.expert_id,
            conversation_id=conversation.id,
            message_id=assistant.id,
            request_id=f"mcp-resume:{pending_id}",
            reservation_multiplier=1,
            settings=self.settings,
        )
        dispatch_confirmed = False

        def finish_confirmed_dispatch() -> None:
            nonlocal dispatch_confirmed
            self._finish_approval(
                claimed.workspace_id,
                pending_id,
                outcome_unknown=False,
            )
            dispatch_confirmed = True

        try:
            meter.reserve()
            loop = ToolLoopTurnExecutor(
                self.db,
                settings=self.settings,
                rag=query._rag,
            ).resume_after_approved_write(
                knowledge=knowledge,
                expert_id=conversation.expert_id,
                question=user_message.content,
                invocation=invocation,
                usage_context=meter.context(),
                resolved=resolved,
                tool_call=tool_call,
                arguments=validated_arguments,
                loop_state=loop_state,
                history=history,
                before_gateway=lambda: self._mark_dispatch(
                    claimed.workspace_id,
                    pending_id,
                ),
                after_gateway=finish_confirmed_dispatch,
            )
            meter.settle(loop.as_payload())
            now = datetime.now(timezone.utc)
            assistant.content = loop.answer
            assistant.citations = loop.citations
            assistant.status = MessageStatus.COMPLETED.value
            assistant.updated_at = now
            conversation.updated_at = now
            delivery_ids = self._finish_external(
                claimed=claimed,
                assistant=assistant,
                answer=loop.answer,
            )
            self.db.commit()
            self._enqueue_deliveries(delivery_ids)
            return {"status": "executed", "deliveries": len(delivery_ids)}
        except AppError as exc:
            if not meter.closed:
                meter.release()
            if dispatch_confirmed:
                return self._confirmed_dispatch_synthesis_failure(
                    workspace_id=claimed.workspace_id,
                    pending_id=pending_id,
                    message_id=claimed.message_id,
                    conversation_id=claimed.conversation_id,
                )
            self._terminal_failure(
                claimed.workspace_id,
                pending_id,
                assistant=assistant,
                conversation=conversation,
                force_unknown=(exc.category == ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN),
            )
            return {
                "status": (
                    "outcome_unknown"
                    if exc.category == ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
                    else "denied"
                )
            }
        except Exception:  # noqa: BLE001
            if not meter.closed:
                meter.release()
            if dispatch_confirmed:
                return self._confirmed_dispatch_synthesis_failure(
                    workspace_id=claimed.workspace_id,
                    pending_id=pending_id,
                    message_id=claimed.message_id,
                    conversation_id=claimed.conversation_id,
                )
            self._terminal_failure(
                claimed.workspace_id,
                pending_id,
                assistant=assistant,
                conversation=conversation,
                force_unknown=False,
            )
            return {"status": "failed"}

    def _confirmed_dispatch_synthesis_failure(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        message_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Materialize a safe terminal response after a confirmed write.

        The remote result already returned and the approval row was durably
        marked ``executed``.  A later model/persistence failure is therefore
        not an ambiguous tool outcome and must never become eligible for
        redispatch.  External surfaces receive one idempotent final revision
        containing no arguments, result content, citations, or tool identity.
        """

        try:
            self.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        pending = self.db.scalar(
            select(McpPendingToolCall).where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.id == pending_id,
                McpPendingToolCall.status == "executed",
            )
        )
        assistant = self.db.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.id == message_id,
            )
        )
        conversation = self.db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.id == conversation_id,
            )
        )
        if pending is None or assistant is None or conversation is None:
            return {"status": "failed"}

        text = "The approved tool completed, but a final answer could not be generated."
        now = datetime.now(timezone.utc)
        assistant.content = text
        assistant.citations = []
        assistant.status = MessageStatus.FAILED.value
        assistant.updated_at = now
        conversation.updated_at = now

        delivery_ids: list[uuid.UUID] = []
        if pending.mcp_tool_surface_binding_id is not None:
            surface = self.db.get(
                McpToolSurfaceBinding,
                pending.mcp_tool_surface_binding_id,
            )
            if surface is not None and surface.surface_kind == "chat_widget":
                receipt = self.db.scalar(
                    select(McpWidgetTurnReceipt).where(
                        McpWidgetTurnReceipt.workspace_id == workspace_id,
                        McpWidgetTurnReceipt.assistant_message_id == assistant.id,
                    )
                )
                if receipt is not None:
                    receipt.status = "failed"
            elif surface is not None and surface.surface_kind == "whatsapp_openwa":
                rows = McpSurfaceOutboxService(
                    self.db,
                    self.settings,
                ).enqueue(
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    assistant_message_id=assistant.id,
                    surface_binding_id=surface.id,
                    rendered_segments=split_whatsapp_text(text),
                    pending_id=pending.id,
                    external_principal_fingerprint=(
                        pending.external_principal_fingerprint
                    ),
                    response_revision=2,
                )
                delivery_ids = [row.id for row in rows]
        self.db.commit()
        self._enqueue_deliveries(delivery_ids)
        return {"status": "failed", "deliveries": len(delivery_ids)}

    def _resume_lock_id(self, pending: McpPendingToolCall) -> uuid.UUID:
        """Rebuild the exact lock identity used by the originating surface."""

        if pending.mcp_tool_surface_binding_id is None:
            return pending.conversation_id
        surface = self.db.get(
            McpToolSurfaceBinding,
            pending.mcp_tool_surface_binding_id,
        )
        if surface is None:
            return pending.conversation_id
        if surface.surface_kind == "chat_widget" and surface.widget_instance_id:
            binding = self.db.scalar(
                select(WidgetConversationBinding).where(
                    WidgetConversationBinding.workspace_id == pending.workspace_id,
                    WidgetConversationBinding.widget_instance_id
                    == surface.widget_instance_id,
                    WidgetConversationBinding.conversation_id
                    == pending.conversation_id,
                )
            )
            if binding is not None:
                try:
                    session_id = uuid.UUID(str(binding.session_id))
                except (TypeError, ValueError):
                    return pending.conversation_id
                return uuid.uuid5(
                    surface.widget_instance_id,
                    f"mcp:{session_id}:{binding.expert_id}",
                )
        if surface.surface_kind == "whatsapp_openwa" and surface.channel_binding_id:
            channel = self.db.get(ChannelBinding, surface.channel_binding_id)
            if channel is not None:
                binding = self.db.scalar(
                    select(ChannelConversationBinding).where(
                        ChannelConversationBinding.workspace_id == pending.workspace_id,
                        ChannelConversationBinding.app_connection_id
                        == channel.app_connection_id,
                        ChannelConversationBinding.conversation_id
                        == pending.conversation_id,
                    )
                )
                if binding is not None:
                    namespace = uuid.uuid5(
                        pending.workspace_id,
                        str(channel.app_connection_id),
                    )
                    return uuid.uuid5(namespace, binding.external_chat_id)
        # Broken source coordinates are cancelled by the current-state checks,
        # but still serialize against the canonical conversation as fail-safe.
        return pending.conversation_id

    def fail_unhandled(self, pending_id: uuid.UUID) -> str:
        """Crash boundary for failures before the main resume try block."""

        pending = self.db.get(McpPendingToolCall, pending_id)
        if pending is None:
            return "missing"
        if pending.status != "executing":
            return pending.status
        marker = pending.gateway_dispatch_started_at is not None
        if marker:
            self._finish_approval(
                pending.workspace_id,
                pending.id,
                outcome_unknown=True,
            )
            status = "outcome_unknown"
        else:
            self._cancel_pre_dispatch(pending.workspace_id, pending.id)
            status = "denied"
        assistant = self.db.get(Message, pending.message_id)
        conversation = self.db.get(Conversation, pending.conversation_id)
        if assistant is not None and conversation is not None:
            self._terminal_failure(
                pending.workspace_id,
                pending.id,
                assistant=assistant,
                conversation=conversation,
                force_unknown=marker,
            )
        return status

    def finalize_terminal(self, pending_id: uuid.UUID) -> bool:
        """Materialize a safe terminal answer/follow-up for a scrubbed row."""

        pending = self.db.get(McpPendingToolCall, pending_id)
        if pending is None or pending.status not in {
            "denied",
            "expired",
            "outcome_unknown",
        }:
            return False
        assistant = self.db.scalar(
            select(Message).where(
                Message.conversation_id == pending.conversation_id,
                Message.id == pending.message_id,
            )
        )
        conversation = self.db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == pending.workspace_id,
                Conversation.id == pending.conversation_id,
            )
        )
        if assistant is None or conversation is None:
            return False
        text = {
            "denied": "This tool request was not approved.",
            "expired": "This tool request expired before approval.",
            "outcome_unknown": "The tool outcome could not be confirmed.",
        }[pending.status]
        changed = bool(
            assistant.status != MessageStatus.FAILED.value
            or assistant.content != text
            or assistant.citations
        )
        if changed:
            now = datetime.now(timezone.utc)
            assistant.content = text
            assistant.citations = []
            assistant.status = MessageStatus.FAILED.value
            assistant.updated_at = now
            conversation.updated_at = now

        delivery_ids: list[uuid.UUID] = []
        if pending.mcp_tool_surface_binding_id is not None:
            surface = self.db.get(
                McpToolSurfaceBinding, pending.mcp_tool_surface_binding_id
            )
            if surface is not None and surface.surface_kind == "chat_widget":
                receipt = self.db.scalar(
                    select(McpWidgetTurnReceipt).where(
                        McpWidgetTurnReceipt.workspace_id == pending.workspace_id,
                        McpWidgetTurnReceipt.assistant_message_id == assistant.id,
                    )
                )
                if receipt is not None:
                    next_status = (
                        "outcome_unknown"
                        if pending.status == "outcome_unknown"
                        else "failed"
                    )
                    changed = changed or receipt.status != next_status
                    receipt.status = next_status
            elif surface is not None and surface.surface_kind == "whatsapp_openwa":
                existing = self.db.scalar(
                    select(McpSurfaceDelivery.id).where(
                        McpSurfaceDelivery.workspace_id == pending.workspace_id,
                        McpSurfaceDelivery.assistant_message_id == assistant.id,
                        McpSurfaceDelivery.response_revision == 2,
                    )
                )
                if existing is None:
                    rows = McpSurfaceOutboxService(
                        self.db, self.settings
                    ).enqueue(
                        workspace_id=pending.workspace_id,
                        conversation_id=pending.conversation_id,
                        assistant_message_id=assistant.id,
                        surface_binding_id=surface.id,
                        rendered_segments=split_whatsapp_text(text),
                        pending_id=pending.id,
                        external_principal_fingerprint=(
                            pending.external_principal_fingerprint
                        ),
                        response_revision=2,
                    )
                    delivery_ids = [row.id for row in rows]
                    changed = changed or bool(rows)
        self.db.commit()
        self._enqueue_deliveries(delivery_ids)
        return changed

    def _invocation(
        self,
        pending: McpPendingToolCall,
        conversation: Conversation,
    ) -> ChatInvocationContext:
        if pending.mcp_tool_surface_binding_id is None:
            if pending.initiated_by_user_id is None:
                raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "Approval actor is missing.")
            return ChatInvocationContext.workspace_user(
                workspace_id=pending.workspace_id,
                user_id=pending.initiated_by_user_id,
                expert_id=conversation.expert_id,
                conversation_id=conversation.id,
                message_id=pending.message_id,
                request_id=str(pending.message_id),
            )
        surface = self.db.get(
            McpToolSurfaceBinding,
            pending.mcp_tool_surface_binding_id,
        )
        if surface is None or surface.state != "active":
            raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "MCP surface is inactive.")
        if surface.surface_kind == "chat_widget":
            widget = self.db.get(WidgetInstance, surface.widget_instance_id)
            binding = self.db.scalar(
                select(WidgetConversationBinding).where(
                    WidgetConversationBinding.workspace_id == pending.workspace_id,
                    WidgetConversationBinding.widget_instance_id == surface.widget_instance_id,
                    WidgetConversationBinding.conversation_id == conversation.id,
                    WidgetConversationBinding.expert_id == conversation.expert_id,
                )
            )
            origin = self._widget_origin(widget, pending.initiating_origin_digest)
            if widget is None or binding is None or origin is None:
                raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "Widget surface changed.")
            return ChatInvocationContext.widget(
                workspace_id=pending.workspace_id,
                widget_id=widget.id,
                expert_id=conversation.expert_id,
                conversation_id=conversation.id,
                message_id=pending.message_id,
                request_id=str(pending.message_id),
                source_binding_id=binding.id,
                external_principal_fingerprint=pending.external_principal_fingerprint,
                initiating_origin=origin,
                external_turn_handle_digest=pending.external_turn_handle_digest,
            )
        channel = self.db.get(ChannelBinding, surface.channel_binding_id)
        if channel is None:
            raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "WhatsApp surface changed.")
        binding = self.db.scalar(
            select(ChannelConversationBinding).where(
                ChannelConversationBinding.workspace_id == pending.workspace_id,
                ChannelConversationBinding.app_connection_id == channel.app_connection_id,
                ChannelConversationBinding.conversation_id == conversation.id,
                ChannelConversationBinding.expert_id == conversation.expert_id,
            )
        )
        if binding is None:
            raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "WhatsApp surface changed.")
        return ChatInvocationContext.channel(
            workspace_id=pending.workspace_id,
            connection_id=channel.app_connection_id,
            expert_id=conversation.expert_id,
            conversation_id=conversation.id,
            message_id=pending.message_id,
            request_id=str(pending.message_id),
            source_binding_id=binding.id,
            external_principal_fingerprint=pending.external_principal_fingerprint,
        )

    def _finish_external(
        self,
        *,
        claimed: McpPendingToolCall,
        assistant: Message,
        answer: str,
    ) -> list[uuid.UUID]:
        if claimed.mcp_tool_surface_binding_id is None:
            return []
        surface = self.db.get(
            McpToolSurfaceBinding,
            claimed.mcp_tool_surface_binding_id,
        )
        if surface is None:
            return []
        if surface.surface_kind == "chat_widget":
            receipt = self.db.scalar(
                select(McpWidgetTurnReceipt).where(
                    McpWidgetTurnReceipt.workspace_id == claimed.workspace_id,
                    McpWidgetTurnReceipt.assistant_message_id == assistant.id,
                    McpWidgetTurnReceipt.initiating_origin_digest
                    == claimed.initiating_origin_digest,
                    McpWidgetTurnReceipt.external_turn_handle_digest
                    == claimed.external_turn_handle_digest,
                )
            )
            if receipt is not None:
                receipt.status = "completed"
            return []
        segments = split_whatsapp_text(answer) if answer else []
        rows = McpSurfaceOutboxService(self.db, self.settings).enqueue(
            workspace_id=claimed.workspace_id,
            conversation_id=claimed.conversation_id,
            assistant_message_id=assistant.id,
            surface_binding_id=surface.id,
            rendered_segments=segments,
            pending_id=claimed.id,
            external_principal_fingerprint=(
                claimed.external_principal_fingerprint
            ),
            response_revision=2,
        )
        return [row.id for row in rows]

    def _decision_actor_is_current(self, pending: McpPendingToolCall) -> bool:
        """Recheck the exact human decision authority after the pause."""

        actor_id = pending.decided_by_user_id
        if actor_id is None:
            return False
        membership = MembershipRepository(self.db).get(
            pending.workspace_id,
            actor_id,
        )
        if membership is None:
            return False
        if pending.mcp_tool_surface_binding_id is not None:
            required = WorkspacePermission.MCP_TOOLS_APPROVE_EXTERNAL
        else:
            if pending.initiated_by_user_id != actor_id:
                return False
            required = WorkspacePermission.CHAT_USE
        return has_permission(membership, required)

    @staticmethod
    def _loop_state_matches(pending, state, resolved, invocation) -> bool:
        return all(
            (
                str(state.get("grant_id") or "") == str(pending.mcp_tool_grant_id),
                str(state.get("grant_id") or "") == str(resolved.grant.id),
                str(state.get("tool_id") or "") == str(resolved.tool.id),
                str(state.get("connection_id") or "") == str(resolved.connection.id),
                str(state.get("surface_binding_id") or "")
                == (
                    str(pending.mcp_tool_surface_binding_id)
                    if pending.mcp_tool_surface_binding_id is not None
                    else ""
                ),
                str(state.get("invocation_source") or "") == invocation.source,
                str(state.get("request_id") or "")
                == str(invocation.request_id or ""),
            )
        )

    def _widget_origin(
        self,
        widget: WidgetInstance | None,
        digest: str | None,
    ) -> str | None:
        if widget is None or not digest or not isinstance(widget.allowed_origins, list):
            return None
        for raw in widget.allowed_origins:
            try:
                origin = normalize_origin(str(raw))
            except ValueError:
                continue
            candidate = keyed_origin_digest(origin, secret=self.settings.jwt_secret)
            if hmac.compare_digest(candidate, digest):
                return origin
        return None

    def _mark_dispatch(self, workspace_id: uuid.UUID, pending_id: uuid.UUID) -> None:
        db = SessionLocal()
        try:
            McpApprovalService(db, self.settings).mark_gateway_dispatch_started(
                workspace_id=workspace_id,
                pending_id=pending_id,
            )
            db.commit()
        finally:
            db.close()

    def _finish_approval(
        self,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        *,
        outcome_unknown: bool,
    ) -> None:
        db = SessionLocal()
        try:
            McpApprovalService(db, self.settings).finish_execution(
                workspace_id=workspace_id,
                pending_id=pending_id,
                outcome_unknown=outcome_unknown,
            )
            db.commit()
        finally:
            db.close()

    def _cancel_pre_dispatch(
        self,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
    ) -> dict[str, str]:
        db = SessionLocal()
        try:
            McpApprovalService(db, self.settings).cancel_before_dispatch(
                workspace_id=workspace_id,
                pending_id=pending_id,
            )
            db.commit()
        finally:
            db.close()
        return {"status": "denied"}

    def _terminal_failure(
        self,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        *,
        assistant: Message,
        conversation: Conversation,
        force_unknown: bool,
    ) -> None:
        marker = self.db.scalar(
            select(McpPendingToolCall.gateway_dispatch_started_at).where(
                McpPendingToolCall.id == pending_id,
                McpPendingToolCall.workspace_id == workspace_id,
            )
        )
        unknown = bool(force_unknown or marker is not None)
        try:
            if unknown:
                self._finish_approval(workspace_id, pending_id, outcome_unknown=True)
            else:
                self._cancel_pre_dispatch(workspace_id, pending_id)
        except AppError:
            # A successful after-gateway callback may already have made the
            # approval terminal; never overwrite that monotonic state.
            pass
        now = datetime.now(timezone.utc)
        assistant.content = (
            "The tool outcome could not be confirmed."
            if unknown
            else "This request could not be completed."
        )
        assistant.citations = []
        assistant.status = MessageStatus.FAILED.value
        assistant.updated_at = now
        conversation.updated_at = now
        widget_receipt = self.db.scalar(
            select(McpWidgetTurnReceipt).where(
                McpWidgetTurnReceipt.assistant_message_id == assistant.id
            )
        )
        if widget_receipt is not None:
            widget_receipt.status = "outcome_unknown" if unknown else "failed"
        self.db.commit()

    @staticmethod
    def _enqueue_deliveries(delivery_ids: list[uuid.UUID]) -> None:
        if not delivery_ids:
            return
        try:
            from app.worker.tasks import deliver_mcp_surface_segment

            for delivery_id in delivery_ids:
                deliver_mcp_surface_segment.delay(str(delivery_id))
        except Exception:
            # Beat recovery claims committed pending rows.
            return


__all__ = ["McpPendingResumeService"]
