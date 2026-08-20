"""Platform Admin orchestration boundary.

Phase 12A exposes identity bootstrap only. Later slices (12B–12G) should
call existing domain services from here rather than duplicating them:

- WorkspaceService
- BillingService / credit + usage services
- ExpertService
- App catalog services

Mutations in those slices MUST write an audit_logs row (see docs/audit.md
and the Platform Admin convention in docs/platform-admin.md). 12A does not
emit fake audit entries.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.identity.models import User
from app.identity.schemas import UserOut
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.schemas import PlatformMeResponse


class PlatformAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_me(self, actor: User) -> PlatformMeResponse:
        user = require_platform_admin_user(actor)
        return PlatformMeResponse(
            user=UserOut.model_validate(user),
            platform_role=user.platform_role,
            authorized=True,
        )
