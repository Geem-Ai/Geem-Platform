from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.common.workspace_resolver import extract_subdomain_slug, resolve_workspace_hint
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.workspaces.policy import WorkspaceAction, WorkspacePolicy
from app.workspaces.models import WorkspaceRole
from app.workspaces.service import _is_slug_unique_violation
from app.workspaces.slug import validate_workspace_slug


def test_validate_slug_ok_and_reserved() -> None:
    settings = Settings(_env_file=None, app_env="local")
    assert validate_workspace_slug("Acme-1", settings=settings) == "acme-1"
    with pytest.raises(AppError) as exc:
        validate_workspace_slug("admin", settings=settings)
    assert exc.value.category == ErrorCategory.WORKSPACE_SLUG_INVALID
    with pytest.raises(AppError):
        validate_workspace_slug("platform-knowledge", settings=settings)


def test_extract_subdomain_slug() -> None:
    reserved = Settings(_env_file=None).reserved_slugs
    assert extract_subdomain_slug("acme.localhost", "localhost", reserved_slugs=reserved) == "acme"
    assert extract_subdomain_slug("acme.geem.ai", "geem.ai", reserved_slugs=reserved) == "acme"
    assert extract_subdomain_slug("localhost", "localhost", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("geem.ai", "geem.ai", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("api.geem.ai", "geem.ai", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("app-uat.geem.ai", "geem.ai", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("api-uat.geem.ai", "geem.ai", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("admin.geem.ai", "geem.ai", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("www.geem.ai", "geem.ai", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("www.localhost", "localhost", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("api.localhost", "localhost", reserved_slugs=reserved) is None
    assert extract_subdomain_slug("ACME.geem.ai", "geem.ai", reserved_slugs=reserved) == "acme"


def test_x_workspace_slug_local_only() -> None:
    def _req(headers: dict[str, str]) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            }
        )

    local = Settings(_env_file=None, app_env="local")
    hint = resolve_workspace_hint(_req({"X-Workspace-Slug": "acme"}), local)
    assert hint.slug == "acme"
    assert hint.source == "header_slug"

    prod = Settings(_env_file=None, app_env="production")
    hint_prod = resolve_workspace_hint(_req({"X-Workspace-Slug": "acme"}), prod)
    assert hint_prod.slug is None
    assert hint_prod.source == "none"


def test_workspace_policy_matrix() -> None:
    assert WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.READ_WORKSPACE)
    assert not WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.UPDATE_WORKSPACE)
    assert WorkspacePolicy.can(WorkspaceRole.ADMIN, WorkspaceAction.MANAGE_MEMBERS)
    assert not WorkspacePolicy.can(WorkspaceRole.ADMIN, WorkspaceAction.PROMOTE_TO_OWNER)
    assert WorkspacePolicy.can(WorkspaceRole.OWNER, WorkspaceAction.DELETE_WORKSPACE)
    # Phase 2A document actions available to members
    assert WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.UPLOAD_DOCUMENT)
    assert WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.LIST_DOCUMENTS)
    assert WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.DELETE_DOCUMENT)
    assert WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.UPDATE_DOCUMENT)
    assert WorkspacePolicy.can(WorkspaceRole.OWNER, WorkspaceAction.MANAGE_API_KEYS)
    assert WorkspacePolicy.can(WorkspaceRole.ADMIN, WorkspaceAction.MANAGE_API_KEYS)
    assert not WorkspacePolicy.can(WorkspaceRole.MEMBER, WorkspaceAction.MANAGE_API_KEYS)

    with pytest.raises(AppError):
        WorkspacePolicy.require(WorkspaceRole.MEMBER, WorkspaceAction.DELETE_WORKSPACE)


class _FakePgOrig:
    def __init__(self, constraint_name: str) -> None:
        self.diag = type("Diag", (), {"constraint_name": constraint_name})()

    def __str__(self) -> str:
        return f'duplicate key value violates unique constraint "{self.diag.constraint_name}"'


def test_slug_unique_violation_is_not_plan_unique() -> None:
    slug_exc = IntegrityError("INSERT", {}, _FakePgOrig("uq_workspaces_slug_active"))
    plan_exc = IntegrityError("INSERT", {}, _FakePgOrig("uq_plans_code"))
    sub_exc = IntegrityError("INSERT", {}, _FakePgOrig("uq_subscriptions_workspace_active"))
    assert _is_slug_unique_violation(slug_exc) is True
    assert _is_slug_unique_violation(plan_exc) is False
    assert _is_slug_unique_violation(sub_exc) is False
