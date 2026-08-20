"""Platform Admin APIs — session users with platform_role=admin only.

Phase 3A Expert scaffolding lives on this router. Phase 12A adds the
authorization/host boundary and GET /api/platform/me. Later slices add
management features without duplicating Workspace/Billing/Expert services.
"""

from app.platform_admin.router import router

__all__ = ["router"]
