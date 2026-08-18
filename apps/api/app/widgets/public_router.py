"""Public Chat Widget endpoints (visitor-facing, no API key)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.common.rate_limit import check_auth_rate_limit
from app.db.session import get_db
from app.identity.dependencies import client_ip
from app.widgets.schemas import WidgetBootstrapOut, WidgetMessageIn, WidgetMessageOut
from app.widgets.service import WidgetService

router = APIRouter(prefix="/api/public/widgets", tags=["public-widgets"])


def _cors_headers(origin: str | None) -> dict[str, str]:
    if not origin:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        }
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
    }


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
    headers = _cors_headers(cors_origin or request.headers.get("origin"))
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
    headers = _cors_headers(cors_origin or request.headers.get("origin"))
    return JSONResponse(content=payload.model_dump(mode="json"), headers=headers)
