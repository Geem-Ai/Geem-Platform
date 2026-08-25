"""Database-backed Agent knowledge-revision isolation tests."""

from __future__ import annotations

import uuid
from dataclasses import replace

from sqlalchemy.orm import Session

from app.agent.retrieval import AgentRetrievalService
from app.db.models import Chunk, Document, DocumentPage
from app.experts.access import AuthorizedExpert
from app.experts.knowledge import ResolvedExpertKnowledge
from app.experts.models import (
    Expert,
    ExpertDocument,
    ExpertKnowledgeMode,
    ExpertStatus,
    ExpertType,
    ExpertVisibility,
)
from app.experts.policy import ExpertAction
from app.experts.rag_config import EffectiveRagConfig
from app.storage.scopes import ExpertRagScope
from app.workspaces.models import Workspace


def _create_workspace(client, token: str) -> dict:
    response = client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Agent revision fixture",
            "slug": f"agent-revision-{uuid.uuid4().hex[:8]}",
        },
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _ready_document(db: Session, workspace_id: uuid.UUID) -> tuple[Document, Chunk]:
    document = Document(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        title="Revision source",
        original_filename="revision.pdf",
        storage_key=f"workspaces/{workspace_id}/documents/revision.pdf",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        mime_type="application/pdf",
        byte_size=100,
        page_count=1,
        status="ready",
        processing_version={"pipeline": "v1"},
    )
    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=document.id,
        page_number=1,
        status="parsed",
        canonical_text="revision evidence",
        search_text="revision evidence",
    )
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=document.id,
        document_page_id=page.id,
        page_number=1,
        ordinal=0,
        canonical_text="revision evidence",
        search_text="revision evidence",
        token_count=2,
        content_hash=uuid.uuid4().hex,
        qdrant_point_id=uuid.uuid4(),
        embedding_model="fixture",
        embedding_version="v1",
    )
    db.add_all([document, page, chunk])
    return document, chunk


def test_knowledge_revision_tracks_only_the_scoped_expert_index(
    client, register_user, db: Session
) -> None:
    user = register_user(email=f"agent-revision-{uuid.uuid4().hex[:8]}@example.com")
    payload = _create_workspace(client, user["access_token"])
    workspace_id = uuid.UUID(payload["id"])
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None

    expert = Expert(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        type=ExpertType.WORKSPACE.value,
        name="Revision expert",
        system_instructions="Use only the linked source.",
        rag_config={"top_k": 3, "client_agent": {"enabled": True}},
        status=ExpertStatus.READY.value,
        visibility=ExpertVisibility.WORKSPACE.value,
        knowledge_mode=ExpertKnowledgeMode.RAG.value,
    )
    document, chunk = _ready_document(db, workspace_id)
    db.add(expert)
    db.flush()
    db.add(ExpertDocument(expert_id=expert.id, document_id=document.id))
    db.commit()

    authorized = AuthorizedExpert(
        expert=expert,
        ownership="workspace",
        workspace=workspace,
        membership=None,
        action=ExpertAction.USE,
    )
    knowledge = ResolvedExpertKnowledge(
        authorized=authorized,
        scope=ExpertRagScope(
            consumer_workspace_id=workspace_id,
            knowledge_workspace_id=workspace_id,
            expert_id=expert.id,
            expert_type=ExpertType.WORKSPACE.value,
        ),
        system_instructions=expert.system_instructions,
        rag_config=EffectiveRagConfig(top_k=3, rerank_top_n=3),
        knowledge_workspace=workspace,
        ready_document_ids=(document.id,),
        all_linked_document_ids=(document.id,),
    )
    service = AgentRetrievalService(db)

    baseline = service.knowledge_revision(knowledge)
    assert baseline is not None

    # An unrelated ready document in the same Workspace cannot invalidate or
    # alias this Expert's cache population.
    _unrelated, _unrelated_chunk = _ready_document(db, workspace_id)
    db.commit()
    assert service.knowledge_revision(knowledge) == baseline

    effective_config_revision = service.knowledge_revision(
        replace(
            knowledge,
            rag_config=EffectiveRagConfig(top_k=9, rerank_top_n=2),
        )
    )
    assert effective_config_revision is not None
    assert effective_config_revision != baseline

    runtime_settings = service.settings.model_copy(
        update={"max_context_tokens": service.settings.max_context_tokens + 1}
    )
    runtime_revision = AgentRetrievalService(
        db, settings=runtime_settings
    ).knowledge_revision(knowledge)
    assert runtime_revision is not None and runtime_revision != baseline

    expert.rag_config = {
        "top_k": 4,
        "client_agent": {"enabled": True},
    }
    db.commit()
    config_revision = service.knowledge_revision(knowledge)
    assert config_revision is not None and config_revision != baseline

    chunk.embedding_version = "v2"
    db.commit()
    index_revision = service.knowledge_revision(knowledge)
    assert index_revision is not None and index_revision != config_revision

    # Any disagreement between the authorized ready set and current DB state
    # disables caching instead of inventing a revisionless shared key.
    mismatched = replace(knowledge, ready_document_ids=(uuid.uuid4(),))
    assert service.knowledge_revision(mismatched) is None
