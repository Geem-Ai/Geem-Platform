"""OpenWA inbound message processor."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.connectors.models import (
    AppConnection,
    ChannelBinding,
    ChannelConversationBinding,
)
from app.connectors.providers.openwa.client import OpenWAClient
from app.connectors.providers.openwa.service import APP_SLUG_DEFAULT, OpenWAChannelService
from app.connectors.providers.openwa.text import split_whatsapp_text
from app.connectors.repository import ConnectorRepository
from app.connectors.service import ConnectorConnectionService
from app.connectors.types import ConnectionStatus
from app.conversations.invocation import ChatInvocationContext
from app.conversations.locks import ConversationGenerationLock
from app.conversations.models import (
    Conversation,
    ConversationSource,
    Message,
    MessageRole,
    MessageStatus,
)
from app.conversations.repository import ConversationRepository
from app.conversations.turn import ChatTurnExecutor
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.access import ExpertAccessService
from app.experts.policy import ExpertAction
from app.mcp.approvals import McpApprovalService
from app.mcp.public_tokens import channel_external_principal_fingerprint
from app.mcp.runtime_models import McpPendingToolCall, McpSurfaceDelivery
from app.mcp.surfaces import McpSurfaceOutboxService
from app.usage.metered import MeteredWorkspaceGeneration
from app.workspaces.models import Workspace


class OpenWAChannelProcessor:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        client_factory: type[OpenWAClient] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = ConnectorRepository(db)
        self.connections = ConnectorConnectionService(db)
        self.access = AppAccessService(db)
        self.experts = ExpertAccessService(db)
        self.conversations = ConversationRepository(db)
        self.executor = ChatTurnExecutor(db, settings=self.settings)
        self.lock = ConversationGenerationLock(settings=self.settings)
        self.client_factory = client_factory or OpenWAClient

    def process_adapter_payload(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            kind = str(payload.get("kind") or "").strip()
            if kind == "openwa_message_received":
                return self.process_inbound_message(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    payload=payload,
                )
            if kind == "openwa_session_event":
                return self.process_session_event(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    payload=payload,
                )
            return {"status": "ignored", "reason": "unknown_payload_kind"}
        except AppError as exc:
            # Retryable lock contention must bubble to Celery.
            if exc.category == ErrorCategory.CONVERSATION_BUSY:
                raise
            self.db.rollback()
            return {"status": "ignored", "reason": exc.category.value}

    def process_inbound_message(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row, _app, _installation = self.connections.require_usable_connection(
            workspace_id,
            connection_id,
            app_slug=APP_SLUG_DEFAULT,
        )
        workspace = self._workspace_or_fail(workspace_id)
        self.access.require_active(workspace_id, app_slug=APP_SLUG_DEFAULT)

        binding = self._binding_for_connection(row)
        if binding is None or not binding.enabled or not binding.auto_reply_enabled:
            return {"status": "ignored", "reason": "channel_disabled"}
        if binding.expert_id is None:
            return {"status": "ignored", "reason": "expert_unbound"}

        try:
            self.experts.resolve_for_workspace_consumer(
                workspace=workspace,
                expert_id=binding.expert_id,
                action=ExpertAction.USE,
            )
        except AppError:
            return {"status": "ignored", "reason": "expert_unavailable"}

        body = str(payload.get("body") or "").strip()
        external_chat_id = str(payload.get("external_chat_id") or "").strip()
        sender_id = str(payload.get("sender_id") or "").strip() or None
        if not body or not external_chat_id:
            return {"status": "ignored", "reason": "empty_message"}
        is_group = bool(payload.get("is_group"))
        if is_group and not binding.respond_to_groups:
            return {"status": "ignored", "reason": "group_disabled"}
        if self._is_ignored_chat(payload, external_chat_id):
            return {"status": "ignored", "reason": "ignored_chat_kind"}

        lock_id = self._chat_lock_id(workspace_id, connection_id, external_chat_id)
        if not self.lock.acquire(lock_id):
            # Signal Celery to retry so same-chat messages stay ordered.
            raise AppError(
                ErrorCategory.CONVERSATION_BUSY,
                "Channel chat is busy processing another message.",
                retryable=True,
            )

        try:
            conversation, conv_binding = self._resolve_or_create_conversation(
                workspace=workspace,
                connection=row,
                binding=binding,
                external_chat_id=external_chat_id,
                sender_id=sender_id,
            )

            provider_message_id = str(payload.get("provider_message_id") or "").strip()
            existing = self._find_existing_channel_turn(
                conversation_id=conversation.id,
                provider_message_id=provider_message_id,
            )
            if existing is not None:
                user_message, assistant_message = existing
                answer = str(assistant_message.content or "").strip()
                if (
                    assistant_message.status == MessageStatus.COMPLETED.value
                    and answer
                ):
                    deliveries = list(
                        self.db.scalars(
                            select(McpSurfaceDelivery).where(
                                McpSurfaceDelivery.workspace_id == workspace.id,
                                McpSurfaceDelivery.assistant_message_id
                                == assistant_message.id,
                            )
                        ).all()
                    )
                    if deliveries:
                        # Tool-enabled replies are owned by the durable outbox.
                        # A duplicate provider webhook must never create a
                        # second direct send outside that identity.
                        return {
                            "status": "processed",
                            "conversation_id": str(conversation.id),
                            "user_message_id": str(user_message.id),
                            "assistant_message_id": str(assistant_message.id),
                            "segments_sent": sum(
                                row.status == "sent" for row in deliveries
                            ),
                            "resent": False,
                        }
                    send_result = self._send_outbound_reply(
                        connection=row,
                        external_chat_id=external_chat_id,
                        answer=answer,
                    )
                    return {
                        "status": (
                            "processed"
                            if send_result.get("status") != "send_failed"
                            else "send_failed"
                        ),
                        "conversation_id": str(conversation.id),
                        "user_message_id": str(user_message.id),
                        "assistant_message_id": str(assistant_message.id),
                        "segments_sent": int(send_result.get("segments_sent") or 0),
                        "resent": True,
                    }
                # Incomplete prior turn — do not create duplicates.
                return {
                    "status": "ignored",
                    "reason": "duplicate_in_progress",
                    "conversation_id": str(conversation.id),
                }

            live_pending = McpApprovalService(
                self.db, self.settings
            ).live_external_pending(
                workspace_id=workspace.id,
                conversation_id=conversation.id,
            )
            if live_pending is not None:
                # Preserve one logical writer for this chat while a prior
                # external write is awaiting an authenticated operator.  This
                # acknowledgement is a durable, idempotent outbox turn and
                # performs no MCP paid-access lookup or model/tool work.
                now = datetime.now(timezone.utc)
                notice = "A previous tool request is still awaiting workspace approval."
                channel_meta = (
                    [{"channel": {"provider_message_id": provider_message_id}}]
                    if provider_message_id
                    else []
                )
                user_message = Message(
                    conversation_id=conversation.id,
                    role=MessageRole.USER.value,
                    content=body,
                    citations=[],
                    attachments=channel_meta,
                    status=MessageStatus.COMPLETED.value,
                    created_at=now,
                    updated_at=now,
                )
                assistant_message = Message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT.value,
                    content=notice,
                    citations=[],
                    attachments=[],
                    status=MessageStatus.COMPLETED.value,
                    created_at=now,
                    updated_at=now,
                )
                self.conversations.create_message(user_message)
                self.conversations.create_message(assistant_message)
                self.db.flush()
                deliveries = McpSurfaceOutboxService(
                    self.db, self.settings
                ).enqueue(
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    assistant_message_id=assistant_message.id,
                    surface_binding_id=live_pending.mcp_tool_surface_binding_id,
                    rendered_segments=[notice],
                    pending_id=live_pending.id,
                    external_principal_fingerprint=(
                        live_pending.external_principal_fingerprint
                    ),
                )
                conversation.updated_at = now
                self.db.commit()
                delivery_ids = [delivery.id for delivery in deliveries]
                self._enqueue_mcp_deliveries(delivery_ids)
                return {
                    "status": "pending_approval",
                    "conversation_id": str(conversation.id),
                    "user_message_id": str(user_message.id),
                    "assistant_message_id": str(assistant_message.id),
                    "segments_sent": 0,
                    "segments_queued": len(delivery_ids),
                }

            now = datetime.now(timezone.utc)
            channel_meta = (
                [{"channel": {"provider_message_id": provider_message_id}}]
                if provider_message_id
                else []
            )
            user_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=body,
                citations=[],
                attachments=channel_meta,
                status=MessageStatus.COMPLETED.value,
                created_at=now,
                updated_at=now,
            )
            assistant_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT.value,
                content="",
                citations=[],
                attachments=[],
                status=MessageStatus.PENDING.value,
                created_at=now,
                updated_at=now,
            )
            self.conversations.create_message(user_message)
            self.conversations.create_message(assistant_message)
            conversation.updated_at = now
            self.db.flush()

            history_limit = max(0, int(self.settings.chat_history_max_messages))
            history: list[dict[str, str]] = []
            if history_limit > 0:
                rows = self.conversations.list_history_for_rag(
                    conversation.id,
                    before_message_id=user_message.id,
                    limit=history_limit,
                )
                history = [
                    {"role": m.role, "content": m.content or ""}
                    for m in rows
                    if (m.content or "").strip()
                ]

            direct_fingerprint = None
            if not is_group:
                effective_sender_id = (
                    sender_id
                    or conv_binding.external_sender_id
                    or external_chat_id
                )
                direct_fingerprint = channel_external_principal_fingerprint(
                    external_chat_id=external_chat_id,
                    external_sender_id=effective_sender_id,
                    workspace_id=workspace.id,
                    connection_id=row.id,
                    binding_id=conv_binding.id,
                    secret=self.settings.jwt_secret,
                )
            invocation = ChatInvocationContext.channel(
                workspace_id=workspace.id,
                connection_id=row.id,
                expert_id=conversation.expert_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                request_id=str(assistant_message.id),
                source_binding_id=(conv_binding.id if not is_group else None),
                external_principal_fingerprint=direct_fingerprint,
            )
            tools = self.executor.select_mcp_tools(
                invocation=invocation,
                expert_id=conversation.expert_id,
            )
            meter = MeteredWorkspaceGeneration(
                self.db,
                workspace_id=workspace.id,
                expert_id=conversation.expert_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                request_id=str(assistant_message.id),
                reservation_multiplier=(
                    self.settings.mcp_max_tool_iterations + 1 if tools else 1
                ),
                settings=self.settings,
            )
            meter.reserve()

            try:
                result = self.executor.execute(
                    workspace=workspace,
                    expert_id=conversation.expert_id,
                    question=body,
                    invocation=invocation,
                    meter=meter,
                    history=history,
                    mcp_tools=tools,
                )
            except AppError as exc:
                meter.release()
                self._mark_failed_assistant(
                    conversation=conversation,
                    assistant=assistant_message,
                    message=exc.message,
                )
                self.db.commit()
                return {"status": "failed", "error": exc.category.value}
            except Exception:
                meter.release()
                self._mark_failed_assistant(
                    conversation=conversation,
                    assistant=assistant_message,
                    message="Generation failed.",
                )
                self.db.commit()
                return {"status": "failed", "error": ErrorCategory.GENERATION_FAILED.value}

            answer = str(result.get("answer") or "").strip()
            citations = list(result.get("citations") or [])
            if result.get("mcp_pending"):
                notice = "This request is awaiting approval from a workspace operator."
                assistant_message.content = notice
                assistant_message.citations = []
                assistant_message.status = MessageStatus.PENDING.value
                assistant_message.updated_at = datetime.now(timezone.utc)
                conversation.updated_at = assistant_message.updated_at
                if sender_id and conv_binding.external_sender_id != sender_id:
                    conv_binding.external_sender_id = sender_id
                delivery_ids = self._create_initial_pending_notice(
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    assistant_message_id=assistant_message.id,
                    pending_payload=result["mcp_pending"],
                    external_principal_fingerprint=direct_fingerprint,
                    notice=notice,
                )
                self.db.commit()
                self._enqueue_mcp_deliveries(delivery_ids)
                return {
                    "status": "pending_approval",
                    "conversation_id": str(conversation.id),
                    "user_message_id": str(user_message.id),
                    "assistant_message_id": str(assistant_message.id),
                    "segments_sent": 0,
                    "segments_queued": len(delivery_ids),
                }
            assistant_message.content = answer
            assistant_message.citations = citations
            assistant_message.status = MessageStatus.COMPLETED.value
            assistant_message.updated_at = datetime.now(timezone.utc)
            conversation.updated_at = assistant_message.updated_at
            delivery_ids: list[uuid.UUID] = []
            if tools and answer:
                surface = getattr(tools[0], "surface_binding", None)
                if surface is None:
                    raise AppError(
                        ErrorCategory.MCP_TOOL_NOT_GRANTED,
                        "The exact WhatsApp MCP surface is unavailable.",
                    )
                deliveries = McpSurfaceOutboxService(
                    self.db, self.settings
                ).enqueue(
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    assistant_message_id=assistant_message.id,
                    surface_binding_id=surface.id,
                    rendered_segments=split_whatsapp_text(answer),
                    external_principal_fingerprint=direct_fingerprint,
                )
                delivery_ids = [item.id for item in deliveries]
            if sender_id and conv_binding.external_sender_id != sender_id:
                conv_binding.external_sender_id = sender_id
            self.db.commit()
            self.db.refresh(assistant_message)

            if delivery_ids:
                self._enqueue_mcp_deliveries(delivery_ids)
                send_result = {
                    "segments_sent": 0,
                    "segments_queued": len(delivery_ids),
                    "status": "queued",
                }
            elif answer:
                send_result = self._send_outbound_reply(
                    connection=row,
                    external_chat_id=external_chat_id,
                    answer=answer,
                )
            else:
                send_result = {"segments_sent": 0, "status": "empty_answer"}

            status = "processed"
            if send_result.get("status") == "send_failed":
                status = "send_failed"
            response = {
                "status": status,
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant_message.id),
                "segments_sent": int(send_result.get("segments_sent") or 0),
            }
            if tools:
                response["segments_queued"] = int(
                    send_result.get("segments_queued") or 0
                )
            return response
        finally:
            self.lock.release(lock_id)

    def _create_initial_pending_notice(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        pending_payload: Any,
        external_principal_fingerprint: str | None,
        notice: str,
    ) -> list[uuid.UUID]:
        """Persist exactly one generic revision before acknowledging a pause."""

        try:
            pending_id = uuid.UUID(str(pending_payload.get("id") or ""))
        except (AttributeError, TypeError, ValueError) as exc:
            raise AppError(
                ErrorCategory.MCP_TOOL_NOT_GRANTED,
                "The pending MCP approval identity is invalid.",
            ) from exc
        pending = self.db.scalar(
            select(McpPendingToolCall).where(
                McpPendingToolCall.id == pending_id,
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.conversation_id == conversation_id,
                McpPendingToolCall.message_id == assistant_message_id,
                McpPendingToolCall.status == "pending",
            )
        )
        if (
            pending is None
            or pending.mcp_tool_surface_binding_id is None
            or pending.external_principal_fingerprint
            != external_principal_fingerprint
        ):
            raise AppError(
                ErrorCategory.MCP_TOOL_NOT_GRANTED,
                "The pending MCP approval identity changed.",
            )
        deliveries = McpSurfaceOutboxService(
            self.db, self.settings
        ).enqueue(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            surface_binding_id=pending.mcp_tool_surface_binding_id,
            rendered_segments=[notice],
            pending_id=pending.id,
            external_principal_fingerprint=external_principal_fingerprint,
            response_revision=1,
        )
        return [delivery.id for delivery in deliveries]

    def process_session_event(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        OpenWAChannelService(
            self.db,
            settings=self.settings,
            client_factory=self.client_factory,
        ).sync_session_event(
            workspace_id=workspace_id,
            connection_id=connection_id,
            provider_status=payload.get("provider_status"),
            last_error=payload.get("last_error"),
        )
        self.db.flush()
        return {
            "status": "processed",
            "provider_status": str(payload.get("provider_status") or ""),
        }

    def _workspace_or_fail(self, workspace_id: uuid.UUID) -> Workspace:
        row = self.db.get(Workspace, workspace_id)
        if row is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        return row

    def _binding_for_connection(self, connection: AppConnection) -> ChannelBinding | None:
        return self.db.scalar(
            select(ChannelBinding).where(
                ChannelBinding.workspace_id == connection.workspace_id,
                ChannelBinding.app_connection_id == connection.id,
            )
        )

    def _find_existing_channel_turn(
        self,
        *,
        conversation_id: uuid.UUID,
        provider_message_id: str,
    ) -> tuple[Message, Message] | None:
        """Return prior user+assistant pair for the same provider message (send retry)."""
        if not provider_message_id:
            return None
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            ).all()
        )
        for idx, msg in enumerate(messages):
            if msg.role != MessageRole.USER.value:
                continue
            attachments = msg.attachments if isinstance(msg.attachments, list) else []
            matched = False
            for item in attachments:
                if not isinstance(item, dict):
                    continue
                channel = item.get("channel")
                if isinstance(channel, dict) and str(
                    channel.get("provider_message_id") or ""
                ).strip() == provider_message_id:
                    matched = True
                    break
            if not matched:
                continue
            # Prefer the next assistant message after this user turn.
            for nxt in messages[idx + 1 :]:
                if nxt.role == MessageRole.ASSISTANT.value:
                    return msg, nxt
            return None
        return None

    def _resolve_or_create_conversation(
        self,
        *,
        workspace: Workspace,
        connection: AppConnection,
        binding: ChannelBinding,
        external_chat_id: str,
        sender_id: str | None,
    ) -> tuple[Conversation, ChannelConversationBinding]:
        conv_binding = self.db.scalar(
            select(ChannelConversationBinding)
            .where(
                ChannelConversationBinding.workspace_id == workspace.id,
                ChannelConversationBinding.app_connection_id == connection.id,
                ChannelConversationBinding.external_chat_id == external_chat_id,
                ChannelConversationBinding.expert_id == binding.expert_id,
            )
            .with_for_update()
        )
        if conv_binding is not None:
            conversation = self.db.get(Conversation, conv_binding.conversation_id)
            if conversation is None:
                raise AppError(
                    ErrorCategory.CONVERSATION_NOT_FOUND,
                    "Channel conversation binding is missing its conversation.",
                )
            return conversation, conv_binding

        conversation = Conversation(
            workspace_id=workspace.id,
            expert_id=binding.expert_id,
            user_id=None,
            source=ConversationSource.CHANNEL.value,
            title=None,
        )
        self.conversations.create(conversation)
        conv_binding = ChannelConversationBinding(
            workspace_id=workspace.id,
            app_connection_id=connection.id,
            conversation_id=conversation.id,
            external_chat_id=external_chat_id,
            external_sender_id=sender_id,
            expert_id=binding.expert_id,
        )
        self.db.add(conv_binding)
        self.db.flush()
        return conversation, conv_binding

    def _send_outbound_reply(
        self,
        *,
        connection: AppConnection,
        external_chat_id: str,
        answer: str,
    ) -> dict[str, Any]:
        creds = self.connections.credentials.get_credentials(connection) or {}
        session_id = str(creds.get("session_id") or "").strip()
        if not session_id:
            return {"status": "skipped", "reason": "missing_session", "segments_sent": 0}

        segments = split_whatsapp_text(answer)
        sent = 0
        try:
            with self.client_factory(settings=self.settings) as client:
                for segment in segments:
                    client.send_text(
                        session_id,
                        chat_id=external_chat_id,
                        text=segment,
                        link_preview=False,
                    )
                    sent += 1
        except AppError as exc:
            connection.last_error_code = exc.category.value
            connection.last_error_message = exc.message
            connection.last_error_at = datetime.now(timezone.utc)
            if connection.status == ConnectionStatus.ACTIVE.value:
                connection.status = ConnectionStatus.DEGRADED.value
            self.db.commit()
            return {
                "status": "send_failed",
                "error": exc.category.value,
                "segments_sent": sent,
            }
        return {"status": "sent", "segments_sent": sent}

    @staticmethod
    def _enqueue_mcp_deliveries(delivery_ids: list[uuid.UUID]) -> None:
        try:
            from app.worker.tasks import deliver_mcp_surface_segment

            for delivery_id in delivery_ids:
                deliver_mcp_surface_segment.delay(str(delivery_id))
        except Exception:
            # Committed pending rows are authoritative; Beat is the backstop.
            return

    @staticmethod
    def _mark_failed_assistant(
        *,
        conversation: Conversation,
        assistant: Message,
        message: str,
    ) -> None:
        assistant.content = message
        assistant.status = MessageStatus.FAILED.value
        assistant.updated_at = datetime.now(timezone.utc)
        conversation.updated_at = assistant.updated_at

    @staticmethod
    def _chat_lock_id(
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        external_chat_id: str,
    ) -> uuid.UUID:
        namespace = uuid.uuid5(workspace_id, str(connection_id))
        return uuid.uuid5(namespace, external_chat_id)

    @staticmethod
    def _is_ignored_chat(payload: dict[str, Any], external_chat_id: str) -> bool:
        chat_kind = str(payload.get("chat_kind") or "").strip().lower()
        if chat_kind in {"status", "broadcast"}:
            return True
        external = external_chat_id.lower()
        return external.endswith("@broadcast") or external == "status@broadcast"
