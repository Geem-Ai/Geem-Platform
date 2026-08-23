"""Platform operational dashboard aggregates (Phase 12G)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps_catalog.models import (
    AppInstallation,
    AppLicense,
    AppLicenseStatus,
    AppStatus,
    AppSubscription,
    AppSubscriptionStatus,
    CatalogApp,
)
from app.billing.models import Purchase, PurchaseStatus, Subscription, SubscriptionStatus
from app.billing.repository import PaymentGatewayConfigRepository
from app.experts.models import Expert, ExpertType, ExpertVisibility
from app.identity.models import User, UserStatus
from app.platform_admin.audit_logs import PlatformAuditLogsService
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.repository import PlatformAdminRepository
from app.platform_admin.schemas import (
    PlatformDashboardAppsOut,
    PlatformDashboardBillingOut,
    PlatformDashboardExpertsOut,
    PlatformDashboardGatewayOut,
    PlatformDashboardSummaryOut,
    PlatformDashboardUsageOut,
    PlatformDashboardUsersOut,
    PlatformDashboardWorkspacesOut,
)
from app.platform_admin.usage_analytics import PlatformUsageAnalyticsService
from app.usage.models import CreditAccount
from app.workspaces.models import Workspace, WorkspaceKind, WorkspaceStatus


class PlatformDashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PlatformAdminRepository(db)
        self.usage = PlatformUsageAnalyticsService(db)
        self.audit = PlatformAuditLogsService(db)

    def summary(self, actor: User) -> PlatformDashboardSummaryOut:
        require_platform_admin_user(actor)
        now = datetime.now(UTC)
        period_start = now - timedelta(days=30)
        tenant_filter = [
            Workspace.kind == WorkspaceKind.TENANT.value,
            Workspace.deleted_at.is_(None),
        ]
        workspaces_total = self.repo.count_workspaces(kind=WorkspaceKind.TENANT.value)
        workspaces_active = self.repo.count_workspaces(
            kind=WorkspaceKind.TENANT.value, status=WorkspaceStatus.ACTIVE.value
        )
        workspaces_non_active = int(
            self.db.scalar(
                select(func.count())
                .select_from(Workspace)
                .where(
                    Workspace.kind == WorkspaceKind.TENANT.value,
                    Workspace.deleted_at.is_(None),
                    Workspace.status != WorkspaceStatus.ACTIVE.value,
                )
            )
            or 0
        )
        users_total = int(
            self.db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
            or 0
        )
        users_active = int(
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.deleted_at.is_(None), User.status == UserStatus.ACTIVE.value)
            )
            or 0
        )
        users_disabled = int(
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.deleted_at.is_(None), User.status == UserStatus.DISABLED.value)
            )
            or 0
        )
        experts_published = int(
            self.db.scalar(
                select(func.count())
                .select_from(Expert)
                .where(
                    Expert.type == ExpertType.PLATFORM.value,
                    Expert.deleted_at.is_(None),
                    Expert.visibility == ExpertVisibility.PLATFORM_PUBLISHED.value,
                )
            )
            or 0
        )
        experts_draft = int(
            self.db.scalar(
                select(func.count())
                .select_from(Expert)
                .where(
                    Expert.type == ExpertType.PLATFORM.value,
                    Expert.deleted_at.is_(None),
                    Expert.visibility != ExpertVisibility.PLATFORM_PUBLISHED.value,
                )
            )
            or 0
        )
        active_subscriptions = int(
            self.db.scalar(
                select(func.count())
                .select_from(Subscription)
                .join(Workspace, Workspace.id == Subscription.workspace_id)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    *tenant_filter,
                )
            )
            or 0
        )
        pending_purchases = int(
            self.db.scalar(
                select(func.count())
                .select_from(Purchase)
                .where(
                    Purchase.status.in_(
                        [PurchaseStatus.PENDING.value, PurchaseStatus.REDIRECTED.value]
                    )
                )
            )
            or 0
        )
        failed_purchases_30d = int(
            self.db.scalar(
                select(func.count())
                .select_from(Purchase)
                .where(
                    Purchase.status == PurchaseStatus.FAILED.value,
                    Purchase.created_at >= period_start,
                )
            )
            or 0
        )
        paid_stats = self.db.execute(
            select(func.count(), func.coalesce(func.sum(Purchase.amount), 0)).where(
                Purchase.status == PurchaseStatus.PAID.value,
                Purchase.paid_at.is_not(None),
                Purchase.paid_at >= period_start,
            )
        ).one()
        paid_count_30d = int(paid_stats[0] or 0)
        paid_volume_30d = str(paid_stats[1] or 0)
        apps_published = int(
            self.db.scalar(
                select(func.count())
                .select_from(CatalogApp)
                .where(CatalogApp.status == AppStatus.PUBLISHED.value)
            )
            or 0
        )
        app_subscriptions_active = int(
            self.db.scalar(
                select(func.count())
                .select_from(AppSubscription)
                .where(AppSubscription.status == AppSubscriptionStatus.ACTIVE.value)
            )
            or 0
        )
        app_licenses_active = int(
            self.db.scalar(
                select(func.count())
                .select_from(AppLicense)
                .where(AppLicense.status == AppLicenseStatus.ACTIVE.value)
            )
            or 0
        )
        app_installations = int(
            self.db.scalar(select(func.count()).select_from(AppInstallation)) or 0
        )
        credit_balance_total = int(
            self.db.scalar(
                select(func.coalesce(func.sum(CreditAccount.balance), 0))
                .select_from(CreditAccount)
                .join(Workspace, Workspace.id == CreditAccount.workspace_id)
                .where(*tenant_filter)
            )
            or 0
        )
        enabled_gateways = PaymentGatewayConfigRepository(self.db).list_enabled()
        gateway_row = enabled_gateways[0] if enabled_gateways else None
        gateway = None
        if gateway_row is not None:
            gateway = PlatformDashboardGatewayOut(
                gateway_config_id=gateway_row.id,
                code=gateway_row.code,
                enabled=gateway_row.enabled,
                test_mode=gateway_row.test_mode,
            )
        usage_window_30d = self.usage.sliding_range(days=30)
        recent = self.audit.recent_platform_activity(limit=8)
        return PlatformDashboardSummaryOut(
            workspaces=PlatformDashboardWorkspacesOut(
                total=workspaces_total,
                active=workspaces_active,
                disabled=workspaces_non_active,
            ),
            users=PlatformDashboardUsersOut(
                total=users_total,
                active=users_active,
                disabled=users_disabled,
            ),
            experts=PlatformDashboardExpertsOut(
                published=experts_published,
                draft=experts_draft,
            ),
            usage=PlatformDashboardUsageOut(
                billed_tokens_24h=self.usage.period_total_billed(hours=24),
                billed_tokens_7d=self.usage.period_total_billed(days=7),
                billed_tokens_30d=self.usage.period_total_billed(days=30),
                active_workspaces_30d=self.usage.active_workspaces(usage_window_30d),
                outstanding_credit_balance=credit_balance_total,
            ),
            billing=PlatformDashboardBillingOut(
                active_subscriptions=active_subscriptions,
                pending_purchases=pending_purchases,
                failed_purchases_30d=failed_purchases_30d,
                paid_purchase_count_30d=paid_count_30d,
                paid_purchase_volume_30d=paid_volume_30d,
            ),
            apps=PlatformDashboardAppsOut(
                published=apps_published,
                active_subscriptions=app_subscriptions_active,
                active_licenses=app_licenses_active,
                installations=app_installations,
            ),
            gateway=gateway,
            recent_activity=recent,
        )
