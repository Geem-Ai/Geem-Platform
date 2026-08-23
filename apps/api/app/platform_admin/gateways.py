"""Platform Admin payment gateway configuration (Phase 12F)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, record_audit
from app.billing.gateways.config_schema import (
    gateway_config_schema,
    gateway_display_name,
    identity_fields_for,
    registered_gateway_codes,
)
from app.billing.gateways.registry import GatewayRegistry, registered_adapter_codes
from app.billing.models import PaymentGatewayConfig
from app.billing.repository import PaymentGatewayConfigRepository
from app.common.crypto import decrypt_json, encrypt_json
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.schemas import (
    PlatformGatewayCredentialStatusOut,
    PlatformPaymentGatewayActivateRequest,
    PlatformPaymentGatewayCreateRequest,
    PlatformPaymentGatewayDetailOut,
    PlatformPaymentGatewayListItem,
    PlatformPaymentGatewayListResponse,
    PlatformPaymentGatewayUpdateRequest,
)


class PlatformAdminGatewaysService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = PaymentGatewayConfigRepository(db)
        self.registry = GatewayRegistry(db, self.settings)

    def list_gateways(self, actor: User) -> PlatformPaymentGatewayListResponse:
        require_platform_admin_user(actor)
        rows = {row.code: row for row in self.repo.list_all()}
        active_id: uuid.UUID | None = None
        items: list[PlatformPaymentGatewayListItem] = []
        for code in registered_gateway_codes():
            row = rows.get(code)
            if row is not None and row.enabled:
                active_id = row.id
            items.append(self._list_item(code, row))
        return PlatformPaymentGatewayListResponse(items=items, active_gateway_id=active_id)

    def get_gateway(self, actor: User, gateway_config_id: uuid.UUID) -> PlatformPaymentGatewayDetailOut:
        require_platform_admin_user(actor)
        row = self.repo.get_by_id(gateway_config_id)
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Payment gateway configuration not found.")
        return self._detail(row)

    def create_gateway(
        self,
        actor: User,
        body: PlatformPaymentGatewayCreateRequest,
    ) -> PlatformPaymentGatewayDetailOut:
        require_platform_admin_user(actor)
        code = body.code.strip().lower()
        self._require_registered(code)
        if self.repo.get_by_code(code) is not None:
            raise AppError(
                ErrorCategory.CONFLICT,
                "A configuration for this gateway already exists.",
                details={"code": code},
            )
        schema = gateway_config_schema(code)
        stored = schema.validate_create_payload(
            credentials=body.credentials,
            test_mode=body.test_mode,
        )
        row = PaymentGatewayConfig(
            code=code,
            enabled=False,
            test_mode=body.test_mode,
            credentials_encrypted=encrypt_json(stored, settings=self.settings),
            extra={"source": "platform_admin"},
        )
        self.repo.create(row)
        record_audit(
            self.db,
            action=AuditAction.PAYMENT_GATEWAY_CREATED,
            entity_type=AuditEntityType.PAYMENT_GATEWAY,
            entity_id=row.id,
            actor_user_id=actor.id,
            metadata={
                "gateway_config_id": str(row.id),
                "code": row.code,
                "test_mode": row.test_mode,
            },
            allowlist=frozenset({"gateway_config_id", "code", "test_mode"}),
        )
        self.db.commit()
        security_log("payment_gateway.create", actor_id=str(actor.id), code=code)
        return self._detail(self.repo.get_by_id(row.id) or row)

    def update_gateway(
        self,
        actor: User,
        gateway_config_id: uuid.UUID,
        body: PlatformPaymentGatewayUpdateRequest,
    ) -> PlatformPaymentGatewayDetailOut:
        require_platform_admin_user(actor)
        row = self.repo.get_by_id_for_update(gateway_config_id)
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Payment gateway configuration not found.")

        schema = gateway_config_schema(row.code)
        existing = self._decrypt_safe(row)
        merged_input: dict[str, Any] = dict(body.credentials or {})
        if body.profile_id is not None:
            merged_input["profile_id"] = body.profile_id

        identity_changed = self._identity_changed(row.code, existing, merged_input, body.test_mode, row.test_mode)
        if identity_changed and self.repo.count_in_flight_purchases(row.id) > 0:
            raise AppError(
                ErrorCategory.CONFLICT,
                "Gateway merchant identity cannot change while purchases are in flight.",
                details={"in_flight_purchases": self.repo.count_in_flight_purchases(row.id)},
            )

        merged, rotated = schema.merge_update_payload(
            existing,
            credentials=merged_input or None,
            test_mode=body.test_mode,
        )
        if body.test_mode is not None:
            row.test_mode = body.test_mode
        row.credentials_encrypted = encrypt_json(merged, settings=self.settings)
        self.db.flush()

        action = (
            AuditAction.PAYMENT_GATEWAY_CREDENTIALS_ROTATED
            if rotated
            else AuditAction.PAYMENT_GATEWAY_UPDATED
        )
        record_audit(
            self.db,
            action=action,
            entity_type=AuditEntityType.PAYMENT_GATEWAY,
            entity_id=row.id,
            actor_user_id=actor.id,
            metadata={
                "gateway_config_id": str(row.id),
                "code": row.code,
                "test_mode": row.test_mode,
                "credential_rotated": rotated,
            },
            allowlist=frozenset(
                {"gateway_config_id", "code", "test_mode", "credential_rotated"}
            ),
        )
        self.db.commit()
        security_log("payment_gateway.update", actor_id=str(actor.id), code=row.code)
        return self._detail(self.repo.get_by_id(row.id) or row)

    def activate_gateway(
        self,
        actor: User,
        gateway_config_id: uuid.UUID,
        body: PlatformPaymentGatewayActivateRequest,
    ) -> PlatformPaymentGatewayDetailOut:
        require_platform_admin_user(actor)
        reason = body.reason.strip()
        rows = self.repo.list_all_for_update()
        target = next((row for row in rows if row.id == gateway_config_id), None)
        if target is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Payment gateway configuration not found.")

        self._require_registered(target.code)
        adapter = self.registry.build_adapter(target.code)
        if not adapter.allowed_in_environment(self.settings):
            raise AppError(
                ErrorCategory.VALIDATION,
                "This payment gateway cannot be activated in the current environment.",
                details={"code": target.code},
            )
        if not self._is_configured(target):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Payment gateway credentials are incomplete.",
                details={"code": target.code},
            )

        previous = next((row for row in rows if row.enabled and row.id != target.id), None)
        for row in rows:
            if row.id != target.id:
                row.enabled = False
        self.db.flush()
        target.enabled = True
        self.db.flush()

        meta: dict[str, Any] = {
            "gateway_config_id": str(target.id),
            "code": target.code,
            "test_mode": target.test_mode,
            "reason": reason,
        }
        if previous is not None:
            meta["previous_gateway_config_id"] = str(previous.id)
            meta["previous_code"] = previous.code
        record_audit(
            self.db,
            action=AuditAction.PAYMENT_GATEWAY_ACTIVATED,
            entity_type=AuditEntityType.PAYMENT_GATEWAY,
            entity_id=target.id,
            actor_user_id=actor.id,
            metadata=meta,
            allowlist=frozenset(
                {
                    "gateway_config_id",
                    "code",
                    "test_mode",
                    "reason",
                    "previous_gateway_config_id",
                    "previous_code",
                }
            ),
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                ErrorCategory.CONFLICT,
                "Could not activate payment gateway due to a concurrent change.",
            ) from exc
        security_log(
            "payment_gateway.activate",
            actor_id=str(actor.id),
            code=target.code,
            gateway_config_id=str(target.id),
        )
        return self._detail(self.repo.get_by_id(target.id) or target)

    def _list_item(self, code: str, row: PaymentGatewayConfig | None) -> PlatformPaymentGatewayListItem:
        configured = row is not None and self._is_configured(row) if row else False
        creds = self._credential_status(row) if row else PlatformGatewayCredentialStatusOut()
        return PlatformPaymentGatewayListItem(
            id=row.id if row else None,
            code=code,
            display_name=gateway_display_name(code),
            enabled=bool(row and row.enabled),
            test_mode=row.test_mode if row else None,
            configured=configured,
            credential_field_status=creds,
            created_at=row.created_at if row else None,
            updated_at=row.updated_at if row else None,
            referenced_purchases_count=self.repo.count_purchases(row.id) if row else 0,
            in_flight_purchases_count=self.repo.count_in_flight_purchases(row.id) if row else 0,
        )

    def _detail(self, row: PaymentGatewayConfig) -> PlatformPaymentGatewayDetailOut:
        return PlatformPaymentGatewayDetailOut(
            id=row.id,
            code=row.code,
            display_name=gateway_display_name(row.code),
            enabled=row.enabled,
            test_mode=row.test_mode,
            configured=self._is_configured(row),
            credentials=self._credential_status(row),
            created_at=row.created_at,
            updated_at=row.updated_at,
            referenced_purchases_count=self.repo.count_purchases(row.id),
            in_flight_purchases_count=self.repo.count_in_flight_purchases(row.id),
        )

    def _credential_status(self, row: PaymentGatewayConfig) -> PlatformGatewayCredentialStatusOut:
        stored = self._decrypt_safe(row)
        profile_id = str(stored.get("profile_id") or "").strip()
        server_key = str(stored.get("server_key") or "").strip()
        if row.code == "clickpay":
            return PlatformGatewayCredentialStatusOut(
                profile_id_configured=bool(profile_id),
                server_key_configured=bool(server_key),
                profile_id=profile_id or None,
            )
        return PlatformGatewayCredentialStatusOut()

    def _is_configured(self, row: PaymentGatewayConfig) -> bool:
        if row.code == "noop":
            return True
        schema = gateway_config_schema(row.code)
        stored = self._decrypt_safe(row)
        for field in schema.credential_fields:
            if field.required_on_create and not str(stored.get(field.key) or "").strip():
                return False
        return True

    def _decrypt_safe(self, row: PaymentGatewayConfig) -> dict[str, Any]:
        raw = (row.credentials_encrypted or "").strip()
        if not raw:
            return {}
        try:
            return decrypt_json(raw, settings=self.settings)
        except (ValueError, TypeError):
            return {}

    @staticmethod
    def _require_registered(code: str) -> None:
        if code not in registered_adapter_codes():
            raise AppError(
                ErrorCategory.VALIDATION,
                "Unknown payment gateway adapter.",
                details={"code": code},
            )

    @staticmethod
    def _identity_changed(
        code: str,
        existing: dict[str, Any],
        incoming: dict[str, Any],
        test_mode: bool | None,
        current_test_mode: bool,
    ) -> bool:
        fields = identity_fields_for(code)
        for key in fields:
            if key == "test_mode":
                if test_mode is not None and bool(test_mode) != bool(current_test_mode):
                    return True
                continue
            if key in incoming and str(incoming.get(key) or "") != str(existing.get(key) or ""):
                return True
        return False
