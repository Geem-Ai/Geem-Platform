"""MCP connection, discovery inventory, classification, and grant services.

Protected mutations deliberately use their own short READ COMMITTED session so
the paid-App fence and access decision are not inherited from a request-scoped
transaction.  Gateway I/O happens only after that admission transaction has
committed.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService, RuntimeAppAccessSnapshot
from app.apps_catalog.policy import require_connect_apps
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    begin_runtime_admission_transaction,
)
from app.audit import AuditAction, AuditEntityType, record_audit
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.locks import workspace_app_connection_lock
from app.connectors.models import AppConnection
from app.connectors.types import (
    CONNECTION_LIMIT_STATUSES,
    CONNECTION_USABLE_STATUSES,
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.experts.models import ExpertType
from app.mcp.constants import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTOR_KEY,
    MCP_CONNECTORS_APP_SLUG,
)
from app.mcp.gateway import (
    McpDiscoveryRequest,
    McpDiscoveryResult,
    McpGatewayClient,
    McpTargetValidationRequest,
    get_mcp_gateway_client,
)
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.normalization import (
    canonicalize_mcp_url,
    endpoint_host,
    normalize_tool_definition,
    principal_fingerprint,
)
from app.mcp.oauth import McpOAuthService
from app.mcp.repository import McpGrantRecord, McpRepository
from app.mcp.schemas import (
    McpDiscoverOut,
    McpGrantCreateIn,
    McpOAuthAuthIn,
    McpServerAuthOut,
    McpServerCreateIn,
    McpServerListOut,
    McpServerOut,
    McpStaticAuthIn,
    McpToolGrantListOut,
    McpToolGrantOut,
    McpToolListOut,
    McpToolOut,
)
from app.mcp.teardown import McpConnectionTeardownService
from app.mcp.types import (
    McpCompatibilityStatus,
    McpGrantState,
    McpToolClassification,
    McpToolStatus,
)
from app.workspaces.repository import MembershipRepository

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rollback_without_masking(db: Session) -> None:
    try:
        db.rollback()
    except SQLAlchemyError:
        logger.error("mcp_transaction_rollback_failed")


def _begin_paid_access(
    db: Session,
    *,
    workspace_id: uuid.UUID,
) -> RuntimeAppAccessSnapshot:
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


def _paid_db_error() -> AppError:
    return AppError(
        ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
        "MCP Connectors access is temporarily unavailable.",
        retryable=True,
    )


def _require_current_connect_actor(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    membership = MembershipRepository(db).get_for_update(workspace_id, actor_id)
    if membership is None:
        raise AppError(
            ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
            "Current Workspace App connection permission is required.",
        )
    require_connect_apps(membership)


def _tool_out(row: McpServerTool) -> McpToolOut:
    return McpToolOut(
        id=row.id,
        app_connection_id=row.app_connection_id,
        tool_name=row.tool_name,
        llm_tool_name=row.llm_tool_name,
        title=row.title,
        description=row.description,
        input_schema=dict(row.input_schema or {}),
        output_schema=dict(row.output_schema) if row.output_schema is not None else None,
        annotations=dict(row.annotations or {}),
        protocol_version=row.protocol_version,
        compatibility_status=row.compatibility_status,
        compatibility_reason=row.compatibility_reason,
        classification=row.classification,
        definition_hash=row.definition_hash,
        status=row.status,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        discovery_generation=row.discovery_generation,
    )


def _grant_out(record: McpGrantRecord) -> McpToolGrantOut:
    grant, tool, connection = record.grant, record.tool, record.connection
    return McpToolGrantOut(
        id=grant.id,
        expert_id=grant.expert_id,
        app_connection_id=grant.app_connection_id,
        tool_id=grant.mcp_server_tool_id,
        tool_name=tool.tool_name,
        llm_tool_name=tool.llm_tool_name,
        connection_display_name=connection.display_name or "MCP server",
        state=grant.state,
        approved_definition_hash=grant.approved_definition_hash,
        approved_classification=grant.approved_classification,
        approved_credential_epoch=grant.approved_credential_epoch,
        allow_workspace_chat=grant.allow_workspace_chat,
        allow_public_api=grant.allow_public_api,
        unattended_write_allowed=grant.unattended_write_allowed,
        outbound_data_acknowledged_at=grant.outbound_data_acknowledged_at,
        unattended_write_acknowledged_at=grant.unattended_write_acknowledged_at,
        approved_by_user_id=grant.approved_by_user_id,
        approved_at=grant.approved_at,
        revoked_at=grant.revoked_at,
        created_at=grant.created_at,
        updated_at=grant.updated_at,
    )


def _redacted_server_out(
    db: Session,
    connection: AppConnection,
    *,
    discovered_tool_count: int,
    settings: Settings,
) -> McpServerOut:
    credentials: dict[str, Any] = {}
    try:
        credentials = ConnectorCredentialService(
            db, settings=settings
        ).get_credentials(connection) or {}
    except Exception:  # corrupt/old ciphertext must never leak into a response
        logger.warning(
            "mcp_connection_credential_redaction_failed",
            extra={"connection_id": str(connection.id)},
        )
    config = credentials.get("mcp") if isinstance(credentials.get("mcp"), dict) else {}
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    mode = str(auth.get("mode") or _mcp_auth_mode(connection.auth_mode))
    issuer = str(auth.get("issuer") or auth.get("expected_issuer") or "")
    server_url = str(config.get("server_url") or "")
    return McpServerOut(
        id=connection.id,
        display_name=connection.display_name or "MCP server",
        endpoint_host=endpoint_host(server_url) or None,
        status=connection.status,
        health=connection.health,
        auth=McpServerAuthOut(
            mode=mode,
            strategy=str(auth.get("strategy")) if auth.get("strategy") else None,
            header_name=(
                str(auth.get("header_name")) if auth.get("header_name") else None
            ),
            secret_hint="configured" if mode == "static" and auth.get("value") else None,
            issuer_host=str(urlsplit(issuer).hostname or "") or None,
            reauthorization_required=connection.mcp_reauthorization_required,
        ),
        protocol_version=connection.mcp_protocol_version,
        session_mode=connection.mcp_session_mode,
        capabilities=dict(connection.mcp_capabilities or {}),
        credential_epoch=connection.mcp_credential_epoch,
        external_identity_label=connection.external_account_name,
        inventory_refreshed_at=connection.mcp_inventory_refreshed_at,
        discovered_tool_count=discovered_tool_count,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _mcp_auth_mode(connector_mode: str) -> str:
    if connector_mode == ConnectorAuthMode.NONE.value:
        return "none"
    if connector_mode == ConnectorAuthMode.API_KEY.value:
        return "static"
    if connector_mode == ConnectorAuthMode.OAUTH2.value:
        return "oauth"
    return "unknown"


def _connector_auth_mode(mode: str) -> str:
    return {
        "none": ConnectorAuthMode.NONE.value,
        "static": ConnectorAuthMode.API_KEY.value,
        "oauth": ConnectorAuthMode.OAUTH2.value,
    }[mode]


@dataclass(frozen=True, slots=True)
class _DiscoverySnapshot:
    connection_id: uuid.UUID
    server_url: str
    resource_uri: str
    auth: dict[str, Any]
    credential_epoch: int
    encrypted_credentials: str


class McpServerService:
    """Workspace-scoped MCP connection and normalized inventory lifecycle."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        session_factory: SessionFactory = SessionLocal,
        gateway: McpGatewayClient | None = None,
        oauth: McpOAuthService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.gateway = gateway or get_mcp_gateway_client()
        self.oauth = oauth or McpOAuthService(
            settings=self.settings,
            session_factory=self.session_factory,
        )

    def create_server(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: McpServerCreateIn,
    ) -> McpServerOut:
        allow_private = self.settings.is_local and self.settings.mcp_allow_private_egress
        server_url = canonicalize_mcp_url(
            body.server_url,
            allow_http=allow_private,
            allow_private_hostnames=allow_private,
        )
        resource_uri = canonicalize_mcp_url(
            body.resource_uri or server_url,
            allow_http=allow_private,
            allow_private_hostnames=allow_private,
        )
        auth = self._credential_auth(body)
        if auth.get("expected_issuer"):
            auth["expected_issuer"] = canonicalize_mcp_url(
                str(auth["expected_issuer"]),
                allow_http=allow_private,
                allow_private_hostnames=allow_private,
            )
        initial_principal = None
        if auth["mode"] != "oauth":
            initial_principal = principal_fingerprint(
                server_url=server_url,
                resource_uri=resource_uri,
                auth_mode=str(auth["mode"]),
                static_header_name=auth.get("header_name"),
            )

        connection_id = uuid.uuid4()
        # Authorize before allowing a caller to consume bounded gateway DNS
        # capacity, then release every database lock before the network call.
        self._admit_server_preflight(
            workspace_id=workspace_id,
            actor_id=actor_id,
        )
        targets = [server_url, resource_uri]
        if auth.get("expected_issuer"):
            targets.append(str(auth["expected_issuer"]))
        self._preflight_targets(
            workspace_id=workspace_id,
            connection_id=connection_id,
            targets=tuple(dict.fromkeys(targets)),
        )

        gate_db = self.session_factory()
        try:
            access = _begin_paid_access(gate_db, workspace_id=workspace_id)
            # Membership or custom-role authority may have changed while DNS
            # preflight ran. This final locked read is the persistence cutoff.
            _require_current_connect_actor(
                gate_db,
                workspace_id=workspace_id,
                actor_id=actor_id,
            )
            workspace_app_connection_lock(gate_db, workspace_id, access.app_id)
            used = int(
                gate_db.scalar(
                    select(func.count())
                    .select_from(AppConnection)
                    .where(
                        AppConnection.workspace_id == workspace_id,
                        AppConnection.app_installation_id == access.installation_id,
                        AppConnection.status.in_(tuple(CONNECTION_LIMIT_STATUSES)),
                    )
                )
                or 0
            )
            limit = access.entitlement(MCP_CONNECTIONS_ENTITLEMENT)
            if used >= limit:
                raise AppError(
                    ErrorCategory.CONNECTOR_LIMIT_REACHED,
                    "MCP server connection limit reached.",
                    details={
                        "metric": MCP_CONNECTIONS_ENTITLEMENT,
                        "limit": limit,
                        "used": used,
                        "remaining": 0,
                    },
                )

            is_oauth = auth["mode"] == "oauth"
            now = _now()
            row = AppConnection(
                id=connection_id,
                workspace_id=workspace_id,
                app_installation_id=access.installation_id,
                connector_key=MCP_CONNECTOR_KEY,
                display_name=body.display_name,
                auth_mode=_connector_auth_mode(str(auth["mode"])),
                status=(
                    ConnectionStatus.CONNECTING.value
                    if is_oauth
                    else ConnectionStatus.ACTIVE.value
                ),
                health=ConnectionHealth.UNKNOWN.value,
                mcp_credential_epoch=1,
                mcp_principal_fingerprint=initial_principal,
                mcp_capabilities={},
                mcp_reauthorization_required=False,
                connected_by_user_id=actor_id,
                connected_at=None if is_oauth else now,
                extra={},
            )
            gate_db.add(row)
            gate_db.flush()
            ConnectorCredentialService(gate_db, settings=self.settings).set_credentials(
                row,
                {
                    "mcp": {
                        "server_url": server_url,
                        "resource_uri": resource_uri,
                        "auth": auth,
                    }
                },
                merge_refresh=False,
            )
            gate_db.flush()
            record_audit(
                gate_db,
                action=AuditAction.APP_MCP_SERVER_ADDED,
                entity_type=AuditEntityType.APP_CONNECTION,
                entity_id=row.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={
                    "connection_id": str(row.id),
                    "connector_key": MCP_CONNECTOR_KEY,
                    "mode": str(auth["mode"]),
                    "credential_epoch": 1,
                },
                allowlist=frozenset(
                    {"connection_id", "connector_key", "mode", "credential_epoch"}
                ),
            )
            out = _redacted_server_out(
                gate_db,
                row,
                discovered_tool_count=0,
                settings=self.settings,
            )
            gate_db.commit()
            return out
        except AppError:
            _rollback_without_masking(gate_db)
            raise
        except SQLAlchemyError as exc:
            _rollback_without_masking(gate_db)
            raise _paid_db_error() from exc
        finally:
            gate_db.close()

    def _admit_server_preflight(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        gate_db = self.session_factory()
        try:
            _begin_paid_access(gate_db, workspace_id=workspace_id)
            _require_current_connect_actor(
                gate_db,
                workspace_id=workspace_id,
                actor_id=actor_id,
            )
            gate_db.commit()
        except AppError:
            _rollback_without_masking(gate_db)
            raise
        except SQLAlchemyError as exc:
            _rollback_without_masking(gate_db)
            raise _paid_db_error() from exc
        finally:
            gate_db.close()

    def _preflight_targets(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        targets: tuple[str, ...],
    ) -> None:
        deadline = time.monotonic() + float(
            self.settings.mcp_egress_total_timeout_seconds
        )
        for index, target in enumerate(targets):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AppError(
                    ErrorCategory.MCP_SERVER_UNREACHABLE,
                    "The MCP target validation exceeded its deadline.",
                    retryable=True,
                )
            try:
                self.gateway.validate_target(
                    McpTargetValidationRequest(
                        workspace_id=workspace_id,
                        connection_id=connection_id,
                        target_url=target,
                        deadline_seconds=remaining,
                        operation_name=f"validate{index}",
                    )
                )
            except AppError:
                raise
            except Exception as exc:
                # Gateway/library errors can contain the tenant URL or DNS
                # details; expose only a fixed safe category and message.
                raise AppError(
                    ErrorCategory.MCP_SERVER_UNREACHABLE,
                    "The MCP target could not be validated safely.",
                    retryable=True,
                ) from exc

    def list_servers(
        self,
        *,
        workspace_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> McpServerListOut:
        repo = McpRepository(self.db)
        rows, total = repo.list_connections(workspace_id, limit=limit, offset=offset)
        return McpServerListOut(
            items=[
                _redacted_server_out(
                    self.db,
                    row,
                    discovered_tool_count=repo.count_tools(workspace_id, row.id),
                    settings=self.settings,
                )
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_server(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> McpServerOut:
        repo = McpRepository(self.db)
        row = repo.get_connection(workspace_id, connection_id)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
        return _redacted_server_out(
            self.db,
            row,
            discovered_tool_count=repo.count_tools(workspace_id, row.id),
            settings=self.settings,
        )

    def delete_server(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> None:
        repo = McpRepository(self.db)
        row = repo.get_connection(workspace_id, connection_id, for_update=True)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
        teardown = McpConnectionTeardownService(
            self.db,
            settings=self.settings,
            oauth=self.oauth,
        )
        revocation = teardown.teardown_connection(
            row,
            actor_id=actor_id,
            target_status=ConnectionStatus.DISCONNECTED.value,
        )
        record_audit(
            self.db,
            action=AuditAction.APP_MCP_SERVER_REMOVED,
            entity_type=AuditEntityType.APP_CONNECTION,
            entity_id=row.id,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            metadata={"connection_id": str(row.id)},
            allowlist=frozenset({"connection_id"}),
        )
        # This commit is the authorization cutoff. Remote revocation is slow
        # and best-effort; it must never hold this transaction or roll back the
        # local disconnect, credential purge, tool withdrawal, or grant revoke.
        self.db.commit()
        teardown.revoke_after_commit([revocation] if revocation is not None else [])

    def list_tools(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> McpToolListOut:
        repo = McpRepository(self.db)
        if repo.get_connection(workspace_id, connection_id) is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
        rows, total = repo.list_tools(
            workspace_id, connection_id, limit=limit, offset=offset
        )
        return McpToolListOut(
            items=[_tool_out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def classify_tool(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        tool_id: uuid.UUID,
        classification: str,
    ) -> McpToolOut:
        gate_db = self.session_factory()
        try:
            _begin_paid_access(gate_db, workspace_id=workspace_id)
            repo = McpRepository(gate_db)
            tool = repo.get_tool(workspace_id, tool_id, for_update=True)
            if tool is None:
                raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP tool not found.")
            if tool.classification != classification:
                tool.classification = classification
                repo.stale_grants_for_classification(tool.id)
            gate_db.flush()
            record_audit(
                gate_db,
                action=AuditAction.APP_CONNECTION_UPDATED,
                entity_type=AuditEntityType.MCP_SERVER_TOOL,
                entity_id=tool.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={
                    "tool_id": str(tool.id),
                    "classification": classification,
                },
                allowlist=frozenset({"tool_id", "classification"}),
            )
            out = _tool_out(tool)
            gate_db.commit()
            return out
        except AppError:
            _rollback_without_masking(gate_db)
            raise
        except SQLAlchemyError as exc:
            _rollback_without_masking(gate_db)
            raise _paid_db_error() from exc
        finally:
            gate_db.close()

    def discover(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> McpDiscoverOut:
        if self._oauth_refresh_candidate(workspace_id, connection_id):
            # Refresh is a separately admitted operation and commits before the
            # discovery admission below. No database transaction spans egress.
            self.oauth.refresh_if_needed(
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
        snapshot = self._admit_discovery(workspace_id, connection_id)
        try:
            result = self.gateway.discover(
                McpDiscoveryRequest(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    server_url=snapshot.server_url,
                    resource_uri=snapshot.resource_uri,
                    auth=copy.deepcopy(snapshot.auth),
                    credential_epoch=snapshot.credential_epoch,
                    deadline_seconds=float(
                        self.settings.mcp_egress_total_timeout_seconds
                    ),
                )
            )
        except AppError as exc:
            if exc.category in {
                ErrorCategory.MCP_AUTH_REQUIRED,
                ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
            }:
                self.oauth.mark_reauthorization_required(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    error_code=exc.category.value,
                )
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                ) from exc
            raise
        except Exception as exc:  # transport/library errors are safe-mapped
            raise AppError(
                ErrorCategory.MCP_SERVER_UNREACHABLE,
                "The MCP server could not be reached.",
                retryable=True,
            ) from exc
        if result.protocol_version not in self.settings.mcp_supported_protocol_version_list:
            raise AppError(
                ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
                "The MCP server negotiated an unsupported protocol revision.",
                details={"protocol_version": result.protocol_version},
            )
        if len(result.tools) > self.settings.mcp_max_discovered_tools:
            raise AppError(
                ErrorCategory.MCP_TOOL_LIMIT_REACHED,
                "The MCP server advertised too many tools.",
                details={"limit": self.settings.mcp_max_discovered_tools},
            )
        return self._import_discovery(
            workspace_id=workspace_id,
            actor_id=actor_id,
            snapshot=snapshot,
            result=result,
        )

    def _oauth_refresh_candidate(
        self, workspace_id: uuid.UUID, connection_id: uuid.UUID
    ) -> bool:
        """Probe in a short session so no request transaction spans refresh I/O."""

        probe = self.session_factory()
        try:
            row = McpRepository(probe).get_connection(workspace_id, connection_id)
            candidate = bool(
                row is not None
                and row.auth_mode == ConnectorAuthMode.OAUTH2.value
                and row.status in CONNECTION_USABLE_STATUSES
                and not row.mcp_reauthorization_required
            )
            probe.commit()
            return candidate
        except SQLAlchemyError as exc:
            _rollback_without_masking(probe)
            raise _paid_db_error() from exc
        finally:
            probe.close()

    def _admit_discovery(
        self, workspace_id: uuid.UUID, connection_id: uuid.UUID
    ) -> _DiscoverySnapshot:
        gate_db = self.session_factory()
        try:
            _begin_paid_access(gate_db, workspace_id=workspace_id)
            row = McpRepository(gate_db).get_connection(
                workspace_id, connection_id, for_share=True
            )
            if row is None:
                raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP server not found.")
            if row.status not in CONNECTION_USABLE_STATUSES:
                if row.auth_mode == ConnectorAuthMode.OAUTH2.value:
                    raise AppError(
                        ErrorCategory.MCP_AUTH_REQUIRED,
                        "This MCP server must be authorized before discovery.",
                    )
                raise AppError(
                    ErrorCategory.CONNECTOR_CONNECTION_FAILED,
                    "The MCP server connection is not usable.",
                )
            if row.mcp_reauthorization_required:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                )
            token = row.credentials_encrypted
            credentials = ConnectorCredentialService(
                gate_db, settings=self.settings
            ).get_credentials(row)
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            if not token or not isinstance(config, dict):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "MCP server credentials are unavailable.",
                )
            auth = config.get("auth")
            if not isinstance(auth, dict):
                raise AppError(
                    ErrorCategory.MCP_AUTH_REQUIRED,
                    "MCP server credentials are unavailable.",
                )
            snapshot = _DiscoverySnapshot(
                connection_id=row.id,
                server_url=str(config.get("server_url") or ""),
                resource_uri=str(config.get("resource_uri") or ""),
                auth=copy.deepcopy(auth),
                credential_epoch=row.mcp_credential_epoch,
                encrypted_credentials=token,
            )
            gate_db.commit()
            return snapshot
        except AppError:
            _rollback_without_masking(gate_db)
            raise
        except SQLAlchemyError as exc:
            _rollback_without_masking(gate_db)
            raise _paid_db_error() from exc
        finally:
            gate_db.close()

    def _import_discovery(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        snapshot: _DiscoverySnapshot,
        result: McpDiscoveryResult,
    ) -> McpDiscoverOut:
        import_db = self.session_factory()
        try:
            repo = McpRepository(import_db)
            row = repo.get_connection(
                workspace_id, snapshot.connection_id, for_update=True
            )
            if (
                row is None
                or row.status not in CONNECTION_USABLE_STATUSES
                or row.mcp_reauthorization_required
                or row.mcp_credential_epoch != snapshot.credential_epoch
                or row.credentials_encrypted != snapshot.encrypted_credentials
            ):
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP connection changed during discovery; retry after reauthorization.",
                )
            now = _now()
            resource_uri = snapshot.resource_uri
            if result.resource_uri:
                allow_private = (
                    self.settings.is_local and self.settings.mcp_allow_private_egress
                )
                resource_uri = canonicalize_mcp_url(
                    result.resource_uri,
                    allow_http=allow_private,
                    allow_private_hostnames=allow_private,
                )
            auth = copy.deepcopy(snapshot.auth)
            if result.issuer:
                auth["issuer"] = result.issuer
            if result.client_id:
                auth["client_id"] = result.client_id
            new_principal = principal_fingerprint(
                server_url=snapshot.server_url,
                resource_uri=resource_uri,
                auth_mode=str(auth.get("mode") or "none"),
                issuer=str(auth.get("issuer") or auth.get("expected_issuer") or "")
                or None,
                client_id=str(auth.get("client_id") or "") or None,
                external_subject=result.external_subject,
                static_header_name=(
                    str(auth.get("header_name")) if auth.get("header_name") else None
                ),
            )
            if (
                row.mcp_principal_fingerprint is not None
                and row.mcp_principal_fingerprint != new_principal
            ):
                row.mcp_credential_epoch += 1
                repo.stale_grants_for_principal(row.id)
            row.mcp_principal_fingerprint = new_principal
            row.mcp_protocol_version = result.protocol_version
            row.mcp_session_mode = result.session_mode
            row.mcp_capabilities = dict(result.capabilities)
            row.mcp_discovery_generation += 1
            generation = row.mcp_discovery_generation
            row.external_account_id = result.external_subject
            row.external_account_name = result.external_identity_label
            row.last_success_at = now
            row.last_error_code = None
            row.last_error_message = None
            row.last_error_at = None
            row.health = (
                ConnectionHealth.HEALTHY.value
                if result.complete
                else ConnectionHealth.DEGRADED.value
            )
            row.status = (
                ConnectionStatus.ACTIVE.value
                if result.complete
                else ConnectionStatus.DEGRADED.value
            )
            if result.complete:
                row.mcp_inventory_refreshed_at = now
            ConnectorCredentialService(
                import_db, settings=self.settings
            ).replace_credentials(
                row,
                {
                    "mcp": {
                        "server_url": snapshot.server_url,
                        "resource_uri": resource_uri,
                        "auth": auth,
                    }
                },
                merge_refresh=False,
            )

            existing = repo.tools_by_name_for_update(workspace_id, row.id)
            seen: set[str] = set()
            created = updated_count = withdrawn = 0
            for ordinal, raw_tool in enumerate(result.tools):
                candidate: Any = raw_tool
                raw_name = raw_tool.get("name") if isinstance(raw_tool, dict) else None
                if isinstance(raw_name, str) and raw_name.strip() in seen:
                    candidate = {
                        "name": "",
                        "_malformed_duplicate_name": raw_name[:256],
                    }
                normalized = normalize_tool_definition(
                    candidate,
                    connection_id=row.id,
                    protocol_version=result.protocol_version,
                    malformed_ordinal=ordinal,
                )
                seen.add(normalized.tool_name)
                tool = existing.get(normalized.tool_name)
                if tool is None:
                    tool = McpServerTool(
                        workspace_id=workspace_id,
                        app_connection_id=row.id,
                        tool_name=normalized.tool_name,
                        llm_tool_name=normalized.llm_tool_name,
                        title=normalized.title,
                        description=normalized.description,
                        input_schema=normalized.input_schema,
                        output_schema=normalized.output_schema,
                        annotations=normalized.annotations,
                        raw_definition=normalized.raw_definition,
                        normalization_version=normalized.normalization_version,
                        protocol_version=result.protocol_version,
                        compatibility_status=normalized.compatibility_status,
                        compatibility_reason=normalized.compatibility_reason,
                        classification=McpToolClassification.UNKNOWN.value,
                        definition_hash=normalized.definition_hash,
                        status=McpToolStatus.ACTIVE.value,
                        first_seen_at=now,
                        last_seen_at=now,
                        discovery_generation=generation,
                    )
                    import_db.add(tool)
                    created += 1
                else:
                    definition_changed = (
                        tool.definition_hash != normalized.definition_hash
                    )
                    if definition_changed:
                        repo.stale_grants_for_definition(tool.id)
                    tool.llm_tool_name = normalized.llm_tool_name
                    tool.title = normalized.title
                    tool.description = normalized.description
                    tool.input_schema = normalized.input_schema
                    tool.output_schema = normalized.output_schema
                    tool.annotations = normalized.annotations
                    tool.raw_definition = normalized.raw_definition
                    tool.normalization_version = normalized.normalization_version
                    tool.protocol_version = result.protocol_version
                    tool.compatibility_status = normalized.compatibility_status
                    tool.compatibility_reason = normalized.compatibility_reason
                    tool.definition_hash = normalized.definition_hash
                    tool.status = McpToolStatus.ACTIVE.value
                    tool.last_seen_at = now
                    tool.discovery_generation = generation
                    updated_count += 1
            if result.complete:
                for name, tool in existing.items():
                    if name in seen or tool.status == McpToolStatus.WITHDRAWN.value:
                        continue
                    tool.status = McpToolStatus.WITHDRAWN.value
                    repo.stale_grants_for_definition(tool.id)
                    withdrawn += 1
            import_db.flush()
            record_audit(
                import_db,
                action=AuditAction.APP_MCP_TOOLS_DISCOVERED,
                entity_type=AuditEntityType.APP_CONNECTION,
                entity_id=row.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={
                    "connection_id": str(row.id),
                    "credential_epoch": row.mcp_credential_epoch,
                    "status": "complete" if result.complete else "partial",
                },
                allowlist=frozenset(
                    {"connection_id", "credential_epoch", "status"}
                ),
            )
            out = McpDiscoverOut(
                server=_redacted_server_out(
                    import_db,
                    row,
                    discovered_tool_count=len(existing) + created,
                    settings=self.settings,
                ),
                generation=generation,
                tools_seen=len(result.tools),
                tools_created=created,
                tools_updated=updated_count,
                tools_withdrawn=withdrawn,
                complete=result.complete,
                warnings=list(result.warnings),
            )
            import_db.commit()
            return out
        except AppError:
            _rollback_without_masking(import_db)
            raise
        except SQLAlchemyError as exc:
            _rollback_without_masking(import_db)
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "MCP inventory could not be persisted.",
                retryable=True,
            ) from exc
        finally:
            import_db.close()

    @staticmethod
    def _credential_auth(body: McpServerCreateIn) -> dict[str, Any]:
        auth = body.auth
        if isinstance(auth, McpStaticAuthIn):
            value = auth.secret.get_secret_value()
            if auth.header_name.casefold() == "authorization" and not value.lower().startswith(
                "bearer "
            ):
                value = f"Bearer {value}"
            return {
                "mode": "static",
                "header_name": auth.header_name,
                "value": value,
            }
        if isinstance(auth, McpOAuthAuthIn):
            result: dict[str, Any] = {
                "mode": "oauth",
                "strategy": auth.strategy,
                "expected_issuer": auth.expected_issuer,
                "client_id": auth.client_id,
                "scopes": list(auth.scopes),
            }
            if auth.client_secret is not None:
                result["client_secret"] = auth.client_secret.get_secret_value()
            return result
        return {"mode": "none"}


class McpGrantService:
    """Explicit review and source-scoped authorization for Workspace Experts."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    def list_grants(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
    ) -> McpToolGrantListOut:
        repo = McpRepository(self.db)
        expert = repo.get_expert(workspace_id, expert_id)
        if expert is None or expert.type != ExpertType.WORKSPACE.value:
            raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
        return McpToolGrantListOut(
            items=[
                _grant_out(record)
                for record in repo.list_grant_records(workspace_id, expert_id)
            ]
        )

    def create_grant(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: McpGrantCreateIn,
    ) -> McpToolGrantOut:
        if not body.allow_workspace_chat and not body.allow_public_api:
            raise AppError(
                ErrorCategory.VALIDATION,
                "At least one invocation source must be enabled.",
            )
        if not body.outbound_data_acknowledged:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Outbound MCP data disclosure must be acknowledged.",
            )
        gate_db = self.session_factory()
        try:
            _begin_paid_access(gate_db, workspace_id=workspace_id)
            repo = McpRepository(gate_db)
            expert = repo.get_expert(workspace_id, expert_id, for_update=True)
            if expert is None or expert.type != ExpertType.WORKSPACE.value:
                raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
            tool_snapshot = repo.get_tool(workspace_id, body.tool_id)
            if tool_snapshot is None:
                raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "MCP tool not found.")
            connection = repo.get_connection(
                workspace_id, tool_snapshot.app_connection_id, for_share=True
            )
            if connection is None or connection.status not in CONNECTION_USABLE_STATUSES:
                raise AppError(
                    ErrorCategory.CONNECTOR_CONNECTION_FAILED,
                    "The MCP server connection is not usable.",
                )
            # Connection-before-tool matches discovery/disconnect lock order.
            tool = repo.get_tool(workspace_id, body.tool_id, for_update=True)
            if tool is None or tool.app_connection_id != connection.id:
                raise AppError(
                    ErrorCategory.MCP_TOOL_SET_CHANGED,
                    "The MCP tool changed while approval was being prepared.",
                )
            if connection.mcp_reauthorization_required:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "This MCP server must be reauthorized.",
                )
            if (
                tool.status != McpToolStatus.ACTIVE.value
                or tool.compatibility_status != McpCompatibilityStatus.COMPATIBLE.value
                or tool.classification == McpToolClassification.UNKNOWN.value
            ):
                raise AppError(
                    ErrorCategory.MCP_TOOL_INCOMPATIBLE,
                    "The MCP tool is not compatible and classified for use.",
                )
            if not connection.mcp_principal_fingerprint:
                raise AppError(
                    ErrorCategory.MCP_REAUTHORIZATION_REQUIRED,
                    "The MCP server identity has not been verified.",
                )
            if connection.mcp_inventory_refreshed_at is None:
                raise AppError(
                    ErrorCategory.MCP_TOOL_SET_CHANGED,
                    "The MCP tool inventory must be refreshed before approval.",
                )
            if body.unattended_write_allowed and (
                tool.classification != McpToolClassification.WRITE.value
                or not body.allow_public_api
                or not body.unattended_write_risk_acknowledged
            ):
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Unattended writes require a write tool, public API access, "
                    "and explicit risk acknowledgement.",
                )

            existing = repo.get_grant_for_tool(
                workspace_id, expert_id, tool.id, for_update=True
            )
            active_count = int(
                gate_db.scalar(
                    select(func.count())
                    .select_from(McpToolGrant)
                    .where(
                        McpToolGrant.workspace_id == workspace_id,
                        McpToolGrant.expert_id == expert_id,
                        McpToolGrant.state == McpGrantState.ACTIVE.value,
                        McpToolGrant.id != (existing.id if existing else uuid.uuid4()),
                    )
                )
                or 0
            )
            if active_count >= self.settings.mcp_max_tools_per_expert:
                raise AppError(
                    ErrorCategory.MCP_TOOL_LIMIT_REACHED,
                    "The Expert MCP tool limit has been reached.",
                    details={"limit": self.settings.mcp_max_tools_per_expert},
                )
            now = _now()
            grant = existing or McpToolGrant(
                workspace_id=workspace_id,
                expert_id=expert_id,
                app_connection_id=connection.id,
                mcp_server_tool_id=tool.id,
            )
            if existing is None:
                gate_db.add(grant)
            grant.app_connection_id = connection.id
            grant.approved_definition_hash = tool.definition_hash
            grant.approved_classification = tool.classification
            grant.approved_principal_fingerprint = (
                connection.mcp_principal_fingerprint
            )
            grant.approved_credential_epoch = connection.mcp_credential_epoch
            grant.state = McpGrantState.ACTIVE.value
            grant.allow_workspace_chat = body.allow_workspace_chat
            grant.allow_public_api = body.allow_public_api
            grant.unattended_write_allowed = body.unattended_write_allowed
            grant.approved_by_user_id = actor_id
            grant.approved_at = now
            grant.outbound_data_acknowledged_at = now
            grant.unattended_write_acknowledged_at = (
                now if body.unattended_write_allowed else None
            )
            grant.revoked_by_user_id = None
            grant.revoked_at = None
            gate_db.flush()
            record_audit(
                gate_db,
                action=AuditAction.APP_MCP_TOOL_GRANTED,
                entity_type=AuditEntityType.MCP_TOOL_GRANT,
                entity_id=grant.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={
                    "expert_id": str(expert_id),
                    "connection_id": str(connection.id),
                    "tool_id": str(tool.id),
                    "grant_id": str(grant.id),
                    "definition_hash": tool.definition_hash,
                    "classification": tool.classification,
                    "credential_epoch": connection.mcp_credential_epoch,
                },
                allowlist=frozenset(
                    {
                        "expert_id",
                        "connection_id",
                        "tool_id",
                        "grant_id",
                        "definition_hash",
                        "classification",
                        "credential_epoch",
                    }
                ),
            )
            out = _grant_out(McpGrantRecord(grant, tool, connection))
            gate_db.commit()
            return out
        except AppError:
            _rollback_without_masking(gate_db)
            raise
        except SQLAlchemyError as exc:
            _rollback_without_masking(gate_db)
            raise _paid_db_error() from exc
        finally:
            gate_db.close()

    def revoke_grant(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        grant_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        repo = McpRepository(self.db)
        expert = repo.get_expert(workspace_id, expert_id)
        if expert is None or expert.type != ExpertType.WORKSPACE.value:
            raise AppError(ErrorCategory.EXPERT_NOT_FOUND, "Expert not found.")
        grant = repo.get_grant(
            workspace_id, expert_id, grant_id, for_update=True
        )
        if grant is None:
            raise AppError(ErrorCategory.MCP_TOOL_NOT_GRANTED, "MCP grant not found.")
        if grant.state != McpGrantState.REVOKED.value:
            now = _now()
            grant.state = McpGrantState.REVOKED.value
            grant.revoked_by_user_id = actor_id
            grant.revoked_at = now
        record_audit(
            self.db,
            action=AuditAction.APP_MCP_TOOL_REVOKED,
            entity_type=AuditEntityType.MCP_TOOL_GRANT,
            entity_id=grant.id,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            metadata={"expert_id": str(expert_id), "grant_id": str(grant.id)},
            allowlist=frozenset({"expert_id", "grant_id"}),
        )


__all__ = ["McpGrantService", "McpServerService"]
