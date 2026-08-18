"""Phase 3A — Expert domain unit tests (policy, rag_config, ownership rules)."""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertVisibility
from app.experts.policy import ExpertAction, ExpertPolicy
from app.experts.service import normalize_rag_config, normalize_system_instructions
from app.workspaces.permissions import ADMIN_PERMISSION_KEYS, MEMBER_PERMISSION_KEYS
from tests.support.rbac import fake_membership


def test_expert_policy_matrix() -> None:
    member = fake_membership(keys=MEMBER_PERMISSION_KEYS)
    admin = fake_membership(keys=ADMIN_PERMISSION_KEYS)
    owner = fake_membership(is_owner=True)

    assert ExpertPolicy.can(member, ExpertAction.VIEW)
    assert ExpertPolicy.can(member, ExpertAction.USE)
    assert not ExpertPolicy.can(member, ExpertAction.CREATE)
    assert not ExpertPolicy.can(member, ExpertAction.UPDATE)
    assert not ExpertPolicy.can(member, ExpertAction.DELETE)
    assert not ExpertPolicy.can(member, ExpertAction.MANAGE_KNOWLEDGE)

    assert ExpertPolicy.can(admin, ExpertAction.CREATE)
    assert ExpertPolicy.can(owner, ExpertAction.DELETE)

    with pytest.raises(AppError) as exc:
        ExpertPolicy.require(member, ExpertAction.CREATE)
    assert exc.value.category == ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE


def test_platform_admin_required() -> None:
    with pytest.raises(AppError) as exc:
        ExpertPolicy.require_platform_admin("none")
    assert exc.value.category == ErrorCategory.PLATFORM_ADMIN_REQUIRED
    ExpertPolicy.require_platform_admin("admin")


def test_normalize_rag_config() -> None:
    assert normalize_rag_config(None) == {}
    assert normalize_rag_config({"top_k": 10}) == {"top_k": 10}
    with pytest.raises(AppError):
        normalize_rag_config({"unknown": 1})
    with pytest.raises(AppError):
        normalize_rag_config({"top_k": 0})
    with pytest.raises(AppError):
        normalize_rag_config({"similarity_threshold": 1.5})


def test_normalize_system_instructions() -> None:
    assert normalize_system_instructions("  hi  ") == "hi"
    with pytest.raises(AppError):
        normalize_system_instructions("x" * 40_000)


def test_workspace_visibility_values() -> None:
    assert ExpertVisibility.WORKSPACE.value == "workspace"
    assert ExpertVisibility.PLATFORM_PUBLISHED.value == "platform_published"
