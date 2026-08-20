"""Platform Admin Workspace Geem billing orchestration (Phase 12C).

Orchestrates existing PlanService / SubscriptionService / CreditService /
EntitlementService. Does not touch App Store commerce.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, record_audit
from app.billing.models import Plan, PlanStatus
from app.billing.money import require_sar
from app.billing.service import BOOTSTRAP_PLAN_METADATA, PlanService, SubscriptionService
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import (
    ENTITLEMENT_DISPLAY_ORDER,
    EntitlementKey,
    EntitlementValueType,
    entitlement_display_sort_key,
)
from app.entitlements.service import EntitlementService
from app.entitlements.values import entitlement_value_from_row
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.repository import PlatformAdminRepository
from app.platform_admin.schemas import (
    PlatformCreditGrantRequest,
    PlatformCreditGrantResponse,
    PlatformCreditHistoryResponse,
    PlatformCreditLedgerItemOut,
    PlatformEntitlementCatalogItem,
    PlatformEntitlementCatalogResponse,
    PlatformEntitlementItemOut,
    PlatformPlanCreateRequest,
    PlatformPlanDetailOut,
    PlatformPlanEntitlementOut,
    PlatformPlanLifecycleRequest,
    PlatformPlanListItem,
    PlatformPlanListResponse,
    PlatformPlanUpdateRequest,
    PlatformSubscriptionAssignRequest,
    PlatformSubscriptionDetailOut,
    PlatformSubscriptionHistoryItem,
    PlatformSubscriptionHistoryResponse,
    PlatformUsageMeterOut,
    PlatformWorkspaceCreditsOut,
    PlatformWorkspaceEntitlementsOut,
    PlatformWorkspaceUsageOut,
)
from app.usage.credits import CreditService
from app.usage.history import VISIBLE_CREDIT_KINDS
from app.usage.metrics import CreditLedgerEntryType
from app.usage.models import CreditLedgerEntry
from app.usage.summary import UsageSummaryService
from app.workspaces.models import Workspace, WorkspaceKind

ENTITLEMENT_UNITS: dict[str, str] = {
    EntitlementKey.AI_TOKENS_DAILY.value: "tokens",
    EntitlementKey.AI_TOKENS_WEEKLY.value: "tokens",
    EntitlementKey.AI_TOKENS_MONTHLY.value: "tokens",
    EntitlementKey.EXPERTS_LIMIT.value: "experts",
    EntitlementKey.STORAGE_BYTES.value: "bytes",
    EntitlementKey.API_REQUESTS_PER_MINUTE.value: "requests_per_minute",
}

REQUIRED_PLAN_ENTITLEMENT_KEYS: tuple[str, ...] = tuple(ENTITLEMENT_DISPLAY_ORDER)


class PlatformAdminBillingService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = PlatformAdminRepository(db)
        self.plans = PlanService(db, self.settings)
        self.subscriptions = SubscriptionService(db, self.settings)
        self.credits = CreditService(db, self.settings)
        self.entitlements = EntitlementService(db, self.settings)
        self.usage = UsageSummaryService(db, self.settings)

    # --- Entitlement catalog ---

    def entitlement_catalog(self, actor: User) -> PlatformEntitlementCatalogResponse:
        require_platform_admin_user(actor)
        items = [
            PlatformEntitlementCatalogItem(
                key=key,
                value_type=EntitlementValueType.INTEGER.value,
                unit=ENTITLEMENT_UNITS.get(key, "integer"),
            )
            for key in ENTITLEMENT_DISPLAY_ORDER
        ]
        return PlatformEntitlementCatalogResponse(items=items)

    # --- Plans ---

    def list_plans(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        currency: str | None = None,
    ) -> PlatformPlanListResponse:
        require_platform_admin_user(actor)
        status_clean = self._normalize_plan_status_filter(status)
        total = self.plans.plans.count_admin(
            search=search, status=status_clean, currency=currency
        )
        rows = self.plans.plans.list_admin(
            limit=limit,
            offset=offset,
            search=search,
            status=status_clean,
            currency=currency,
        )
        counts = self.plans.plans.count_active_subscribers_batch([p.id for p in rows])
        items = [
            self._plan_list_item(plan, subscriber_count=counts.get(plan.id, 0))
            for plan in rows
        ]
        return PlatformPlanListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def get_plan(self, actor: User, plan_id: uuid.UUID) -> PlatformPlanDetailOut:
        require_platform_admin_user(actor)
        plan = self.plans.plans.get_by_id(plan_id)
        if plan is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Plan not found.")
        return self._plan_detail(plan)

    def create_plan(
        self, actor: User, body: PlatformPlanCreateRequest
    ) -> PlatformPlanDetailOut:
        require_platform_admin_user(actor)
        entitlements = self._entitlements_map(body.entitlements, require_all=True)
        currency = require_sar(body.currency)
        plan = self.plans.create_plan(
            code=body.code,
            name=body.name,
            description=body.description,
            entitlements=entitlements,
            price_amount=body.price_amount,
            currency=currency,
            extra={"source": "platform_admin"},
        )
        extra = dict(plan.extra or {})
        extra["source"] = "platform_admin"
        extra["commercial"] = self._is_commercial(plan)
        plan.extra = extra
        self.db.flush()
        record_audit(
            self.db,
            action=AuditAction.PLAN_CREATED,
            entity_type=AuditEntityType.PLAN,
            entity_id=plan.id,
            actor_user_id=actor.id,
            metadata={
                "plan_id": str(plan.id),
                "code": plan.code,
                "name": plan.name,
                "status": plan.status,
                "price_amount": self._price_str(plan.price_amount),
                "currency": plan.currency,
                "entitlements": {k: entitlements[k] for k in sorted(entitlements)},
            },
            allowlist=frozenset(
                {
                    "plan_id",
                    "code",
                    "name",
                    "status",
                    "price_amount",
                    "currency",
                    "entitlements",
                }
            ),
        )
        self.db.commit()
        security_log("plan.create", actor_id=str(actor.id), plan_id=str(plan.id))
        return self._plan_detail(self.plans.plans.get_by_id(plan.id) or plan)

    def update_plan(
        self,
        actor: User,
        plan_id: uuid.UUID,
        body: PlatformPlanUpdateRequest,
    ) -> PlatformPlanDetailOut:
        require_platform_admin_user(actor)
        plan = self.plans.plans.get_by_id(plan_id)
        if plan is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Plan not found.")

        before = self._plan_snapshot(plan)
        entitlements_map: dict[str, int] | None = None
        if body.entitlements is not None:
            entitlements_map = self._entitlements_map(body.entitlements, require_all=False)
            subscriber_count = self.plans.plans.count_active_subscribers(plan.id)
            if subscriber_count > 0:
                reason = (body.reason or "").strip()
                if not reason:
                    raise AppError(
                        ErrorCategory.VALIDATION,
                        "A reason is required when changing entitlements on an in-use plan.",
                    )

        update_price = body.clear_price or body.price_amount is not None
        currency = require_sar(body.currency) if body.currency is not None else None
        updated = self.plans.update_plan(
            plan_id,
            name=body.name,
            description=body.description,
            price_amount=body.price_amount,
            clear_price=body.clear_price,
            currency=currency,
            entitlements=entitlements_map,
            update_price=update_price,
        )
        if not self._is_bootstrap(updated):
            extra = dict(updated.extra or {})
            extra["commercial"] = self._is_commercial(updated)
            if extra.get("source") is None:
                extra["source"] = "platform_admin"
            updated.extra = extra
            self.db.flush()
        after = self._plan_snapshot(updated)
        subscriber_count = self.plans.plans.count_active_subscribers(updated.id)
        entitlements_changed = before["entitlements"] != after["entitlements"]
        action = (
            AuditAction.PLAN_ENTITLEMENTS_UPDATED
            if entitlements_changed
            else AuditAction.PLAN_UPDATED
        )
        meta: dict[str, Any] = {
            "plan_id": str(updated.id),
            "code": updated.code,
            "before": before,
            "after": after,
            "subscriber_count": subscriber_count,
        }
        allow = {"plan_id", "code", "before", "after", "subscriber_count"}
        if body.reason and body.reason.strip():
            meta["reason"] = body.reason.strip()
            allow.add("reason")
        record_audit(
            self.db,
            action=action,
            entity_type=AuditEntityType.PLAN,
            entity_id=updated.id,
            actor_user_id=actor.id,
            metadata=meta,
            allowlist=frozenset(allow),
        )
        self.db.commit()
        security_log("plan.update", actor_id=str(actor.id), plan_id=str(updated.id))
        return self._plan_detail(self.plans.plans.get_by_id(updated.id) or updated)

    def activate_plan(
        self,
        actor: User,
        plan_id: uuid.UUID,
        body: PlatformPlanLifecycleRequest,
    ) -> PlatformPlanDetailOut:
        require_platform_admin_user(actor)
        plan = self.plans.activate_plan(plan_id)
        record_audit(
            self.db,
            action=AuditAction.PLAN_ACTIVATED,
            entity_type=AuditEntityType.PLAN,
            entity_id=plan.id,
            actor_user_id=actor.id,
            metadata={
                "plan_id": str(plan.id),
                "code": plan.code,
                "status": plan.status,
                "reason": body.reason.strip(),
            },
            allowlist=frozenset({"plan_id", "code", "status", "reason"}),
        )
        self.db.commit()
        return self._plan_detail(self.plans.plans.get_by_id(plan.id) or plan)

    def deactivate_plan(
        self,
        actor: User,
        plan_id: uuid.UUID,
        body: PlatformPlanLifecycleRequest,
    ) -> PlatformPlanDetailOut:
        require_platform_admin_user(actor)
        plan = self.plans.plans.get_by_id(plan_id)
        if plan is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Plan not found.")
        if self._is_bootstrap(plan):
            raise AppError(
                ErrorCategory.VALIDATION,
                "The bootstrap/dev plan cannot be deactivated.",
                details={"code": plan.code},
            )
        plan = self.plans.archive_plan(plan_id)
        record_audit(
            self.db,
            action=AuditAction.PLAN_DEACTIVATED,
            entity_type=AuditEntityType.PLAN,
            entity_id=plan.id,
            actor_user_id=actor.id,
            metadata={
                "plan_id": str(plan.id),
                "code": plan.code,
                "status": plan.status,
                "reason": body.reason.strip(),
                "subscriber_count": self.plans.plans.count_active_subscribers(plan.id),
            },
            allowlist=frozenset(
                {"plan_id", "code", "status", "reason", "subscriber_count"}
            ),
        )
        self.db.commit()
        return self._plan_detail(self.plans.plans.get_by_id(plan.id) or plan)

    # --- Workspace subscription / entitlements ---

    def get_workspace_subscription(
        self, actor: User, workspace_id: uuid.UUID
    ) -> PlatformSubscriptionDetailOut | None:
        require_platform_admin_user(actor)
        workspace = self._require_workspace(workspace_id)
        sub = self.subscriptions.get_current(workspace.id)
        if sub is None or sub.plan is None:
            return None
        return self._subscription_detail(sub)

    def list_workspace_subscriptions(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> PlatformSubscriptionHistoryResponse:
        require_platform_admin_user(actor)
        workspace = self._require_workspace(workspace_id)
        total = self.subscriptions.subscriptions.count_for_workspace(workspace.id)
        rows = self.subscriptions.subscriptions.list_for_workspace_paginated(
            workspace.id, limit=limit, offset=offset
        )
        items = [
            PlatformSubscriptionHistoryItem(
                subscription_id=sub.id,
                status=sub.status,
                plan_id=sub.plan_id,
                plan_code=sub.plan.code if sub.plan else "",
                plan_name=sub.plan.name if sub.plan else "",
                starts_at=sub.starts_at,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                ends_at=sub.ends_at,
                source=self._subscription_source(sub),
                created_at=sub.created_at,
            )
            for sub in rows
        ]
        return PlatformSubscriptionHistoryResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def assign_workspace_subscription(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        body: PlatformSubscriptionAssignRequest,
    ) -> PlatformSubscriptionDetailOut:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        current = self.subscriptions.get_current(workspace.id)
        old_plan_id = str(current.plan_id) if current else None
        old_plan_code = current.plan.code if current and current.plan else None

        plan = self.plans.plans.get_by_id(body.plan_id)
        if plan is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Plan not found.")
        if plan.status != PlanStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.PLAN_UNAVAILABLE,
                "Plan is not active.",
                details={"plan_id": str(plan.id), "status": plan.status},
            )
        if self._is_bootstrap(plan):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Bootstrap/dev plans cannot be assigned through Platform Admin.",
                details={"code": plan.code},
            )

        assigned = self.subscriptions.assign_plan(
            workspace.id,
            plan.id,
            extra={
                "source": "platform_admin",
                "reason": body.reason.strip(),
                "actor_user_id": str(actor.id),
            },
        )
        action = (
            AuditAction.WORKSPACE_SUBSCRIPTION_CHANGED
            if old_plan_id and old_plan_id != str(plan.id)
            else AuditAction.WORKSPACE_SUBSCRIPTION_ASSIGNED
        )
        record_audit(
            self.db,
            action=action,
            entity_type=AuditEntityType.SUBSCRIPTION,
            entity_id=assigned.id,
            workspace_id=workspace.id,
            actor_user_id=actor.id,
            metadata={
                "workspace_id": str(workspace.id),
                "subscription_id": str(assigned.id),
                "old_plan_id": old_plan_id,
                "old_plan_code": old_plan_code,
                "new_plan_id": str(plan.id),
                "new_plan_code": plan.code,
                "reason": body.reason.strip(),
            },
            allowlist=frozenset(
                {
                    "workspace_id",
                    "subscription_id",
                    "old_plan_id",
                    "old_plan_code",
                    "new_plan_id",
                    "new_plan_code",
                    "reason",
                }
            ),
        )
        self.db.commit()
        security_log(
            "workspace.subscription_assign",
            actor_id=str(actor.id),
            workspace_id=str(workspace.id),
            plan_id=str(plan.id),
        )
        refreshed = self.subscriptions.get_current(workspace.id) or assigned
        return self._subscription_detail(refreshed)

    def get_workspace_entitlements(
        self, actor: User, workspace_id: uuid.UUID
    ) -> PlatformWorkspaceEntitlementsOut:
        require_platform_admin_user(actor)
        workspace = self._require_workspace(workspace_id)
        if workspace.kind == WorkspaceKind.SYSTEM.value:
            raise AppError(
                ErrorCategory.SYSTEM_WORKSPACE_NOT_BILLABLE,
                "System Workspaces do not have tenant commercial entitlements.",
            )
        resolved = self.entitlements.get_effective_entitlements(workspace.id)
        items = [
            PlatformEntitlementItemOut(
                key=key,
                value=item.as_python(),
                value_type=item.value_type.value,
            )
            for key, item in sorted(
                resolved.items.items(), key=lambda pair: entitlement_display_sort_key(pair[0])
            )
        ]
        return PlatformWorkspaceEntitlementsOut(
            workspace_id=resolved.workspace_id,
            subscription_id=resolved.subscription_id,
            plan_id=resolved.plan_id,
            plan_code=resolved.plan_code,
            plan_name=resolved.plan_name,
            plan_status=resolved.plan_status,
            items=items,
        )

    def get_workspace_usage(
        self, actor: User, workspace_id: uuid.UUID
    ) -> PlatformWorkspaceUsageOut:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        summary = self.usage.summarize(workspace.id)

        def _meter(snap) -> PlatformUsageMeterOut:
            return PlatformUsageMeterOut(
                limit=snap.limit,
                used=snap.used,
                reserved=snap.reserved,
                remaining=snap.remaining,
                period_start=snap.period_start,
                period_end=snap.period_end,
            )

        return PlatformWorkspaceUsageOut(
            ai_tokens_daily=_meter(summary.ai_daily),
            ai_tokens_weekly=_meter(summary.ai_weekly),
            ai_tokens_monthly=_meter(summary.ai_monthly),
            experts=_meter(summary.experts),
            storage_bytes=_meter(summary.storage),
            credit_balance=summary.credit_balance,
        )

    # --- Credits ---

    def get_workspace_credits(
        self, actor: User, workspace_id: uuid.UUID
    ) -> PlatformWorkspaceCreditsOut:
        require_platform_admin_user(actor)
        workspace = self._require_workspace(workspace_id)
        self.credits.ensure_account(workspace.id)
        balance = self.credits.get_balance(workspace.id)
        recent = self.credits.list_ledger(
            workspace.id,
            limit=20,
            offset=0,
            entry_types=list(VISIBLE_CREDIT_KINDS.keys()),
        )
        return PlatformWorkspaceCreditsOut(
            workspace_id=workspace.id,
            balance=balance,
            recent=[self._ledger_item(row) for row in recent],
        )

    def list_workspace_credit_history(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> PlatformCreditHistoryResponse:
        require_platform_admin_user(actor)
        workspace = self._require_workspace(workspace_id)
        types = list(VISIBLE_CREDIT_KINDS.keys())
        total = self.credits.count_ledger(workspace.id, entry_types=types)
        rows = self.credits.list_ledger(
            workspace.id, limit=limit, offset=offset, entry_types=types
        )
        return PlatformCreditHistoryResponse(
            items=[self._ledger_item(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def grant_workspace_credits(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        body: PlatformCreditGrantRequest,
    ) -> PlatformCreditGrantResponse:
        require_platform_admin_user(actor)
        workspace = self._require_tenant_workspace(workspace_id)
        if body.amount <= 0:
            raise AppError(ErrorCategory.VALIDATION, "Credit amount must be a positive integer.")
        reason = body.reason.strip()
        if not reason:
            raise AppError(ErrorCategory.VALIDATION, "A reason is required to grant credits.")

        request_id = (body.request_id or "").strip() or f"platform-credit-grant:{uuid.uuid4()}"
        if len(request_id) > 128:
            raise AppError(ErrorCategory.VALIDATION, "request_id must be at most 128 characters.")

        existing = self.credits.repo.get_ledger_by_request_id(workspace.id, request_id)
        entry = self.credits.append(
            workspace.id,
            entry_type=CreditLedgerEntryType.GRANT,
            amount=int(body.amount),
            request_id=request_id,
            source_type="platform_admin",
            source_id=str(actor.id),
            extra={"reason": reason, "actor_user_id": str(actor.id)},
        )
        replay = existing is not None
        if not replay:
            record_audit(
                self.db,
                action=AuditAction.WORKSPACE_CREDIT_GRANTED,
                entity_type=AuditEntityType.CREDIT_LEDGER_ENTRY,
                entity_id=entry.id,
                workspace_id=workspace.id,
                actor_user_id=actor.id,
                metadata={
                    "workspace_id": str(workspace.id),
                    "amount": int(body.amount),
                    "ledger_entry_id": str(entry.id),
                    "request_id": request_id,
                    "reason": reason,
                },
                allowlist=frozenset(
                    {
                        "workspace_id",
                        "amount",
                        "ledger_entry_id",
                        "request_id",
                        "reason",
                    }
                ),
            )
            self.db.commit()
            security_log(
                "workspace.credit_grant",
                actor_id=str(actor.id),
                workspace_id=str(workspace.id),
                amount=int(body.amount),
            )
        else:
            self.db.commit()

        return PlatformCreditGrantResponse(
            workspace_id=workspace.id,
            balance=self.credits.get_balance(workspace.id),
            entry=self._ledger_item(entry),
            idempotent_replay=replay,
        )

    # --- helpers ---

    def _require_workspace(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = self.repo.get_workspace(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        return workspace

    def _require_tenant_workspace(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = self._require_workspace(workspace_id)
        if workspace.kind == WorkspaceKind.SYSTEM.value:
            raise AppError(
                ErrorCategory.SYSTEM_WORKSPACE_NOT_BILLABLE,
                "System Workspaces cannot receive tenant commercial subscriptions or credit grants.",
            )
        return workspace

    @staticmethod
    def _normalize_plan_status_filter(status: str | None) -> str | None:
        if not status:
            return None
        clean = status.strip().lower()
        if clean in {"active", "archived"}:
            return clean
        if clean in {"inactive", "deactivated"}:
            return PlanStatus.ARCHIVED.value
        raise AppError(ErrorCategory.VALIDATION, "Invalid plan status filter.")

    def _entitlements_map(
        self,
        rows: list,
        *,
        require_all: bool,
    ) -> dict[str, int]:
        mapped: dict[str, int] = {}
        for row in rows:
            key = row.key.strip()
            try:
                parsed = EntitlementKey(key)
            except ValueError as exc:
                raise AppError(
                    ErrorCategory.ENTITLEMENT_INVALID,
                    f"Unknown entitlement key: {key}",
                    details={"key": key},
                ) from exc
            if not isinstance(row.value, int) or isinstance(row.value, bool):
                raise AppError(
                    ErrorCategory.ENTITLEMENT_INVALID,
                    f"Entitlement '{parsed.value}' must be an integer.",
                    details={"key": parsed.value},
                )
            if row.value < 0:
                raise AppError(
                    ErrorCategory.ENTITLEMENT_INVALID,
                    f"Entitlement '{parsed.value}' must be non-negative.",
                    details={"key": parsed.value},
                )
            mapped[parsed.value] = int(row.value)
        if require_all:
            missing = [k for k in REQUIRED_PLAN_ENTITLEMENT_KEYS if k not in mapped]
            if missing:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Plan create requires all canonical entitlement keys.",
                    details={"missing": missing},
                )
        return mapped

    def _plan_list_item(self, plan: Plan, *, subscriber_count: int) -> PlatformPlanListItem:
        return PlatformPlanListItem(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            status=plan.status,
            price_amount=self._price_str(plan.price_amount),
            currency=plan.currency,
            is_bootstrap=self._is_bootstrap(plan),
            is_commercial=self._is_commercial(plan),
            subscriber_count=subscriber_count,
            entitlements=self._entitlement_outs(plan),
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    def _plan_detail(self, plan: Plan) -> PlatformPlanDetailOut:
        return PlatformPlanDetailOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            status=plan.status,
            price_amount=self._price_str(plan.price_amount),
            currency=plan.currency,
            is_bootstrap=self._is_bootstrap(plan),
            is_commercial=self._is_commercial(plan),
            subscriber_count=self.plans.plans.count_active_subscribers(plan.id),
            entitlements=self._entitlement_outs(plan),
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    def _entitlement_outs(self, plan: Plan) -> list[PlatformPlanEntitlementOut]:
        rows = list(plan.entitlements or [])
        rows.sort(key=lambda row: entitlement_display_sort_key(row.key))
        outs: list[PlatformPlanEntitlementOut] = []
        for row in rows:
            parsed = entitlement_value_from_row(
                key=row.key, raw=row.value, value_type=row.value_type
            )
            outs.append(
                PlatformPlanEntitlementOut(
                    key=row.key,
                    value=parsed.as_python(),
                    value_type=parsed.value_type.value,
                )
            )
        return outs

    def _plan_snapshot(self, plan: Plan) -> dict[str, Any]:
        return {
            "name": plan.name,
            "description": plan.description,
            "status": plan.status,
            "price_amount": self._price_str(plan.price_amount),
            "currency": plan.currency,
            "entitlements": {
                item.key: item.value for item in self._entitlement_outs(plan)
            },
        }

    def _is_bootstrap(self, plan: Plan) -> bool:
        code = self.settings.bootstrap_plan_code.strip().lower()
        meta = plan.extra or {}
        return plan.code == code or meta.get("kind") == BOOTSTRAP_PLAN_METADATA["kind"]

    @staticmethod
    def _is_commercial(plan: Plan) -> bool:
        meta = plan.extra or {}
        if meta.get("commercial") is False or meta.get("kind") == "bootstrap_dev":
            return False
        return plan.price_amount is not None and plan.price_amount > 0

    @staticmethod
    def _price_str(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value:.2f}"

    def _subscription_detail(self, sub) -> PlatformSubscriptionDetailOut:
        plan = sub.plan
        return PlatformSubscriptionDetailOut(
            subscription_id=sub.id,
            status=sub.status,
            plan_id=sub.plan_id,
            plan_code=plan.code if plan else "",
            plan_name=plan.name if plan else "",
            plan_status=plan.status if plan else "",
            starts_at=sub.starts_at,
            current_period_start=sub.current_period_start,
            current_period_end=sub.current_period_end,
            ends_at=sub.ends_at,
            source=self._subscription_source(sub),
            created_at=sub.created_at,
        )

    @staticmethod
    def _subscription_source(sub) -> str | None:
        meta = sub.extra or {}
        source = meta.get("source")
        return str(source) if source else None

    @staticmethod
    def _ledger_item(row: CreditLedgerEntry) -> PlatformCreditLedgerItemOut:
        meta = row.extra or {}
        reason = meta.get("reason")
        return PlatformCreditLedgerItemOut(
            id=row.id,
            entry_type=row.entry_type,
            amount=int(row.amount),
            remaining_amount=(
                int(row.remaining_amount) if row.remaining_amount is not None else None
            ),
            request_id=row.request_id,
            source_type=row.source_type,
            source_id=row.source_id,
            reason=str(reason) if reason else None,
            created_at=row.created_at,
        )
