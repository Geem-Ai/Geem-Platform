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
from app.conversations.models import Conversation, ConversationSource, Message, MessageRole, MessageStatus
from app.conversations.repository import ConversationRepository
from app.conversations.turn import ChatTurnExecutor
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.access import ExpertAccessService
from app.experts.policy import ExpertAction
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
        if bool(payload.get("is_group")) and not binding.respond_to_groups:
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

            meter = MeteredWorkspaceGeneration(
                self.db,
                workspace_id=workspace.id,
                expert_id=conversation.expert_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                request_id=str(assistant_message.id),
                settings=self.settings,
            )
            meter.reserve()

            invocation = ChatInvocationContext.channel(
                workspace_id=workspace.id,
                connection_id=row.id,
                expert_id=conversation.expert_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                request_id=str(assistant_message.id),
            )

            try:
                result = self.executor.execute(
                    workspace=workspace,
                    expert_id=conversation.expert_id,
                    question=body,
                    invocation=invocation,
                    meter=meter,
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
            assistant_message.content = answer
            assistant_message.citations = citations
            assistant_message.status = MessageStatus.COMPLETED.value
            assistant_message.updated_at = datetime.now(timezone.utc)
            conversation.updated_at = assistant_message.updated_at
            self.db.commit()
            self.db.refresh(assistant_message)

            if answer:
                send_result = self._send_outbound_reply(
                    connection=row,
                    external_chat_id=external_chat_id,
                    answer=answer,
                )
            else:
                send_result = {"segments_sent": 0, "status": "empty_answer"}

            if sender_id and conv_binding.external_sender_id != sender_id:
                conv_binding.external_sender_id = sender_id
                self.db.commit()

            status = "processed"
            if send_result.get("status") == "send_failed":
                status = "send_failed"
            return {
                "status": status,
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant_message.id),
                "segments_sent": int(send_result.get("segments_sent") or 0),
            }
        finally:
            self.lock.release(lock_id)

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
