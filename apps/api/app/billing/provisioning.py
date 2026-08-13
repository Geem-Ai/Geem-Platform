"""Attach bootstrap plan + credit account to a tenant Workspace (Phase 5A).

Local/dev also seeds the Noop payment gateway when none is enabled (Phase 6A).
Does not commit — callers own the transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.models import PaymentGatewayConfig
from app.billing.repository import PaymentGatewayConfigRepository
from app.billing.service import SubscriptionService
from app.common.crypto import encrypt_json
from app.core.config import Settings, get_settings
from app.usage.credits import CreditService

NOOP_GATEWAY_CODE = "noop"


def provision_tenant_workspace(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    SubscriptionService(db, cfg).ensure_bootstrap_subscription(workspace_id)
    CreditService(db, cfg).ensure_account(workspace_id)
    ensure_local_noop_gateway(db, settings=cfg)


def ensure_local_noop_gateway(
    db: Session,
    *,
    settings: Settings | None = None,
) -> PaymentGatewayConfig | None:
    """Idempotent local/dev Noop gateway. Never enables Noop in production."""
    cfg = settings or get_settings()
    if not cfg.is_local:
        return None
    repo = PaymentGatewayConfigRepository(db)
    enabled = repo.list_enabled()
    if len(enabled) == 1:
        return enabled[0]
    if len(enabled) > 1:
        return None
    existing = repo.get_by_code(NOOP_GATEWAY_CODE)
    if existing is not None:
        existing.enabled = True
        existing.test_mode = True
        db.flush()
        return existing
    row = PaymentGatewayConfig(
        code=NOOP_GATEWAY_CODE,
        enabled=True,
        test_mode=True,
        credentials_encrypted=encrypt_json({}, settings=cfg),
        extra={"bootstrap": True, "local": True},
    )
    try:
        with db.begin_nested():
            return repo.create(row)
    except IntegrityError:
        winner = repo.get_by_code(NOOP_GATEWAY_CODE) or (
            repo.list_enabled()[0] if repo.list_enabled() else None
        )
        return winner
