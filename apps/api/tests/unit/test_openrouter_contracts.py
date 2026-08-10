from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.core.config import Settings
from app.openrouter.chat import OpenRouterChatProvider
from app.openrouter.client import OpenRouterClient
from app.openrouter.embeddings import OpenRouterEmbeddingProvider
from app.openrouter.parser import OpenRouterDocumentParser
from app.openrouter.rerank import OpenRouterRerankProvider


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_pdf_trigger_model="test/trigger",
        openrouter_embedding_model="test/embed",
        openrouter_rerank_model="test/rerank",
        openrouter_chat_model="test/chat",
        openrouter_chat_fallback_model="test/fallback",
    )


@respx.mock
def test_parser_success_annotations(settings: Settings):
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen_1",
                "model": "test/trigger",
                "choices": [
                    {
                        "message": {
                            "content": "ignored summary",
                            "annotations": [
                                {"type": "file", "file": {"content": "# عنوان\nنص عربي"}}
                            ],
                        }
                    }
                ],
            },
        )
    )
    parser = OpenRouterDocumentParser(client=OpenRouterClient(settings), settings=settings)
    parsed = parser.parse_page(b"%PDF-1.4 fake", "p1.pdf", 1)
    assert "نص عربي" in parsed.raw_markdown
    assert parsed.page_number == 1


@respx.mock
def test_parser_recovers_annotations_from_error_metadata(settings: Settings):
    # Non-retryable status with annotations in error metadata (parse OK, generation failed)
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "message": "generation failed",
                    "metadata": {
                        "file_annotations": [
                            {"type": "file", "file": {"content": "parsed ok"}}
                        ]
                    },
                }
            },
        )
    )
    parser = OpenRouterDocumentParser(client=OpenRouterClient(settings), settings=settings)
    parsed = parser.parse_page(b"%PDF-1.4", "p1.pdf", 2)
    assert "parsed ok" in parsed.raw_markdown


@respx.mock
def test_embeddings_batch(settings: Settings):
    respx.post("https://openrouter.ai/api/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]
            },
        )
    )
    emb = OpenRouterEmbeddingProvider(client=OpenRouterClient(settings), settings=settings)
    vectors = emb.embed_documents(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


@respx.mock
def test_rerank_preserves_ids(settings: Settings):
    respx.post("https://openrouter.ai/api/v1/rerank").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ]
            },
        )
    )
    rerank = OpenRouterRerankProvider(client=OpenRouterClient(settings), settings=settings)
    ranked = rerank.rerank(
        "q",
        [
            {"chunk_id": "a", "search_text": "first"},
            {"chunk_id": "b", "search_text": "second"},
        ],
        top_n=2,
    )
    assert ranked[0]["chunk_id"] == "b"
    assert ranked[0]["final_rank"] == 1


@respx.mock
def test_chat_fallback(settings: Settings):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [
        httpx.Response(400, json={"error": {"message": "fail"}}),
        httpx.Response(
            200,
            json={
                "model": "test/fallback",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer_markdown": "جواب",
                                    "citation_chunk_ids": ["c1"],
                                    "insufficient_context": False,
                                }
                            )
                        }
                    }
                ],
            },
        ),
    ]
    chat = OpenRouterChatProvider(
        client=OpenRouterClient(settings),
        settings=settings,
        system_prompt="sys",
    )
    out = chat.answer("سؤال", "<SOURCE id='c1'>x</SOURCE>")
    assert out["answer_markdown"] == "جواب"
    assert out["model"] == "test/fallback"
