"""Connector HTTP API — Workspace-scoped connections + generic OAuth/webhooks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.apps_catalog.policy import require_browse, require_manage_apps
from app.connectors.health import ConnectorHealthService
from app.connectors.oauth_state import ConnectorOAuthStateService
from app.connectors.registry import connector_registry
from app.connectors.schemas import (
    AppConnectionListOut,
    AppConnectionOut,
    ConnectorSyncRunListOut,
    ConnectorSyncRunOut,
    ManualSyncRequest,
    StartConnectionRequest,
)
from app.connectors.service import ConnectorConnectionService
from app.connectors.sync import ConnectorSyncService
from app.connectors.webhooks import ConnectorWebhookDispatcher
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

# Nested under App Store paths.
apps_connections_router = APIRouter(prefix="/api/apps", tags=["connectors"])

# Provider-neutral connector routes (OAuth callback + webhooks).
connectors_router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@apps_connections_router.get(
    "/{app_slug}/connections", response_model=AppConnectionListOut
)
def list_connections(
    app_slug: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> AppConnectionListOut:
    workspace, membership = pair
    require_browse(membership.role)
    return ConnectorConnectionService(db).list_connections(
        workspace=workspace,
        role=membership.role,
        app_slug=app_slug,
        limit=limit,
        offset=offset,
    )


@apps_connections_router.get(
    "/{app_slug}/connections/{connection_id}", response_model=AppConnectionOut
)
def get_connection(
    app_slug: str,
    connection_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> AppConnectionOut:
    workspace, membership = pair
    require_browse(membership.role)
    return ConnectorConnectionService(db).get_connection(
        workspace=workspace,
        role=membership.role,
        app_slug=app_slug,
        connection_id=connection_id,
    )


@apps_connections_router.post(
    "/{app_slug}/connections", response_model=AppConnectionOut, status_code=201
)
def start_connection(
    app_slug: str,
    body: StartConnectionRequest,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppConnectionOut:
    workspace, membership = pair
    require_manage_apps(membership.role)
    out = ConnectorConnectionService(db).start_connection(
        workspace=workspace,
        role=membership.role,
        actor_id=user.id,
        app_slug=app_slug,
        display_name=body.display_name,
        connection_id=body.connection_id,
    )
    db.commit()
    return out


@apps_connections_router.delete(
    "/{app_slug}/connections/{connection_id}", response_model=AppConnectionOut
)
def disconnect_connection(
    app_slug: str,
    connection_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppConnectionOut:
    workspace, membership = pair
    require_manage_apps(membership.role)
    out = ConnectorConnectionService(db).disconnect(
        workspace=workspace,
        role=membership.role,
        actor_id=user.id,
        app_slug=app_slug,
        connection_id=connection_id,
    )
    db.commit()
    return out


@apps_connections_router.post(
    "/{app_slug}/connections/{connection_id}/health-check",
    response_model=AppConnectionOut,
)
def health_check_connection(
    app_slug: str,
    connection_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppConnectionOut:
    workspace, membership = pair
    require_manage_apps(membership.role)
    out = ConnectorHealthService(db).health_check(
        workspace=workspace,
        role=membership.role,
        actor_id=user.id,
        app_slug=app_slug,
        connection_id=connection_id,
    )
    db.commit()
    return out


@apps_connections_router.post(
    "/{app_slug}/connections/{connection_id}/sync",
    response_model=ConnectorSyncRunOut,
    status_code=201,
)
def request_sync(
    app_slug: str,
    connection_id: uuid.UUID,
    body: ManualSyncRequest | None = None,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorSyncRunOut:
    workspace, membership = pair
    require_manage_apps(membership.role)
    req = body or ManualSyncRequest()
    out = ConnectorSyncService(db).request_manual_sync(
        workspace=workspace,
        role=membership.role,
        actor_id=user.id,
        app_slug=app_slug,
        connection_id=connection_id,
        idempotency_key=req.idempotency_key,
    )
    db.commit()
    return out


@apps_connections_router.get(
    "/{app_slug}/connections/{connection_id}/sync-runs",
    response_model=ConnectorSyncRunListOut,
)
def list_sync_runs(
    app_slug: str,
    connection_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> ConnectorSyncRunListOut:
    workspace, membership = pair
    require_browse(membership.role)
    return ConnectorSyncService(db).list_sync_runs(
        workspace=workspace,
        role=membership.role,
        app_slug=app_slug,
        connection_id=connection_id,
        limit=limit,
        offset=offset,
    )


@apps_connections_router.get(
    "/{app_slug}/connections/{connection_id}/sync-runs/{run_id}",
    response_model=ConnectorSyncRunOut,
)
def get_sync_run(
    app_slug: str,
    connection_id: uuid.UUID,
    run_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> ConnectorSyncRunOut:
    workspace, membership = pair
    require_browse(membership.role)
    return ConnectorSyncService(db).get_sync_run(
        workspace=workspace,
        role=membership.role,
        app_slug=app_slug,
        connection_id=connection_id,
        run_id=run_id,
    )


@connectors_router.get("/oauth/{connector_key}/callback")
def oauth_callback(
    connector_key: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Provider-neutral OAuth callback.

    Production adapters complete auth in 9D/9E. Until then, return typed error
    after validating state when present.
    """
    _ = db
    state = request.query_params.get("state")
    if state:
        # Consume is actor/workspace bound — without session we cannot complete.
        # Validate state exists shape only for unsupported connectors.
        public = ConnectorOAuthStateService().peek_public(state)
        if public and public.get("connector_key") != connector_key:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state connector mismatch.",
            )

    if not connector_registry.is_available(connector_key):
        raise AppError(
            ErrorCategory.CONNECTOR_NOT_AVAILABLE,
            "Connector adapter is not available for OAuth completion.",
            details={"connector_key": connector_key},
        )

    # Adapter available but OAuth completion wiring lands with the provider phase.
    raise AppError(
        ErrorCategory.CONNECTOR_NOT_SUPPORTED,
        "OAuth completion is not implemented for this connector yet.",
        details={"connector_key": connector_key},
    )


@connectors_router.api_route(
    "/webhooks/{connector_key}/{routing_token}",
    methods=["GET", "POST", "PUT"],
)
async def inbound_webhook(
    connector_key: str,
    routing_token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    query_params = {k: v for k, v in request.query_params.multi_items()}
    status, body, resp_headers = ConnectorWebhookDispatcher(db).dispatch(
        connector_key=connector_key,
        routing_token=routing_token,
        raw_body=raw_body,
        headers=headers,
        query_params=query_params,
    )
    db.commit()
    response = Response(content=body, status_code=status)
    for key, value in resp_headers.items():
        response.headers[key] = value
    return response
