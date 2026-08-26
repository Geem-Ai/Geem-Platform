"""Durable, source-authorized delivery of MCP WhatsApp result segments."""

from __future__ import annotations

import hmac
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    begin_runtime_admission_transaction,
)
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import (
    AppConnection,
    ChannelBinding,
    ChannelConversationBinding,
)
from app.connectors.providers.openwa.client import OpenWAClient
from app.connectors.types import CONNECTION_USABLE_STATUSES
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.mcp.public_tokens import channel_external_principal_fingerprint
from app.mcp.runtime_models import McpSurfaceDelivery, McpToolSurfaceBinding
from app.mcp.surfaces import (
    WHATSAPP_APP_SLUG,
    McpSurfaceOutboxService,
    _channel_config_hash,
    _channel_source_fingerprint,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _DeliverySnapshot:
    delivery_id: uuid.UUID
    conversation_id: uuid.UUID
    connection_id: uuid.UUID
    session_id: str
    external_chat_id: str
    text: str


class McpWhatsAppDeliveryService:
    """Claim one immutable segment, then send with no database transaction held."""

    _DEFINITE_PRE_SEND = frozenset(
        {
            ErrorCategory.OPENWA_NOT_CONFIGURED,
            ErrorCategory.OPENWA_UNAUTHORIZED,
            ErrorCategory.OPENWA_REQUEST_INVALID,
            ErrorCategory.OPENWA_SESSION_NOT_FOUND,
            ErrorCategory.CONNECTOR_CREDENTIALS_INVALID,
        }
    )

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client_factory: type[OpenWAClient] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client_factory = client_factory or OpenWAClient

    def deliver(self, delivery_id: uuid.UUID) -> dict[str, Any]:
        snapshot = self._claim_authorized(delivery_id)
        if snapshot is None:
            return {"status": "not_claimed", "delivery_id": str(delivery_id)}
        try:
            with self.client_factory(settings=self.settings) as client:
                response = client.send_text(
                    snapshot.session_id,
                    chat_id=snapshot.external_chat_id,
                    text=snapshot.text,
                    link_preview=False,
                )
        except AppError as exc:
            if exc.category in self._DEFINITE_PRE_SEND:
                self._release_pre_send(delivery_id)
                status = "retry_pending"
            else:
                # A POST transport/provider failure may have happened after the
                # remote side accepted the message. Never auto-resend it.
                self._mark_unknown(delivery_id)
                status = "delivery_unknown"
            return {
                "status": status,
                "delivery_id": str(delivery_id),
                "error": exc.category.value,
            }
        except Exception:  # noqa: BLE001
            # Provider exceptions may embed the outbound text or credential-
            # bearing request metadata. Record only the stable delivery ID.
            logger.error(
                "mcp_whatsapp_delivery_failed",
                extra={"delivery_id": str(delivery_id)},
            )
            self._mark_unknown(delivery_id)
            return {"status": "delivery_unknown", "delivery_id": str(delivery_id)}

        self._mark_sent(delivery_id, provider_message_id=response.messageId)
        return {
            "status": "sent",
            "delivery_id": str(delivery_id),
            "provider_message_id": response.messageId,
        }

    def _claim_authorized(self, delivery_id: uuid.UUID) -> _DeliverySnapshot | None:
        # Resolve only opaque server-owned identifiers before the fresh paid
        # admission transaction. Every mutable row is re-read after its fence.
        lookup = SessionLocal()
        try:
            identity = lookup.execute(
                select(
                    McpSurfaceDelivery.workspace_id,
                    McpToolSurfaceBinding.channel_binding_id,
                    ChannelBinding.app_connection_id,
                )
                .outerjoin(
                    McpToolSurfaceBinding,
                    McpToolSurfaceBinding.id
                    == McpSurfaceDelivery.mcp_tool_surface_binding_id,
                )
                .outerjoin(
                    ChannelBinding,
                    ChannelBinding.id == McpToolSurfaceBinding.channel_binding_id,
                )
                .where(McpSurfaceDelivery.id == delivery_id)
            ).one_or_none()
            if identity is not None and (
                identity.channel_binding_id is None
                or identity.app_connection_id is None
            ):
                McpSurfaceOutboxService(
                    lookup, self.settings
                ).cancel_before_send(delivery_id)
                lookup.commit()
                return None
        finally:
            lookup.close()
        if identity is None:
            return None

        workspace_id, channel_binding_id, connection_id = identity
        target_key = f"whatsapp:{connection_id}:{channel_binding_id}"
        db = SessionLocal()
        try:
            begin_runtime_admission_transaction(db)
            acquire_runtime_admission_fences(
                db,
                workspace_id=workspace_id,
                app_slugs=(WHATSAPP_APP_SLUG,),
                surface_target_keys=(target_key,),
            )
            outbox = McpSurfaceOutboxService(db, self.settings)
            try:
                access = AppAccessService(db).require_runtime_active(
                    workspace_id,
                    app_slug=WHATSAPP_APP_SLUG,
                )
            except AppError as exc:
                if exc.retryable:
                    raise
                # Subscription/install/workspace denial is authoritative for
                # this immutable segment.  Cancel under the same target fence;
                # a later renewal must not resurrect or requeue it.
                outbox.cancel_before_send(delivery_id)
                db.commit()
                return None
            delivery = outbox.claim(delivery_id)
            if delivery is None:
                db.commit()
                return None
            surface = db.scalar(
                select(McpToolSurfaceBinding)
                .where(
                    McpToolSurfaceBinding.workspace_id == workspace_id,
                    McpToolSurfaceBinding.id
                    == delivery.mcp_tool_surface_binding_id,
                )
                .with_for_update(read=True)
            )
            channel = db.scalar(
                select(ChannelBinding)
                .where(
                    ChannelBinding.workspace_id == workspace_id,
                    ChannelBinding.id == channel_binding_id,
                    ChannelBinding.app_connection_id == connection_id,
                )
                .with_for_update(read=True)
            )
            connection = db.scalar(
                select(AppConnection)
                .where(
                    AppConnection.workspace_id == workspace_id,
                    AppConnection.id == connection_id,
                )
                .with_for_update(read=True)
            )
            conversation_binding = db.scalar(
                select(ChannelConversationBinding)
                .where(
                    ChannelConversationBinding.workspace_id == workspace_id,
                    ChannelConversationBinding.app_connection_id == connection_id,
                    ChannelConversationBinding.conversation_id
                    == delivery.conversation_id,
                )
                .with_for_update(read=True)
            )
            try:
                text, pinned_principal = outbox.rendered_payload(delivery)
            except (AppError, TypeError, ValueError):
                text = ""
                pinned_principal = None
            current_principal = None
            if conversation_binding is not None:
                current_principal = _channel_principal_fingerprint(
                    conversation_binding,
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    secret=self.settings.jwt_secret,
                )
            current = bool(
                surface
                and channel
                and connection
                and conversation_binding
                and surface.surface_kind == "whatsapp_openwa"
                and surface.state == "active"
                and surface.channel_binding_id == channel.id
                and surface.expert_id == channel.expert_id
                and conversation_binding.expert_id == surface.expert_id
                and channel.enabled
                and channel.auto_reply_enabled
                and not channel.respond_to_groups
                and connection.app_installation_id == access.installation_id
                and connection.status in CONNECTION_USABLE_STATUSES
                and surface.approved_source_epoch == channel.mcp_source_epoch
                and surface.approved_surface_config_hash
                == _channel_config_hash(channel, connection)
                and surface.approved_source_principal_fingerprint
                == _channel_source_fingerprint(channel, connection)
                and pinned_principal is not None
                and current_principal is not None
                and hmac.compare_digest(pinned_principal, current_principal)
            )
            if not current:
                outbox.cancel_before_send(delivery.id)
                db.commit()
                return None
            try:
                credentials = ConnectorCredentialService(
                    db, settings=self.settings
                ).get_credentials(connection)
            except (TypeError, ValueError):
                outbox.cancel_before_send(delivery.id)
                db.commit()
                return None
            session_id = str((credentials or {}).get("session_id") or "").strip()
            if not session_id:
                outbox.cancel_before_send(delivery.id)
                db.commit()
                return None
            snapshot = _DeliverySnapshot(
                delivery_id=delivery.id,
                conversation_id=delivery.conversation_id,
                connection_id=connection.id,
                session_id=session_id,
                external_chat_id=conversation_binding.external_chat_id,
                text=text,
            )
            db.commit()
            return snapshot
        except AppError:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "WhatsApp delivery authorization is temporarily unavailable.",
                retryable=True,
            ) from exc
        finally:
            db.close()

    def _mark_sent(self, delivery_id: uuid.UUID, *, provider_message_id: str) -> None:
        db = SessionLocal()
        try:
            McpSurfaceOutboxService(db, self.settings).mark_sent(
                delivery_id, provider_message_id=provider_message_id
            )
            db.commit()
        finally:
            db.close()

    def _mark_unknown(self, delivery_id: uuid.UUID) -> None:
        db = SessionLocal()
        try:
            McpSurfaceOutboxService(db, self.settings).mark_unknown(delivery_id)
            db.commit()
        finally:
            db.close()

    def _release_pre_send(self, delivery_id: uuid.UUID) -> None:
        db = SessionLocal()
        try:
            McpSurfaceOutboxService(db, self.settings).release_definite_pre_send_failure(
                delivery_id
            )
            db.commit()
        finally:
            db.close()


def _channel_principal_fingerprint(
    binding: ChannelConversationBinding,
    *,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    secret: str,
) -> str | None:
    """Rebuild the turn's keyed direct-chat/sender identity from current rows."""

    try:
        return channel_external_principal_fingerprint(
            external_chat_id=binding.external_chat_id,
            external_sender_id=binding.external_sender_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            binding_id=binding.id,
            secret=secret,
        )
    except ValueError:
        return None


__all__ = ["McpWhatsAppDeliveryService"]
