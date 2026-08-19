from app.usage.cost_metadata import sanitize_cost_metadata


def test_allowed_fields_retained() -> None:
    cleaned = sanitize_cost_metadata(
        {
            "family": "chat",
            "multiplier": 1.5,
            "billed_tokens": 40,
            "raw_prompt_tokens": 10,
            "chunk_count": 3,
        }
    )
    assert cleaned == {
        "family": "chat",
        "multiplier": 1.5,
        "raw_prompt_tokens": 10,
        "billed_tokens": 40,
        "chunk_count": 3,
    }


def test_secrets_and_prompts_removed() -> None:
    cleaned = sanitize_cost_metadata(
        {
            "family": "embed",
            "billed_tokens": 8,
            "api_key": "geem_sk_secret",
            "authorization": "Bearer x",
            "prompt": "ignore",
            "messages": [{"role": "user", "content": "hi"}],
            "raw_response": {"text": "hello"},
        }
    )
    assert cleaned is not None
    assert set(cleaned) <= {"family", "billed_tokens"}
    assert "api_key" not in cleaned
    assert "prompt" not in cleaned
    assert "messages" not in cleaned


def test_oversized_diagnostics_dropped_accounting_kept() -> None:
    cleaned = sanitize_cost_metadata(
        {
            "family": "chat",
            "billed_tokens": 1,
            "prompt_version": "x" * 256,
            "population": "workspace",
            "token_source": "provider",
            "provider_request_id": "p" * 256,
            "billing_request_id": "b" * 256,
            "expert_type": "workspace",
            "audio_format": "wav",
        }
    )
    assert cleaned is not None
    assert cleaned["billed_tokens"] == 1
    assert cleaned["family"] == "chat"
    assert len(str(cleaned)) < 4000
