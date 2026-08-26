"""Public Chat Widget endpoints (visitor-facing, no API key)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.common.rate_limit import check_auth_rate_limit
from app.db.session import SessionLocal, get_db
from app.identity.dependencies import client_ip
from app.widgets.schemas import (
    WidgetBootstrapOut,
    WidgetMcpTurnIn,
    WidgetMcpTurnStatusIn,
    WidgetMcpTurnStatusOut,
    WidgetMessageIn,
    WidgetMessageOut,
)
from app.widgets.service import WidgetService

router = APIRouter(prefix="/api/public/widgets", tags=["public-widgets"])

_PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def _cors_headers(
    origin: str | None,
    *,
    method: str,
    allowed_headers: str = "",
) -> dict[str, str]:
    allowed_methods = f"{method}, OPTIONS"
    headers = (
        {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": allowed_methods,
            "Access-Control-Max-Age": "86400",
        }
        if not origin
        else {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": allowed_methods,
            "Access-Control-Max-Age": "86400",
            "Vary": "Origin",
        }
    )
    if allowed_headers:
        headers["Access-Control-Allow-Headers"] = allowed_headers
    return headers


@router.get("/{widget_id}/bootstrap", response_model=WidgetBootstrapOut)
def widget_bootstrap(
    widget_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload, cors_origin = WidgetService(db).bootstrap(
        widget_id,
        origin_header=request.headers.get("origin"),
        referer=request.headers.get("referer"),
    )
    headers = _cors_headers(
        cors_origin or request.headers.get("origin"),
        method="GET",
    )
    return JSONResponse(content=payload.model_dump(mode="json"), headers=headers)


@router.post("/{widget_id}/messages", response_model=WidgetMessageOut)
def widget_message(
    widget_id: uuid.UUID,
    body: WidgetMessageIn,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    check_auth_rate_limit("widget_message", f"{widget_id}:{client_ip(request)}")
    payload, cors_origin = WidgetService(db).message(
        widget_id,
        message=body.message,
        session_id=body.session_id,
        origin_header=request.headers.get("origin"),
        referer=request.headers.get("referer"),
    )
    headers = _cors_headers(
        cors_origin or request.headers.get("origin"),
        method="POST",
        allowed_headers="Content-Type",
    )
    # The legacy endpoint remains tool-free and body-compatible, but its
    # answer and opaque session token are still private visitor state.  Make
    # that response non-replayable by browser and intermediary caches.
    headers.update(_PRIVATE_NO_STORE_HEADERS)
    return JSONResponse(content=payload.model_dump(mode="json"), headers=headers)


def _sse(event: str, data: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _private_widget_headers(
    origin: str,
    *,
    allowed_headers: str,
    sse: bool = False,
) -> dict[str, str]:
    headers = {
        **_cors_headers(
            origin,
            method="POST",
            allowed_headers=allowed_headers,
        ),
        **_PRIVATE_NO_STORE_HEADERS,
    }
    if sse:
        headers["X-Accel-Buffering"] = "no"
    return headers


@router.post("/{widget_id}/messages/stream")
def widget_mcp_turn_stream(
    widget_id: uuid.UUID,
    body: WidgetMcpTurnIn,
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Audience-bound final-only Widget SSE; no tool details leave Geem."""

    check_auth_rate_limit("widget_mcp_turn", f"{widget_id}:{client_ip(request)}")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    initial, cors_origin = WidgetService(db).begin_mcp_turn(
        widget_id,
        message=body.message,
        client_turn_id=body.client_turn_id,
        session_token=body.session_token,
        origin_header=origin,
        referer=referer,
    )

    def generate() -> Iterator[str]:
        payload = initial.model_dump(mode="json", exclude_none=True)
        yield _sse(
            "accepted",
            {
                "turn_handle": initial.turn_handle,
                "status": "accepted",
                "session_token": initial.session_token,
            },
        )
        terminal = {"pending", "completed", "failed", "outcome_unknown"}
        if initial.status in terminal:
            yield _sse(
                "pending" if initial.status == "pending" else "final",
                payload,
            )
            return
        session_token = str(initial.session_token or "")
        deadline = time.monotonic() + 135.0
        next_keepalive = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            time.sleep(0.5)
            poll_db = SessionLocal()
            try:
                current, _ = WidgetService(poll_db).mcp_turn_status(
                    widget_id,
                    raw_handle=initial.turn_handle,
                    session_token=session_token,
                    origin_header=origin,
                    referer=referer,
                )
            finally:
                poll_db.close()
            if current.status in terminal:
                current_payload = current.model_dump(mode="json", exclude_none=True)
                yield _sse(
                    "pending" if current.status == "pending" else "final",
                    current_payload,
                )
                return
            if current.session_token:
                session_token = current.session_token
            if time.monotonic() >= next_keepalive:
                yield ": keepalive\n\n"
                next_keepalive = time.monotonic() + 10.0
        yield _sse(
            "accepted",
            {
                "turn_handle": initial.turn_handle,
                "status": "accepted",
                "session_token": session_token,
            },
        )

    return StreamingResponse(
        iterate_in_threadpool(generate()),
        media_type="text/event-stream",
        headers=_private_widget_headers(
            cors_origin,
            allowed_headers="Accept, Content-Type",
            sse=True,
        ),
    )


@router.post(
    "/{widget_id}/tool-turns/status",
    response_model=WidgetMcpTurnStatusOut,
)
def widget_mcp_turn_status(
    widget_id: uuid.UUID,
    body: WidgetMcpTurnStatusIn,
    request: Request,
    session_token: str = Header(..., alias="X-Geem-Widget-Session"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    check_auth_rate_limit("widget_mcp_turn_status", f"{widget_id}:{client_ip(request)}")
    payload, cors_origin = WidgetService(db).mcp_turn_status(
        widget_id,
        raw_handle=body.turn_handle,
        session_token=session_token,
        origin_header=request.headers.get("origin"),
        referer=request.headers.get("referer"),
    )
    return JSONResponse(
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=_private_widget_headers(
            cors_origin,
            allowed_headers="Content-Type, X-Geem-Widget-Session",
        ),
    )
