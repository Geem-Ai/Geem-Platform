from app.common.public_model import (
    PUBLIC_MODEL_ID,
    public_model_id,
    public_model_or_none,
    redact_public_models,
)


def test_public_model_id_never_leaks_provider_name() -> None:
    assert public_model_id("google/gemini-1.5-flash") == PUBLIC_MODEL_ID
    assert public_model_id(None) == PUBLIC_MODEL_ID
    assert public_model_or_none(None) is None
    assert public_model_or_none("qwen/qwen3.8-max") == PUBLIC_MODEL_ID


def test_redact_public_models() -> None:
    out = redact_public_models(
        {
            "answer": "hi",
            "model": "google/gemini-1.5-flash",
            "general_model": "openai/gpt-5",
        }
    )
    assert out["model"] == PUBLIC_MODEL_ID
    assert out["general_model"] == PUBLIC_MODEL_ID
    assert out["answer"] == "hi"
