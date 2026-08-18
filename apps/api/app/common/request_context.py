from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True, frozen=True)
class RequestContext:
    """Per-request tenancy / identity snapshot.

    Frontend hostname/slug is UX context only; backend always re-resolves and authorizes.
    ``workspace_resolution`` records how the candidate was obtained (host|header_slug|
    header_id|api_key|none) so Phase 7 API-key resolution can share this system.

    ``effective_permissions`` is derived server-side from membership + role (never
    trusted from the client). Resolution is per-request from the database.
    """

    request_id: str | None = None
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    workspace_slug: str | None = None
    membership_role: str | None = None
    membership_role_id: UUID | None = None
    effective_permissions: frozenset[str] = field(default_factory=frozenset)
    platform_role: str | None = None
    session_id: UUID | None = None
    workspace_resolution: str | None = None
    auth_required: bool = False
    api_key_id: UUID | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    @property
    def is_api_key_authenticated(self) -> bool:
        return self.api_key_id is not None

    @property
    def has_workspace(self) -> bool:
        return self.workspace_id is not None

    @property
    def is_platform_admin(self) -> bool:
        return self.platform_role == "admin"


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "geem_request_context",
    default=None,
)


def get_request_context() -> RequestContext:
    ctx = _request_context.get()
    if ctx is None:
        return RequestContext()
    return ctx


def set_request_context(ctx: RequestContext) -> Token[RequestContext | None]:
    return _request_context.set(ctx)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _request_context.reset(token)


def clear_request_context() -> None:
    _request_context.set(None)
