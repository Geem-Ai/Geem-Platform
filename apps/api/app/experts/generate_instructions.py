"""AI-assisted Expert system instructions generation (Workspace Owner/Admin).

Uses the same AI token pool and CHAT family multiplier as chat turns:
reserve → OpenRouter completion → UsageEvent + settle (or release on failure).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import MAX_SYSTEM_INSTRUCTIONS_LENGTH
from app.experts.policy import ExpertAction, ExpertPolicy
from app.experts.service import normalize_system_instructions
from app.identity.models import User
from app.openrouter.client import OpenRouterClient
from app.usage.metered import MeteredWorkspaceGeneration
from app.usage.openrouter_billing import record_openrouter_event
from app.usage.weights import OpenRouterFamily
from app.workspaces.models import Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "expert_instructions_v1.txt"
)

_MAX_FIELD = 2000
_MAX_BRIEF = 4000
_MAX_NAME = 200
_MAX_DESCRIPTION = 2000

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:[\w+-]+)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)


def _clip(raw: str | None, max_len: int) -> str:
    return (raw or "").strip()[:max_len]


def sanitize_generated_instructions(text: str) -> str:
    """Normalize LLM output into plain system instructions."""
    cleaned = (text or "").strip()
    fence = _CODE_FENCE_RE.match(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    cleaned = cleaned.strip("\"'`“”‘’")
    # Drop a single leading label line if the model echoed the field name.
    first_line, _, rest = cleaned.partition("\n")
    if first_line.strip().lower().rstrip(":") in {
        "system instructions",
        "instructions",
        "system prompt",
        "تعليمات النظام",
        "التعليمات",
    }:
        cleaned = rest.strip()
    if len(cleaned) > MAX_SYSTEM_INSTRUCTIONS_LENGTH:
        cleaned = cleaned[:MAX_SYSTEM_INSTRUCTIONS_LENGTH].rstrip()
    return normalize_system_instructions(cleaned)


def _build_user_content(
    *,
    brief: str,
    persona: str,
    audience: str,
    tone: str,
    constraints: str,
    name: str,
    description: str,
) -> str:
    parts: list[str] = [f"Brief:\n{brief}"]
    if name:
        parts.append(f"Expert name (context):\n{name}")
    if description:
        parts.append(f"Expert description (context):\n{description}")
    if persona:
        parts.append(f"Persona / role:\n{persona}")
    if audience:
        parts.append(f"Audience:\n{audience}")
    if tone:
        parts.append(f"Tone:\n{tone}")
    if constraints:
        parts.append(f"Constraints (do / don't):\n{constraints}")
    parts.append("Return only the system instructions text.")
    return "\n\n".join(parts)


def generate_expert_instructions_call(
    *,
    brief: str,
    persona: str = "",
    audience: str = "",
    tone: str = "",
    constraints: str = "",
    name: str = "",
    description: str = "",
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(system_instructions, openrouter_meta)`` or raise on failure."""
    cfg = settings or get_settings()
    clean_brief = _clip(brief, _MAX_BRIEF)
    if not clean_brief:
        raise AppError(ErrorCategory.VALIDATION, "brief is required.")

    try:
        prompt = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.exception("expert_instructions_prompt_missing")
        raise AppError(
            ErrorCategory.GENERATION_FAILED,
            "Expert instructions prompt is unavailable.",
        ) from exc

    or_client = client or OpenRouterClient(cfg)
    model = (cfg.openrouter_general_model or "").strip() or cfg.openrouter_chat_model
    user_content = _build_user_content(
        brief=clean_brief,
        persona=_clip(persona, _MAX_FIELD),
        audience=_clip(audience, _MAX_FIELD),
        tone=_clip(tone, _MAX_FIELD),
        constraints=_clip(constraints, _MAX_FIELD),
        name=_clip(name, _MAX_NAME),
        description=_clip(description, _MAX_DESCRIPTION),
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "max_tokens": 4096,
        "temperature": 0.4,
        "provider": or_client.provider_preferences(),
    }
    body, meta, status = or_client.request(
        "POST",
        "/chat/completions",
        json_body=payload,
        timeout=45.0,
        max_attempts=2,
    )
    if status >= 400 or not body:
        raise AppError(
            ErrorCategory.GENERATION_FAILED,
            "Failed to generate Expert system instructions.",
            details={"status": status, "request_id": meta.get("request_id")},
            retryable=status in {408, 429, 500, 502, 503, 504, 529},
        )
    choices = body.get("choices") or []
    if not choices:
        raise AppError(
            ErrorCategory.GENERATION_FAILED,
            "Failed to generate Expert system instructions.",
            details={"reason": "empty_choices"},
        )
    content = (choices[0].get("message", {}) or {}).get("content") or ""
    instructions = sanitize_generated_instructions(content)
    if not instructions:
        raise AppError(
            ErrorCategory.GENERATION_FAILED,
            "Generated system instructions were empty.",
        )
    # Ensure meta carries model for CHAT settlement when provider omits it.
    if isinstance(meta, dict) and not meta.get("model"):
        meta = {**meta, "model": model}
    return instructions, meta


def generate_expert_instructions_for_workspace(
    db: Session,
    *,
    workspace: Workspace,
    membership: WorkspaceMembership,
    actor: User,
    brief: str,
    persona: str | None = None,
    audience: str | None = None,
    tone: str | None = None,
    constraints: str | None = None,
    name: str | None = None,
    description: str | None = None,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
) -> str:
    """Owner/Admin only. Reserves and settles workspace AI tokens (CHAT family)."""
    ExpertPolicy.require(membership.role, ExpertAction.CREATE)
    cfg = settings or get_settings()

    meter = MeteredWorkspaceGeneration(
        db,
        workspace_id=workspace.id,
        user_id=actor.id,
        settings=cfg,
    )
    usage_ctx = meter.reserve()
    try:
        instructions, meta = generate_expert_instructions_call(
            brief=brief,
            persona=persona or "",
            audience=audience or "",
            tone=tone or "",
            constraints=constraints or "",
            name=name or "",
            description=description or "",
            settings=cfg,
            client=client,
        )
        model = (
            (meta.get("model") if isinstance(meta, dict) else None)
            or (cfg.openrouter_general_model or "").strip()
            or cfg.openrouter_chat_model
        )
        record_openrouter_event(
            db,
            cfg,
            family=OpenRouterFamily.CHAT,
            operation_type="expert_instructions",
            provider_usage=meta.get("usage") if isinstance(meta, dict) else None,
            model=model if isinstance(model, str) else None,
            request_id=(
                (meta.get("request_id") if isinstance(meta, dict) else None)
                or usage_ctx.request_id
            ),
            workspace_id=workspace.id,
            user_id=actor.id,
        )
        settle_payload: dict[str, Any] = {
            "usage": meta.get("usage") if isinstance(meta, dict) else None,
            "model": model,
        }
        meter.settle(settle_payload)
        return instructions
    except Exception:
        meter.release()
        raise
