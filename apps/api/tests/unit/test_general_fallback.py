from __future__ import annotations

from unittest.mock import MagicMock

from app.core.config import Settings
from app.rag.service import RagService


def test_maybe_attach_general_answer_when_insufficient():
    settings = Settings(
        general_fallback_enabled=True,
        openrouter_api_key="test",
        openrouter_chat_model="test/chat",
    )
    db = MagicMock()
    svc = RagService.__new__(RagService)
    svc.settings = settings
    svc.db = db
    svc.general_chat = MagicMock()
    svc.general_chat.answer_general.return_value = {
        "answer_markdown": "General info here",
        "model": "test/general",
        "_meta": {"request_id": "r1"},
    }
    svc._record_generation_usage = MagicMock()

    validated = {
        "answer": "Not in docs",
        "insufficient_context": True,
        "citations": [],
        "model": "test/chat",
    }
    svc._maybe_attach_general_answer("ما هو X؟", validated)
    assert validated["used_general_knowledge"] is True
    assert validated["general_answer"] == "General info here"
    assert validated["general_model"] == "test/general"
    svc._record_generation_usage.assert_called_once()


def test_maybe_attach_general_answer_skipped_when_sufficient():
    settings = Settings(general_fallback_enabled=True, openrouter_api_key="test")
    svc = RagService.__new__(RagService)
    svc.settings = settings
    svc.general_chat = MagicMock()
    validated = {
        "answer": "From docs",
        "insufficient_context": False,
        "citations": [{"chunk_id": "c1"}],
        "model": "test/chat",
    }
    svc._maybe_attach_general_answer("q", validated)
    svc.general_chat.answer_general.assert_not_called()
    assert validated["used_general_knowledge"] is False
