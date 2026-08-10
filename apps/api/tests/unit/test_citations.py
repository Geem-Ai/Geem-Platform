from __future__ import annotations

import uuid

from app.rag.service import RagService, build_source_xml


class _Dummy:
    pass


def test_build_source_xml_contains_ids():
    xml = build_source_xml(
        [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "document_title": "عقد",
                "page": 2,
                "canonical_text": "النص",
            }
        ]
    )
    assert 'id="c1"' in xml
    assert 'page="2"' in xml
    assert "النص" in xml


def test_citation_validation_drops_unknown(monkeypatch):
    # Build a minimal RagService without real deps
    from app.core.config import Settings

    svc = RagService.__new__(RagService)
    svc.settings = Settings()
    allowed = {"good"}
    context = [
        {
            "chunk_id": "good",
            "document_id": "d1",
            "document_title": "Doc",
            "page": 1,
            "canonical_text": "hello",
        }
    ]
    result = {
        "answer_markdown": "ans",
        "citation_chunk_ids": ["good", "fabricated"],
        "insufficient_context": False,
        "model": "test",
    }
    out = RagService._validate_citations(svc, result, allowed, context)
    assert len(out["citations"]) == 1
    assert out["citations"][0]["chunk_id"] == "good"
    assert "fabricated" in out["_invalid_citation_ids"]
