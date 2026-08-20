"""Chat Widget business logic."""

from __future__ import annotations

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
from app.usage.metered import MeteredWorkspaceGeneration
from app.widgets.retention import WidgetRetentionService
from app.workspaces.lifecycle import require_active_workspace
from app.workspaces.models import Workspace, WorkspaceMembership
from app.widgets.models import (
    WidgetConversationBinding,
    WidgetInstance,
    WidgetInstanceStatus,
)
from app.widgets.origins import normalize_origins_list, origin_allowed, request_origin
from app.widgets.schemas import (
    WidgetBootstrapOut,
    WidgetExpertOut,
    WidgetInstanceOut,
    WidgetMessageOut,
    WidgetUpdateIn,
)
from app.widgets.session_tokens import (
    mint_session_token,
    parse_bare_session_uuid,
    parse_session_token,
)

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
        if "allowed_origins" in data:
            row.allowed_origins = normalize_origins_list(data.pop("allowed_origins"))
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
