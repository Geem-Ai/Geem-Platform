"""Connector HTTP API — Workspace-scoped connections + generic OAuth/webhooks."""

from __future__ import annotations

import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.apps_catalog.policy import require_browse, require_manage_apps
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.health import ConnectorHealthService
from app.connectors.oauth_state import ConnectorOAuthStateService
from app.connectors.oauth_redirect import effective_oauth_redirect_uri
from app.connectors.oauth_tokens import apply_token_response, merge_token_response
from app.connectors.providers.google_drive.token import (
    ensure_fresh_access as ensure_google_fresh_access,
    expires_at_from_credentials,
)
from app.connectors.providers.microsoft_onedrive.token import (
    ensure_fresh_access as ensure_onedrive_fresh_access,
)
from app.connectors.registry import connector_registry
from app.connectors.schemas import (
    AppConnectionListOut,
    AppConnectionOut,
    ConnectorSyncRunListOut,
    ConnectorSyncRunOut,
    GoogleDrivePickerSessionOut,
    ManualSyncRequest,
    MicrosoftOneDrivePickerSessionOut,
    MicrosoftOneDrivePickerTokenOut,
    MicrosoftOneDrivePickerTokenRequest,
    StartConnectionRequest,
)
from app.connectors.service import ConnectorConnectionService
from app.connectors.sync import ConnectorSyncService
from app.connectors.webhooks import ConnectorWebhookDispatcher
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

# Nested under App Store paths.
apps_connections_router = APIRouter(prefix="/api/apps", tags=["connectors"])

# Provider-neutral connector routes (OAuth callback + webhooks).
connectors_router = APIRouter(prefix="/api/connectors", tags=["connectors"])


def _oauth_redirect(
    *,
    return_path: str | None,
    params: dict[str, str],
) -> RedirectResponse:
    """Send the browser to the Workspace SPA after OAuth — never stay on the API host."""
    settings = get_settings()
    spa_base = (settings.effective_workspace_web_url or "").rstrip("/")
    api_base = (settings.app_url or "").rstrip("/")
    path = return_path or "/apps/google-drive"
    if not path.startswith("/"):
        path = f"/{path}"
    query = urlencode({k: v for k, v in params.items() if v is not None and v != ""})

    if not spa_base:
        raise AppError(
            ErrorCategory.VALIDATION,
            "WORKSPACE_WEB_URL is not configured; cannot return to the Workspace app "
            "after Google Drive OAuth.",
        )
    # Misconfiguration guard: relative redirects would land on APP_URL (API).
    if spa_base == api_base:
        raise AppError(
            ErrorCategory.VALIDATION,
            "WORKSPACE_WEB_URL must be the Workspace SPA origin, not APP_URL.",
            details={"workspace_web_url": spa_base, "app_url": api_base},
        )

    target = f"{spa_base}{path}"
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(url=target, status_code=302)


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
        return_path=body.return_path,
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


@apps_connections_router.post(
    "/google-drive/connections/{connection_id}/picker-session",
    response_model=GoogleDrivePickerSessionOut,
)
def google_drive_picker_session(
    connection_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoogleDrivePickerSessionOut:
    """Short-lived access token for the Google Picker (never returns refresh_token)."""
    _ = user
    workspace, membership = pair
    require_manage_apps(membership.role)
    settings = get_settings()
    if not settings.google_drive_configured:
        raise AppError(
            ErrorCategory.GOOGLE_DRIVE_NOT_CONFIGURED,
            "Google Drive OAuth is not configured.",
        )
    if not connector_registry.is_available("google_drive"):
        raise AppError(
            ErrorCategory.CONNECTOR_NOT_AVAILABLE,
            "Google Drive connector is not available.",
        )
    svc = ConnectorConnectionService(db)
    row, _app, _inst = svc.require_usable_connection(
        workspace.id, connection_id, app_slug="google-drive"
    )
    cred_svc = ConnectorCredentialService(db, settings=settings)
    credentials = cred_svc.get_credentials(row)
    if not credentials:
        raise AppError(
            ErrorCategory.CONNECTOR_CREDENTIALS_INVALID,
            "Connection credentials are missing.",
        )
    fresh = ensure_google_fresh_access(db, row, credentials, settings)
    db.commit()
    out = GoogleDrivePickerSessionOut(
        access_token=str(fresh["access_token"]),
        expires_at=expires_at_from_credentials(fresh),
    )
    app_id = (settings.google_drive_app_id or "").strip()
    picker_key = (settings.google_drive_picker_api_key or "").strip()
    if app_id:
        out.app_id = app_id
    if picker_key:
        out.developer_key = picker_key
    return out


@apps_connections_router.post(
    "/microsoft-onedrive/connections/{connection_id}/picker-session",
    response_model=MicrosoftOneDrivePickerSessionOut,
)
def microsoft_onedrive_picker_session(
    connection_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MicrosoftOneDrivePickerSessionOut:
    """Picker v8 bootstrap — SharePoint-audience token + OneDrive base URL (memory-only)."""
    _ = user
    workspace, membership = pair
    require_manage_apps(membership.role)
    settings = get_settings()
    if not settings.microsoft_onedrive_configured:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_NOT_CONFIGURED,
            "Microsoft OneDrive OAuth is not configured.",
        )
    if not connector_registry.is_available("microsoft_onedrive"):
        raise AppError(
            ErrorCategory.CONNECTOR_NOT_AVAILABLE,
            "Microsoft OneDrive connector is not available.",
        )
    svc = ConnectorConnectionService(db)
    row, _app, _inst = svc.require_usable_connection(
        workspace.id, connection_id, app_slug="microsoft-onedrive"
    )
    cred_svc = ConnectorCredentialService(db, settings=settings)
    credentials = cred_svc.get_credentials(row)
    if not credentials or not credentials.get("refresh_token"):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
            "Microsoft OneDrive refresh token is missing.",
        )
    fresh = ensure_onedrive_fresh_access(db, row, credentials, settings)
    sync_state = cred_svc.get_sync_state(row) or {}

    from app.connectors.providers.microsoft_onedrive.picker_auth import (
        mint_picker_resource_token,
        resolve_picker_base_url,
    )
    from app.connectors.providers.microsoft_onedrive.scopes import (
        ACCOUNT_KIND_PERSONAL,
        auth_tenant_for_account_kind,
    )

    picker_base, sync_state, account_kind = resolve_picker_base_url(
        sync_state=sync_state,
        credentials=fresh,
        settings=settings,
        access_token=str(fresh["access_token"]),
    )
    # Mirror kind onto credentials for later refreshes.
    if fresh.get("account_kind") != account_kind:
        fresh = dict(fresh)
        fresh["account_kind"] = account_kind
        fresh["auth_tenant"] = auth_tenant_for_account_kind(
            account_kind=account_kind,
            settings_tenant=settings.microsoft_onedrive_tenant,
            stored_auth_tenant=str(fresh.get("auth_tenant") or "") or None,
        )
        cred_svc.set_credentials(
            row,
            fresh,
            expires_at=expires_at_from_credentials(fresh),
            merge_refresh=True,
        )
    cred_svc.set_sync_state(row, sync_state)
    token_payload, _updated = mint_picker_resource_token(
        db=db,
        connection=row,
        credentials=fresh,
        resource=picker_base,
        settings=settings,
        sync_state=sync_state,
        account_kind=account_kind,
    )
    db.commit()
    sp_creds = apply_token_response({}, token_payload)
    picker_mode = "personal_live" if account_kind == ACCOUNT_KIND_PERSONAL else "odsp"
    return MicrosoftOneDrivePickerSessionOut(
        access_token=str(token_payload["access_token"]),
        expires_at=expires_at_from_credentials(sp_creds),
        base_url=picker_base,
        client_id=settings.microsoft_onedrive_client_id.strip() or None,
        tenant=str(
            fresh.get("auth_tenant")
            or fresh.get("tenant_id")
            or settings.microsoft_onedrive_tenant
        ),
        drive_id=str(sync_state.get("drive_id") or fresh.get("drive_id") or "")
        or None,
        account_kind=account_kind,
        picker_mode=picker_mode,
    )


@apps_connections_router.post(
    "/microsoft-onedrive/connections/{connection_id}/picker-token",
    response_model=MicrosoftOneDrivePickerTokenOut,
)
def microsoft_onedrive_picker_token(
    connection_id: uuid.UUID,
    body: MicrosoftOneDrivePickerTokenRequest,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MicrosoftOneDrivePickerTokenOut:
    """Mint a short-lived SharePoint-resource token for File Picker v8 authenticate."""
    _ = user
    workspace, membership = pair
    require_manage_apps(membership.role)
    settings = get_settings()
    if not settings.microsoft_onedrive_configured:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_NOT_CONFIGURED,
            "Microsoft OneDrive OAuth is not configured.",
        )
    svc = ConnectorConnectionService(db)
    row, _app, _inst = svc.require_usable_connection(
        workspace.id, connection_id, app_slug="microsoft-onedrive"
    )
    cred_svc = ConnectorCredentialService(db, settings=settings)
    credentials = cred_svc.get_credentials(row)
    if not credentials or not credentials.get("refresh_token"):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
            "Microsoft OneDrive refresh token is missing.",
        )
    from app.connectors.providers.microsoft_onedrive.picker_auth import (
        mint_picker_resource_token,
        resolve_picker_base_url,
    )

    # Ensure drive host / account kind is resolved before allowlisting (fail closed).
    sync_state = cred_svc.get_sync_state(row) or {}
    if not (
        sync_state.get("drive_web_url")
        or credentials.get("drive_web_url")
        or sync_state.get("account_kind")
        or credentials.get("account_kind")
    ):
        fresh = ensure_onedrive_fresh_access(db, row, credentials, settings)
        _, sync_state, _kind = resolve_picker_base_url(
            sync_state=sync_state,
            credentials=fresh,
            settings=settings,
            access_token=str(fresh["access_token"]),
        )
        cred_svc.set_sync_state(row, sync_state)
        credentials = fresh

    token_payload, _updated = mint_picker_resource_token(
        db=db,
        connection=row,
        credentials=credentials,
        resource=body.resource,
        settings=settings,
        sync_state=sync_state,
    )
    db.commit()
    expires_at = expires_at_from_credentials(apply_token_response({}, token_payload))
    return MicrosoftOneDrivePickerTokenOut(
        access_token=str(token_payload["access_token"]),
        expires_at=expires_at,
        resource=(body.resource or "").strip().rstrip("/"),
    )


def _oauth_auth_failed_code(connector_key: str) -> str:
    if connector_key == "google_drive":
        return ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED.value
    if connector_key == "microsoft_onedrive":
        return ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED.value
    return ErrorCategory.CONNECTOR_CONNECTION_FAILED.value


def _oauth_reauth_code(connector_key: str) -> str:
    if connector_key == "google_drive":
        return ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED.value
    if connector_key == "microsoft_onedrive":
        return ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED.value
    return ErrorCategory.CONNECTOR_CREDENTIALS_INVALID.value


def _persist_oauth_failure(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID | None,
    error_code: str,
    error_message: str | None = None,
) -> None:
    """Leave ``connecting`` for ERROR so the SPA shows a connection error."""
    if connection_id is None:
        return
    try:
        ConnectorConnectionService(db).mark_authorization_failed(
            workspace_id=workspace_id,
            connection_id=connection_id,
            error_code=error_code,
            error_message=error_message,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("connector_oauth_mark_failure_failed")


@connectors_router.get("/oauth/{connector_key}/callback")
def oauth_callback(
    connector_key: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Provider OAuth callback — completes authorization and redirects to the SPA."""
    settings = get_settings()
    error_param = request.query_params.get("error")
    state = request.query_params.get("state")
    code = request.query_params.get("code")

    if not connector_registry.is_available(connector_key):
        raise AppError(
            ErrorCategory.CONNECTOR_NOT_AVAILABLE,
            "Connector adapter is not available for OAuth completion.",
            details={"connector_key": connector_key},
        )

    if not state:
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
            "OAuth state is missing.",
        )

    oauth = ConnectorOAuthStateService(settings=settings)
    try:
        payload = oauth.consume_once(state)
    except AppError as exc:
        if settings.effective_workspace_web_url:
            return _oauth_redirect(
                return_path="/apps",
                params={
                    "connector": connector_key,
                    "oauth": "error",
                    "error": exc.category.value,
                },
            )
        raise

    if payload.connector_key != connector_key:
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
            "OAuth state connector mismatch.",
        )

    return_path = payload.return_path or f"/apps/{connector_key.replace('_', '-')}"

    if error_param:
        _persist_oauth_failure(
            db,
            workspace_id=payload.workspace_id,
            connection_id=payload.connection_id,
            error_code=_oauth_auth_failed_code(connector_key),
            error_message=str(error_param),
        )
        return _oauth_redirect(
            return_path=return_path,
            params={
                "connector": connector_key,
                "oauth": "error",
                "error": error_param,
                "connection_id": str(payload.connection_id) if payload.connection_id else "",
            },
        )

    if not code:
        auth_failed = _oauth_auth_failed_code(connector_key)
        _persist_oauth_failure(
            db,
            workspace_id=payload.workspace_id,
            connection_id=payload.connection_id,
            error_code=auth_failed,
            error_message="Authorization code missing.",
        )
        return _oauth_redirect(
            return_path=return_path,
            params={
                "connector": connector_key,
                "oauth": "error",
                "error": auth_failed,
                "connection_id": str(payload.connection_id) if payload.connection_id else "",
            },
        )

    if payload.connection_id is None:
        return _oauth_redirect(
            return_path=return_path,
            params={
                "connector": connector_key,
                "oauth": "error",
                "error": ErrorCategory.CONNECTOR_NOT_FOUND.value,
            },
        )

    adapter = connector_registry.get(connector_key)
    if not hasattr(adapter, "complete_authorization"):
        raise AppError(
            ErrorCategory.CONNECTOR_NOT_SUPPORTED,
            "OAuth completion is not implemented for this connector yet.",
            details={"connector_key": connector_key},
        )

    redirect_uri = effective_oauth_redirect_uri(settings, connector_key)

    try:
        result = adapter.complete_authorization(  # type: ignore[attr-defined]
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=payload.code_verifier,
            state_payload=payload.to_public_dict(),
        )
        svc = ConnectorConnectionService(db)
        row = svc.repo.get_connection(payload.workspace_id, payload.connection_id)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        cred_svc = ConnectorCredentialService(db, settings=settings)
        old_creds = cred_svc.get_credentials(row)
        merged = merge_token_response(old_creds, result.credentials)
        if not merged.get("refresh_token"):
            reauth = _oauth_reauth_code(connector_key)
            db.rollback()
            _persist_oauth_failure(
                db,
                workspace_id=payload.workspace_id,
                connection_id=payload.connection_id,
                error_code=reauth,
                error_message="Refresh token missing from provider response.",
            )
            return _oauth_redirect(
                return_path=return_path,
                params={
                    "connector": connector_key,
                    "oauth": "error",
                    "error": reauth,
                    "connection_id": str(payload.connection_id),
                },
            )
        svc.activate_connection(
            workspace_id=payload.workspace_id,
            connection_id=payload.connection_id,
            credentials=merged,
            actor_id=payload.actor_id,
            external_account_id=result.external_account_id,
            external_account_name=result.external_account_name,
            display_name=result.display_name,
            credentials_expires_at=result.credentials_expires_at,
        )
        db.commit()
        return _oauth_redirect(
            return_path=return_path,
            params={
                "connector": connector_key,
                "oauth": "success",
                "connection_id": str(payload.connection_id),
            },
        )
    except AppError as exc:
        db.rollback()
        _persist_oauth_failure(
            db,
            workspace_id=payload.workspace_id,
            connection_id=payload.connection_id,
            error_code=exc.category.value,
            error_message=str(exc.message),
        )
        return _oauth_redirect(
            return_path=return_path,
            params={
                "connector": connector_key,
                "oauth": "error",
                "error": exc.category.value,
                "connection_id": str(payload.connection_id),
            },
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("connector_oauth_callback_failed")
        auth_failed = _oauth_auth_failed_code(connector_key)
        _persist_oauth_failure(
            db,
            workspace_id=payload.workspace_id,
            connection_id=payload.connection_id,
            error_code=auth_failed,
            error_message="Authorization failed.",
        )
        return _oauth_redirect(
            return_path=return_path,
            params={
                "connector": connector_key,
                "oauth": "error",
                "error": auth_failed,
                "connection_id": str(payload.connection_id),
            },
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
