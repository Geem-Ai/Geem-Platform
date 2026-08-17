"""App-plan entitlement resolution (Phase 9B).

Separate from Geem Workspace subscription entitlements.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.repository import AppCatalogRepository
from app.core.errors import AppError, ErrorCategory


class AppEntitlementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AppCatalogRepository(db)
        self.access = AppAccessService(db)

    def get(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str,
        key: str,
        default: Any = None,
    ) -> Any:
        plan = self.access.effective_plan(workspace_id, app_slug=app_slug)
        if plan is None:
            return default
        row = self.repo.get_entitlement(plan.id, key)
        if row is None:
            return default
        return row.value

    def require(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str,
        key: str,
    ) -> Any:
        self.access.require_active(workspace_id, app_slug=app_slug)
        value = self.get(workspace_id, app_slug=app_slug, key=key)
        if value is None:
            raise AppError(
                ErrorCategory.ENTITLEMENT_NOT_FOUND,
                "App plan entitlement not found.",
                details={"app_slug": app_slug, "key": key},
            )
        return value
