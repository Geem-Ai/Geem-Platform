from __future__ import annotations

from app.ingestion.chunker import PageChunker
from app.rag.service import RagService


def test_neighbor_expansion_helpers_exist():
    # Ensure token budget drops overflow
    svc = RagService.__new__(RagService)
    from app.core.config import Settings

    svc.settings = Settings(max_context_tokens=50)
    svc.chunker = PageChunker(svc.settings)
    chunks = [
        {"canonical_text": "كلمة " * 40, "token_count": 40, "chunk_id": "1"},
        {"canonical_text": "كلمة " * 40, "token_count": 40, "chunk_id": "2"},
        {"canonical_text": "كلمة " * 40, "token_count": 40, "chunk_id": "3"},
    ]
    selected = RagService._apply_token_budget(svc, chunks)
    assert len(selected) >= 1
    assert len(selected) < len(chunks)
