"""Agent-only General fallback boundaries for Expert knowledge resolution."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import app.experts.query_service as query_module
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.experts.access import AuthorizedExpert
from app.experts.knowledge import ExpertKnowledgeResolver
from app.experts.models import (
    ExpertKnowledgeMode,
    ExpertSourceStatus,
    ExpertStatus,
    ExpertType,
)
from app.experts.policy import ExpertAction
from app.experts.query_service import ExpertQueryService


def test_ordinary_knowledge_resolution_does_not_load_agent_source_evidence() -> None:
    workspace = SimpleNamespace(id=uuid.uuid4())
    expert = SimpleNamespace(
        id=uuid.uuid4(),
        type=ExpertType.WORKSPACE.value,
        rag_config={},
        system_instructions="",
    )
    authorized = AuthorizedExpert(
        expert=expert,
        ownership="workspace",
        workspace=workspace,
        membership=None,
        action=ExpertAction.USE,
    )
    resolver = object.__new__(ExpertKnowledgeResolver)
    resolver.settings = Settings(_env_file=None)
    resolver._resolve_knowledge_workspace = lambda _authorized: workspace
    resolver._list_active_linked_documents = lambda *_args: []
    source_calls: list[tuple[uuid.UUID, bool]] = []

    def list_sources(expert_id: uuid.UUID, *, lock_rows: bool):
        source_calls.append((expert_id, lock_rows))
        return []

    resolver._list_active_sources = list_sources

    ordinary = resolver.resolve(authorized)
    locked = resolver.resolve(authorized, lock_active_sources=True)

    assert ordinary.active_source_statuses == ()
    assert locked.active_source_statuses == ()
    assert source_calls == [(expert.id, True)]


def _boundary(
    *,
    status: str,
    mode: str = ExpertKnowledgeMode.RAG.value,
    ready_document_ids: tuple[uuid.UUID, ...] = (),
    all_linked_document_ids: tuple[uuid.UUID, ...] = (),
    active_source_statuses: tuple[str, ...] = (),
):
    workspace = SimpleNamespace(id=uuid.uuid4())
    expert = SimpleNamespace(
        id=uuid.uuid4(),
        type=ExpertType.WORKSPACE.value,
        status=status,
        knowledge_mode=mode,
    )
    authorized = AuthorizedExpert(
        expert=expert,
        ownership="workspace",
        workspace=workspace,
        membership=None,
        action=ExpertAction.USE,
    )
    knowledge = SimpleNamespace(
        authorized=authorized,
        has_ready_knowledge=bool(ready_document_ids),
        ready_document_ids=ready_document_ids,
        all_linked_document_ids=all_linked_document_ids,
        active_source_statuses=active_source_statuses,
        has_active_sources=bool(active_source_statuses),
    )
    resolutions: list[tuple[AuthorizedExpert, bool]] = []
    service = object.__new__(ExpertQueryService)

    def resolve(
        value: AuthorizedExpert,
        *,
        lock_active_sources: bool = False,
    ):
        resolutions.append((value, lock_active_sources))
        return knowledge

    service.resolver = SimpleNamespace(resolve=resolve)
    return service, authorized, workspace, knowledge, resolutions


@pytest.mark.parametrize("status", [ExpertStatus.DRAFT.value, ExpertStatus.READY.value])
def test_agent_rag_expert_without_active_links_selects_general_fallback(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    service, authorized, workspace, knowledge, resolutions = _boundary(status=status)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        query_module,
        "security_log",
        lambda event, **fields: events.append((event, fields)),
    )

    resolved = service.resolve_knowledge_for_agent(
        authorized,
        workspace=workspace,
        expert_id=authorized.expert_id,
        actor_id=uuid.uuid4(),
    )

    assert resolved is knowledge
    assert resolutions == [(authorized, True)]
    assert events[-1][0] == "agent.general_fallback_selected"
    assert events[-1][1]["reason"] == "no_active_linked_documents"
    # Runtime fallback must not rewrite the persisted configuration.
    assert authorized.expert.knowledge_mode == ExpertKnowledgeMode.RAG.value


def test_agent_ready_rag_expert_with_ready_knowledge_keeps_rag() -> None:
    document_id = uuid.uuid4()
    service, authorized, workspace, knowledge, resolutions = _boundary(
        status=ExpertStatus.READY.value,
        ready_document_ids=(document_id,),
        all_linked_document_ids=(document_id,),
    )

    resolved = service.resolve_knowledge_for_agent(
        authorized,
        workspace=workspace,
        expert_id=authorized.expert_id,
        actor_id=uuid.uuid4(),
    )

    assert resolved is knowledge
    assert resolutions == [(authorized, True)]


def test_explicit_general_expert_keeps_existing_resolution_path() -> None:
    service, authorized, workspace, knowledge, resolutions = _boundary(
        status=ExpertStatus.READY.value,
        mode=ExpertKnowledgeMode.GENERAL.value,
    )

    resolved = service.resolve_knowledge_for_agent(
        authorized,
        workspace=workspace,
        expert_id=authorized.expert_id,
        actor_id=uuid.uuid4(),
    )

    assert resolved is knowledge
    assert resolutions == [(authorized, False)]


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        (ExpertSourceStatus.PENDING.value, ErrorCategory.EXPERT_NOT_READY),
        (ExpertSourceStatus.PROCESSING.value, ErrorCategory.EXPERT_NOT_READY),
        (
            ExpertSourceStatus.FAILED.value,
            ErrorCategory.EXPERT_KNOWLEDGE_UNAVAILABLE,
        ),
    ],
)
def test_source_without_document_never_selects_general_fallback(
    source_status: str,
    expected: ErrorCategory,
) -> None:
    service, authorized, workspace, _knowledge, resolutions = _boundary(
        status=ExpertStatus.DRAFT.value,
        active_source_statuses=(source_status,),
    )

    with pytest.raises(AppError) as raised:
        service.resolve_knowledge_for_agent(
            authorized,
            workspace=workspace,
            expert_id=authorized.expert_id,
            actor_id=uuid.uuid4(),
        )

    assert raised.value.category == expected
    assert resolutions == [(authorized, True)]


@pytest.mark.parametrize(
    ("status", "linked", "expected"),
    [
        (ExpertStatus.DRAFT.value, True, ErrorCategory.EXPERT_HAS_NO_KNOWLEDGE),
        (ExpertStatus.READY.value, True, ErrorCategory.EXPERT_HAS_NO_KNOWLEDGE),
        (ExpertStatus.PROCESSING.value, False, ErrorCategory.EXPERT_NOT_READY),
        (
            ExpertStatus.FAILED.value,
            False,
            ErrorCategory.EXPERT_KNOWLEDGE_UNAVAILABLE,
        ),
        (ExpertStatus.DISABLED.value, False, ErrorCategory.EXPERT_DISABLED),
    ],
)
def test_agent_fallback_never_bypasses_linked_or_unserviceable_knowledge(
    status: str,
    linked: bool,
    expected: ErrorCategory,
) -> None:
    document_ids = (uuid.uuid4(),) if linked else ()
    service, authorized, workspace, _knowledge, resolutions = _boundary(
        status=status,
        all_linked_document_ids=document_ids,
    )

    with pytest.raises(AppError) as raised:
        service.resolve_knowledge_for_agent(
            authorized,
            workspace=workspace,
            expert_id=authorized.expert_id,
            actor_id=uuid.uuid4(),
        )

    assert raised.value.category == expected
    if status in {ExpertStatus.DRAFT.value, ExpertStatus.READY.value}:
        assert resolutions == [(authorized, True)]
    else:
        # Existing lifecycle checks intentionally happen before knowledge
        # resolution for disabled, processing, and failed Experts.
        assert resolutions == []
