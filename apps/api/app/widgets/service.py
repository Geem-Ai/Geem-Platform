"""Chat Widget business logic."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
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
from app.conversations.turn import ChatTurnExecutor
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import Expert, ExpertStatus
from app.experts.service import ExpertService
from app.usage.metered import MeteredWorkspaceGeneration
from app.widgets.models import WidgetInstance, WidgetInstanceStatus
from app.widgets.origins import normalize_origins_list, origin_allowed, request_origin
from app.widgets.schemas import (
    WidgetBootstrapOut,
    WidgetExpertOut,
    WidgetInstanceOut,
    WidgetMessageOut,
    WidgetUpdateIn,
)
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
        self._require_ready_expert(workspace, row.expert_id)

        turn_id = str(uuid.uuid4())
        executor = ChatTurnExecutor(self.db, settings=self.settings)
        question = executor.validate_message(message)
        executor.authorize_expert(
            workspace=workspace,
            expert_id=row.expert_id,
            actor_id=None,
        )
        invocation = ChatInvocationContext.widget(
            workspace_id=workspace.id,
            widget_id=row.id,
            expert_id=row.expert_id,
            request_id=turn_id,
        )
        meter = MeteredWorkspaceGeneration(
            self.db,
            workspace_id=workspace.id,
            user_id=None,
            expert_id=row.expert_id,
            conversation_id=None,
            message_id=None,
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
            )
        except Exception:
            meter.release()
            raise

        return (
            WidgetMessageOut(
                answer=str(result.get("answer") or ""),
                session_id=session_id,
            ),
            cors_origin,
        )

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
