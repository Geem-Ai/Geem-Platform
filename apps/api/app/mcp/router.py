"""Workspace MCP connection, inventory review, and Expert grant API."""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.apps_catalog.policy import (
    require_browse,
    require_connect_apps,
    require_manage_apps,
)
from app.db.session import get_db
from app.documents.dependencies import DocumentAccess, get_document_access
from app.experts.policy import ExpertAction, ExpertPolicy
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.oauth import (
    McpOAuthService,
    _CIMD_ROUTE_PATH,
    _OAUTH_CALLBACK_PATH,
)
from app.mcp.schemas import (
    McpAuthStatusOut,
    McpDiscoverOut,
    McpGrantCreateIn,
    McpOAuthReauthorizeIn,
    McpOAuthStartIn,
    McpOAuthStartOut,
    McpServerCreateIn,
    McpServerListOut,
    McpServerOut,
    McpToolClassificationIn,
    McpToolGrantListOut,
    McpToolGrantOut,
    McpToolListOut,
    McpToolOut,
)
from app.mcp.services import McpGrantService, McpServerService


_PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def _private_no_store(response: Response) -> None:
    response.headers.update(_PRIVATE_NO_STORE_HEADERS)


router = APIRouter(
    tags=["mcp"],
    dependencies=[Depends(_private_no_store)],
)


def _oauth_workspace_redirect(
    *,
    return_path: str,
    success: bool,
    connection_id: uuid.UUID | None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    spa_base = (settings.effective_workspace_web_url or "").rstrip("/")
    api_base = (settings.app_url or "").rstrip("/")
    if not spa_base or spa_base == api_base:
        raise AppError(
            ErrorCategory.VALIDATION,
            "WORKSPACE_WEB_URL must identify the Workspace app for OAuth return.",
        )
    path = return_path if return_path.startswith("/") else f"/{return_path}"
    params = {
        "connector": "mcp_remote",
        "oauth": "success" if success else "error",
        "connection_id": str(connection_id) if connection_id else "",
        "error": error or "",
    }
    query = urlencode({key: value for key, value in params.items() if value})
    return RedirectResponse(
        url=f"{spa_base}{path}?{query}",
        status_code=302,
        headers=_PRIVATE_NO_STORE_HEADERS,
    )


@router.get(_CIMD_ROUTE_PATH, include_in_schema=False)
def mcp_client_metadata_document() -> JSONResponse:
    document = McpOAuthService().public_client_metadata()
    return JSONResponse(
        document,
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(_OAUTH_CALLBACK_PATH, include_in_schema=False)
def mcp_oauth_callback(request: Request) -> Response:
    state = request.query_params.get("state")
    if not state:
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
            "OAuth state is missing.",
        )
    try:
        result = McpOAuthService().complete_callback(
            state=state,
            code=request.query_params.get("code"),
            issuer_parameter=request.query_params.get("iss"),
            oauth_error=request.query_params.get("error"),
        )
    except AppError as exc:
        settings = get_settings()
        if not settings.effective_workspace_web_url:
            raise
        return _oauth_workspace_redirect(
            return_path="/apps/mcp",
            success=False,
            connection_id=None,
            error=exc.category.value,
        )
    return _oauth_workspace_redirect(
        return_path=result.return_path,
        success=result.success,
        connection_id=result.connection_id,
        error=result.error,
    )


@router.post(
    "/api/apps/mcp/servers",
    response_model=McpServerOut,
    status_code=status.HTTP_201_CREATED,
)
def create_mcp_server(
    body: McpServerCreateIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpServerOut:
    require_connect_apps(access.membership)
    return McpServerService(db).create_server(
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        body=body,
    )


@router.get("/api/apps/mcp/servers", response_model=McpServerListOut)
def list_mcp_servers(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpServerListOut:
    require_browse(access.membership)
    return McpServerService(db).list_servers(
        workspace_id=access.workspace.id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/api/apps/mcp/servers/{connection_id}", response_model=McpServerOut
)
def get_mcp_server(
    connection_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpServerOut:
    require_browse(access.membership)
    return McpServerService(db).get_server(
        workspace_id=access.workspace.id,
        connection_id=connection_id,
    )


@router.post(
    "/api/apps/mcp/servers/{connection_id}/oauth/start",
    response_model=McpOAuthStartOut,
)
def start_mcp_oauth(
    connection_id: uuid.UUID,
    body: McpOAuthStartIn,
    access: DocumentAccess = Depends(get_document_access),
) -> McpOAuthStartOut:
    require_connect_apps(access.membership)
    return McpOAuthService().start_authorization(
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        connection_id=connection_id,
        return_path=body.return_path,
    )


@router.post(
    "/api/apps/mcp/servers/{connection_id}/reauthorize",
    response_model=McpOAuthStartOut,
)
def reauthorize_mcp_oauth(
    connection_id: uuid.UUID,
    body: McpOAuthReauthorizeIn,
    access: DocumentAccess = Depends(get_document_access),
) -> McpOAuthStartOut:
    require_connect_apps(access.membership)
    return McpOAuthService().start_authorization(
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        connection_id=connection_id,
        return_path=body.return_path,
        requested_scopes=body.scopes,
        reauthorize=True,
    )


@router.get(
    "/api/apps/mcp/servers/{connection_id}/auth-status",
    response_model=McpAuthStatusOut,
)
def get_mcp_auth_status(
    connection_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpAuthStatusOut:
    require_browse(access.membership)
    return McpOAuthService(db).auth_status(
        workspace_id=access.workspace.id,
        connection_id=connection_id,
    )


@router.delete(
    "/api/apps/mcp/servers/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_mcp_server(
    connection_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> Response:
    require_connect_apps(access.membership)
    McpServerService(db).delete_server(
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        connection_id=connection_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/apps/mcp/servers/{connection_id}/discover",
    response_model=McpDiscoverOut,
)
def discover_mcp_server(
    connection_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpDiscoverOut:
    require_connect_apps(access.membership)
    return McpServerService(db).discover(
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        connection_id=connection_id,
    )


@router.get(
    "/api/apps/mcp/servers/{connection_id}/tools",
    response_model=McpToolListOut,
)
def list_mcp_server_tools(
    connection_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpToolListOut:
    require_browse(access.membership)
    return McpServerService(db).list_tools(
        workspace_id=access.workspace.id,
        connection_id=connection_id,
        limit=limit,
        offset=offset,
        q=q,
    )


@router.patch("/api/apps/mcp/tools/{tool_id}", response_model=McpToolOut)
def classify_mcp_tool(
    tool_id: uuid.UUID,
    body: McpToolClassificationIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpToolOut:
    require_manage_apps(access.membership)
    return McpServerService(db).classify_tool(
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        tool_id=tool_id,
        classification=body.classification,
    )


@router.get(
    "/api/experts/{expert_id}/mcp-grants",
    response_model=McpToolGrantListOut,
)
def list_expert_mcp_grants(
    expert_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpToolGrantListOut:
    ExpertPolicy.require(access.membership, ExpertAction.UPDATE)
    return McpGrantService(db).list_grants(
        workspace_id=access.workspace.id,
        expert_id=expert_id,
    )


@router.post(
    "/api/experts/{expert_id}/mcp-grants",
    response_model=McpToolGrantOut,
    status_code=status.HTTP_201_CREATED,
)
def create_expert_mcp_grant(
    expert_id: uuid.UUID,
    body: McpGrantCreateIn,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> McpToolGrantOut:
    ExpertPolicy.require(access.membership, ExpertAction.UPDATE)
    return McpGrantService(db).create_grant(
        workspace_id=access.workspace.id,
        expert_id=expert_id,
        actor_id=access.user.id,
        body=body,
    )


@router.delete(
    "/api/experts/{expert_id}/mcp-grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_expert_mcp_grant(
    expert_id: uuid.UUID,
    grant_id: uuid.UUID,
    access: DocumentAccess = Depends(get_document_access),
    db: Session = Depends(get_db),
) -> Response:
    ExpertPolicy.require(access.membership, ExpertAction.UPDATE)
    McpGrantService(db).revoke_grant(
        workspace_id=access.workspace.id,
        expert_id=expert_id,
        grant_id=grant_id,
        actor_id=access.user.id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
