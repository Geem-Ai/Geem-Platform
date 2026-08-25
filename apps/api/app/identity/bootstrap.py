"""Idempotent bootstrap for platform admin + default migration workspace.

Usage (from apps/api):

    python -m app.identity.bootstrap

Requires env:

    BOOTSTRAP_ADMIN_EMAIL
    BOOTSTRAP_ADMIN_PASSWORD

Optional:

    DEFAULT_WORKSPACE_SLUG   (default: default)
    DEFAULT_WORKSPACE_NAME   (default: Default Workspace)

Safe to re-run: existing admin email is promoted to platform_role=admin;
password is only set when creating a new user (existing passwords unchanged
unless BOOTSTRAP_ADMIN_RESET_PASSWORD=true). Pass ``--resync-bootstrap-plan``
to overwrite the bootstrap plan name/description/entitlements from env
(``BOOTSTRAP_PLAN_*`` / ``BOOTSTRAP_AI_TOKENS_*`` / ``BOOTSTRAP_EXPERTS_LIMIT`` /
``BOOTSTRAP_STORAGE_BYTES`` / ``BOOTSTRAP_API_REQUESTS_PER_MINUTE``). Local/dev
also seeds a demo billing catalog (Starter/Pro/Business + credit packs) for
checkout testing.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.identity.models import PlatformRole, User, UserStatus
from app.identity.repository import UserRepository
from app.identity.security import hash_password, normalize_email, validate_password
from app.experts.geem_general import ensure_geem_general_expert
from app.workspaces.service import WorkspaceService

logger = logging.getLogger(__name__)


def bootstrap_platform_admin(
    *,
    email: str | None = None,
    password: str | None = None,
    reset_password: bool = False,
    ensure_default_workspace: bool = True,
    resync_bootstrap_plan: bool = False,
) -> User:
    settings = get_settings()
    email_raw = email or settings.bootstrap_admin_email
    password_raw = password or settings.bootstrap_admin_password
    if not email_raw or not password_raw:
        raise SystemExit(
            "BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are required."
        )

    normalized = normalize_email(email_raw)
    validate_password(password_raw)

    db = SessionLocal()
    try:
        users = UserRepository(db)
        user = users.get_by_email(normalized)
        if user is None:
            user = User(
                email=normalized,
                password_hash=hash_password(password_raw),
                status=UserStatus.ACTIVE.value,
                platform_role=PlatformRole.ADMIN.value,
                email_verified_at=datetime.now(timezone.utc),
            )
            users.create(user)
            logger.info("bootstrap_admin_created email=%s", normalized)
        else:
            user.platform_role = PlatformRole.ADMIN.value
            user.status = UserStatus.ACTIVE.value
            if user.email_verified_at is None:
                user.email_verified_at = datetime.now(timezone.utc)
            if reset_password:
                user.password_hash = hash_password(password_raw)
                logger.info("bootstrap_admin_password_reset email=%s", normalized)
            else:
                logger.info("bootstrap_admin_ensured email=%s", normalized)

        db.commit()
        db.refresh(user)

        from app.workspaces.rbac_seed import ensure_default_workspace_roles, seed_permission_catalog
        from app.workspaces.models import Workspace, WorkspaceKind
        from sqlalchemy import select

        seed_permission_catalog(db)
        tenant_ids = db.scalars(
            select(Workspace.id).where(
                Workspace.kind == WorkspaceKind.TENANT.value,
                Workspace.deleted_at.is_(None),
            )
        ).all()
        for workspace_id in tenant_ids:
            ensure_default_workspace_roles(db, workspace_id)
        db.commit()

        if ensure_default_workspace:
            WorkspaceService(db, settings).ensure_migration_workspace(created_by=user.id)

        # Platform Knowledge system Workspace — no tenant memberships.
        WorkspaceService(db, settings).ensure_platform_knowledge_workspace()

        # Bootstrap/dev plan so existing tenant Workspaces have entitlements.
        from app.billing.service import PlanService

        plans = PlanService(db, settings)
        if resync_bootstrap_plan:
            plans.resync_bootstrap_plan()
        else:
            plans.ensure_bootstrap_plan()
        from app.billing.provisioning import (
            ensure_clickpay_from_env,
            ensure_local_checkout_gateway,
        )
        from app.billing.seed import ensure_local_demo_catalog

        ensure_clickpay_from_env(db, settings=settings)
        ensure_local_checkout_gateway(db, settings=settings)
        ensure_local_demo_catalog(db, settings=settings)

        # App Store starter catalog (Google Drive, OneDrive, WhatsApp coming soon).
        from app.apps_catalog.seed import ensure_app_catalog

        ensure_app_catalog(db, settings=settings)
        db.commit()

        # Geem General Platform Expert (LLM-only; available to all workspaces).
        ensure_geem_general_expert(db, settings=settings)

        return user
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    reset = "--reset-password" in sys.argv
    resync_plan = "--resync-bootstrap-plan" in sys.argv
    if resync_plan and not reset:
        from app.billing.service import PlanService

        db = SessionLocal()
        try:
            plan = PlanService(db, settings).resync_bootstrap_plan()
            db.commit()
        finally:
            db.close()
        print(f"Bootstrap plan resynced: {plan.code} ({plan.name})")
        return
    user = bootstrap_platform_admin(
        reset_password=reset,
        resync_bootstrap_plan=resync_plan,
    )
    print(
        f"Platform admin ready: {user.email} (id={user.id}) "
        f"default_workspace_slug={settings.default_workspace_slug}"
    )


if __name__ == "__main__":
    main()
