from __future__ import annotations

from app.identity.schemas import UserOut
from pydantic import BaseModel


class PlatformMeResponse(BaseModel):
    """Authoritative Platform Admin bootstrap payload (Phase 12A)."""

    user: UserOut
    platform_role: str
    authorized: bool = True
