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
unless BOOTSTRAP_ADMIN_RESET_PASSWORD=true).
"""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.identity.models import PlatformRole, User, UserStatus
from app.identity.repository import UserRepository
from app.identity.security import hash_password, normalize_email, validate_password
from app.workspaces.service import WorkspaceService

logger = logging.getLogger(__name__)


def bootstrap_platform_admin(
    *,
    email: str | None = None,
    password: str | None = None,
    reset_password: bool = False,
    ensure_default_workspace: bool = True,
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
            )
            users.create(user)
            logger.info("bootstrap_admin_created email=%s", normalized)
        else:
            user.platform_role = PlatformRole.ADMIN.value
            user.status = UserStatus.ACTIVE.value
            if reset_password:
                user.password_hash = hash_password(password_raw)
                logger.info("bootstrap_admin_password_reset email=%s", normalized)
            else:
                logger.info("bootstrap_admin_ensured email=%s", normalized)

        db.commit()
        db.refresh(user)

        if ensure_default_workspace:
            WorkspaceService(db, settings).ensure_migration_workspace(created_by=user.id)

        # Platform Knowledge system Workspace — no tenant memberships.
        WorkspaceService(db, settings).ensure_platform_knowledge_workspace()

        return user
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    reset = False
    # Allow one-shot password reset via argv flag
    if "--reset-password" in sys.argv:
        reset = True
    user = bootstrap_platform_admin(reset_password=reset)
    print(
        f"Platform admin ready: {user.email} (id={user.id}) "
        f"default_workspace_slug={settings.default_workspace_slug}"
    )


if __name__ == "__main__":
    main()
