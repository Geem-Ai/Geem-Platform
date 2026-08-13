"""Attach bootstrap plan + credit account to a tenant Workspace (Phase 5A).

Local/dev also seeds a checkout gateway when none is enabled (Phase 6A)
and a demo plan/credit-pack catalog for billing UI testing.
Does not commit — callers own the transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.gateways.clickpay import CLICKPAY_CODE
from app.billing.models import PaymentGatewayConfig
from app.billing.repository import PaymentGatewayConfigRepository
from app.billing.seed import ensure_local_demo_catalog
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
    ensure_local_checkout_gateway(db, settings=cfg)
    ensure_local_demo_catalog(db, settings=cfg)


def clickpay_env_configured(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.clickpay_profile_id.strip() and cfg.clickpay_server_key.strip())


def ensure_local_checkout_gateway(
    db: Session,
    *,
    settings: Settings | None = None,
) -> PaymentGatewayConfig | None:
    """Enable ClickPay from env when configured; otherwise seed Noop.

    Local/dev/test only. Never enables a gateway in production.
    """
    cfg = settings or get_settings()
    if not cfg.is_local:
        return None
    if clickpay_env_configured(cfg):
        return _enable_clickpay_from_env(db, cfg)
    return ensure_local_noop_gateway(db, settings=cfg)


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


def _enable_clickpay_from_env(db: Session, settings: Settings) -> PaymentGatewayConfig:
    repo = PaymentGatewayConfigRepository(db)
    blob = encrypt_json(
        {
            "profile_id": settings.clickpay_profile_id.strip(),
            "server_key": settings.clickpay_server_key.strip(),
            "base_url": (settings.clickpay_base_url or "").strip(),
        },
        settings=settings,
    )
    for row in repo.list_all():
        if row.code != CLICKPAY_CODE and row.enabled:
            row.enabled = False
    db.flush()
    existing = repo.get_by_code(CLICKPAY_CODE)
    if existing is not None:
        existing.enabled = True
        existing.test_mode = bool(settings.clickpay_test_mode)
        existing.credentials_encrypted = blob
        extra = dict(existing.extra or {})
        extra["source"] = "env"
        extra["local"] = True
        existing.extra = extra
        db.flush()
        return existing
    row = PaymentGatewayConfig(
        code=CLICKPAY_CODE,
        enabled=True,
        test_mode=bool(settings.clickpay_test_mode),
        credentials_encrypted=blob,
        extra={"source": "env", "local": True},
    )
    try:
        with db.begin_nested():
            return repo.create(row)
    except IntegrityError:
        winner = repo.get_by_code(CLICKPAY_CODE)
        if winner is None:
            raise
        winner.enabled = True
        winner.test_mode = bool(settings.clickpay_test_mode)
        winner.credentials_encrypted = blob
        db.flush()
        return winner
