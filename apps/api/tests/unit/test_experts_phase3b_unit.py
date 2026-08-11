"""Phase 3B unit tests — parsers, rag_config, prompt, ExpertRagScope invariants."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.experts.prompt import compose_expert_system_prompt
from app.experts.rag_config import resolve_effective_rag_config
from app.ingestion.parsers.markdown_parser import MarkdownParser
from app.ingestion.parsers.registry import DocumentFormat, detect_document_format
from app.ingestion.parsers.text_parser import TextParser
from app.storage.scopes import ExpertRagScope


def test_compose_expert_system_prompt_keeps_base_and_instructions() -> None:
    base = "BASE RULES"
    composed = compose_expert_system_prompt(base, "Be a legal specialist.")
    assert "BASE RULES" in composed
    assert "Be a legal specialist." in composed
    assert composed.index("BASE RULES") < composed.index("Be a legal specialist.")
    # Safety footer is always last (prompt injection / model secrecy)
    assert "Security and confidentiality" in composed
    assert composed.index("Be a legal specialist.") < composed.index(
        "Security and confidentiality"
    )
    # Empty instructions → base + safety only
    empty = compose_expert_system_prompt(base, "")
    assert empty.startswith("BASE RULES")
    assert "Security and confidentiality" in empty
    assert "## Expert-specific instructions" not in empty
    assert compose_expert_system_prompt(base, "   ") == empty


def test_rag_config_defaults_and_clamps() -> None:
    settings = Settings(_env_file=None, retrieval_top_k=20, rerank_top_n=6)
    cfg = resolve_effective_rag_config({}, settings)
    assert cfg.top_k == 20
    assert cfg.rerank_top_n == 6
    assert cfg.similarity_threshold is None

    cfg2 = resolve_effective_rag_config({"top_k": 5, "rerank_top_n": 3}, settings)
    assert cfg2.top_k == 5
    assert cfg2.rerank_top_n == 3

    cfg3 = resolve_effective_rag_config({"top_k": 999, "similarity_threshold": 0.4}, settings)
    assert cfg3.top_k == 100
    assert cfg3.similarity_threshold == 0.4

    # Unknown keys ignored
    cfg4 = resolve_effective_rag_config({"model": "gpt-x", "top_k": 8}, settings)
    assert cfg4.top_k == 8
    assert "model" not in cfg4.as_dict()


def test_text_parser_utf8_bom_and_arabic() -> None:
    parser = TextParser()
    bom = b"\xef\xbb\xbfhello"
    parsed = parser.parse(bom, "a.txt")
    assert parsed.pages[0].plain_text == "hello"

    arabic = "عاصمة المملكة العربية السعودية هي الرياض".encode("utf-8")
    parsed_ar = parser.parse(arabic, "ar.txt")
    assert "الرياض" in parsed_ar.pages[0].plain_text


def test_text_parser_rejects_binary() -> None:
    parser = TextParser()
    with pytest.raises(AppError) as exc:
        parser.parse(b"%PDF-1.4\x00\x01\x02binary", "x.txt")
    assert exc.value.category in {
        ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
        ErrorCategory.INVALID_DOCUMENT,
        ErrorCategory.VALIDATION,
    }


def test_markdown_parser_strips_script_keeps_headings() -> None:
    parser = MarkdownParser()
    md = b"# Title\n\n<script>alert(1)</script>\n\n- item\n"
    parsed = parser.parse(md, "a.md")
    text = parsed.pages[0].plain_text or parsed.pages[0].raw_markdown or ""
    assert "Title" in text
    assert "item" in text
    assert "<script>" not in text
    assert "alert" not in text


def test_detect_document_format() -> None:
    assert detect_document_format(b"%PDF-1.4", "x.pdf", "application/pdf").format == DocumentFormat.PDF
    assert detect_document_format(b"hello", "x.txt", "text/plain").format == DocumentFormat.TEXT
    assert detect_document_format(b"# hi", "x.md", "text/markdown").format == DocumentFormat.MARKDOWN
    with pytest.raises(AppError):
        detect_document_format(b"\x00\x01\x02", "x.bin", "application/octet-stream")


def test_expert_rag_scope_fields() -> None:
    consumer = uuid.uuid4()
    knowledge = uuid.uuid4()
    expert = uuid.uuid4()
    scope = ExpertRagScope(
        consumer_workspace_id=consumer,
        knowledge_workspace_id=knowledge,
        expert_id=expert,
        expert_type="platform",
    )
    assert scope.consumer_workspace_id != scope.knowledge_workspace_id
    assert scope.kind == "expert"
