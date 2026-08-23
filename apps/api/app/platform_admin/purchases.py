"""Platform Admin global purchase operations (Phase 12F)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, record_audit
from app.billing.checkout import BillingService
from app.billing.gateways.config_schema import gateway_display_name
from app.billing.models import Purchase, PurchaseStatus
from app.billing.purchase_view import purchase_catalog_fields
from app.billing.repository import PurchaseRepository
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.schemas import (
    PlatformPurchaseActorOut,
    PlatformPurchaseDetailOut,
    PlatformPurchaseFulfillmentOut,
    PlatformPurchaseGatewayOut,
    PlatformPurchaseListItem,
    PlatformPurchaseListResponse,
    PlatformPurchaseReconcileResponse,
    PlatformPurchaseTargetOut,
    PlatformPurchaseWorkspaceOut,
)
from app.workspaces.models import Workspace

_RECONCILE_ELIGIBLE = frozenset(
    {
        PurchaseStatus.PENDING.value,
        PurchaseStatus.REDIRECTED.value,
    }
)


class PlatformAdminPurchasesService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.purchases = PurchaseRepository(db)
        self.billing = BillingService(db, self.settings)

    def list_purchases(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        workspace_id: uuid.UUID | None = None,
        status: str | None = None,
        kind: str | None = None,
        gateway: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> PlatformPurchaseListResponse:
        require_platform_admin_user(actor)
        status_clean = self._normalize_status(status)
        kind_clean = self._normalize_kind(kind)
        gateway_clean = gateway.strip().lower() if gateway else None
        total = self.purchases.count_platform(
            search=search,
            workspace_id=workspace_id,
            status=status_clean,
            kind=kind_clean,
            gateway_code=gateway_clean,
            created_from=created_from,
            created_to=created_to,
        )
        rows = self.purchases.list_platform(
            limit=limit,
            offset=offset,
            search=search,
            workspace_id=workspace_id,
            status=status_clean,
            kind=kind_clean,
            gateway_code=gateway_clean,
            created_from=created_from,
            created_to=created_to,
        )
        workspace_map = self._workspace_map([row.workspace_id for row in rows])
        actor_map = self._actor_map([row.actor_id for row in rows])
        items = [
            self._list_item(
                row,
                workspace=workspace_map.get(row.workspace_id),
                actor=actor_map.get(row.actor_id),
            )
            for row in rows
        ]
        return PlatformPurchaseListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_purchase(self, actor: User, purchase_id: uuid.UUID) -> PlatformPurchaseDetailOut:
        require_platform_admin_user(actor)
        purchase = self.purchases.get_by_id(purchase_id)
        if purchase is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Purchase not found.")
        workspace = self.db.get(Workspace, purchase.workspace_id)
        actor_row = self.db.get(User, purchase.actor_id)
        return self._detail(purchase, workspace=workspace, actor=actor_row)

    def reconcile_purchase(
        self,
        actor: User,
        purchase_id: uuid.UUID,
    ) -> PlatformPurchaseReconcileResponse:
        require_platform_admin_user(actor)
        peek = self.purchases.get_by_id(purchase_id)
        if peek is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Purchase not found.")
        prior_status = peek.status
        result = self.billing.reconcile_purchase(purchase_id)
        idempotent = prior_status == PurchaseStatus.PAID.value
        record_audit(
            self.db,
            action=AuditAction.PURCHASE_RECONCILED,
            entity_type=AuditEntityType.PURCHASE,
            entity_id=result.purchase.id,
            workspace_id=result.purchase.workspace_id,
            actor_user_id=actor.id,
            metadata={
                "purchase_id": str(result.purchase.id),
                "workspace_id": str(result.purchase.workspace_id),
                "gateway_config_id": str(result.purchase.payment_gateway_config_id),
                "prior_status": prior_status,
                "resulting_status": result.purchase.status,
                "fulfillment_applied": result.fulfillment_applied,
                "provider_status": result.provider_status,
            },
            allowlist=frozenset(
                {
                    "purchase_id",
                    "workspace_id",
                    "gateway_config_id",
                    "prior_status",
                    "resulting_status",
                    "fulfillment_applied",
                    "provider_status",
                }
            ),
        )
        self.db.commit()
        security_log(
            "purchase.reconcile",
            actor_id=str(actor.id),
            purchase_id=str(result.purchase.id),
            fulfillment_applied=result.fulfillment_applied,
        )
        workspace = self.db.get(Workspace, result.purchase.workspace_id)
        actor_row = self.db.get(User, result.purchase.actor_id)
        detail = self._detail(result.purchase, workspace=workspace, actor=actor_row)
        return PlatformPurchaseReconcileResponse(
            purchase=detail,
            prior_status=prior_status,
            resulting_status=result.purchase.status,
            fulfillment_applied=result.fulfillment_applied,
            provider_status=result.provider_status,
            idempotent_replay=idempotent,
        )

    def purchase_invoice(self, actor: User, purchase_id: uuid.UUID) -> tuple[bytes, str]:
        require_platform_admin_user(actor)
        from app.billing.invoices.service import InvoiceService

        purchase = self.purchases.get_by_id(purchase_id)
        if purchase is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Purchase not found.")
        workspace = self.db.get(Workspace, purchase.workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Purchase not found.")
        pdf, filename = InvoiceService(self.db, self.settings).pdf_for_workspace(
            workspace, purchase_id
        )
        self.db.commit()
        return pdf, filename

    def _list_item(
        self,
        purchase: Purchase,
        *,
        workspace: Workspace | None,
        actor: User | None,
    ) -> PlatformPurchaseListItem:
        config = purchase.gateway_config
        extra = purchase.extra or {}
        return PlatformPurchaseListItem(
            id=purchase.id,
            workspace=self._workspace_out(workspace, purchase.workspace_id),
            actor=self._actor_out(actor, purchase.actor_id),
            kind=purchase.kind,
            status=purchase.status,
            amount=f"{purchase.amount:.2f}",
            currency=purchase.currency,
            gateway_code=config.code if config else (extra.get("gateway_code") or ""),
            gateway_config_id=purchase.payment_gateway_config_id,
            cart_id=purchase.cart_id,
            tran_ref=purchase.provider_transaction_ref,
            target=self._target_out(purchase),
            paid_at=purchase.paid_at,
            created_at=purchase.created_at,
            updated_at=purchase.updated_at,
            reconcile_eligible=purchase.status in _RECONCILE_ELIGIBLE,
            invoice_available=purchase.status == PurchaseStatus.PAID.value,
        )

    def _detail(
        self,
        purchase: Purchase,
        *,
        workspace: Workspace | None,
        actor: User | None,
    ) -> PlatformPurchaseDetailOut:
        config = purchase.gateway_config
        extra = purchase.extra or {}
        return PlatformPurchaseDetailOut(
            id=purchase.id,
            workspace=self._workspace_out(workspace, purchase.workspace_id),
            actor=self._actor_out(actor, purchase.actor_id),
            kind=purchase.kind,
            status=purchase.status,
            amount=f"{purchase.amount:.2f}",
            currency=purchase.currency,
            target=self._target_out(purchase),
            gateway=PlatformPurchaseGatewayOut(
                code=config.code if config else str(extra.get("gateway_code") or ""),
                display_name=gateway_display_name(config.code if config else ""),
                gateway_config_id=purchase.payment_gateway_config_id,
                cart_id=purchase.cart_id,
                tran_ref=purchase.provider_transaction_ref,
                provider_status=extra.get("provider_status"),
                last_query_status=extra.get("last_query_status"),
            ),
            fulfillment=PlatformPurchaseFulfillmentOut(
                fulfilled=purchase.status == PurchaseStatus.PAID.value,
                invoice_available=purchase.status == PurchaseStatus.PAID.value,
                invoice_number=purchase.invoice_number,
            ),
            paid_at=purchase.paid_at,
            created_at=purchase.created_at,
            updated_at=purchase.updated_at,
            reconcile_eligible=purchase.status in _RECONCILE_ELIGIBLE,
        )

    def _target_out(self, purchase: Purchase) -> PlatformPurchaseTargetOut:
        fields = purchase_catalog_fields(purchase)
        return PlatformPurchaseTargetOut(
            kind=purchase.kind,
            item_name=fields.item_name,
            item_code=fields.item_code,
            credits=fields.credits,
            app_id=fields.app_id,
            app_slug=fields.app_slug,
            app_name=fields.app_name,
        )

    @staticmethod
    def _workspace_out(workspace: Workspace | None, workspace_id: uuid.UUID) -> PlatformPurchaseWorkspaceOut:
        if workspace is None:
            return PlatformPurchaseWorkspaceOut(id=workspace_id, name="—", slug="—")
        return PlatformPurchaseWorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
        )

    @staticmethod
    def _actor_out(actor: User | None, actor_id: uuid.UUID) -> PlatformPurchaseActorOut:
        if actor is None:
            return PlatformPurchaseActorOut(id=actor_id, email="—")
        return PlatformPurchaseActorOut(id=actor.id, email=actor.email)

    def _workspace_map(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, Workspace]:
        if not ids:
            return {}
        rows = self.db.scalars(select(Workspace).where(Workspace.id.in_(set(ids))))
        return {row.id: row for row in rows}

    def _actor_map(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not ids:
            return {}
        rows = self.db.scalars(select(User).where(User.id.in_(set(ids))))
        return {row.id: row for row in rows}

    @staticmethod
    def _normalize_status(status: str | None) -> str | None:
        if not status:
            return None
        clean = status.strip().lower()
        allowed = {item.value for item in PurchaseStatus}
        if clean not in allowed:
            raise AppError(ErrorCategory.VALIDATION, "Unknown purchase status filter.")
        return clean

    @staticmethod
    def _normalize_kind(kind: str | None) -> str | None:
        if not kind:
            return None
        clean = kind.strip().lower()
        from app.billing.models import PurchaseKind

        allowed = {item.value for item in PurchaseKind}
        if clean not in allowed:
            raise AppError(ErrorCategory.VALIDATION, "Unknown purchase kind filter.")
        return clean
