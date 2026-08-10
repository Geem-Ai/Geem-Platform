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


def test_extract_partial_json_string_incremental():
    from app.openrouter.chat import extract_partial_json_string

    assert extract_partial_json_string('{"answer_markdown": "', "answer_markdown") == ""
    assert (
        extract_partial_json_string('{"answer_markdown": "مرحبا', "answer_markdown") == "مرحبا"
    )
    assert (
        extract_partial_json_string(
            '{"answer_markdown": "line1\\nline2", "citation_chunk_ids": []}',
            "answer_markdown",
        )
        == "line1\nline2"
    )


@respx.mock
def test_chat_answer_stream(settings: Settings):
    payload = {
        "answer_markdown": "Hello world",
        "citation_chunk_ids": ["c1"],
        "insufficient_context": False,
    }
    raw = json.dumps(payload, ensure_ascii=False)
    # Simulate OpenRouter SSE chunks splitting the JSON mid-string
    mid = raw.index("Hello") + 3
    part1 = raw[:mid]
    part2 = raw[mid:]
    sse = (
        f'data: {json.dumps({"choices": [{"delta": {"content": part1}}]})}\n\n'
        f'data: {json.dumps({"model": "test/chat", "choices": [{"delta": {"content": part2}}]})}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=sse.encode("utf-8"),
            headers={"Content-Type": "text/event-stream"},
        )
    )
    chat = OpenRouterChatProvider(
        client=OpenRouterClient(settings),
        settings=settings,
        system_prompt="sys",
    )
    events = list(chat.answer_stream("q", "<SOURCE id='c1'>x</SOURCE>"))
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "Hello world"
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["answer_markdown"] == "Hello world"
    assert done["result"]["citation_chunk_ids"] == ["c1"]


@respx.mock
def test_chat_stream_ignores_trailing_full_message(settings: Settings):
    """Final chunk with full message.content must not double-append after deltas."""
    raw = json.dumps(
        {
            "answer_markdown": "Hi",
            "citation_chunk_ids": [],
            "insufficient_context": False,
        },
        ensure_ascii=False,
    )
    sse = (
        f'data: {json.dumps({"choices": [{"delta": {"content": raw}}]})}\n\n'
        f'data: {json.dumps({"choices": [{"delta": {}, "message": {"content": raw}, "finish_reason": "stop"}]})}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=sse.encode("utf-8"),
            headers={"Content-Type": "text/event-stream"},
        )
    )
    chat = OpenRouterChatProvider(
        client=OpenRouterClient(settings),
        settings=settings,
        system_prompt="sys",
    )
    events = list(chat.answer_stream("q", "ctx"))
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["answer_markdown"] == "Hi"


@respx.mock
def test_chat_stream_fallback_after_partial_deltas(settings: Settings):
    """Primary may emit tokens then fail; fallback should clear and complete."""
    # Truncated JSON: answer_markdown is extractable, but final parse fails.
    bad = '{"answer_markdown": "partial", "citation_chunk_ids": '
    primary_sse = (
        f'data: {json.dumps({"choices": [{"delta": {"content": bad}}]})}\n\n'
        "data: [DONE]\n\n"
    )
    good = json.dumps(
        {
            "answer_markdown": "fallback ok",
            "citation_chunk_ids": ["c1"],
            "insufficient_context": False,
        },
        ensure_ascii=False,
    )
    fallback_sse = (
        f'data: {json.dumps({"model": "test/fallback", "choices": [{"delta": {"content": good}}]})}\n\n'
        "data: [DONE]\n\n"
    )
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [
        httpx.Response(
            200,
            content=primary_sse.encode("utf-8"),
            headers={"Content-Type": "text/event-stream"},
        ),
        httpx.Response(
            200,
            content=fallback_sse.encode("utf-8"),
            headers={"Content-Type": "text/event-stream"},
        ),
    ]
    chat = OpenRouterChatProvider(
        client=OpenRouterClient(settings),
        settings=settings,
        system_prompt="sys",
    )
    events = list(chat.answer_stream("q", "ctx"))
    assert any(e.get("type") == "replace" and e.get("text") == "" for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["answer_markdown"] == "fallback ok"
    assert done["result"]["model"] == "test/fallback"

