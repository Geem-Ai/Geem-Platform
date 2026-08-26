"""OAuth 2.1 lifecycle for tenant-configured remote MCP servers.

All tenant-derived HTTP is sent through the datastore-isolated mTLS egress
gateway.  This module never opens a direct connection to a protected resource,
authorization server, registration endpoint, or token endpoint.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from urllib.request import parse_http_list

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    begin_runtime_admission_transaction,
)
from app.apps_catalog.policy import require_connect_apps
from app.audit import AuditAction, AuditEntityType, record_audit
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.oauth_redirect import effective_oauth_redirect_uri
from app.connectors.oauth_state import ConnectorOAuthStateService, OAuthStatePayload
from app.connectors.oauth_tokens import (
    apply_token_response,
    credentials_need_refresh,
    expires_at_from_credentials,
)
from app.connectors.types import (
    CONNECTION_LIMIT_STATUSES,
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.mcp.constants import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTOR_KEY,
    MCP_CONNECTORS_APP_SLUG,
)
from app.mcp.normalization import (
    canonicalize_mcp_url,
    endpoint_host,
    principal_fingerprint,
)
from app.mcp.mtls import mcp_gateway_ssl_context
from app.mcp.repository import McpRepository
from app.mcp.schemas import McpAuthStatusOut, McpOAuthStartOut

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

_SCOPE = re.compile(r"^[\x21\x23-\x5B\x5D-\x7E]{1,256}$")
_CLIENT_ID_MAX = 2_048
_CLIENT_SECRET_MAX = 8_192
_TOKEN_MAX = 32_768
_MAX_AUTH_SERVERS = 8
_MAX_METADATA_ITEMS = 256
_OAUTH_CALLBACK_PATH = "/api/connectors/oauth/mcp_remote/callback"
_CIMD_ROUTE_PATH = "/api/connectors/oauth/mcp_remote/client-metadata.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rollback(db: Session) -> None:
    try:
        db.rollback()
    except SQLAlchemyError:
        logger.error("mcp_oauth_transaction_rollback_failed")


def _paid_db_error() -> AppError:
    return AppError(
        ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
        "MCP Connectors access is temporarily unavailable.",
        retryable=True,
    )


def _begin_paid_access(db: Session, workspace_id: uuid.UUID):
    begin_runtime_admission_transaction(db)
    acquire_runtime_admission_fences(
        db,
        workspace_id=workspace_id,
        app_slugs=(MCP_CONNECTORS_APP_SLUG,),
    )
    return AppAccessService(db).require_runtime_active(
        workspace_id,
        app_slug=MCP_CONNECTORS_APP_SLUG,
        entitlement_keys=(MCP_CONNECTIONS_ENTITLEMENT,),
    )


def _require_actor_can_connect(
    db: Session, *, workspace_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    # Import lazily so this module remains importable before the application's
    # aggregate model registry has loaded every relationship target.
    from app.workspaces.repository import MembershipRepository

    membership = MembershipRepository(db).get(workspace_id, actor_id)
    if membership is None:
        raise AppError(
            ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
            "Workspace membership is required.",
        )
    require_connect_apps(membership)


@dataclass(frozen=True, slots=True)
class OAuthHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class McpOAuthHttpClient(Protocol):
    """One bounded request through the internal egress gateway."""

    def request(
        self,
        *,
        operation_id: str,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        follow_redirects: bool = False,
    ) -> OAuthHttpResponse: ...


class HttpMcpOAuthGateway:
    """mTLS client for the gateway's provider-neutral ``/v1/outbound`` API."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        base = (self.settings.mcp_egress_gateway_url or "").strip().rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.hostname:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP egress gateway is unavailable.",
                retryable=True,
            )
        self._endpoint = f"{base}/v1/outbound"
        self._owns_client = client is None
        if client is None:
            client = httpx.Client(
                verify=mcp_gateway_ssl_context(self.settings),
                timeout=httpx.Timeout(
                    float(self.settings.mcp_egress_total_timeout_seconds),
                    connect=float(self.settings.mcp_egress_connect_timeout_seconds),
                    read=float(self.settings.mcp_egress_read_timeout_seconds),
                ),
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json"},
            )
        self._client: httpx.Client = client

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request(
        self,
        *,
        operation_id: str,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        follow_redirects: bool = False,
    ) -> OAuthHttpResponse:
        method = method.upper()
        if method not in {"GET", "HEAD", "POST"}:
            raise AppError(ErrorCategory.VALIDATION, "Unsupported OAuth request method.")
        raw_body = body or b""
        if len(raw_body) > self.settings.mcp_egress_max_request_bytes:
            raise AppError(
                ErrorCategory.VALIDATION,
                "The OAuth request exceeds the configured limit.",
            )
        payload: dict[str, Any] = {
            "operation_id": operation_id[:128],
            "method": method,
            "url": url,
            "headers": dict(headers or {}),
            "follow_redirects": bool(follow_redirects),
        }
        if method == "POST":
            payload["body_base64"] = base64.b64encode(raw_body).decode("ascii")
        try:
            response = self._client.post(self._endpoint, json=payload)
        except httpx.TransportError as exc:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP authorization service could not be reached.",
                retryable=True,
            ) from exc
        if len(response.content) > self.settings.mcp_egress_max_response_bytes * 2 + 16_384:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP authorization response exceeds the configured limit.",
            )
        try:
            envelope = response.json()
        except ValueError as exc:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP egress gateway returned an invalid response.",
                retryable=True,
            ) from exc
        if response.is_error or not isinstance(envelope, dict):
            error = envelope.get("error") if isinstance(envelope, dict) else None
            code = str(error.get("code") or "") if isinstance(error, dict) else ""
            category = (
                ErrorCategory.EGRESS_TARGET_BLOCKED
                if code == "egress_target_blocked"
                else ErrorCategory.MCP_SERVER_UNREACHABLE
            )
            raise AppError(
                category,
                "The OAuth target is blocked by egress policy."
                if category == ErrorCategory.EGRESS_TARGET_BLOCKED
                else "The MCP authorization service could not be reached.",
                retryable=category == ErrorCategory.MCP_SERVER_UNREACHABLE,
            )
        try:
            status_code = int(envelope["status_code"])
            response_headers = envelope["headers"]
            encoded = envelope["body_base64"]
            if not isinstance(response_headers, dict) or not isinstance(encoded, str):
                raise TypeError
            decoded = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP egress gateway returned an invalid response.",
                retryable=True,
            ) from exc
        if len(decoded) > self.settings.mcp_egress_max_response_bytes:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP authorization response exceeds the configured limit.",
            )
        return OAuthHttpResponse(
            status_code=status_code,
            headers={str(k): str(v) for k, v in response_headers.items()},
            body=decoded,
        )


@dataclass(frozen=True, slots=True)
class _ConnectionSnapshot:
    workspace_id: uuid.UUID
    actor_id: uuid.UUID
    installation_id: uuid.UUID
    connection_id: uuid.UUID
    server_url: str
    resource_uri: str
    auth: dict[str, Any]
    credential_epoch: int
    encrypted_credentials: str
    had_principal: bool


@dataclass(frozen=True, slots=True)
class _AuthorizationMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None
    revocation_endpoint: str | None
    code_challenge_methods_supported: tuple[str, ...]
    token_endpoint_auth_methods_supported: tuple[str, ...]
    client_id_metadata_document_supported: bool
    authorization_response_iss_parameter_supported: bool


@dataclass(frozen=True, slots=True)
class _Registration:
    strategy: str
    issuer: str
    client_id: str
    client_secret: str | None
    token_endpoint_auth_method: str


@dataclass(frozen=True, slots=True)
class _AuthorizationFlow:
    resource_metadata_url: str
    resource_uri: str
    scopes: tuple[str, ...]
    metadata: _AuthorizationMetadata
    registration: _Registration


@dataclass(frozen=True, slots=True)
class _PersistedStart:
    installation_id: uuid.UUID
    credential_epoch: int
    encrypted_credentials: str
    reauthorization: bool


@dataclass(frozen=True, slots=True)
class McpOAuthCallbackResult:
    success: bool
    connection_id: uuid.UUID | None
    return_path: str
    error: str | None = None


class _TokenEndpointError(AppError):
    def __init__(self, oauth_error: str, status_code: int) -> None:
        super().__init__(
            ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
            "The MCP authorization grant is invalid or expired.",
        )
        self.oauth_error = oauth_error
        self.status_code = status_code


class McpOAuthService:
    """Challenge discovery, PKCE authorization, token storage, and refresh."""

    def __init__(
        self,
        db: Session | None = None,
        *,
        settings: Settings | None = None,
        session_factory: SessionFactory = SessionLocal,
        gateway: McpOAuthHttpClient | None = None,
        state_service: ConnectorOAuthStateService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self._gateway_client = gateway
        self.state_service = state_service or ConnectorOAuthStateService(
            settings=self.settings
        )

    @property
    def gateway(self) -> McpOAuthHttpClient:
        if self._gateway_client is None:
            self._gateway_client = HttpMcpOAuthGateway(self.settings)
        return self._gateway_client

    def public_client_metadata(self) -> dict[str, Any]:
        """Return the public CIMD document; it contains no tenant data."""

        configured = self._client_metadata_url()
        if configured is None:
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "MCP Client ID Metadata Documents are not configured.",
            )
        redirect_uri = self._redirect_uri()
        return {
            "client_id": configured,
            "client_name": "Geem",
            "client_uri": self._public_client_uri(),
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "application_type": "web",
        }

    def start_authorization(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        connection_id: uuid.UUID,
        return_path: str | None,
        requested_scopes: list[str] | None = None,
        reauthorize: bool = False,
    ) -> McpOAuthStartOut:
        self._require_enabled()
        snapshot = self._admit_start(
            workspace_id=workspace_id,
            actor_id=actor_id,
            connection_id=connection_id,
        )
        try:
            flow = self._discover_flow(snapshot, requested_scopes=requested_scopes)
        except AppError as exc:
            # The create transaction has already committed. Persist a safe,
            # compare-and-set failure state so a rejected provider bootstrap
            # cannot leave a new connection looking perpetually in progress.
            self._mark_start_failure(snapshot=snapshot, error=exc)
            raise
        persisted = self._persist_start(
            snapshot=snapshot,
            flow=flow,
            reauthorize=reauthorize,
        )
        binding = {
            "credential_epoch": persisted.credential_epoch,
            "credential_token_sha256": _sha256_text(
                persisted.encrypted_credentials
            ),
            "resource": flow.resource_uri,
            "resource_metadata": flow.resource_metadata_url,
            "issuer": flow.metadata.issuer,
            "authorization_endpoint": flow.metadata.authorization_endpoint,
            "token_endpoint": flow.metadata.token_endpoint,
            "revocation_endpoint": flow.metadata.revocation_endpoint,
            "client_id": flow.registration.client_id,
            "strategy": flow.registration.strategy,
            "scopes": list(flow.scopes),
            "token_endpoint_auth_method": (
                flow.registration.token_endpoint_auth_method
            ),
            "authorization_response_iss_parameter_supported": (
                flow.metadata.authorization_response_iss_parameter_supported
            ),
            "redirect_uri": self._redirect_uri(),
            "reauthorization": persisted.reauthorization,
        }
        state = self.state_service.create(
            workspace_id=workspace_id,
            actor_id=actor_id,
            app_installation_id=persisted.installation_id,
            connector_key=MCP_CONNECTOR_KEY,
            connection_id=connection_id,
            return_path=return_path or f"/apps/mcp/servers/{connection_id}",
            include_pkce=True,
            binding=binding,
        )
        if not state.code_verifier:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "Unable to create an OAuth PKCE binding.",
            )
        challenge = _pkce_s256(state.code_verifier)
        authorization_url = _authorization_url(
            flow.metadata.authorization_endpoint,
            client_id=flow.registration.client_id,
            redirect_uri=self._redirect_uri(),
            state=state.state,
            code_challenge=challenge,
            resource=flow.resource_uri,
            scopes=flow.scopes,
        )
        return McpOAuthStartOut(authorization_url=authorization_url)

    def complete_callback(
        self,
        *,
        state: str,
        code: str | None,
        issuer_parameter: str | None,
        oauth_error: str | None,
    ) -> McpOAuthCallbackResult:
        payload = self.state_service.consume_once(state)
        self._require_enabled()
        if payload.connector_key != MCP_CONNECTOR_KEY or payload.connection_id is None:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state connector binding is invalid.",
            )
        return_path = payload.return_path or f"/apps/mcp/servers/{payload.connection_id}"
        binding = _validated_state_binding(payload)
        try:
            _validate_callback_issuer(
                issuer_parameter,
                expected_issuer=str(binding["issuer"]),
                required=bool(
                    binding["authorization_response_iss_parameter_supported"]
                ),
                settings=self.settings,
            )
            if oauth_error:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "MCP authorization was not completed.",
                )
            clean_code = _bounded_secret(code, field="authorization code", maximum=8_192)
            snapshot = self._admit_callback(payload=payload, binding=binding)
            token = self._exchange_authorization_code(
                snapshot=snapshot,
                binding=binding,
                code=clean_code,
                code_verifier=payload.code_verifier,
            )
            self._persist_callback(
                payload=payload,
                binding=binding,
                snapshot=snapshot,
                token=token,
            )
            return McpOAuthCallbackResult(
                success=True,
                connection_id=payload.connection_id,
                return_path=return_path,
            )
        except AppError as exc:
            self._mark_callback_failure(
                payload=payload,
                error_code=exc.category.value,
            )
            return McpOAuthCallbackResult(
                success=False,
                connection_id=payload.connection_id,
                return_path=return_path,
                error=exc.category.value,
            )

    def auth_status(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> McpAuthStatusOut:
        if self.db is None:
            raise RuntimeError("auth_status requires a request database session")
        row = McpRepository(self.db).get_connection(workspace_id, connection_id)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
        credentials = ConnectorCredentialService(
            self.db, settings=self.settings
        ).get_credentials(row) or {}
        config = credentials.get("mcp") if isinstance(credentials, dict) else None
        config = config if isinstance(config, dict) else {}
        auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
        issuer = str(auth.get("issuer") or auth.get("expected_issuer") or "")
        resource = str(config.get("resource_uri") or "")
        client_id = str(auth.get("client_id") or "")
        mode = "oauth" if row.auth_mode == ConnectorAuthMode.OAUTH2.value else (
            "static" if row.auth_mode == ConnectorAuthMode.API_KEY.value else "none"
        )
        hint = None
        if mode == "oauth" and client_id:
            hint = f"sha256:{_sha256_text(client_id)[:12]}"
        elif mode == "static" and auth.get("value"):
            hint = "configured"
        return McpAuthStatusOut(
            connection_id=row.id,
            auth_mode=mode,
            strategy=str(auth.get("strategy")) if auth.get("strategy") else None,
            status=row.status,
            issuer=endpoint_host(issuer) or None,
            # Historical field name retained for the current SPA contract. It
            # contains only a hostname, never a resource URL/path/query.
            resource_url=endpoint_host(resource) or None,
            external_identity_label=row.external_account_name,
            credential_epoch=row.mcp_credential_epoch,
            reauthorization_required=row.mcp_reauthorization_required,
            redacted_credential=hint,
        )

    def refresh_if_needed(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> bool:
        """Refresh an expiring token with paid admission and ciphertext CAS.

        Returns ``True`` only when this caller persisted a fresh token. A
        concurrent winner returns ``False`` and is never overwritten.
        """

        self._require_enabled()
        snapshot = self._admit_refresh(workspace_id, connection_id)
        if snapshot is None:
            return False
        refresh_token = _bounded_secret(
            snapshot.auth.get("refresh_token"),
            field="refresh token",
            maximum=_TOKEN_MAX,
        )
        binding = _refresh_binding(snapshot.auth, snapshot.resource_uri)
        try:
            token = self._request_token(
                token_endpoint=str(binding["token_endpoint"]),
                client_id=str(binding["client_id"]),
                client_secret=(
                    str(snapshot.auth["client_secret"])
                    if snapshot.auth.get("client_secret") is not None
                    else None
                ),
                auth_method=str(binding["token_endpoint_auth_method"]),
                form={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": str(binding["client_id"]),
                    "resource": snapshot.resource_uri,
                },
                operation_id=_operation_id("refresh", snapshot.connection_id),
                requested_scopes=tuple(_scope_list(snapshot.auth.get("scopes"))),
            )
        except _TokenEndpointError as exc:
            self.mark_reauthorization_required(
                workspace_id=workspace_id,
                connection_id=connection_id,
                error_code=exc.oauth_error or ErrorCategory.MCP_AUTH_REQUIRED.value,
            )
            raise AppError(
                ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                "This MCP server must be reauthorized.",
            ) from exc
        return self._persist_refresh(snapshot=snapshot, token=token)

    def mark_reauthorization_required(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        error_code: str = ErrorCategory.MCP_AUTH_REQUIRED.value,
    ) -> None:
        """Restrict an OAuth connection after a runtime 401/insufficient_scope."""

        db = self.session_factory()
        try:
            row = McpRepository(db).get_connection(
                workspace_id, connection_id, for_update=True
            )
            if row is None or row.auth_mode != ConnectorAuthMode.OAUTH2.value:
                db.rollback()
                return
            now = _now()
            row.mcp_reauthorization_required = True
            if row.status in {
                ConnectionStatus.ACTIVE.value,
                ConnectionStatus.DEGRADED.value,
            }:
                row.status = ConnectionStatus.DEGRADED.value
            row.health = ConnectionHealth.DEGRADED.value
            row.last_error_code = str(error_code)[:128]
            row.last_error_message = "MCP authorization must be renewed."
            row.last_error_at = now
            db.commit()
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def revoke_best_effort(
        self,
        *,
        connection_id: uuid.UUID,
        auth: Mapping[str, Any],
    ) -> bool:
        """Best-effort RFC 7009 revocation after local credential destruction.

        The caller must first commit the restrictive local disconnect.  This
        method performs no database work and never raises, so a remote outage,
        malformed historical credential, or revocation rejection cannot roll
        back or re-enable the local connection.  Prefer the refresh token: RFC
        7009 recommends invalidating access tokens derived from the same grant
        when a refresh token is revoked.
        """

        endpoint = auth.get("revocation_endpoint")
        refresh_token = auth.get("refresh_token")
        access_token = auth.get("access_token")
        token = refresh_token or access_token
        token_type_hint = "refresh_token" if refresh_token else "access_token"
        client_id = auth.get("client_id")
        auth_method = str(auth.get("token_endpoint_auth_method") or "")
        if (
            not isinstance(endpoint, str)
            or not endpoint.strip()
            or not isinstance(token, str)
            or not token
            or not isinstance(client_id, str)
            or not client_id
            or auth_method
            not in {"none", "client_secret_basic", "client_secret_post"}
        ):
            return False

        try:
            clean_endpoint = self._canonical_url(endpoint)
            clean_token = _bounded_secret(
                token,
                field="revocation token",
                maximum=_TOKEN_MAX,
            )
            clean_client_id = _bounded_client_id(client_id)
            client_secret = _optional_secret(
                auth.get("client_secret"), maximum=_CLIENT_SECRET_MAX
            )
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            form = {
                "token": clean_token,
                "token_type_hint": token_type_hint,
                "client_id": clean_client_id,
            }
            if auth_method == "client_secret_basic":
                if client_secret is None:
                    return False
                user = quote_plus(clean_client_id, safe="~")
                password = quote_plus(client_secret, safe="~")
                basic = base64.b64encode(
                    f"{user}:{password}".encode("utf-8")
                ).decode("ascii")
                headers["Authorization"] = f"Basic {basic}"
                form.pop("client_id", None)
            elif auth_method == "client_secret_post":
                if client_secret is None:
                    return False
                form["client_secret"] = client_secret
            response = self.gateway.request(
                operation_id=_operation_id("revoke", connection_id),
                method="POST",
                url=clean_endpoint,
                headers=headers,
                body=urlencode(form).encode("ascii"),
                follow_redirects=False,
            )
            return response.status_code in {200, 204}
        except Exception:  # noqa: BLE001 - cleanup is deliberately best effort
            # Never include the exception: transport errors may embed the
            # credential-bearing form body or the tenant-derived endpoint.
            logger.warning(
                "mcp_oauth_remote_revocation_failed",
                extra={"connection_id": str(connection_id)},
            )
            return False

    def _require_enabled(self) -> None:
        if not self.settings.mcp_connector_enabled:
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "MCP Connectors is not enabled.",
            )

    def _admit_start(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> _ConnectionSnapshot:
        db = self.session_factory()
        try:
            access = _begin_paid_access(db, workspace_id)
            _require_actor_can_connect(
                db, workspace_id=workspace_id, actor_id=actor_id
            )
            row = McpRepository(db).get_connection(
                workspace_id, connection_id, for_share=True
            )
            if row is None:
                raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
            if row.app_installation_id != access.installation_id:
                raise AppError(
                    ErrorCategory.CONNECTOR_ACCESS_REQUIRED,
                    "The MCP server installation is no longer active.",
                )
            if row.auth_mode != ConnectorAuthMode.OAUTH2.value:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "This MCP server is not configured for OAuth.",
                )
            if row.status not in CONNECTION_LIMIT_STATUSES:
                raise AppError(
                    ErrorCategory.CONNECTOR_CONNECTION_FAILED,
                    "The MCP server connection is not available for authorization.",
                )
            encrypted = row.credentials_encrypted
            credentials = ConnectorCredentialService(
                db, settings=self.settings
            ).get_credentials(row)
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            auth = config.get("auth") if isinstance(config, dict) else None
            if not encrypted or not isinstance(config, dict) or not isinstance(auth, dict):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "MCP OAuth configuration is unavailable.",
                )
            if str(auth.get("mode")) != "oauth":
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "This MCP server is not configured for OAuth.",
                )
            snapshot = _ConnectionSnapshot(
                workspace_id=workspace_id,
                actor_id=actor_id,
                installation_id=row.app_installation_id,
                connection_id=row.id,
                server_url=self._canonical_url(str(config.get("server_url") or "")),
                resource_uri=self._canonical_url(
                    str(config.get("resource_uri") or config.get("server_url") or "")
                ),
                auth=copy.deepcopy(auth),
                credential_epoch=row.mcp_credential_epoch,
                encrypted_credentials=encrypted,
                had_principal=row.mcp_principal_fingerprint is not None,
            )
            db.commit()
            return snapshot
        except AppError:
            _rollback(db)
            raise
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def _mark_start_failure(
        self,
        *,
        snapshot: _ConnectionSnapshot,
        error: AppError,
    ) -> None:
        """Best-effort, concurrency-safe persistence for OAuth setup failure."""

        db = self.session_factory()
        try:
            row = McpRepository(db).get_connection(
                snapshot.workspace_id, snapshot.connection_id, for_update=True
            )
            if (
                row is None
                or row.app_installation_id != snapshot.installation_id
                or row.auth_mode != ConnectorAuthMode.OAUTH2.value
                or row.mcp_credential_epoch != snapshot.credential_epoch
                or row.credentials_encrypted != snapshot.encrypted_credentials
                or (snapshot.had_principal and not row.mcp_reauthorization_required)
            ):
                _rollback(db)
                return
            row.status = ConnectionStatus.ERROR.value
            row.health = ConnectionHealth.FAILED.value
            row.mcp_reauthorization_required = True
            row.last_error_code = error.category.value[:128]
            row.last_error_message = "MCP OAuth authorization could not be started."
            row.last_error_at = _now()
            db.commit()
        except SQLAlchemyError:
            _rollback(db)
            # Failure-state persistence must never replace the original safe
            # provider error returned to the caller.
            logger.error("mcp_oauth_start_failure_persistence_failed")
        finally:
            db.close()

    def _discover_flow(
        self,
        snapshot: _ConnectionSnapshot,
        *,
        requested_scopes: list[str] | None,
    ) -> _AuthorizationFlow:
        challenge = self._oauth_challenge(snapshot)
        if challenge.status_code != 401:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The MCP server did not advertise an OAuth resource challenge.",
            )
        authenticate = _response_header(challenge.headers, "www-authenticate")
        metadata_value, challenged_scopes = _parse_bearer_challenge(authenticate)
        resource_metadata_url = self._canonical_url(metadata_value)
        protected = self._get_json(
            url=resource_metadata_url,
            operation_id=_operation_id("resource", snapshot.connection_id),
        )
        resource = self._canonical_url(_required_text(protected, "resource", 2_048))
        if resource != snapshot.resource_uri:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The OAuth protected resource does not match this MCP connection.",
            )
        raw_servers = protected.get("authorization_servers")
        if not isinstance(raw_servers, list) or not 1 <= len(raw_servers) <= _MAX_AUTH_SERVERS:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The MCP protected resource metadata is incomplete.",
            )
        issuers: list[str] = []
        for value in raw_servers:
            issuer = self._canonical_issuer(str(value) if isinstance(value, str) else "")
            if issuer not in issuers:
                issuers.append(issuer)
        expected = str(
            snapshot.auth.get("issuer")
            or snapshot.auth.get("registration_issuer")
            or snapshot.auth.get("expected_issuer")
            or ""
        )
        if expected:
            selected = self._canonical_issuer(expected)
            if selected not in issuers:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP authorization server changed and must be reviewed.",
                )
        elif len(issuers) == 1:
            selected = issuers[0]
        else:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "Select the expected OAuth issuer before authorizing this MCP server.",
            )
        authorization = self._discover_authorization_metadata(selected, snapshot.connection_id)
        protected_scopes = _scope_list(protected.get("scopes_supported"))
        configured_scopes = _scope_list(snapshot.auth.get("scopes"))
        override_scopes = (
            _scope_list(requested_scopes) if requested_scopes is not None else None
        )
        scopes = _select_scopes(
            challenged=challenged_scopes,
            protected=protected_scopes,
            configured=configured_scopes,
            override=override_scopes,
        )
        registration = self._registration(
            snapshot=snapshot,
            metadata=authorization,
        )
        return _AuthorizationFlow(
            resource_metadata_url=resource_metadata_url,
            resource_uri=resource,
            scopes=tuple(scopes),
            metadata=authorization,
            registration=registration,
        )

    def _oauth_challenge(
        self,
        snapshot: _ConnectionSnapshot,
    ) -> OAuthHttpResponse:
        """Obtain a Bearer challenge from Streamable HTTP or legacy servers."""

        # Modern Streamable HTTP starts with initialize. Only revisions that
        # define that method may be used here; the newer discovery protocol has
        # a different request shape and must never be paired with initialize.
        versions = self.settings.mcp_supported_protocol_version_list
        protocol_version = next(
            (
                version
                for version in ("2025-11-25", "2024-11-05")
                if version in versions
            ),
            None,
        )
        if protocol_version is not None:
            initialize = {
                "jsonrpc": "2.0",
                "id": "oauth-discovery",
                "method": "initialize",
                "params": {
                    "protocolVersion": protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "Geem", "version": "1"},
                },
            }
            challenge = self.gateway.request(
                operation_id=_operation_id("challengeinit", snapshot.connection_id),
                method="POST",
                url=snapshot.server_url,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                body=json.dumps(
                    initialize,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8"),
                follow_redirects=False,
            )
            if challenge.status_code not in {400, 404, 405}:
                return challenge

        # HTTP+SSE servers use GET. Streamable HTTP permits this compatibility
        # fallback only after the initialize endpoint rejects POST.
        return self.gateway.request(
            operation_id=_operation_id("challenge", snapshot.connection_id),
            method="GET",
            url=snapshot.server_url,
            headers={"Accept": "application/json, text/event-stream"},
            follow_redirects=True,
        )

    def _discover_authorization_metadata(
        self, issuer: str, connection_id: uuid.UUID
    ) -> _AuthorizationMetadata:
        for ordinal, url in enumerate(_metadata_candidates(issuer)):
            response = self.gateway.request(
                operation_id=_operation_id(f"asmeta{ordinal}", connection_id),
                method="GET",
                url=self._canonical_url(url),
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
            if response.status_code != 200:
                continue
            payload = _json_object(response.body, "authorization server metadata")
            actual_issuer = self._canonical_issuer(
                _required_text(payload, "issuer", 2_048)
            )
            if actual_issuer != issuer:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth authorization server issuer does not match discovery.",
                )
            methods = tuple(_text_list(payload.get("code_challenge_methods_supported")))
            if "S256" not in methods:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth authorization server does not support PKCE S256.",
                )
            response_types = _text_list(payload.get("response_types_supported"))
            if response_types and "code" not in response_types:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth authorization server does not support authorization code flow.",
                )
            grant_types = _text_list(payload.get("grant_types_supported"))
            if grant_types and "authorization_code" not in grant_types:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth authorization server does not support authorization code flow.",
                )
            return _AuthorizationMetadata(
                issuer=actual_issuer,
                authorization_endpoint=self._canonical_url(
                    _required_text(payload, "authorization_endpoint", 2_048)
                ),
                token_endpoint=self._canonical_url(
                    _required_text(payload, "token_endpoint", 2_048)
                ),
                registration_endpoint=self._optional_url(
                    payload.get("registration_endpoint")
                ),
                revocation_endpoint=self._optional_url(
                    payload.get("revocation_endpoint")
                ),
                code_challenge_methods_supported=methods,
                token_endpoint_auth_methods_supported=tuple(
                    _text_list(payload.get("token_endpoint_auth_methods_supported"))
                ),
                client_id_metadata_document_supported=(
                    payload.get("client_id_metadata_document_supported") is True
                ),
                authorization_response_iss_parameter_supported=(
                    payload.get("authorization_response_iss_parameter_supported") is True
                ),
            )
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "OAuth authorization server metadata could not be discovered.",
        )

    def _registration(
        self,
        *,
        snapshot: _ConnectionSnapshot,
        metadata: _AuthorizationMetadata,
    ) -> _Registration:
        strategy = str(snapshot.auth.get("strategy") or "")
        if strategy == "cimd":
            client_id = self._client_metadata_url()
            if client_id is None or not metadata.client_id_metadata_document_supported:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "This authorization server does not support the configured "
                    "Client ID Metadata Document.",
                )
            return _Registration(
                strategy=strategy,
                issuer=metadata.issuer,
                client_id=client_id,
                client_secret=None,
                token_endpoint_auth_method="none",
            )
        if strategy == "pre_registered":
            client_id = _bounded_client_id(snapshot.auth.get("client_id"))
            bound = str(
                snapshot.auth.get("registration_issuer")
                or snapshot.auth.get("expected_issuer")
                or ""
            )
            if bound and self._canonical_issuer(bound) != metadata.issuer:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "Pre-registered OAuth credentials are bound to another issuer.",
                )
            secret = _optional_secret(
                snapshot.auth.get("client_secret"), maximum=_CLIENT_SECRET_MAX
            )
            method = _select_token_auth_method(
                secret=secret,
                supported=metadata.token_endpoint_auth_methods_supported,
                preferred=str(snapshot.auth.get("token_endpoint_auth_method") or "") or None,
            )
            return _Registration(
                strategy=strategy,
                issuer=metadata.issuer,
                client_id=client_id,
                client_secret=secret,
                token_endpoint_auth_method=method,
            )
        if strategy != "dynamic_registration":
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The MCP OAuth registration strategy is invalid.",
            )
        existing_issuer = str(snapshot.auth.get("registration_issuer") or "")
        existing_client = snapshot.auth.get("client_id")
        if existing_issuer and existing_client:
            if self._canonical_issuer(existing_issuer) != metadata.issuer:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "Dynamically registered OAuth credentials are bound to another issuer.",
                )
            secret = _optional_secret(
                snapshot.auth.get("client_secret"), maximum=_CLIENT_SECRET_MAX
            )
            return _Registration(
                strategy=strategy,
                issuer=metadata.issuer,
                client_id=_bounded_client_id(existing_client),
                client_secret=secret,
                token_endpoint_auth_method=_select_token_auth_method(
                    secret=secret,
                    supported=metadata.token_endpoint_auth_methods_supported,
                    preferred=str(snapshot.auth.get("token_endpoint_auth_method") or "") or None,
                ),
            )
        if metadata.registration_endpoint is None:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "This authorization server does not advertise dynamic client registration.",
            )
        registration_auth_method = _select_dynamic_registration_auth_method(
            metadata.token_endpoint_auth_methods_supported
        )
        registration_body = {
            "client_name": "Geem",
            "redirect_uris": [self._redirect_uri()],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": registration_auth_method,
            "application_type": "web",
        }
        response = self.gateway.request(
            operation_id=_operation_id("register", snapshot.connection_id),
            method="POST",
            url=metadata.registration_endpoint,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            body=json.dumps(
                registration_body, separators=(",", ":"), allow_nan=False
            ).encode("utf-8"),
            follow_redirects=False,
        )
        if response.status_code == 429:
            raise AppError(
                ErrorCategory.RATE_LIMITED,
                "The OAuth provider temporarily rate-limited client registration.",
                retryable=True,
            )
        if response.status_code >= 500:
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The OAuth provider could not complete client registration.",
                retryable=True,
            )
        if response.status_code not in {200, 201}:
            raise AppError(
                ErrorCategory.MCP_OAUTH_CLIENT_REGISTRATION_FAILED,
                "The OAuth provider rejected this MCP client registration.",
            )
        try:
            registered = _json_object(response.body, "dynamic client registration")
            client_id = _bounded_client_id(registered.get("client_id"))
            secret = _optional_secret(
                registered.get("client_secret"), maximum=_CLIENT_SECRET_MAX
            )
            advertised_method = str(
                registered.get("token_endpoint_auth_method") or ""
            ).strip()
            method = _select_token_auth_method(
                secret=secret,
                supported=metadata.token_endpoint_auth_methods_supported,
                preferred=advertised_method or registration_auth_method,
            )
        except AppError as exc:
            raise AppError(
                ErrorCategory.MCP_OAUTH_CLIENT_REGISTRATION_FAILED,
                "The OAuth provider returned an invalid client registration.",
            ) from exc
        return _Registration(
            strategy=strategy,
            issuer=metadata.issuer,
            client_id=client_id,
            client_secret=secret,
            token_endpoint_auth_method=method,
        )

    def _persist_start(
        self,
        *,
        snapshot: _ConnectionSnapshot,
        flow: _AuthorizationFlow,
        reauthorize: bool,
    ) -> _PersistedStart:
        db = self.session_factory()
        try:
            access = _begin_paid_access(db, snapshot.workspace_id)
            _require_actor_can_connect(
                db,
                workspace_id=snapshot.workspace_id,
                actor_id=snapshot.actor_id,
            )
            row = McpRepository(db).get_connection(
                snapshot.workspace_id, snapshot.connection_id, for_update=True
            )
            if (
                row is None
                or row.app_installation_id != access.installation_id
                or row.app_installation_id != snapshot.installation_id
                or row.mcp_credential_epoch != snapshot.credential_epoch
                or row.credentials_encrypted != snapshot.encrypted_credentials
                or row.auth_mode != ConnectorAuthMode.OAUTH2.value
            ):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP connection changed while OAuth was being prepared.",
                )
            credentials = ConnectorCredentialService(
                db, settings=self.settings
            ).get_credentials(row) or {}
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            auth = config.get("auth") if isinstance(config, dict) else None
            if not isinstance(config, dict) or not isinstance(auth, dict):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "MCP OAuth configuration is unavailable.",
                )
            updated_auth = copy.deepcopy(auth)
            old_bound = (
                str(auth.get("issuer") or ""),
                str(auth.get("client_id") or ""),
                str(auth.get("authorization_endpoint") or ""),
                str(auth.get("token_endpoint") or ""),
            )
            new_bound = (
                flow.metadata.issuer,
                flow.registration.client_id,
                flow.metadata.authorization_endpoint,
                flow.metadata.token_endpoint,
            )
            binding_changed = all(old_bound) and old_bound != new_bound
            if binding_changed:
                row.mcp_credential_epoch += 1
                row.mcp_principal_fingerprint = None
                row.external_account_id = None
                row.external_account_name = None
                McpRepository(db).stale_grants_for_principal(row.id)
            updated_auth.update(
                {
                    "mode": "oauth",
                    "strategy": flow.registration.strategy,
                    "issuer": flow.metadata.issuer,
                    "registration_issuer": flow.registration.issuer,
                    "client_id": flow.registration.client_id,
                    "token_endpoint_auth_method": (
                        flow.registration.token_endpoint_auth_method
                    ),
                    "authorization_endpoint": flow.metadata.authorization_endpoint,
                    "token_endpoint": flow.metadata.token_endpoint,
                    "registration_endpoint": flow.metadata.registration_endpoint,
                    "revocation_endpoint": flow.metadata.revocation_endpoint,
                    "resource_metadata_url": flow.resource_metadata_url,
                    "scopes": list(flow.scopes),
                }
            )
            if flow.registration.client_secret is None:
                updated_auth.pop("client_secret", None)
            else:
                updated_auth["client_secret"] = flow.registration.client_secret
            config = {
                **config,
                "server_url": snapshot.server_url,
                "resource_uri": flow.resource_uri,
                "auth": updated_auth,
            }
            ConnectorCredentialService(
                db, settings=self.settings
            ).replace_credentials(
                row,
                {**credentials, "mcp": config},
                expires_at=row.credentials_expires_at,
                merge_refresh=False,
            )
            row.status = ConnectionStatus.CONNECTING.value
            row.health = ConnectionHealth.UNKNOWN.value
            row.mcp_reauthorization_required = bool(
                reauthorize
                or snapshot.had_principal
                or auth.get("access_token")
                or row.mcp_reauthorization_required
            )
            row.last_error_code = None
            row.last_error_message = None
            row.last_error_at = None
            db.flush()
            encrypted = row.credentials_encrypted
            if not encrypted:
                raise AppError(
                    ErrorCategory.CONNECTOR_CONNECTION_FAILED,
                    "Unable to persist the OAuth registration binding.",
                )
            result = _PersistedStart(
                installation_id=row.app_installation_id,
                credential_epoch=row.mcp_credential_epoch,
                encrypted_credentials=encrypted,
                reauthorization=row.mcp_reauthorization_required,
            )
            db.commit()
            return result
        except AppError:
            _rollback(db)
            raise
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def _admit_callback(
        self,
        *,
        payload: OAuthStatePayload,
        binding: dict[str, Any],
    ) -> _ConnectionSnapshot:
        assert payload.connection_id is not None
        db = self.session_factory()
        try:
            access = _begin_paid_access(db, payload.workspace_id)
            _require_actor_can_connect(
                db,
                workspace_id=payload.workspace_id,
                actor_id=payload.actor_id,
            )
            row = McpRepository(db).get_connection(
                payload.workspace_id, payload.connection_id, for_share=True
            )
            if (
                row is None
                or row.app_installation_id != access.installation_id
                or row.app_installation_id != payload.app_installation_id
                or row.mcp_credential_epoch != int(binding["credential_epoch"])
                or row.auth_mode != ConnectorAuthMode.OAUTH2.value
                or not row.credentials_encrypted
                or _sha256_text(row.credentials_encrypted)
                != binding["credential_token_sha256"]
            ):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP connection changed during OAuth authorization.",
                )
            credentials = ConnectorCredentialService(
                db, settings=self.settings
            ).get_credentials(row) or {}
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            auth = config.get("auth") if isinstance(config, dict) else None
            if not isinstance(config, dict) or not isinstance(auth, dict):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "MCP OAuth configuration is unavailable.",
                )
            _assert_auth_binding(auth, config, binding)
            snapshot = _ConnectionSnapshot(
                workspace_id=payload.workspace_id,
                actor_id=payload.actor_id,
                installation_id=row.app_installation_id,
                connection_id=row.id,
                server_url=self._canonical_url(str(config.get("server_url") or "")),
                resource_uri=self._canonical_url(str(config.get("resource_uri") or "")),
                auth=copy.deepcopy(auth),
                credential_epoch=row.mcp_credential_epoch,
                encrypted_credentials=row.credentials_encrypted,
                had_principal=row.mcp_principal_fingerprint is not None,
            )
            db.commit()
            return snapshot
        except AppError:
            _rollback(db)
            raise
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def _exchange_authorization_code(
        self,
        *,
        snapshot: _ConnectionSnapshot,
        binding: dict[str, Any],
        code: str,
        code_verifier: str | None,
    ) -> dict[str, Any]:
        verifier = _bounded_secret(
            code_verifier, field="PKCE verifier", maximum=256
        )
        return self._request_token(
            token_endpoint=str(binding["token_endpoint"]),
            client_id=str(binding["client_id"]),
            client_secret=(
                str(snapshot.auth["client_secret"])
                if snapshot.auth.get("client_secret") is not None
                else None
            ),
            auth_method=str(binding["token_endpoint_auth_method"]),
            form={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": str(binding["redirect_uri"]),
                "client_id": str(binding["client_id"]),
                "code_verifier": verifier,
                "resource": str(binding["resource"]),
            },
            operation_id=_operation_id("token", snapshot.connection_id),
            requested_scopes=tuple(binding["scopes"]),
        )

    def _request_token(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        client_secret: str | None,
        auth_method: str,
        form: dict[str, str],
        operation_id: str,
        requested_scopes: tuple[str, ...],
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        encoded_form = dict(form)
        if auth_method == "client_secret_basic":
            if client_secret is None:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "OAuth client authentication is incomplete.",
                )
            user = quote_plus(client_id, safe="~")
            password = quote_plus(client_secret, safe="~")
            basic = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode(
                "ascii"
            )
            headers["Authorization"] = f"Basic {basic}"
            encoded_form.pop("client_id", None)
        elif auth_method == "client_secret_post":
            if client_secret is None:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "OAuth client authentication is incomplete.",
                )
            encoded_form["client_secret"] = client_secret
        elif auth_method != "none":
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The OAuth token endpoint authentication method is unsupported.",
            )
        response = self.gateway.request(
            operation_id=operation_id,
            method="POST",
            url=self._canonical_url(token_endpoint),
            headers=headers,
            body=urlencode(encoded_form).encode("ascii"),
            follow_redirects=False,
        )
        if response.status_code != 200:
            oauth_error = ""
            try:
                failure = _json_object(response.body, "OAuth token error")
                raw_error = failure.get("error")
                if isinstance(raw_error, str) and len(raw_error) <= 128:
                    oauth_error = raw_error
            except AppError:
                pass
            if response.status_code in {400, 401, 403}:
                raise _TokenEndpointError(oauth_error, response.status_code)
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The OAuth token endpoint could not complete the request.",
                retryable=response.status_code >= 500,
            )
        payload = _json_object(response.body, "OAuth token response")
        access_token = _bounded_secret(
            payload.get("access_token"), field="access token", maximum=_TOKEN_MAX
        )
        token_type = str(payload.get("token_type") or "Bearer").strip()
        if token_type.casefold() != "bearer":
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The MCP authorization server returned an unsupported token type.",
            )
        result: dict[str, Any] = {
            "access_token": access_token,
            "token_type": "Bearer",
        }
        if payload.get("refresh_token") not in {None, ""}:
            result["refresh_token"] = _bounded_secret(
                payload.get("refresh_token"),
                field="refresh token",
                maximum=_TOKEN_MAX,
            )
        if payload.get("expires_in") is not None:
            try:
                expires_in = int(payload["expires_in"])
            except (TypeError, ValueError) as exc:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth token expiry is invalid.",
                ) from exc
            if not 1 <= expires_in <= 315_576_000:
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth token expiry is invalid.",
                )
            result["expires_in"] = expires_in
        granted = _scope_list(payload.get("scope"))
        if granted:
            if requested_scopes and not set(granted).issubset(requested_scopes):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "The OAuth token response widened the approved scope set.",
                )
            result["scope"] = " ".join(granted)
        elif requested_scopes:
            result["scope"] = " ".join(requested_scopes)
        return result

    def _persist_callback(
        self,
        *,
        payload: OAuthStatePayload,
        binding: dict[str, Any],
        snapshot: _ConnectionSnapshot,
        token: dict[str, Any],
    ) -> None:
        assert payload.connection_id is not None
        db = self.session_factory()
        try:
            access = _begin_paid_access(db, payload.workspace_id)
            _require_actor_can_connect(
                db,
                workspace_id=payload.workspace_id,
                actor_id=payload.actor_id,
            )
            row = McpRepository(db).get_connection(
                payload.workspace_id, payload.connection_id, for_update=True
            )
            if (
                row is None
                or row.app_installation_id != access.installation_id
                or row.app_installation_id != payload.app_installation_id
                or row.mcp_credential_epoch != snapshot.credential_epoch
                or row.credentials_encrypted != snapshot.encrypted_credentials
                or row.auth_mode != ConnectorAuthMode.OAUTH2.value
            ):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP connection changed before OAuth credentials could be saved.",
                )
            credentials = ConnectorCredentialService(
                db, settings=self.settings
            ).get_credentials(row) or {}
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            auth = config.get("auth") if isinstance(config, dict) else None
            if not isinstance(config, dict) or not isinstance(auth, dict):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "MCP OAuth configuration is unavailable.",
                )
            _assert_auth_binding(auth, config, binding)
            # An authorization-code callback creates a new grant. Never carry
            # an older grant's refresh token into it when the server omits a
            # new optional refresh token.
            updated_auth = _apply_mcp_token_response(
                _without_token_material(auth), token
            )
            updated_auth["token_type"] = "Bearer"
            updated_auth["scopes"] = list(binding["scopes"])
            if not updated_auth.get("granted_scopes"):
                updated_auth["granted_scopes"] = list(binding["scopes"])
            new_principal = principal_fingerprint(
                server_url=str(config["server_url"]),
                resource_uri=str(binding["resource"]),
                auth_mode="oauth",
                issuer=str(binding["issuer"]),
                client_id=str(binding["client_id"]),
            )
            conservative_reauth = bool(binding.get("reauthorization"))
            if row.mcp_principal_fingerprint is not None and (
                row.mcp_principal_fingerprint != new_principal
                or conservative_reauth
            ):
                row.mcp_credential_epoch += 1
                McpRepository(db).stale_grants_for_principal(row.id)
                row.external_account_id = None
                row.external_account_name = None
            row.mcp_principal_fingerprint = new_principal
            now = _now()
            row.mcp_reauthorization_required = False
            row.status = ConnectionStatus.ACTIVE.value
            row.health = ConnectionHealth.UNKNOWN.value
            row.connected_by_user_id = payload.actor_id
            row.connected_at = now
            row.disconnected_at = None
            row.last_error_code = None
            row.last_error_message = None
            row.last_error_at = None
            config = {**config, "resource_uri": str(binding["resource"]), "auth": updated_auth}
            expires_at = expires_at_from_credentials(updated_auth)
            if expires_at is None:
                row.credentials_expires_at = None
            ConnectorCredentialService(
                db, settings=self.settings
            ).replace_credentials(
                row,
                {**credentials, "mcp": config},
                expires_at=expires_at,
                merge_refresh=False,
            )
            record_audit(
                db,
                action=AuditAction.APP_CONNECTION_UPDATED,
                entity_type=AuditEntityType.APP_CONNECTION,
                entity_id=row.id,
                workspace_id=payload.workspace_id,
                actor_user_id=payload.actor_id,
                metadata={
                    "connection_id": str(row.id),
                    "connector_key": MCP_CONNECTOR_KEY,
                    "mode": "oauth",
                    "strategy": str(binding["strategy"]),
                    "credential_epoch": row.mcp_credential_epoch,
                },
                allowlist=frozenset(
                    {
                        "connection_id",
                        "connector_key",
                        "mode",
                        "strategy",
                        "credential_epoch",
                    }
                ),
            )
            db.commit()
        except AppError:
            _rollback(db)
            raise
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def _mark_callback_failure(
        self,
        *,
        payload: OAuthStatePayload,
        error_code: str,
    ) -> None:
        if payload.connection_id is None:
            return
        db = self.session_factory()
        try:
            row = McpRepository(db).get_connection(
                payload.workspace_id, payload.connection_id, for_update=True
            )
            if row is None or row.auth_mode != ConnectorAuthMode.OAUTH2.value:
                db.rollback()
                return
            row.mcp_reauthorization_required = True
            row.status = ConnectionStatus.ERROR.value
            row.health = ConnectionHealth.FAILED.value
            row.last_error_code = str(error_code)[:128]
            row.last_error_message = "MCP OAuth authorization failed."
            row.last_error_at = _now()
            db.commit()
        except SQLAlchemyError:
            _rollback(db)
            logger.error("mcp_oauth_callback_failure_persistence_failed")
        finally:
            db.close()

    def _admit_refresh(
        self, workspace_id: uuid.UUID, connection_id: uuid.UUID
    ) -> _ConnectionSnapshot | None:
        db = self.session_factory()
        try:
            access = _begin_paid_access(db, workspace_id)
            row = McpRepository(db).get_connection(
                workspace_id, connection_id, for_share=True
            )
            if row is None:
                raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
            if row.app_installation_id != access.installation_id:
                raise AppError(
                    ErrorCategory.CONNECTOR_ACCESS_REQUIRED,
                    "The MCP server installation is no longer active.",
                )
            if row.auth_mode != ConnectorAuthMode.OAUTH2.value:
                db.commit()
                return None
            if row.mcp_reauthorization_required:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                )
            encrypted = row.credentials_encrypted
            credentials = ConnectorCredentialService(
                db, settings=self.settings
            ).get_credentials(row) or {}
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            auth = config.get("auth") if isinstance(config, dict) else None
            if not encrypted or not isinstance(config, dict) or not isinstance(auth, dict):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                )
            if not credentials_need_refresh(auth):
                db.commit()
                return None
            if not auth.get("refresh_token"):
                db.commit()
                self.mark_reauthorization_required(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                )
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                )
            snapshot = _ConnectionSnapshot(
                workspace_id=workspace_id,
                actor_id=row.connected_by_user_id or uuid.UUID(int=0),
                installation_id=row.app_installation_id,
                connection_id=row.id,
                server_url=self._canonical_url(str(config.get("server_url") or "")),
                resource_uri=self._canonical_url(str(config.get("resource_uri") or "")),
                auth=copy.deepcopy(auth),
                credential_epoch=row.mcp_credential_epoch,
                encrypted_credentials=encrypted,
                had_principal=row.mcp_principal_fingerprint is not None,
            )
            db.commit()
            return snapshot
        except AppError:
            _rollback(db)
            raise
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def _persist_refresh(
        self,
        *,
        snapshot: _ConnectionSnapshot,
        token: dict[str, Any],
    ) -> bool:
        db = self.session_factory()
        try:
            access = _begin_paid_access(db, snapshot.workspace_id)
            row = McpRepository(db).get_connection(
                snapshot.workspace_id, snapshot.connection_id, for_update=True
            )
            if row is None or row.app_installation_id != access.installation_id:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP connection changed during token refresh.",
                )
            credentials = ConnectorCredentialService(
                db, settings=self.settings
            ).get_credentials(row) or {}
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            current_auth = config.get("auth") if isinstance(config, dict) else None
            if not isinstance(config, dict) or not isinstance(current_auth, dict):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                )
            if (
                row.auth_mode != ConnectorAuthMode.OAUTH2.value
                or row.mcp_reauthorization_required
                or row.mcp_credential_epoch != snapshot.credential_epoch
            ):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP credential changed during token refresh.",
                )
            if row.credentials_encrypted != snapshot.encrypted_credentials:
                # A concurrent refresh winner must never be overwritten with a
                # response based on an older rotating refresh token.
                if _is_concurrent_refresh_winner(
                    snapshot_auth=snapshot.auth,
                    snapshot_resource=snapshot.resource_uri,
                    current_auth=current_auth,
                    current_resource=str(config.get("resource_uri") or ""),
                ):
                    db.commit()
                    return False
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP credential changed during token refresh.",
                )
            _assert_refresh_binding(snapshot.auth, current_auth, snapshot.resource_uri)
            updated_auth = _apply_mcp_token_response(current_auth, token)
            updated_auth["token_type"] = "Bearer"
            expires_at = expires_at_from_credentials(updated_auth)
            if expires_at is None:
                row.credentials_expires_at = None
            ConnectorCredentialService(
                db, settings=self.settings
            ).replace_credentials(
                row,
                {**credentials, "mcp": {**config, "auth": updated_auth}},
                expires_at=expires_at,
                merge_refresh=False,
            )
            row.last_error_code = None
            row.last_error_message = None
            row.last_error_at = None
            db.commit()
            return True
        except AppError:
            _rollback(db)
            raise
        except SQLAlchemyError as exc:
            _rollback(db)
            raise _paid_db_error() from exc
        finally:
            db.close()

    def _get_json(self, *, url: str, operation_id: str) -> dict[str, Any]:
        response = self.gateway.request(
            operation_id=operation_id,
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
        if response.status_code != 200:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "MCP OAuth metadata could not be loaded.",
            )
        return _json_object(response.body, "MCP OAuth metadata")

    def _canonical_url(self, value: str) -> str:
        allow_private = self.settings.is_local and self.settings.mcp_allow_private_egress
        return canonicalize_mcp_url(
            value,
            allow_http=allow_private,
            allow_private_hostnames=allow_private,
        )

    def _canonical_issuer(self, value: str) -> str:
        canonical = self._canonical_url(value)
        parsed = urlsplit(canonical)
        if parsed.query:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The OAuth issuer identifier is invalid.",
            )
        return canonical.rstrip("/")

    def _optional_url(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "OAuth authorization server metadata contains an invalid endpoint.",
            )
        return self._canonical_url(value)

    def _redirect_uri(self) -> str:
        return self._canonical_public_url(
            effective_oauth_redirect_uri(self.settings, MCP_CONNECTOR_KEY)
        )

    def _client_metadata_url(self) -> str | None:
        value = (self.settings.mcp_client_metadata_url or "").strip()
        if not value:
            return None
        canonical = self._canonical_public_url(value)
        parsed = urlsplit(canonical)
        if parsed.path in {"", "/"} or parsed.query:
            raise AppError(
                ErrorCategory.VALIDATION,
                "MCP_CLIENT_METADATA_URL must be a stable public HTTPS document URL.",
            )
        return canonical

    def _public_client_uri(self) -> str:
        value = (self.settings.effective_workspace_web_url or self.settings.app_url).strip()
        canonical = self._canonical_public_url(value)
        parsed = urlsplit(canonical)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    def _canonical_public_url(self, value: str) -> str:
        parsed = urlsplit(value)
        if self.settings.is_local and parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
        }:
            if parsed.username or parsed.password or parsed.fragment:
                raise AppError(ErrorCategory.VALIDATION, "OAuth public URL is invalid.")
            return value
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise AppError(
                ErrorCategory.VALIDATION,
                "OAuth public URLs must use public HTTPS.",
            )
        return value


def _response_header(headers: Mapping[str, str], name: str) -> str:
    lowered = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == lowered:
            return str(value)
    raise AppError(
        ErrorCategory.MCP_AUTH_REQUIRED,
        "The MCP server OAuth challenge is incomplete.",
    )


def _parse_bearer_challenge(value: str) -> tuple[str, list[str]]:
    """Parse one Bearer challenge without treating quoted commas as separators."""

    active = False
    parameters: dict[str, str] = {}
    for raw_item in parse_http_list(value):
        item = raw_item.strip()
        scheme_match = re.match(r"^([A-Za-z][A-Za-z0-9!#$%&'*+.^_`|~-]*)\s+(.*)$", item)
        if scheme_match and "=" not in scheme_match.group(1):
            active = scheme_match.group(1).casefold() == "bearer"
            item = scheme_match.group(2).strip()
        if not active or "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        key = key.strip().casefold()
        raw_value = raw_value.strip()
        if raw_value.startswith('"') and raw_value.endswith('"'):
            raw_value = raw_value[1:-1]
            raw_value = re.sub(r"\\(.)", r"\1", raw_value)
        if key in parameters:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The MCP server OAuth challenge is ambiguous.",
            )
        parameters[key] = raw_value
    metadata = parameters.get("resource_metadata")
    if not metadata:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "The MCP server did not advertise protected resource metadata.",
        )
    scopes = _scope_list(parameters.get("scope"))
    return metadata, scopes


def _json_object(body: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            f"The {label} response is not valid JSON.",
        ) from exc
    if not isinstance(value, dict) or len(value) > _MAX_METADATA_ITEMS:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            f"The {label} response is invalid.",
        )
    return value


def _required_text(payload: Mapping[str, Any], key: str, maximum: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "OAuth metadata is missing a required field.",
        )
    if any(ord(char) < 0x20 for char in value):
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "OAuth metadata contains an invalid field.",
        )
    return value.strip()


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_METADATA_ITEMS:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "OAuth metadata contains an invalid list.",
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 512:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "OAuth metadata contains an invalid list item.",
            )
        if item not in result:
            result.append(item)
    return result


def _scope_list(value: Any) -> list[str]:
    if value is None:
        return []
    items: list[Any]
    if isinstance(value, str):
        items = value.split()
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "OAuth scopes are invalid.",
        )
    if len(items) > 64:
        raise AppError(ErrorCategory.MCP_AUTH_REQUIRED, "Too many OAuth scopes.")
    result: list[str] = []
    for item in items:
        if not isinstance(item, str) or not _SCOPE.fullmatch(item):
            raise AppError(ErrorCategory.MCP_AUTH_REQUIRED, "OAuth scopes are invalid.")
        if item not in result:
            result.append(item)
    return result


def _apply_mcp_token_response(
    current: Mapping[str, Any], token: dict[str, Any]
) -> dict[str, Any]:
    """Merge a token response without retaining an obsolete expiry.

    ``expires_in`` is optional.  When a refreshed access token omits it, the
    previous token's absolute expiry must not make the new token immediately
    refresh again.  Such a token remains usable until the server rejects it.
    """

    updated = apply_token_response(dict(current), token)
    if "expires_in" not in token:
        updated.pop("expires_in", None)
        updated.pop("expires_at", None)
    return updated


def _without_token_material(auth: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = dict(auth)
    for key in (
        "access_token",
        "refresh_token",
        "token_type",
        "expires_in",
        "expires_at",
        "granted_scopes",
    ):
        cleaned.pop(key, None)
    return cleaned


def _select_scopes(
    *,
    challenged: list[str],
    protected: list[str],
    configured: list[str],
    override: list[str] | None,
) -> list[str]:
    if override is not None:
        selected = list(override)
    elif configured:
        selected = list(configured)
    elif challenged:
        selected = list(challenged)
    else:
        selected = list(protected)
    if challenged and not set(challenged).issubset(selected):
        raise AppError(
            ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
            "The MCP server requires scopes that were not explicitly approved.",
        )
    if protected and selected and not set(selected).issubset(protected):
        # Challenged scopes are authoritative even if PRM's list is stale or
        # incomplete, as permitted by the MCP authorization specification.
        extra = set(selected) - set(protected)
        if not extra.issubset(challenged):
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The requested OAuth scopes are not advertised by this resource.",
            )
    return selected


def _metadata_candidates(issuer: str) -> tuple[str, ...]:
    parsed = urlsplit(issuer)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    path = parsed.path.strip("/")
    suffix = f"/{path}" if path else ""
    candidates = [
        f"{origin}/.well-known/oauth-authorization-server{suffix}",
        f"{origin}/.well-known/openid-configuration{suffix}",
    ]
    if path:
        candidates.append(f"{origin}/{path}/.well-known/openid-configuration")
    return tuple(candidates)


def _select_token_auth_method(
    *,
    secret: str | None,
    supported: tuple[str, ...],
    preferred: str | None,
) -> str:
    allowed = set(supported) if supported else {
        "client_secret_basic" if secret is not None else "none"
    }
    if preferred:
        if preferred not in {"none", "client_secret_basic", "client_secret_post"}:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The OAuth client authentication method is unsupported.",
            )
        if supported and preferred not in allowed:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The OAuth client authentication method is not advertised.",
            )
        if preferred != "none" and secret is None:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "OAuth client authentication is incomplete.",
            )
        return preferred
    if secret is None:
        if "none" not in allowed:
            raise AppError(
                ErrorCategory.MCP_AUTH_REQUIRED,
                "The OAuth server does not accept this public client.",
            )
        return "none"
    for candidate in ("client_secret_basic", "client_secret_post"):
        if candidate in allowed:
            return candidate
    raise AppError(
        ErrorCategory.MCP_AUTH_REQUIRED,
        "The OAuth server does not support the configured client authentication.",
    )


def _select_dynamic_registration_auth_method(supported: tuple[str, ...]) -> str:
    """Choose the safest client type the authorization server advertises."""

    if not supported:
        # RFC 8414 defines client_secret_basic as the default when authorization
        # server metadata omits token_endpoint_auth_methods_supported.
        return "client_secret_basic"
    for candidate in ("none", "client_secret_basic", "client_secret_post"):
        if candidate in supported:
            return candidate
    raise AppError(
        ErrorCategory.MCP_OAUTH_CLIENT_REGISTRATION_FAILED,
        "The OAuth provider does not support a compatible MCP client type.",
    )


def _bounded_client_id(value: Any) -> str:
    return _bounded_secret(value, field="client ID", maximum=_CLIENT_ID_MAX)


def _optional_secret(value: Any, *, maximum: int) -> str | None:
    if value is None or value == "":
        return None
    return _bounded_secret(value, field="OAuth client secret", maximum=maximum)


def _bounded_secret(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            f"The OAuth {field} is missing or invalid.",
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            f"The OAuth {field} is missing or invalid.",
        )
    return value


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _authorization_url(
    endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    resource: str,
    scopes: tuple[str, ...],
) -> str:
    parsed = urlsplit(endpoint)
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    controlled = {
        "client_id",
        "redirect_uri",
        "response_type",
        "state",
        "code_challenge",
        "code_challenge_method",
        "resource",
        "scope",
    }
    if any(key.casefold() in controlled for key, _value in existing):
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "The OAuth authorization endpoint contains conflicting parameters.",
        )
    parameters = [
        *existing,
        ("response_type", "code"),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("state", state),
        ("code_challenge", code_challenge),
        ("code_challenge_method", "S256"),
        ("resource", resource),
    ]
    if scopes:
        parameters.append(("scope", " ".join(scopes)))
    rendered = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(parameters), "")
    )
    if len(rendered) > 8_192:
        raise AppError(
            ErrorCategory.MCP_AUTH_REQUIRED,
            "The OAuth authorization request is too large.",
        )
    return rendered


def _validated_state_binding(payload: OAuthStatePayload) -> dict[str, Any]:
    binding = payload.binding
    required = {
        "credential_epoch",
        "credential_token_sha256",
        "resource",
        "resource_metadata",
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "client_id",
        "strategy",
        "scopes",
        "token_endpoint_auth_method",
        "authorization_response_iss_parameter_supported",
        "redirect_uri",
        "reauthorization",
    }
    if not isinstance(binding, dict) or not required.issubset(binding):
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
            "OAuth state binding is incomplete.",
        )
    if (
        not isinstance(binding["credential_epoch"], int)
        or binding["credential_epoch"] < 1
        or not isinstance(binding["credential_token_sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", binding["credential_token_sha256"])
        or not isinstance(binding["scopes"], list)
        or not isinstance(binding["authorization_response_iss_parameter_supported"], bool)
        or not isinstance(binding["reauthorization"], bool)
    ):
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
            "OAuth state binding is invalid.",
        )
    _scope_list(binding["scopes"])
    for key in (
        "resource",
        "resource_metadata",
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "client_id",
        "strategy",
        "token_endpoint_auth_method",
        "redirect_uri",
    ):
        if not isinstance(binding[key], str) or not binding[key]:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "OAuth state binding is invalid.",
            )
    return dict(binding)


def _validate_callback_issuer(
    value: str | None,
    *,
    expected_issuer: str,
    required: bool,
    settings: Settings,
) -> None:
    if value is None or not value.strip():
        if required:
            raise AppError(
                ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
                "The OAuth authorization response omitted its issuer.",
            )
        return
    allow_private = settings.is_local and settings.mcp_allow_private_egress
    actual = canonicalize_mcp_url(
        value,
        allow_http=allow_private,
        allow_private_hostnames=allow_private,
    ).rstrip("/")
    if actual != expected_issuer.rstrip("/"):
        raise AppError(
            ErrorCategory.CONNECTOR_OAUTH_STATE_INVALID,
            "The OAuth authorization response issuer does not match.",
        )


def _assert_auth_binding(
    auth: Mapping[str, Any], config: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    checks = {
        "issuer": auth.get("issuer"),
        "client_id": auth.get("client_id"),
        "authorization_endpoint": auth.get("authorization_endpoint"),
        "token_endpoint": auth.get("token_endpoint"),
        "token_endpoint_auth_method": auth.get("token_endpoint_auth_method"),
        "strategy": auth.get("strategy"),
        "resource": config.get("resource_uri"),
    }
    for key, current in checks.items():
        if str(current or "") != str(binding.get(key) or ""):
            raise AppError(
                ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                "The MCP OAuth binding changed during authorization.",
            )
    if _scope_list(auth.get("scopes")) != _scope_list(binding.get("scopes")):
        raise AppError(
            ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
            "The MCP OAuth scopes changed during authorization.",
        )


def _refresh_binding(auth: Mapping[str, Any], resource: str) -> dict[str, str]:
    required = {
        "issuer": str(auth.get("issuer") or ""),
        "client_id": str(auth.get("client_id") or ""),
        "token_endpoint": str(auth.get("token_endpoint") or ""),
        "token_endpoint_auth_method": str(
            auth.get("token_endpoint_auth_method") or ""
        ),
        "resource": resource,
    }
    if any(not value for value in required.values()):
        raise AppError(
            ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
            "This MCP server must be reauthorized.",
        )
    return required


def _assert_refresh_binding(
    old: Mapping[str, Any], current: Mapping[str, Any], resource: str
) -> None:
    old_binding = _refresh_binding(old, resource)
    current_binding = _refresh_binding(current, resource)
    if old_binding != current_binding or old.get("refresh_token") != current.get(
        "refresh_token"
    ):
        raise AppError(
            ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
            "The MCP OAuth binding changed during token refresh.",
        )


def _is_concurrent_refresh_winner(
    *,
    snapshot_auth: Mapping[str, Any],
    snapshot_resource: str,
    current_auth: Mapping[str, Any],
    current_resource: str,
) -> bool:
    """Recognize a same-authority refresh winner without comparing token age.

    A valid rotated token can intentionally have a lifetime shorter than the
    proactive refresh skew.  The losing caller still must not overwrite it or
    incorrectly force reauthorization merely because it remains refreshable.
    """

    if not current_auth.get("access_token"):
        return False
    try:
        return _refresh_binding(
            snapshot_auth, snapshot_resource
        ) == _refresh_binding(current_auth, current_resource)
    except AppError:
        return False


def _operation_id(prefix: str, connection_id: uuid.UUID) -> str:
    return f"oauth-{prefix}:{connection_id.hex}"[:128]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "HttpMcpOAuthGateway",
    "McpOAuthCallbackResult",
    "McpOAuthHttpClient",
    "McpOAuthService",
    "OAuthHttpResponse",
    "_CIMD_ROUTE_PATH",
    "_OAUTH_CALLBACK_PATH",
]
