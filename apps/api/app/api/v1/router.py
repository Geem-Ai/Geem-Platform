"""Public Workspace Chat API — ``POST /api/v1/chat``.

Authenticated exclusively by Workspace API key (``chat:write``).
Workspace identity is taken from the key; Host/headers/body/cookies cannot
override it. Generation reuses ExpertQueryService + Phase 5 AI metering.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.api.schemas import Citation
from app.api.v1.schemas import PublicChatRequest, PublicChatResponse, PublicChatUsage
from app.api_keys.dependencies import require_api_scope
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.scopes import SCOPE_CHAT_WRITE
from app.conversations.invocation import ChatInvocationContext
from app.conversations.turn import ChatTurnExecutor
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal, get_db
from app.rate_limits.service import ApiRateLimiter
from app.usage.metered import MeteredWorkspaceGeneration
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["public-chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _workspace(request: Request, principal: ApiKeyPrincipal, db: Session) -> Workspace:
    workspace = getattr(request.state, "workspace", None)
    if isinstance(workspace, Workspace) and workspace.id == principal.workspace_id:
        return workspace
    row = db.get(Workspace, principal.workspace_id)
    if row is None:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid API key.")
    return row


@router.post(
    "/chat",
    response_model=PublicChatResponse,
    responses={
        200: {
            "description": (
                "JSON answer when ``stream=false``. When ``stream=true`` the "
                "response is ``text/event-stream`` with message_start, delta, "
                "replace (full-buffer reset from the RAG engine), "
                "message_complete, and error events. Quota and credit failures "
                "are HTTP errors even for ``stream=true``."
            ),
        },
        401: {"description": "Missing or invalid API key."},
        403: {"description": "API key is missing the ``chat:write`` scope."},
        404: {"description": "Expert is not accessible to this Workspace."},
        422: {"description": "Malformed request body."},
        429: {
            "description": (
                "API rate limit exceeded (``rate_limit_exceeded``) or AI quota "
                "(``quota_exceeded``)."
            ),
        },
        402: {"description": "Insufficient purchased AI credits (``insufficient_credits``)."},
    },
    openapi_extra={
        "security": [{"ApiKey": []}],
    },
)
def public_chat(
    body: PublicChatRequest,
    request: Request,
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_CHAT_WRITE)),
    db: Session = Depends(get_db),
) -> JSONResponse | StreamingResponse:
    """Run one Expert turn for the API key's Workspace.

    Send ``Authorization: Bearer geem_sk_xxxxxxxxxxxxxxxxx`` (example secret
    only — never a real key). Workspace is derived from the key alone.
    """
    started = time.perf_counter()
    # Server-owned turn id — never the client/middleware X-Request-Id.
    # AI reservation is idempotent on (workspace_id, request_id); reusing a
    # client header would skip a new hold and under-bill retries.
    turn_id = str(uuid.uuid4())
    workspace = _workspace(request, principal, db)
    rate_headers: dict[str, str] = {}

    executor = ChatTurnExecutor(db)
    question = executor.validate_message(body.message)

    rate = ApiRateLimiter(db).consume(
        workspace_id=principal.workspace_id,
        api_key_id=principal.api_key_id,
    )
    rate_headers = rate.as_headers()

    executor.authorize_expert(
        workspace=workspace,
        expert_id=body.expert_id,
        actor_id=principal.api_key_id,
    )

    invocation = ChatInvocationContext.api_key(
        workspace_id=workspace.id,
        api_key_id=principal.api_key_id,
        expert_id=body.expert_id,
        request_id=turn_id,
    )

    meter = MeteredWorkspaceGeneration(
        db,
        workspace_id=workspace.id,
        user_id=None,
        expert_id=body.expert_id,
        conversation_id=None,
        message_id=None,
        api_key_id=principal.api_key_id,
        request_id=turn_id,
    )
    try:
        meter.reserve()
    except Exception:
        meter.release()
        _log_request(
            request_id=turn_id,
            workspace_id=workspace.id,
            api_key_id=principal.api_key_id,
            expert_id=body.expert_id,
            stream=body.stream,
            status="error",
            started=started,
        )
        raise

    if body.stream:
        return _stream_chat(
            workspace=workspace,
            principal=principal,
            expert_id=body.expert_id,
            question=question,
            invocation=invocation,
            request_id=turn_id,
            rate_headers=rate_headers,
            started=started,
        )

    try:
        result = executor.execute(
            workspace=workspace,
            expert_id=body.expert_id,
            question=question,
            invocation=invocation,
            meter=meter,
        )
    except Exception:
        meter.release()
        _log_request(
            request_id=turn_id,
            workspace_id=workspace.id,
            api_key_id=principal.api_key_id,
            expert_id=body.expert_id,
            stream=False,
            status="error",
            started=started,
        )
        raise

    payload = PublicChatResponse(
        id=turn_id,
        expert_id=body.expert_id,
        answer=result["answer"],
        citations=[Citation.model_validate(c) for c in result["citations"]],
        usage=PublicChatUsage(billed_tokens=int(result["billed_tokens"])),
    )
    _log_request(
        request_id=turn_id,
        workspace_id=workspace.id,
        api_key_id=principal.api_key_id,
        expert_id=body.expert_id,
        stream=False,
        status="ok",
        started=started,
    )
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers=rate_headers,
    )


def _stream_chat(
    *,
    workspace: Workspace,
    principal: ApiKeyPrincipal,
    expert_id: uuid.UUID,
    question: str,
    invocation: ChatInvocationContext,
    request_id: str,
    rate_headers: dict[str, str],
    started: float,
) -> StreamingResponse:
    def generate() -> Iterator[str]:
        db = SessionLocal()
        meter: MeteredWorkspaceGeneration | None = None
        status = "ok"
        try:
            # Hold was taken on the request session before StreamingResponse
            # so quota/credits are HTTP 402/429, not an SSE error after 200.
            meter = MeteredWorkspaceGeneration(
                db,
                workspace_id=workspace.id,
                user_id=None,
                expert_id=expert_id,
                conversation_id=None,
                message_id=None,
                api_key_id=principal.api_key_id,
                request_id=request_id,
            )
            executor = ChatTurnExecutor(db)
            for item in executor.stream(
                workspace=workspace,
                expert_id=expert_id,
                question=question,
                invocation=invocation,
                meter=meter,
                request_id=request_id,
            ):
                if item.get("event") == "error":
                    status = "error"
                yield _sse(item["event"], item["data"])
        except AppError as exc:
            status = "error"
            if meter is not None:
                meter.release()
            yield _sse(
                "error",
                {
                    "code": exc.category.value,
                    "error": exc.category.value,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except GeneratorExit:
            status = "cancelled"
            if meter is not None:
                meter.release()
            raise
        except Exception:  # noqa: BLE001
            status = "error"
            logger.exception("public_chat_stream_failed")
            if meter is not None:
                meter.release()
            yield _sse(
                "error",
                {
                    "code": "generation_failed",
                    "error": "generation_failed",
                    "message": "Generation failed.",
                },
            )
        finally:
            _log_request(
                request_id=request_id,
                workspace_id=workspace.id,
                api_key_id=principal.api_key_id,
                expert_id=expert_id,
                stream=True,
                status=status,
                started=started,
            )
            db.close()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        **rate_headers,
    }
    return StreamingResponse(
        iterate_in_threadpool(generate()),
        media_type="text/event-stream",
        headers=headers,
    )


def _log_request(
    *,
    request_id: str,
    workspace_id: uuid.UUID,
    api_key_id: uuid.UUID,
    expert_id: uuid.UUID,
    stream: bool,
    status: str,
    started: float,
) -> None:
    latency_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "public_chat.request",
        extra={
            "request_id": request_id,
            "workspace_id": str(workspace_id),
            "api_key_id": str(api_key_id),
            "expert_id": str(expert_id),
            "stream": stream,
            "status": status,
            "latency_ms": latency_ms,
        },
    )
