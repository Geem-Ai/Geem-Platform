"""Chat Widget business logic."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.entitlements import AppEntitlementService
from app.apps_catalog.models import (
    AppInstallation,
    AppInstallationStatus,
    CatalogApp,
)
from app.apps_catalog.policy import require_manage_apps
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.service import AppInstallationService
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
from app.experts.models import Expert, ExpertStatus
from app.experts.service import ExpertService
from app.mcp.approvals import McpApprovalService
from app.mcp.public_tokens import (
    derive_initial_widget_session_id,
    derive_turn_handle,
    external_principal_digest,
    mint_widget_mcp_session,
    normalize_client_turn_id,
    origin_digest as mcp_origin_digest,
    parse_widget_mcp_session,
    turn_handle_digest,
    widget_external_principal_fingerprint,
)
from app.mcp.runtime_models import McpToolSurfaceBinding, McpWidgetTurnReceipt
from app.usage.metered import MeteredWorkspaceGeneration
from app.widgets.models import (
    WidgetConversationBinding,
    WidgetInstance,
    WidgetInstanceStatus,
)
from app.widgets.origins import (
    normalize_origin,
    normalize_origins_list,
    origin_allowed,
    request_origin,
)
from app.widgets.retention import WidgetRetentionService
from app.widgets.schemas import (
    WidgetBootstrapOut,
    WidgetExpertOut,
    WidgetInstanceOut,
    WidgetMessageOut,
    WidgetMcpTurnStatusOut,
    WidgetUpdateIn,
)
from app.widgets.session_tokens import (
    mint_session_token,
    parse_bare_session_uuid,
    parse_session_token,
)
from app.workspaces.lifecycle import require_active_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

APP_SLUG = "chat-widget"
_DEFAULT_TITLE = "Geem"
_DEFAULT_GREETING_AR = "مرحباً بك"


class WidgetService:
    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.access = AppAccessService(db)
        self.entitlements = AppEntitlementService(db)
        self.catalog = AppCatalogRepository(db)
        self.installations = AppInstallationService(db, self.settings)
        self.experts = ExpertService(db)
        self.conversations = ConversationRepository(db)
        self.lock = ConversationGenerationLock(settings=self.settings)
        self.retention = WidgetRetentionService(db, settings=self.settings)

    def get_or_create_for_workspace(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
    ) -> WidgetInstanceOut:
        self.access.require_active(workspace.id, app_slug=APP_SLUG)
        installation = self._require_active_installation(workspace.id)
        row = self._get_by_installation(workspace.id, installation.id)
        if row is None:
            require_manage_apps(membership)
            row = self._create_instance(workspace.id, installation.id)
            self.db.commit()
        elif row.status == WidgetInstanceStatus.DISABLED.value:
            # Disconnect disables the row; reinstall must restore public access
            # without requiring a redundant Save.
            from app.mcp.surfaces import stale_widget_surface_bindings

            stale_widget_surface_bindings(self.db, row)
            row.status = WidgetInstanceStatus.ACTIVE.value
            self.db.commit()
            self.db.refresh(row)
        return self._to_out(row)

    def update(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        body: WidgetUpdateIn,
    ) -> WidgetInstanceOut:
        require_manage_apps(membership)
        self.access.require_active(workspace.id, app_slug=APP_SLUG)
        installation = self._require_active_installation(workspace.id)
        row = self._get_by_installation(workspace.id, installation.id)
        if row is None:
            row = self._create_instance(workspace.id, installation.id)

        data = body.model_dump(exclude_unset=True)
        next_origins = row.allowed_origins
        if "allowed_origins" in data:
            next_origins = normalize_origins_list(data["allowed_origins"])
        next_expert_id = data.get("expert_id", row.expert_id)
        source_changes = bool(
            next_origins != row.allowed_origins
            or next_expert_id != row.expert_id
            or row.status == WidgetInstanceStatus.DISABLED.value
        )
        if source_changes:
            from app.mcp.surfaces import stale_widget_surface_bindings

            # Restrictive target fence is acquired before audience mutation.
            stale_widget_surface_bindings(self.db, row)
        if "allowed_origins" in data:
            row.allowed_origins = next_origins
            data.pop("allowed_origins")
        if "expert_id" in data:
            expert_id = data.pop("expert_id")
            if expert_id is None:
                row.expert_id = None
            else:
                self._require_ready_expert(workspace, expert_id)
                row.expert_id = expert_id
        for key, value in data.items():
            setattr(row, key, value)
        if row.status == WidgetInstanceStatus.DISABLED.value:
            row.status = WidgetInstanceStatus.ACTIVE.value
        from app.audit import AuditAction, AuditEntityType, record_audit

        record_audit(
            self.db,
            action=AuditAction.APP_WIDGET_UPDATED,
            entity_type=AuditEntityType.APP_CONNECTION,
            entity_id=row.id,
            workspace_id=workspace.id,
            actor_user_id=membership.user_id,
            metadata={"expert_id": str(row.expert_id) if row.expert_id else None},
            allowlist=frozenset({"expert_id"}),
        )
        self.db.commit()
        self.db.refresh(row)
        return self._to_out(row)

    def disconnect(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
    ) -> None:
        """Disable widget and uninstall the app."""
        require_manage_apps(membership)
        app = self._app()
        installation = self.catalog.get_installation_by_app(workspace.id, app.id)
        if installation is not None:
            row = self._get_by_installation(workspace.id, installation.id)
            if row is not None:
                from app.mcp.surfaces import stale_widget_surface_bindings

                stale_widget_surface_bindings(self.db, row)
                row.status = WidgetInstanceStatus.DISABLED.value
                self.db.flush()
            if installation.status == AppInstallationStatus.ACTIVE.value:
                self.installations.uninstall_app(
                    workspace=workspace,
                    actor_id=membership.user_id,
                    slug=APP_SLUG,
                )
            else:
                self.db.commit()

    def bootstrap(
        self,
        widget_id: uuid.UUID,
        *,
        origin_header: str | None,
        referer: str | None,
    ) -> tuple[WidgetBootstrapOut, str | None]:
        row = self._require_public_widget(widget_id)
        cors_origin = self._enforce_origin(row, origin_header, referer)
        mcp_tools_enabled = self._has_active_mcp_surface(row)
        return (
            WidgetBootstrapOut(
                widget_id=row.id,
                title=row.title,
                subtitle=row.subtitle,
                greeting=row.greeting,
                logo_url=row.logo_url,
                locale=row.locale,
                position=row.position,
                primary_color=row.primary_color,
                text_color=row.text_color,
                mcp_tools_enabled=mcp_tools_enabled,
                tool_transport=("fetch_sse" if mcp_tools_enabled else None),
                mcp_public_audience_disclosure=(
                    (
                        "قد يرسل هذا المساعد رسالتك إلى "
                        "أدوات خارجية معتمدة."
                        if row.locale == "ar"
                        else "This assistant may send your message to approved external tools."
                    )
                    if mcp_tools_enabled
                    else None
                ),
            ),
            cors_origin,
        )

    def message(
        self,
        widget_id: uuid.UUID,
        *,
        message: str,
        session_id: str | None,
        origin_header: str | None,
        referer: str | None,
    ) -> tuple[WidgetMessageOut, str | None]:
        row = self._require_public_widget(widget_id)
        cors_origin = self._enforce_origin(row, origin_header, referer)
        if row.expert_id is None:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Widget is not bound to an Expert.",
            )
        workspace = self.db.get(Workspace, row.workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Widget not found.")
        require_active_workspace(workspace)
        self._require_ready_expert(workspace, row.expert_id)

        session_uuid, session_token = self._resolve_session_token(
            session_id, widget=row, expert_id=row.expert_id
        )
        # Serialize first-message create + concurrent turns for this visitor session.
        session_lock_id = uuid.uuid5(row.id, f"{session_uuid}:{row.expert_id}")
        if not self.lock.acquire(session_lock_id):
            raise AppError(
                ErrorCategory.CONVERSATION_BUSY,
                "This chat is busy processing another message.",
                retryable=True,
            )

        try:
            conversation, _binding = self._resolve_or_create_conversation(
                workspace=workspace,
                widget=row,
                expert_id=row.expert_id,
                session_id=session_uuid,
            )
            self._enforce_daily_session_quota(
                widget_id=row.id,
                session_id=session_uuid,
            )

            turn_id = str(uuid.uuid4())
            executor = ChatTurnExecutor(self.db, settings=self.settings)
            question = executor.validate_message(message)
            executor.authorize_expert(
                workspace=workspace,
                expert_id=row.expert_id,
                actor_id=None,
            )

            # Drop messages older than TTL before persisting this turn / loading history.
            self.retention.purge_expired_for_conversation(conversation.id)

            now = datetime.now(timezone.utc)
            user_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=question,
                citations=[],
                attachments=[],
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

            history = self._history_payload(
                conversation.id, before_message_id=user_message.id
            )
            invocation = ChatInvocationContext.widget(
                workspace_id=workspace.id,
                widget_id=row.id,
                expert_id=row.expert_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                request_id=turn_id,
            )
            meter = MeteredWorkspaceGeneration(
                self.db,
                workspace_id=workspace.id,
                user_id=None,
                expert_id=row.expert_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                api_key_id=None,
                request_id=turn_id,
                settings=self.settings,
            )
            try:
                meter.reserve()
            except Exception:
                meter.release()
                raise
            try:
                result = executor.execute(
                    workspace=workspace,
                    expert_id=row.expert_id,
                    question=question,
                    invocation=invocation,
                    meter=meter,
                    history=history,
                )
            except Exception:
                meter.release()
                assistant_message.status = MessageStatus.FAILED.value
                assistant_message.updated_at = datetime.now(timezone.utc)
                conversation.updated_at = assistant_message.updated_at
                self.db.commit()
                raise

            answer = str(result.get("answer") or "")
            # Public widget never returns citations to the visitor.
            assistant_message.content = answer
            assistant_message.citations = []
            assistant_message.status = MessageStatus.COMPLETED.value
            assistant_message.updated_at = datetime.now(timezone.utc)
            conversation.updated_at = assistant_message.updated_at
            self.db.commit()

            return (
                WidgetMessageOut(answer=answer, session_id=session_token),
                cors_origin,
            )
        finally:
            self.lock.release(session_lock_id)

    def begin_mcp_turn(
        self,
        widget_id: uuid.UUID,
        *,
        message: str,
        client_turn_id: str,
        session_token: str | None,
        origin_header: str | None,
        referer: str | None,
    ) -> tuple[WidgetMcpTurnStatusOut, str]:
        """Create or replay one idempotent v2 Widget turn, then enqueue it."""

        widget = self._require_public_widget(widget_id)
        cors_origin = self._enforce_origin(widget, origin_header, referer)
        if (
            not cors_origin
            or not origin_header
            or not isinstance(widget.allowed_origins, list)
            or not widget.allowed_origins
        ):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "An exact allowed Origin is required for Widget streaming.",
            )
        if not self._has_active_mcp_surface(widget):
            # The bundled client stays on the legacy tool-free JSON path unless
            # an exact reviewed surface binding enables this transport.
            raise AppError(
                ErrorCategory.NOT_FOUND,
                "Widget tool transport is not available.",
            )
        try:
            normalized_origin = normalize_origin(cors_origin)
        except ValueError as exc:
            raise AppError(ErrorCategory.FORBIDDEN, "Widget Origin is invalid.") from exc
        if widget.expert_id is None:
            raise AppError(ErrorCategory.VALIDATION, "Widget is not bound to an Expert.")
        workspace = self.db.get(Workspace, widget.workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Widget not found.")
        require_active_workspace(workspace)
        self._require_ready_expert(workspace, widget.expert_id)

        try:
            clean_client_turn = normalize_client_turn_id(client_turn_id)
        except ValueError as exc:
            raise AppError(ErrorCategory.VALIDATION, str(exc)) from exc
        od = mcp_origin_digest(normalized_origin, secret=self.settings.jwt_secret)
        session_uuid, issued_token = self._resolve_mcp_session_token(
            session_token,
            widget=widget,
            origin_digest=od,
            client_turn_id=clean_client_turn,
        )
        session_lock_id = uuid.uuid5(widget.id, f"mcp:{session_uuid}:{widget.expert_id}")
        if not self.lock.acquire(session_lock_id):
            raise AppError(
                ErrorCategory.CONVERSATION_BUSY,
                "This chat is busy processing another message.",
                retryable=True,
            )
        try:
            conversation, binding = self._resolve_or_create_conversation(
                workspace=workspace,
                widget=widget,
                expert_id=widget.expert_id,
                session_id=session_uuid,
            )
            question = ChatTurnExecutor(self.db, settings=self.settings).validate_message(
                message
            )
            content_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()
            session_fingerprint = widget_external_principal_fingerprint(
                session_uuid,
                widget_id=widget.id,
                secret=self.settings.jwt_secret,
            )
            client_digest = external_principal_digest(
                clean_client_turn,
                audience=f"widget-turn:{widget.id}:{binding.id}",
                secret=self.settings.jwt_secret,
            )
            raw_handle = derive_turn_handle(
                client_turn_id=clean_client_turn,
                widget_id=widget.id,
                session_id=session_uuid,
                origin_digest=od,
                secret=self.settings.jwt_secret,
            )
            handle_digest = turn_handle_digest(
                raw_handle,
                widget_id=widget.id,
                session_id=session_uuid,
                origin_digest=od,
                secret=self.settings.jwt_secret,
            )
            existing = self.db.scalar(
                select(McpWidgetTurnReceipt).where(
                    McpWidgetTurnReceipt.widget_instance_id == widget.id,
                    McpWidgetTurnReceipt.widget_conversation_binding_id == binding.id,
                    McpWidgetTurnReceipt.client_turn_id_digest == client_digest,
                )
            )
            if existing is not None:
                if (
                    existing.request_content_hash != content_hash
                    or existing.session_id_digest != session_fingerprint
                    or existing.initiating_origin_digest != od
                    or existing.external_turn_handle_digest != handle_digest
                ):
                    raise AppError(
                        ErrorCategory.CONFLICT,
                        "client_turn_id is already bound to a different Widget turn.",
                    )
                return (
                    self._widget_turn_status_out(
                        existing,
                        raw_handle=raw_handle,
                        session_token=issued_token,
                    ),
                    normalized_origin,
                )

            self._enforce_daily_session_quota(
                widget_id=widget.id,
                session_id=session_uuid,
            )
            now = datetime.now(timezone.utc)
            user_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=question,
                citations=[],
                attachments=[],
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
            self.db.flush()
            receipt = McpWidgetTurnReceipt(
                workspace_id=workspace.id,
                expert_id=widget.expert_id,
                widget_instance_id=widget.id,
                widget_conversation_binding_id=binding.id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                request_content_hash=content_hash,
                client_turn_id_digest=client_digest,
                session_id_digest=session_fingerprint,
                initiating_origin_digest=od,
                external_turn_handle_digest=handle_digest,
                status="accepted",
            )
            self.db.add(receipt)
            conversation.updated_at = now
            self.db.commit()
            self.db.refresh(receipt)
            self._enqueue_widget_turn(receipt.id)
            return (
                self._widget_turn_status_out(
                    receipt,
                    raw_handle=raw_handle,
                    session_token=issued_token,
                ),
                normalized_origin,
            )
        finally:
            self.lock.release(session_lock_id)

    def mcp_turn_status(
        self,
        widget_id: uuid.UUID,
        *,
        raw_handle: str,
        session_token: str,
        origin_header: str | None,
        referer: str | None,
    ) -> tuple[WidgetMcpTurnStatusOut, str]:
        widget = self._require_public_widget(widget_id)
        cors_origin = self._enforce_origin(widget, origin_header, referer)
        if not cors_origin or not origin_header:
            raise AppError(ErrorCategory.FORBIDDEN, "Widget Origin is required.")
        normalized_origin = normalize_origin(cors_origin)
        od = mcp_origin_digest(normalized_origin, secret=self.settings.jwt_secret)
        parsed = parse_widget_mcp_session(
            session_token,
            expected_widget_id=widget.id,
            expected_origin_digest=od,
            secret=self.settings.jwt_secret,
        )
        if parsed is None:
            raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid Widget session.")
        session_fingerprint = widget_external_principal_fingerprint(
            parsed.session_id,
            widget_id=widget.id,
            secret=self.settings.jwt_secret,
        )
        try:
            digest = turn_handle_digest(
                raw_handle,
                widget_id=widget.id,
                session_id=parsed.session_id,
                origin_digest=od,
                secret=self.settings.jwt_secret,
            )
        except (TypeError, ValueError) as exc:
            raise AppError(ErrorCategory.NOT_FOUND, "Widget turn not found.") from exc
        receipt = self.db.scalar(
            select(McpWidgetTurnReceipt).where(
                McpWidgetTurnReceipt.widget_instance_id == widget.id,
                McpWidgetTurnReceipt.session_id_digest == session_fingerprint,
                McpWidgetTurnReceipt.initiating_origin_digest == od,
                McpWidgetTurnReceipt.external_turn_handle_digest == digest,
            )
        )
        if receipt is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Widget turn not found.")
        refreshed_token = mint_widget_mcp_session(
            session_id=parsed.session_id,
            widget_id=widget.id,
            origin_digest=od,
            ttl_seconds=self.settings.widget_message_ttl_seconds,
            secret=self.settings.jwt_secret,
        )
        return (
            self._widget_turn_status_out(
                receipt,
                raw_handle=raw_handle,
                session_token=refreshed_token,
            ),
            normalized_origin,
        )

    def execute_mcp_turn_receipt(self, receipt_id: uuid.UUID) -> str:
        """Worker entrypoint; only IDs cross the broker boundary."""

        receipt = self.db.scalar(
            select(McpWidgetTurnReceipt)
            .where(McpWidgetTurnReceipt.id == receipt_id)
            .with_for_update()
        )
        if receipt is None:
            return "missing"
        if receipt.status != "accepted":
            return receipt.status
        receipt.status = "running"
        self.db.commit()

        widget = self.db.get(WidgetInstance, receipt.widget_instance_id)
        binding = self.db.get(
            WidgetConversationBinding,
            receipt.widget_conversation_binding_id,
        )
        conversation = self.db.get(Conversation, receipt.conversation_id)
        user_message = self.db.get(Message, receipt.user_message_id)
        assistant = self.db.get(Message, receipt.assistant_message_id)
        workspace = self.db.get(Workspace, receipt.workspace_id)
        if not all((widget, binding, conversation, user_message, assistant, workspace)):
            return self._fail_widget_receipt(receipt, assistant, "failed")
        assert widget is not None and binding is not None and conversation is not None
        assert user_message is not None and assistant is not None and workspace is not None
        if (
            widget.status != WidgetInstanceStatus.ACTIVE.value
            or widget.expert_id != receipt.expert_id
            or binding.widget_instance_id != widget.id
            or binding.conversation_id != conversation.id
            or binding.expert_id != receipt.expert_id
        ):
            return self._fail_widget_receipt(receipt, assistant, "failed")
        origin = self._origin_for_digest(widget, receipt.initiating_origin_digest)
        if origin is None:
            return self._fail_widget_receipt(receipt, assistant, "failed")

        live_pending = McpApprovalService(
            self.db, self.settings
        ).live_external_pending(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            exclude_message_id=assistant.id,
        )
        if live_pending is not None:
            # Do not interleave a newer tool loop with a human-paused write.
            # The receipt still completes deterministically so client retries
            # replay this same safe acknowledgement without paid MCP lookup.
            now = datetime.now(timezone.utc)
            receipt.status = "completed"
            assistant.content = (
                "A previous tool request is still awaiting workspace approval."
            )
            assistant.citations = []
            assistant.status = MessageStatus.COMPLETED.value
            assistant.updated_at = now
            conversation.updated_at = now
            self.db.commit()
            return receipt.status

        executor = ChatTurnExecutor(self.db, settings=self.settings)
        meter: MeteredWorkspaceGeneration | None = None
        try:
            executor.authorize_expert(
                workspace=workspace,
                expert_id=receipt.expert_id,
                actor_id=None,
            )
            self.retention.purge_expired_for_conversation(conversation.id)
            history = self._history_payload(
                conversation.id,
                before_message_id=user_message.id,
            )
            invocation = ChatInvocationContext.widget(
                workspace_id=workspace.id,
                widget_id=widget.id,
                expert_id=receipt.expert_id,
                conversation_id=conversation.id,
                message_id=assistant.id,
                request_id=str(assistant.id),
                source_binding_id=binding.id,
                external_principal_fingerprint=receipt.session_id_digest,
                initiating_origin=origin,
                external_turn_handle_digest=receipt.external_turn_handle_digest,
            )
            tools = executor.select_mcp_tools(
                invocation=invocation,
                expert_id=receipt.expert_id,
            )
            meter = MeteredWorkspaceGeneration(
                self.db,
                workspace_id=workspace.id,
                expert_id=receipt.expert_id,
                conversation_id=conversation.id,
                message_id=assistant.id,
                request_id=str(assistant.id),
                reservation_multiplier=(
                    self.settings.mcp_max_tool_iterations + 1 if tools else 1
                ),
                settings=self.settings,
            )
            meter.reserve()
            result = executor.execute(
                workspace=workspace,
                expert_id=receipt.expert_id,
                question=user_message.content,
                invocation=invocation,
                meter=meter,
                history=history,
                mcp_tools=tools,
            )
            now = datetime.now(timezone.utc)
            if result.get("mcp_pending"):
                receipt.status = "pending"
                assistant.content = "This request is awaiting approval from a workspace operator."
                assistant.status = MessageStatus.PENDING.value
            else:
                receipt.status = "completed"
                assistant.content = str(result.get("answer") or "")
                assistant.status = MessageStatus.COMPLETED.value
            assistant.citations = []
            assistant.updated_at = now
            conversation.updated_at = now
            self.db.commit()
            return receipt.status
        except AppError as exc:
            if meter is not None:
                meter.release()
            status = (
                "outcome_unknown"
                if exc.category == ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN
                else "failed"
            )
            return self._fail_widget_receipt(receipt, assistant, status)
        except Exception:  # noqa: BLE001
            logger.error("widget_mcp_turn_failed", extra={"receipt_id": str(receipt_id)})
            if meter is not None:
                meter.release()
            return self._fail_widget_receipt(receipt, assistant, "failed")

    def _fail_widget_receipt(
        self,
        receipt: McpWidgetTurnReceipt,
        assistant: Message | None,
        status: str,
    ) -> str:
        receipt.status = status
        if assistant is not None:
            assistant.content = (
                "The tool outcome could not be confirmed."
                if status == "outcome_unknown"
                else "This request could not be completed."
            )
            assistant.citations = []
            assistant.status = MessageStatus.FAILED.value
            assistant.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return status

    def _resolve_session_token(
        self,
        session_id: str | None,
        *,
        widget: WidgetInstance,
        expert_id: uuid.UUID,
    ) -> tuple[str, str]:
        """Return ``(session_uuid, signed_token)`` for DB + client storage."""
        secret = self.settings.jwt_secret
        raw = (session_id or "").strip()
        if len(raw) > 128:
            raise AppError(
                ErrorCategory.VALIDATION,
                "session_id must be at most 128 characters.",
            )
        if not raw:
            sid = str(uuid.uuid4())
            return sid, mint_session_token(sid, secret=secret)

        parsed = parse_session_token(raw, secret=secret)
        if parsed is not None:
            return parsed, mint_session_token(parsed, secret=secret)

        # Grandfather bare UUIDs that already have a binding (pre-HMAC clients).
        bare = parse_bare_session_uuid(raw)
        if bare is not None and self._session_binding_exists(
            widget_id=widget.id, session_id=bare, expert_id=expert_id
        ):
            return bare, mint_session_token(bare, secret=secret)

        raise AppError(ErrorCategory.VALIDATION, "Invalid session_id.")

    def _resolve_mcp_session_token(
        self,
        token: str | None,
        *,
        widget: WidgetInstance,
        origin_digest: str,
        client_turn_id: str,
    ) -> tuple[str, str]:
        raw = (token or "").strip()
        if not raw:
            session_id = derive_initial_widget_session_id(
                client_turn_id=client_turn_id,
                widget_id=widget.id,
                origin_digest=origin_digest,
                secret=self.settings.jwt_secret,
            )
        else:
            parsed = parse_widget_mcp_session(
                raw,
                expected_widget_id=widget.id,
                expected_origin_digest=origin_digest,
                secret=self.settings.jwt_secret,
            )
            if parsed is None:
                raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid Widget session.")
            session_id = parsed.session_id
        issued = mint_widget_mcp_session(
            session_id=session_id,
            widget_id=widget.id,
            origin_digest=origin_digest,
            ttl_seconds=self.settings.widget_message_ttl_seconds,
            secret=self.settings.jwt_secret,
        )
        return session_id, issued

    def _widget_turn_status_out(
        self,
        receipt: McpWidgetTurnReceipt,
        *,
        raw_handle: str,
        session_token: str,
    ) -> WidgetMcpTurnStatusOut:
        answer = None
        if receipt.status in {"pending", "completed", "failed", "outcome_unknown"}:
            assistant = self.db.scalar(
                select(Message).where(
                    Message.conversation_id == receipt.conversation_id,
                    Message.id == receipt.assistant_message_id,
                )
            )
            if assistant is not None:
                answer = str(assistant.content or "") or None
        return WidgetMcpTurnStatusOut(
            turn_handle=raw_handle,
            status=receipt.status,
            answer=answer,
            session_token=session_token,
        )

    def _origin_for_digest(
        self,
        widget: WidgetInstance,
        expected_digest: str,
    ) -> str | None:
        origins = widget.allowed_origins if isinstance(widget.allowed_origins, list) else []
        for value in origins:
            try:
                origin = normalize_origin(str(value))
            except ValueError:
                continue
            digest = mcp_origin_digest(origin, secret=self.settings.jwt_secret)
            if hmac.compare_digest(digest, expected_digest):
                return origin
        return None

    def _has_active_mcp_surface(self, widget: WidgetInstance) -> bool:
        # Exact-binding preflight only. It deliberately performs no MCP paid
        # access lookup when the Widget has no reviewed binding.
        if not self.settings.mcp_connector_enabled:
            return False
        return bool(
            widget.expert_id
            and isinstance(widget.allowed_origins, list)
            and bool(widget.allowed_origins)
            and self.db.scalar(
                select(McpToolSurfaceBinding.id)
                .where(
                    McpToolSurfaceBinding.workspace_id == widget.workspace_id,
                    McpToolSurfaceBinding.expert_id == widget.expert_id,
                    McpToolSurfaceBinding.widget_instance_id == widget.id,
                    McpToolSurfaceBinding.state == "active",
                )
                .limit(1)
            )
        )

    @staticmethod
    def _enqueue_widget_turn(receipt_id: uuid.UUID) -> None:
        try:
            from app.worker.tasks import run_mcp_widget_turn_receipt

            run_mcp_widget_turn_receipt.delay(str(receipt_id))
        except Exception:  # noqa: BLE001
            # A periodic accepted-row recovery sweep is the durable backstop.
            logger.error(
                "widget_mcp_turn_enqueue_failed",
                extra={"receipt_id": str(receipt_id)},
            )

    def _session_binding_exists(
        self,
        *,
        widget_id: uuid.UUID,
        session_id: str,
        expert_id: uuid.UUID,
    ) -> bool:
        return (
            self.db.scalar(
                select(WidgetConversationBinding.id).where(
                    WidgetConversationBinding.widget_instance_id == widget_id,
                    WidgetConversationBinding.session_id == session_id,
                    WidgetConversationBinding.expert_id == expert_id,
                )
            )
            is not None
        )

    def _enforce_daily_session_quota(
        self,
        *,
        widget_id: uuid.UUID,
        session_id: str,
    ) -> None:
        limit = max(0, int(self.settings.widget_session_max_messages_per_day))
        if limit == 0:
            return
        used = self._count_session_user_messages_today(
            widget_id=widget_id, session_id=session_id
        )
        if used >= limit:
            raise AppError(
                ErrorCategory.RATE_LIMIT_EXCEEDED,
                "This chat session has reached its daily message limit.",
                details={"limit": limit, "used": used},
            )

    def _count_session_user_messages_today(
        self,
        *,
        widget_id: uuid.UUID,
        session_id: str,
    ) -> int:
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        count = self.db.scalar(
            select(func.count(Message.id))
            .select_from(Message)
            .join(
                WidgetConversationBinding,
                WidgetConversationBinding.conversation_id == Message.conversation_id,
            )
            .where(
                WidgetConversationBinding.widget_instance_id == widget_id,
                WidgetConversationBinding.session_id == session_id,
                Message.role == MessageRole.USER.value,
                Message.created_at >= start,
            )
        )
        return int(count or 0)

    def _resolve_or_create_conversation(
        self,
        *,
        workspace: Workspace,
        widget: WidgetInstance,
        expert_id: uuid.UUID,
        session_id: str,
    ) -> tuple[Conversation, WidgetConversationBinding]:
        existing = self._get_session_binding(
            workspace_id=workspace.id,
            widget_id=widget.id,
            session_id=session_id,
            expert_id=expert_id,
            for_update=True,
        )
        if existing is not None:
            conversation = self.db.get(Conversation, existing.conversation_id)
            if conversation is None:
                raise AppError(
                    ErrorCategory.CONVERSATION_NOT_FOUND,
                    "Widget conversation binding is missing its conversation.",
                )
            return conversation, existing

        try:
            with self.db.begin_nested():
                conversation = Conversation(
                    workspace_id=workspace.id,
                    expert_id=expert_id,
                    user_id=None,
                    source=ConversationSource.WIDGET.value,
                    title=None,
                )
                self.conversations.create(conversation)
                binding = WidgetConversationBinding(
                    workspace_id=workspace.id,
                    widget_instance_id=widget.id,
                    conversation_id=conversation.id,
                    session_id=session_id,
                    expert_id=expert_id,
                )
                self.db.add(binding)
                self.db.flush()
        except IntegrityError:
            # Concurrent first message lost the unique race — reload winner.
            existing = self._get_session_binding(
                workspace_id=workspace.id,
                widget_id=widget.id,
                session_id=session_id,
                expert_id=expert_id,
                for_update=True,
            )
            if existing is None:
                raise AppError(
                    ErrorCategory.CONVERSATION_BUSY,
                    "This chat is busy processing another message.",
                    retryable=True,
                )
            conversation = self.db.get(Conversation, existing.conversation_id)
            if conversation is None:
                raise AppError(
                    ErrorCategory.CONVERSATION_NOT_FOUND,
                    "Widget conversation binding is missing its conversation.",
                )
            return conversation, existing
        return conversation, binding

    def _get_session_binding(
        self,
        *,
        workspace_id: uuid.UUID,
        widget_id: uuid.UUID,
        session_id: str,
        expert_id: uuid.UUID,
        for_update: bool = False,
    ) -> WidgetConversationBinding | None:
        stmt = select(WidgetConversationBinding).where(
            WidgetConversationBinding.workspace_id == workspace_id,
            WidgetConversationBinding.widget_instance_id == widget_id,
            WidgetConversationBinding.session_id == session_id,
            WidgetConversationBinding.expert_id == expert_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def _history_payload(
        self,
        conversation_id: uuid.UUID,
        *,
        before_message_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        limit = max(0, int(self.settings.widget_chat_history_max_messages))
        if limit == 0:
            return []
        rows = self.conversations.list_history_for_rag(
            conversation_id,
            before_message_id=before_message_id,
            limit=limit,
        )
        cutoff = self.retention.cutoff
        return [
            {"role": m.role, "content": m.content or ""}
            for m in rows
            if (m.content or "").strip() and self._message_within_ttl(m.created_at, cutoff)
        ]

    @staticmethod
    def _message_within_ttl(created_at: datetime | None, cutoff: datetime) -> bool:
        if created_at is None:
            return False
        when = created_at if created_at.tzinfo is not None else created_at.replace(
            tzinfo=timezone.utc
        )
        return when >= cutoff

    def cors_origin_for_options(
        self,
        widget_id: uuid.UUID,
        *,
        origin_header: str | None,
        referer: str | None,
    ) -> str | None:
        row = self.db.get(WidgetInstance, widget_id)
        if row is None or row.status != WidgetInstanceStatus.ACTIVE.value:
            return None
        try:
            return self._enforce_origin(row, origin_header, referer)
        except AppError:
            return None

    def _app(self) -> CatalogApp:
        app = self.catalog.get_app_by_slug(APP_SLUG)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "Chat Widget app not found.")
        return app

    def _require_active_installation(self, workspace_id: uuid.UUID) -> AppInstallation:
        installation = self.catalog.get_installation_by_app(workspace_id, self._app().id)
        if installation is None or installation.status != AppInstallationStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.APP_NOT_INSTALLED,
                "Install Chat Widget before configuring it.",
            )
        return installation

    def _get_by_installation(
        self, workspace_id: uuid.UUID, installation_id: uuid.UUID
    ) -> WidgetInstance | None:
        return self.db.scalar(
            select(WidgetInstance).where(
                WidgetInstance.workspace_id == workspace_id,
                WidgetInstance.app_installation_id == installation_id,
            )
        )

    def _count_active_widgets(self, workspace_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(WidgetInstance)
                .where(
                    WidgetInstance.workspace_id == workspace_id,
                    WidgetInstance.status == WidgetInstanceStatus.ACTIVE.value,
                )
            )
            or 0
        )

    def _create_instance(
        self, workspace_id: uuid.UUID, installation_id: uuid.UUID
    ) -> WidgetInstance:
        limit = int(
            self.entitlements.get(
                workspace_id, app_slug=APP_SLUG, key="widgets", default=1
            )
            or 1
        )
        if self._count_active_widgets(workspace_id) >= limit:
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Widget limit reached for this plan.",
                details={"limit": limit},
            )
        row = WidgetInstance(
            workspace_id=workspace_id,
            app_installation_id=installation_id,
            status=WidgetInstanceStatus.ACTIVE.value,
            title=_DEFAULT_TITLE,
            greeting=_DEFAULT_GREETING_AR,
            locale="ar",
            position="bottom-right",
            primary_color="#0e2f44",
            text_color="#f2f2f2",
            allowed_origins=None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _require_ready_expert(self, workspace: Workspace, expert_id: uuid.UUID) -> Expert:
        pairs = self.experts.list_for_workspace(workspace)
        for expert, _ownership in pairs:
            if expert.id == expert_id:
                if expert.status != ExpertStatus.READY.value:
                    raise AppError(
                        ErrorCategory.EXPERT_NOT_READY,
                        "Expert is not ready.",
                    )
                return expert
        raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")

    def _require_public_widget(self, widget_id: uuid.UUID) -> WidgetInstance:
        row = self.db.get(WidgetInstance, widget_id)
        if row is None or row.status != WidgetInstanceStatus.ACTIVE.value:
            raise AppError(ErrorCategory.NOT_FOUND, "Widget not found.")
        try:
            self.access.require_active(row.workspace_id, app_slug=APP_SLUG)
        except AppError as exc:
            if exc.category in (
                ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
                ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
                ErrorCategory.APP_BILLING_REQUIRED,
            ):
                raise
            raise AppError(ErrorCategory.NOT_FOUND, "Widget not found.") from exc
        installation = self.db.get(AppInstallation, row.app_installation_id)
        if installation is None or installation.status != AppInstallationStatus.ACTIVE.value:
            raise AppError(ErrorCategory.NOT_FOUND, "Widget not found.")
        return row

    def _enforce_origin(
        self,
        row: WidgetInstance,
        origin_header: str | None,
        referer: str | None,
    ) -> str | None:
        allowed = row.allowed_origins if isinstance(row.allowed_origins, list) else None
        req_origin = request_origin(origin_header, referer)
        if not origin_allowed(allowed, req_origin):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Origin is not allowed for this widget.",
            )
        if not allowed:
            return req_origin
        return req_origin

    def _embed_script_url(self) -> str:
        base = self.settings.app_url.rstrip("/")
        return f"{base}/geem-widget.js"

    def _embed_html(self, row: WidgetInstance) -> str:
        script_url = self._embed_script_url()
        locale = row.locale or "ar"
        return (
            f'<script\n'
            f'  src="{script_url}"\n'
            f'  data-widget-id="{row.id}"\n'
            f'  data-locale="{locale}"\n'
            f'  async\n'
            f'></script>'
        )

    def _to_out(self, row: WidgetInstance) -> WidgetInstanceOut:
        expert_out: WidgetExpertOut | None = None
        if row.expert_id is not None:
            expert = self.db.get(Expert, row.expert_id)
            if expert is not None:
                expert_out = WidgetExpertOut(
                    id=expert.id,
                    name=expert.name,
                    status=expert.status,
                )
        origins = row.allowed_origins if isinstance(row.allowed_origins, list) else []
        return WidgetInstanceOut(
            id=row.id,
            status=row.status,
            expert_id=row.expert_id,
            expert=expert_out,
            title=row.title,
            subtitle=row.subtitle,
            greeting=row.greeting,
            logo_url=row.logo_url,
            locale=row.locale,
            position=row.position,
            primary_color=row.primary_color,
            text_color=row.text_color,
            allowed_origins=[str(o) for o in origins],
            embed_script_url=self._embed_script_url(),
            embed_html=self._embed_html(row),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
