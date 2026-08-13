"""Record and (when needed) immediately charge OpenRouter usage."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import UsageEvent
from app.usage.ai_usage import AiUsageService
from app.usage.attribution import GenerationUsageContext
from app.usage.weights import OpenRouterFamily, billed_usage
from app.workspaces.models import Workspace


def is_billable_workspace(db: Session, workspace_id: uuid.UUID | None) -> bool:
    if workspace_id is None:
        return False
    workspace = db.get(Workspace, workspace_id)
    return workspace is not None and workspace.is_tenant


def provider_meta(provider: Any) -> dict[str, Any]:
    meta = getattr(provider, "last_meta", None)
    return meta if isinstance(meta, dict) else {}


def charge_immediate(
    db: Session,
    settings: Settings,
    *,
    workspace_id: uuid.UUID,
    request_id: str,
    billed_tokens: int,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    expert_id: uuid.UUID | None = None,
) -> None:
    if billed_tokens <= 0 or not is_billable_workspace(db, workspace_id):
        return
    rid = (request_id or "").strip() or str(uuid.uuid4())
    svc = AiUsageService(db, settings)
    svc.reserve_ai_usage(
        workspace_id,
        rid,
        billed_tokens,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        expert_id=expert_id,
    )
    svc.settle_ai_usage(workspace_id, rid, billed_tokens)


def record_openrouter_event(
    db: Session,
    settings: Settings,
    *,
    family: OpenRouterFamily,
    operation_type: str,
    provider_usage: Any = None,
    model: str | None = None,
    request_id: str | None = None,
    workspace_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    expert_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    page_number: int | None = None,
    usage_context: GenerationUsageContext | None = None,
    extra_metadata: dict[str, Any] | None = None,
    charge_now: bool = False,
    fallback_tokens: int | None = None,
) -> int:
    """Persist a UsageEvent with billed tokens. Returns billed total.

    When ``usage_context`` is set, billed tokens are folded into the turn
    settlement (chat reservation). Otherwise ``charge_now`` immediately
    consumes from the Workspace pool.
    """
    raw, billed, multiplier = billed_usage(
        settings,
        family,
        provider_usage=provider_usage,
        model=model,
        fallback_tokens=fallback_tokens,
    )
    if billed.prompt_tokens is None and billed.completion_tokens is None:
        input_tokens = billed.total_tokens
        output_tokens = 0
    else:
        input_tokens = int(billed.prompt_tokens or 0)
        output_tokens = (
            int(billed.completion_tokens)
            if billed.completion_tokens is not None
            else max(0, billed.total_tokens - input_tokens)
        )
    cost_metadata: dict[str, Any] = {
        "family": family.value,
        "multiplier": multiplier,
        "raw_prompt_tokens": raw.prompt_tokens,
        "raw_completion_tokens": raw.completion_tokens,
        "raw_total_tokens": raw.total_tokens,
        "billed_tokens": billed.total_tokens,
        "token_source": billed.source,
        **(extra_metadata or {}),
    }
    ws_id = (
        usage_context.workspace_id
        if usage_context and usage_context.workspace_id
        else workspace_id
    )
    uid = usage_context.user_id if usage_context else user_id
    eid = usage_context.expert_id if usage_context else expert_id
    cid = usage_context.conversation_id if usage_context else conversation_id
    mid = usage_context.message_id if usage_context else message_id
    kid = usage_context.api_key_id if usage_context else None
    rid = request_id or (usage_context.request_id if usage_context else None)

    db.add(
        UsageEvent(
            id=uuid.uuid4(),
            operation_type=operation_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_metadata=cost_metadata,
            request_id=rid,
            workspace_id=ws_id,
            user_id=uid,
            expert_id=eid,
            conversation_id=cid,
            message_id=mid,
            api_key_id=kid,
            document_id=document_id,
            page_number=page_number,
        )
    )

    if billed.total_tokens > 0 and usage_context is not None:
        usage_context.add_billed(billed.total_tokens)
    elif charge_now and billed.total_tokens > 0 and ws_id is not None:
        charge_immediate(
            db,
            settings,
            workspace_id=ws_id,
            request_id=rid or f"{family.value}:{uuid.uuid4()}",
            billed_tokens=billed.total_tokens,
            conversation_id=cid,
            message_id=mid,
            user_id=uid,
            expert_id=eid,
        )
    return billed.total_tokens
