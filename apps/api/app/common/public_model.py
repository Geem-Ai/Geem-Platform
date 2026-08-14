"""User-facing model branding.

Internal OpenRouter / provider model ids stay in usage_events and logs for
cost attribution. Customer-facing responses and UI must never expose them.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

PUBLIC_MODEL_ID = "dalseen/geem-1.0"


def public_model_id(_raw: str | None = None) -> str:
    """Always return the Geem brand model id (provider ids are never returned)."""
    return PUBLIC_MODEL_ID


def public_model_or_none(raw: str | None) -> str | None:
    """Map a stored/provider model to the brand id, preserving nulls."""
    if raw is None:
        return None
    return PUBLIC_MODEL_ID


def redact_public_models(data: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a payload and replace user-visible model fields with the brand id."""
    out: dict[str, Any] = dict(data)
    if out.get("model") is not None:
        out["model"] = PUBLIC_MODEL_ID
    if out.get("general_model") is not None:
        out["general_model"] = PUBLIC_MODEL_ID
    return out


def redact_public_models_inplace(data: MutableMapping[str, Any]) -> None:
    if data.get("model") is not None:
        data["model"] = PUBLIC_MODEL_ID
    if data.get("general_model") is not None:
        data["general_model"] = PUBLIC_MODEL_ID
