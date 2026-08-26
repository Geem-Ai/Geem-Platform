"""Public OpenAI-compatible Chat Completions + Models API.

Authenticated exclusively by Workspace API key (``chat:write``).
Workspace identity is taken from the key; Host/headers/body/cookies cannot
override it. Expert identity is ``X-Geem-Expert-Id`` (alias ``X-Expert-Id``).
Generation reuses ExpertQueryService + Phase 5 AI metering.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.api.v1.openai_compat import (
    completion_response,
    iter_completion_sse,
    iter_sse_error,
    messages_to_question,
    model_object,
    parse_expert_id,
)
from app.api.v1.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelListResponse,
    ModelObject,
)
from app.api_keys.dependencies import require_api_scope
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.scopes import SCOPE_CHAT_WRITE
from app.common.public_model import PUBLIC_MODEL_ID
from app.conversations.invocation import ChatInvocationContext
from app.conversations.turn import ChatTurnExecutor
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal, get_db
from app.experts.models import Expert, ExpertStatus
from app.experts.service import ExpertService
from app.rate_limits.service import ApiRateLimiter
from app.usage.metered import MeteredWorkspaceGeneration
from app.workspaces.models import Workspace
from app.mcp.executor import RuntimeResolvedTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["public-chat"])

_CHAT_RESPONSES = {
    200: {
        "description": (
            "OpenAI Chat Completions JSON when ``stream=false``. When "
            "``stream=true`` the response is ``text/event-stream`` with "
            "OpenAI chunks (``data: {...}`` then ``data: [DONE]``). Quota "
            "and credit failures are HTTP errors even for ``stream=true``."
        ),
    },
    400: {"description": "Invalid request (missing Expert header or user message)."},
    401: {"description": "Missing or invalid API key."},
    403: {"description": "API key is missing the ``chat:write`` scope."},
    404: {"description": "Expert is not accessible to this Workspace."},
    429: {
        "description": (
            "API rate limit exceeded (``rate_limit_exceeded``) or AI quota "
            "(``quota_exceeded``)."
        ),
    },
    402: {"description": "Insufficient purchased AI credits (``insufficient_credits``)."},
}


def _workspace(request: Request, principal: ApiKeyPrincipal, db: Session) -> Workspace:
    workspace = getattr(request.state, "workspace", None)
    if isinstance(workspace, Workspace) and workspace.id == principal.workspace_id:
        return workspace
    row = db.get(Workspace, principal.workspace_id)
    if row is None:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Invalid API key.")
    return row


def _ready_experts(db: Session, workspace: Workspace) -> list[tuple[Expert, str]]:
    pairs = ExpertService(db).list_for_workspace(workspace)
    return [
        (expert, ownership)
        for expert, ownership in pairs
        if expert.status == ExpertStatus.READY.value
    ]


def _get_ready_expert(
    db: Session, workspace: Workspace, expert_id: uuid.UUID
) -> tuple[Expert, str]:
    for expert, ownership in _ready_experts(db, workspace):
        if expert.id == expert_id:
            return expert, ownership
    raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    responses=_CHAT_RESPONSES,
    openapi_extra={"security": [{"ApiKey": []}]},
)
def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_CHAT_WRITE)),
    db: Session = Depends(get_db),
) -> JSONResponse | StreamingResponse:
    """Run one Expert turn for the API key's Workspace.

    Send ``Authorization: Bearer geem_sk_xxxxxxxxxxxxxxxxx`` (example secret
    only — never a real key) and ``X-Geem-Expert-Id: <expert-uuid>``.
    ``model`` is echoed and is not used for routing. Workspace is derived
    from the key alone.
    """
    started = time.perf_counter()
    created = int(time.time())
    # Server-owned turn id — never the client/middleware X-Request-Id.
    # AI reservation is idempotent on (workspace_id, request_id); reusing a
    # client header would skip a new hold and under-bill retries.
    turn_id = str(uuid.uuid4())
    expert_id = parse_expert_id(request)
    workspace = _workspace(request, principal, db)
    rate_headers: dict[str, str] = {}
    # Never echo provider model ids — Geem presents one brand model to users.
    echoed_model = PUBLIC_MODEL_ID

    executor = ChatTurnExecutor(db)
    question = executor.validate_message(messages_to_question(body.messages))

    rate = ApiRateLimiter(db).consume(
        workspace_id=principal.workspace_id,
        api_key_id=principal.api_key_id,
    )
    rate_headers = rate.as_headers()

    executor.authorize_expert(
        workspace=workspace,
        expert_id=expert_id,
        actor_id=principal.api_key_id,
    )

    invocation = ChatInvocationContext.api_key(
        workspace_id=workspace.id,
        api_key_id=principal.api_key_id,
        expert_id=expert_id,
        request_id=turn_id,
    )

    # Preserve the legacy one-reservation path exactly when there are no
    # eligible grants.  A tool-capable turn reserves every possible model
    # iteration plus the required final synthesis before any provider call.
    mcp_tools = executor.select_mcp_tools(
        invocation=invocation,
        expert_id=expert_id,
    )
    reservation_multiplier = (
        executor.settings.mcp_max_tool_iterations + 1 if mcp_tools else 1
    )

    meter = MeteredWorkspaceGeneration(
        db,
        workspace_id=workspace.id,
        user_id=None,
        expert_id=expert_id,
        conversation_id=None,
        message_id=None,
        api_key_id=principal.api_key_id,
        request_id=turn_id,
        reservation_multiplier=reservation_multiplier,
    )
    try:
        meter.reserve()
    except Exception:
        meter.release()
        _log_request(
            request_id=turn_id,
            workspace_id=workspace.id,
            api_key_id=principal.api_key_id,
            expert_id=expert_id,
            stream=body.stream,
            status="error",
            started=started,
        )
        raise

    if body.stream:
        return _stream_completions(
            workspace=workspace,
            principal=principal,
            expert_id=expert_id,
            question=question,
            invocation=invocation,
            request_id=turn_id,
            model=echoed_model,
            created=created,
            rate_headers=rate_headers,
            started=started,
            mcp_tools=mcp_tools,
        )

    try:
        result = executor.execute(
            workspace=workspace,
            expert_id=expert_id,
            question=question,
            invocation=invocation,
            meter=meter,
            mcp_tools=mcp_tools,
        )
    except Exception:
        meter.release()
        _log_request(
            request_id=turn_id,
            workspace_id=workspace.id,
            api_key_id=principal.api_key_id,
            expert_id=expert_id,
            stream=False,
            status="error",
            started=started,
        )
        raise

    payload = completion_response(
        turn_id=turn_id,
        model=echoed_model,
        created=created,
        answer=result["answer"],
        citations=result["citations"],
        billed_tokens=int(result["billed_tokens"]),
    )
    _log_request(
        request_id=turn_id,
        workspace_id=workspace.id,
        api_key_id=principal.api_key_id,
        expert_id=expert_id,
        stream=False,
        status="ok",
        started=started,
    )
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers=rate_headers,
    )


@router.get(
    "/models",
    response_model=ModelListResponse,
    openapi_extra={"security": [{"ApiKey": []}]},
)
def list_models(
    request: Request,
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_CHAT_WRITE)),
    db: Session = Depends(get_db),
) -> ModelListResponse:
    """List ready Experts the API key's Workspace can USE."""
    workspace = _workspace(request, principal, db)
    data = [
        model_object(expert, ownership) for expert, ownership in _ready_experts(db, workspace)
    ]
    return ModelListResponse(data=data)


@router.get(
    "/models/{model_id}",
    response_model=ModelObject,
    openapi_extra={"security": [{"ApiKey": []}]},
)
def get_model(
    model_id: str,
    request: Request,
    principal: ApiKeyPrincipal = Depends(require_api_scope(SCOPE_CHAT_WRITE)),
    db: Session = Depends(get_db),
) -> ModelObject:
    """Return one ready Expert the API key's Workspace can USE."""
    workspace = _workspace(request, principal, db)
    try:
        expert_id = uuid.UUID(model_id)
    except ValueError:
        raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.") from None
    expert, ownership = _get_ready_expert(db, workspace, expert_id)
    return model_object(expert, ownership)


def _stream_completions(
    *,
    workspace: Workspace,
    principal: ApiKeyPrincipal,
    expert_id: uuid.UUID,
    question: str,
    invocation: ChatInvocationContext,
    request_id: str,
    model: str,
    created: int,
    rate_headers: dict[str, str],
    started: float,
    mcp_tools: list[RuntimeResolvedTool],
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
            yield from iter_completion_sse(
                executor.stream(
                    workspace=workspace,
                    expert_id=expert_id,
                    question=question,
                    invocation=invocation,
                    meter=meter,
                    request_id=request_id,
                    mcp_tools=mcp_tools,
                ),
                turn_id=request_id,
                model=model,
                created=created,
            )
        except AppError as exc:
            status = "error"
            if meter is not None:
                meter.release()
            yield from iter_sse_error(exc)
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
            yield from iter_sse_error(Exception("Generation failed."))
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
