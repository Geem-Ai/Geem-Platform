"""Chat actor / attribution context (Phase 7B / 9F channel).

One invocation never claims both a session User and an API key.
Channel invocations have neither — tenancy comes from the connection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.usage.attribution import GenerationUsageContext

SOURCE_WORKSPACE = "workspace"
SOURCE_API = "api"
SOURCE_CHANNEL = "channel"
SOURCE_WIDGET = "widget"


@dataclass(slots=True, frozen=True)
class ChatInvocationContext:
    """Who is invoking Chat for which Workspace.

    Workspace UI: user_id set, api_key_id None, source=workspace.
    Public API: api_key_id set, user_id None, source=api.
    Channel (WhatsApp): both None, source=channel, connection_id set.
    Widget: both None, source=widget, widget_id set.
    """

    workspace_id: uuid.UUID
    source: str
    user_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    expert_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    request_id: str | None = None
    connection_id: uuid.UUID | None = None
    widget_id: uuid.UUID | None = None
    # Exact server-resolved WidgetConversationBinding or
    # ChannelConversationBinding. Legacy Widget JSON intentionally omits this
    # and therefore remains tool-free.
    source_binding_id: uuid.UUID | None = None
    # Keyed digest only; raw visitor/sender identifiers never enter MCP rows.
    external_principal_fingerprint: str | None = None
    # Normalized exact Widget Origin. It is accepted only on the v2 audience-
    # bound session route and is never populated by the legacy JSON endpoint.
    initiating_origin: str | None = None
    # Audience-bound keyed digest of the opaque Widget turn handle. The raw
    # handle exists only in the visitor response and is never persisted.
    external_turn_handle_digest: str | None = None

    def __post_init__(self) -> None:
        if self.source == SOURCE_API:
            if self.api_key_id is None or self.user_id is not None:
                raise ValueError("API Chat invocations require api_key_id and no user_id.")
        elif self.source == SOURCE_WORKSPACE:
            if self.user_id is None or self.api_key_id is not None:
                raise ValueError(
                    "Workspace Chat invocations require user_id and no api_key_id."
                )
        elif self.source == SOURCE_CHANNEL:
            if self.user_id is not None or self.api_key_id is not None:
                raise ValueError(
                    "Channel Chat invocations must not set user_id or api_key_id."
                )
            if self.connection_id is None:
                raise ValueError("Channel Chat invocations require connection_id.")
        elif self.source == SOURCE_WIDGET:
            if self.user_id is not None or self.api_key_id is not None:
                raise ValueError(
                    "Widget Chat invocations must not set user_id or api_key_id."
                )
            if self.widget_id is None:
                raise ValueError("Widget Chat invocations require widget_id.")
        else:
            raise ValueError(f"Unknown Chat invocation source: {self.source}")

    @classmethod
    def workspace_user(
        cls,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        expert_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> ChatInvocationContext:
        return cls(
            workspace_id=workspace_id,
            source=SOURCE_WORKSPACE,
            user_id=user_id,
            api_key_id=None,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=request_id,
        )

    @classmethod
    def api_key(
        cls,
        *,
        workspace_id: uuid.UUID,
        api_key_id: uuid.UUID,
        expert_id: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> ChatInvocationContext:
        return cls(
            workspace_id=workspace_id,
            source=SOURCE_API,
            user_id=None,
            api_key_id=api_key_id,
            expert_id=expert_id,
            conversation_id=None,
            message_id=None,
            request_id=request_id,
        )

    @classmethod
    def channel(
        cls,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        expert_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        request_id: str | None = None,
        source_binding_id: uuid.UUID | None = None,
        external_principal_fingerprint: str | None = None,
    ) -> ChatInvocationContext:
        return cls(
            workspace_id=workspace_id,
            source=SOURCE_CHANNEL,
            user_id=None,
            api_key_id=None,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=request_id,
            connection_id=connection_id,
            source_binding_id=source_binding_id,
            external_principal_fingerprint=external_principal_fingerprint,
        )

    @classmethod
    def widget(
        cls,
        *,
        workspace_id: uuid.UUID,
        widget_id: uuid.UUID,
        expert_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        request_id: str | None = None,
        source_binding_id: uuid.UUID | None = None,
        external_principal_fingerprint: str | None = None,
        initiating_origin: str | None = None,
        external_turn_handle_digest: str | None = None,
    ) -> ChatInvocationContext:
        return cls(
            workspace_id=workspace_id,
            source=SOURCE_WIDGET,
            user_id=None,
            api_key_id=None,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=request_id,
            widget_id=widget_id,
            source_binding_id=source_binding_id,
            external_principal_fingerprint=external_principal_fingerprint,
            initiating_origin=initiating_origin,
            external_turn_handle_digest=external_turn_handle_digest,
        )

    def to_usage_context(self) -> GenerationUsageContext:
        return GenerationUsageContext(
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            expert_id=self.expert_id,
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            api_key_id=self.api_key_id,
            request_id=self.request_id,
        )
