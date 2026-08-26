"""Fail-closed local teardown and post-commit OAuth revocation for MCP."""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import Session

from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.types import (
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
)
from app.core.config import Settings, get_settings
from app.mcp.constants import MCP_CONNECTOR_KEY
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.oauth import McpOAuthService
from app.mcp.runtime_models import (
    McpPendingToolCall,
    McpSurfaceDelivery,
    McpToolInvocation,
    McpToolSurfaceBinding,
    McpWidgetTurnReceipt,
)
from app.mcp.types import McpGrantState, McpToolStatus

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True, repr=False)
class McpOAuthRevocationSnapshot:
    """Request-local secret snapshot that must never be logged or persisted."""

    connection_id: uuid.UUID
    auth: dict[str, Any]


class McpConnectionTeardownService:
    """Make MCP connections inert locally, then revoke only after commit."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        oauth: McpOAuthService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.oauth = oauth or McpOAuthService(settings=self.settings)

    def connections_for_installation(
        self,
        *,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
    ) -> list[AppConnection]:
        return list(
            self.db.scalars(
                select(AppConnection)
                .where(
                    AppConnection.workspace_id == workspace_id,
                    AppConnection.app_installation_id == installation_id,
                    AppConnection.connector_key == MCP_CONNECTOR_KEY,
                )
                .order_by(AppConnection.id)
                .with_for_update()
            )
        )

    def teardown_connection(
        self,
        connection: AppConnection,
        *,
        actor_id: uuid.UUID | None,
        target_status: str = ConnectionStatus.DISCONNECTED.value,
        at: datetime | None = None,
    ) -> McpOAuthRevocationSnapshot | None:
        """Apply every restrictive MCP mutation in the caller's transaction."""

        if connection.connector_key != MCP_CONNECTOR_KEY:
            raise ValueError("MCP teardown requires an mcp_remote connection")
        stamp = at or _now()
        revocation = self._revocation_snapshot(connection)

        # Finish every live child state before withdrawing its authority.
        # Rows that may already have crossed an external side-effect boundary
        # become *_unknown; work proven not to have left Geem is cancelled.
        self._terminalize_connection_runtime(connection, at=stamp)

        ConnectorCredentialService(
            self.db, settings=self.settings
        ).clear_all_secrets(connection)
        connection.status = target_status
        connection.health = ConnectionHealth.UNKNOWN.value
        connection.disconnected_at = connection.disconnected_at or stamp
        connection.mcp_reauthorization_required = False
        connection.mcp_credential_epoch = int(connection.mcp_credential_epoch or 0) + 1
        connection.mcp_principal_fingerprint = None
        connection.external_account_id = None
        connection.external_account_name = None
        connection.last_error_code = None
        connection.last_error_message = None
        connection.last_error_at = None

        self.db.execute(
            update(McpServerTool)
            .where(
                McpServerTool.workspace_id == connection.workspace_id,
                McpServerTool.app_connection_id == connection.id,
            )
            .values(status=McpToolStatus.WITHDRAWN.value, updated_at=stamp)
        )
        self.db.execute(
            update(McpToolGrant)
            .where(
                McpToolGrant.workspace_id == connection.workspace_id,
                McpToolGrant.app_connection_id == connection.id,
                McpToolGrant.state != McpGrantState.REVOKED.value,
            )
            .values(
                state=McpGrantState.REVOKED.value,
                revoked_by_user_id=actor_id,
                revoked_at=stamp,
                updated_at=stamp,
            )
        )
        self.db.flush()
        return revocation

    def terminalize_workspace_runtime(
        self,
        *,
        workspace_id: uuid.UUID,
        at: datetime | None = None,
    ) -> None:
        """Make any remaining live MCP runtime rows terminal before hard purge."""

        stamp = at or _now()
        live_receipts = McpWidgetTurnReceipt.status.in_(
            ("accepted", "running", "pending")
        )
        ambiguous_receipt = or_(
            exists().where(
                McpSurfaceDelivery.workspace_id == workspace_id,
                McpSurfaceDelivery.assistant_message_id
                == McpWidgetTurnReceipt.assistant_message_id,
                McpSurfaceDelivery.status.in_(
                    ("dispatching", "delivery_unknown")
                ),
            ),
            exists().where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.conversation_id
                == McpWidgetTurnReceipt.conversation_id,
                McpPendingToolCall.initiating_origin_digest
                == McpWidgetTurnReceipt.initiating_origin_digest,
                McpPendingToolCall.external_turn_handle_digest
                == McpWidgetTurnReceipt.external_turn_handle_digest,
                or_(
                    McpPendingToolCall.status == "outcome_unknown",
                    McpPendingToolCall.gateway_dispatch_started_at.is_not(None),
                ),
            ),
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == workspace_id,
                live_receipts,
                ambiguous_receipt,
            )
            .values(status="outcome_unknown", updated_at=stamp)
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == workspace_id,
                live_receipts,
            )
            .values(status="failed", updated_at=stamp)
        )
        self._terminalize_deliveries(
            workspace_id=workspace_id,
            surface_ids=None,
            at=stamp,
        )
        self._terminalize_pending_calls(
            workspace_id=workspace_id,
            grant_ids=None,
            at=stamp,
        )
        self._terminalize_invocations(
            workspace_id=workspace_id,
            connection_id=None,
            at=stamp,
        )
        self.db.execute(
            update(McpToolSurfaceBinding)
            .where(
                McpToolSurfaceBinding.workspace_id == workspace_id,
                McpToolSurfaceBinding.state != "revoked",
            )
            .values(state="revoked", updated_at=stamp)
        )
        self.db.flush()

    def terminalize_conversation_runtime(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        at: datetime | None = None,
    ) -> None:
        """Terminate only MCP work owned by one retained conversation."""

        stamp = at or _now()
        live_receipts = McpWidgetTurnReceipt.status.in_(
            ("accepted", "running", "pending")
        )
        ambiguous_receipt = or_(
            exists().where(
                McpSurfaceDelivery.workspace_id == workspace_id,
                McpSurfaceDelivery.conversation_id == conversation_id,
                McpSurfaceDelivery.assistant_message_id
                == McpWidgetTurnReceipt.assistant_message_id,
                McpSurfaceDelivery.status.in_(
                    ("dispatching", "delivery_unknown")
                ),
            ),
            exists().where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.conversation_id == conversation_id,
                McpPendingToolCall.initiating_origin_digest
                == McpWidgetTurnReceipt.initiating_origin_digest,
                McpPendingToolCall.external_turn_handle_digest
                == McpWidgetTurnReceipt.external_turn_handle_digest,
                or_(
                    McpPendingToolCall.status == "outcome_unknown",
                    McpPendingToolCall.gateway_dispatch_started_at.is_not(None),
                ),
            ),
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == workspace_id,
                McpWidgetTurnReceipt.conversation_id == conversation_id,
                live_receipts,
                ambiguous_receipt,
            )
            .values(status="outcome_unknown", updated_at=stamp)
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == workspace_id,
                McpWidgetTurnReceipt.conversation_id == conversation_id,
                live_receipts,
            )
            .values(status="failed", updated_at=stamp)
        )
        self._terminalize_deliveries(
            workspace_id=workspace_id,
            surface_ids=None,
            conversation_id=conversation_id,
            at=stamp,
        )
        self._terminalize_pending_calls(
            workspace_id=workspace_id,
            grant_ids=None,
            conversation_id=conversation_id,
            at=stamp,
        )
        self._terminalize_invocations(
            workspace_id=workspace_id,
            connection_id=None,
            conversation_id=conversation_id,
            error_code="MCP_CONVERSATION_RETIRED",
            at=stamp,
        )
        self.db.flush()

    def terminalize_expert_runtime(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        at: datetime | None = None,
    ) -> None:
        """Terminate remaining MCP authority owned by one retained Expert."""

        stamp = at or _now()
        grant_ids = select(McpToolGrant.id).where(
            McpToolGrant.workspace_id == workspace_id,
            McpToolGrant.expert_id == expert_id,
        )
        surface_ids = select(McpToolSurfaceBinding.id).where(
            McpToolSurfaceBinding.workspace_id == workspace_id,
            McpToolSurfaceBinding.expert_id == expert_id,
        )
        live_receipts = McpWidgetTurnReceipt.status.in_(
            ("accepted", "running", "pending")
        )
        ambiguous_receipt = or_(
            exists().where(
                McpSurfaceDelivery.workspace_id == workspace_id,
                McpSurfaceDelivery.mcp_tool_surface_binding_id.in_(surface_ids),
                McpSurfaceDelivery.assistant_message_id
                == McpWidgetTurnReceipt.assistant_message_id,
                McpSurfaceDelivery.status.in_(
                    ("dispatching", "delivery_unknown")
                ),
            ),
            exists().where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.mcp_tool_grant_id.in_(grant_ids),
                McpPendingToolCall.conversation_id
                == McpWidgetTurnReceipt.conversation_id,
                McpPendingToolCall.initiating_origin_digest
                == McpWidgetTurnReceipt.initiating_origin_digest,
                McpPendingToolCall.external_turn_handle_digest
                == McpWidgetTurnReceipt.external_turn_handle_digest,
                or_(
                    McpPendingToolCall.status == "outcome_unknown",
                    McpPendingToolCall.gateway_dispatch_started_at.is_not(None),
                ),
            ),
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == workspace_id,
                McpWidgetTurnReceipt.expert_id == expert_id,
                live_receipts,
                ambiguous_receipt,
            )
            .values(status="outcome_unknown", updated_at=stamp)
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == workspace_id,
                McpWidgetTurnReceipt.expert_id == expert_id,
                live_receipts,
            )
            .values(status="failed", updated_at=stamp)
        )
        self._terminalize_deliveries(
            workspace_id=workspace_id,
            surface_ids=surface_ids,
            at=stamp,
        )
        self._terminalize_pending_calls(
            workspace_id=workspace_id,
            grant_ids=grant_ids,
            at=stamp,
        )
        self._terminalize_invocations(
            workspace_id=workspace_id,
            connection_id=None,
            expert_id=expert_id,
            error_code="MCP_EXPERT_RETIRED",
            at=stamp,
        )
        self.db.execute(
            update(McpToolSurfaceBinding)
            .where(
                McpToolSurfaceBinding.workspace_id == workspace_id,
                McpToolSurfaceBinding.expert_id == expert_id,
                McpToolSurfaceBinding.state != "revoked",
            )
            .values(state="revoked", updated_at=stamp)
        )
        self.db.execute(
            update(McpToolGrant)
            .where(
                McpToolGrant.workspace_id == workspace_id,
                McpToolGrant.expert_id == expert_id,
                McpToolGrant.state != McpGrantState.REVOKED.value,
            )
            .values(
                state=McpGrantState.REVOKED.value,
                revoked_at=stamp,
                updated_at=stamp,
            )
        )
        self.db.flush()

    def teardown_installation(
        self,
        *,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        target_status: str = ConnectionStatus.REVOKED.value,
    ) -> list[McpOAuthRevocationSnapshot]:
        snapshots: list[McpOAuthRevocationSnapshot] = []
        stamp = _now()
        for connection in self.connections_for_installation(
            workspace_id=workspace_id,
            installation_id=installation_id,
        ):
            snapshot = self.teardown_connection(
                connection,
                actor_id=actor_id,
                target_status=target_status,
                at=stamp,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def revoke_after_commit(
        self, snapshots: list[McpOAuthRevocationSnapshot]
    ) -> None:
        """Attempt bounded revocation only when no DB transaction is open."""

        if not snapshots:
            return
        if self.db.in_transaction():
            # Fail closed: skipping remote cleanup is safer than holding a
            # datastore transaction across tenant-derived network I/O.
            logger.warning("mcp_oauth_revocation_skipped_open_transaction")
            return
        for snapshot in snapshots:
            try:
                self.oauth.revoke_best_effort(
                    connection_id=snapshot.connection_id,
                    auth=snapshot.auth,
                )
            except Exception:  # noqa: BLE001 - remote cleanup cannot undo local deny
                logger.warning(
                    "mcp_oauth_remote_revocation_failed",
                    extra={"connection_id": str(snapshot.connection_id)},
                )

    def _terminalize_connection_runtime(
        self,
        connection: AppConnection,
        *,
        at: datetime,
    ) -> None:
        grant_ids = select(McpToolGrant.id).where(
            McpToolGrant.workspace_id == connection.workspace_id,
            McpToolGrant.app_connection_id == connection.id,
        )
        surface_ids = select(McpToolSurfaceBinding.id).where(
            McpToolSurfaceBinding.workspace_id == connection.workspace_id,
            McpToolSurfaceBinding.mcp_tool_grant_id.in_(grant_ids),
        )
        live_receipts = McpWidgetTurnReceipt.status.in_(
            ("accepted", "running", "pending")
        )
        impacted_receipt = or_(
            exists().where(
                McpSurfaceDelivery.workspace_id == connection.workspace_id,
                McpSurfaceDelivery.mcp_tool_surface_binding_id.in_(surface_ids),
                McpSurfaceDelivery.assistant_message_id
                == McpWidgetTurnReceipt.assistant_message_id,
            ),
            exists().where(
                McpPendingToolCall.workspace_id == connection.workspace_id,
                McpPendingToolCall.mcp_tool_grant_id.in_(grant_ids),
                McpPendingToolCall.conversation_id
                == McpWidgetTurnReceipt.conversation_id,
                McpPendingToolCall.initiating_origin_digest
                == McpWidgetTurnReceipt.initiating_origin_digest,
                McpPendingToolCall.external_turn_handle_digest
                == McpWidgetTurnReceipt.external_turn_handle_digest,
            ),
        )
        ambiguous_receipt = or_(
            exists().where(
                McpSurfaceDelivery.workspace_id == connection.workspace_id,
                McpSurfaceDelivery.mcp_tool_surface_binding_id.in_(surface_ids),
                McpSurfaceDelivery.assistant_message_id
                == McpWidgetTurnReceipt.assistant_message_id,
                McpSurfaceDelivery.status.in_(
                    ("dispatching", "delivery_unknown")
                ),
            ),
            exists().where(
                McpPendingToolCall.workspace_id == connection.workspace_id,
                McpPendingToolCall.mcp_tool_grant_id.in_(grant_ids),
                McpPendingToolCall.conversation_id
                == McpWidgetTurnReceipt.conversation_id,
                McpPendingToolCall.initiating_origin_digest
                == McpWidgetTurnReceipt.initiating_origin_digest,
                McpPendingToolCall.external_turn_handle_digest
                == McpWidgetTurnReceipt.external_turn_handle_digest,
                or_(
                    McpPendingToolCall.status == "outcome_unknown",
                    McpPendingToolCall.gateway_dispatch_started_at.is_not(None),
                ),
            ),
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == connection.workspace_id,
                live_receipts,
                ambiguous_receipt,
            )
            .values(status="outcome_unknown", updated_at=at)
        )
        self.db.execute(
            update(McpWidgetTurnReceipt)
            .where(
                McpWidgetTurnReceipt.workspace_id == connection.workspace_id,
                live_receipts,
                impacted_receipt,
            )
            .values(status="failed", updated_at=at)
        )
        self._terminalize_deliveries(
            workspace_id=connection.workspace_id,
            surface_ids=surface_ids,
            at=at,
        )
        self._terminalize_pending_calls(
            workspace_id=connection.workspace_id,
            grant_ids=grant_ids,
            at=at,
        )
        self._terminalize_invocations(
            workspace_id=connection.workspace_id,
            connection_id=connection.id,
            at=at,
        )
        self.db.execute(
            update(McpToolSurfaceBinding)
            .where(
                McpToolSurfaceBinding.workspace_id == connection.workspace_id,
                McpToolSurfaceBinding.id.in_(surface_ids),
                McpToolSurfaceBinding.state != "revoked",
            )
            .values(state="revoked", updated_at=at)
        )

    def _terminalize_deliveries(
        self,
        *,
        workspace_id: uuid.UUID,
        surface_ids: Any | None,
        at: datetime,
        conversation_id: uuid.UUID | None = None,
    ) -> None:
        scope = [
            McpSurfaceDelivery.workspace_id == workspace_id,
            McpSurfaceDelivery.status == "dispatching",
        ]
        if surface_ids is not None:
            scope.append(McpSurfaceDelivery.mcp_tool_surface_binding_id.in_(surface_ids))
        if conversation_id is not None:
            scope.append(McpSurfaceDelivery.conversation_id == conversation_id)
        self.db.execute(
            update(McpSurfaceDelivery)
            .where(*scope)
            .values(
                status="delivery_unknown",
                claim_lease_expires_at=None,
                version=McpSurfaceDelivery.version + 1,
                updated_at=at,
            )
        )
        scope = [
            McpSurfaceDelivery.workspace_id == workspace_id,
            McpSurfaceDelivery.status == "pending",
        ]
        if surface_ids is not None:
            scope.append(McpSurfaceDelivery.mcp_tool_surface_binding_id.in_(surface_ids))
        if conversation_id is not None:
            scope.append(McpSurfaceDelivery.conversation_id == conversation_id)
        self.db.execute(
            update(McpSurfaceDelivery)
            .where(*scope)
            .values(
                status="cancelled",
                claim_lease_expires_at=None,
                version=McpSurfaceDelivery.version + 1,
                updated_at=at,
            )
        )

    def _terminalize_pending_calls(
        self,
        *,
        workspace_id: uuid.UUID,
        grant_ids: Any | None,
        at: datetime,
        conversation_id: uuid.UUID | None = None,
    ) -> None:
        scope = [
            McpPendingToolCall.workspace_id == workspace_id,
            McpPendingToolCall.status == "executing",
            McpPendingToolCall.gateway_dispatch_started_at.is_not(None),
        ]
        if grant_ids is not None:
            scope.append(McpPendingToolCall.mcp_tool_grant_id.in_(grant_ids))
        if conversation_id is not None:
            scope.append(McpPendingToolCall.conversation_id == conversation_id)
        self.db.execute(
            update(McpPendingToolCall)
            .where(*scope)
            .values(
                status="outcome_unknown",
                arguments_encrypted=None,
                loop_state_encrypted=None,
                claim_lease_expires_at=None,
                execution_deadline=None,
                executed_at=at,
                version=McpPendingToolCall.version + 1,
                updated_at=at,
            )
        )
        scope = [
            McpPendingToolCall.workspace_id == workspace_id,
            McpPendingToolCall.status.in_(("pending", "approved", "executing")),
        ]
        if grant_ids is not None:
            scope.append(McpPendingToolCall.mcp_tool_grant_id.in_(grant_ids))
        if conversation_id is not None:
            scope.append(McpPendingToolCall.conversation_id == conversation_id)
        self.db.execute(
            update(McpPendingToolCall)
            .where(*scope)
            .values(
                status="expired",
                arguments_encrypted=None,
                loop_state_encrypted=None,
                claim_lease_expires_at=None,
                execution_deadline=None,
                resume_requested_at=None,
                resume_enqueued_at=None,
                version=McpPendingToolCall.version + 1,
                updated_at=at,
            )
        )

    def _terminalize_invocations(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID | None,
        at: datetime,
        conversation_id: uuid.UUID | None = None,
        expert_id: uuid.UUID | None = None,
        error_code: str = "MCP_CONNECTION_RETIRED",
    ) -> None:
        scope = [
            McpToolInvocation.workspace_id == workspace_id,
            McpToolInvocation.status == "dispatching",
        ]
        if connection_id is not None:
            scope.append(McpToolInvocation.app_connection_id == connection_id)
        if conversation_id is not None:
            scope.append(McpToolInvocation.conversation_id == conversation_id)
        if expert_id is not None:
            scope.append(McpToolInvocation.expert_id == expert_id)
        self.db.execute(
            update(McpToolInvocation)
            .where(*scope)
            .values(
                status="outcome_unknown",
                error_code=error_code,
                completed_at=at,
            )
        )
        scope = [
            McpToolInvocation.workspace_id == workspace_id,
            McpToolInvocation.status == "admitted",
        ]
        if connection_id is not None:
            scope.append(McpToolInvocation.app_connection_id == connection_id)
        if conversation_id is not None:
            scope.append(McpToolInvocation.conversation_id == conversation_id)
        if expert_id is not None:
            scope.append(McpToolInvocation.expert_id == expert_id)
        self.db.execute(
            update(McpToolInvocation)
            .where(*scope)
            .values(
                status="failed",
                error_code=error_code,
                completed_at=at,
            )
        )

    def _revocation_snapshot(
        self, connection: AppConnection
    ) -> McpOAuthRevocationSnapshot | None:
        if connection.auth_mode != ConnectorAuthMode.OAUTH2.value:
            return None
        try:
            credentials = ConnectorCredentialService(
                self.db, settings=self.settings
            ).get_credentials(connection)
            config = credentials.get("mcp") if isinstance(credentials, dict) else None
            auth = config.get("auth") if isinstance(config, dict) else None
            if not isinstance(auth, dict):
                return None
            # Retain only fields required by RFC 7009 client authentication.
            allowed = {
                "revocation_endpoint",
                "client_id",
                "client_secret",
                "token_endpoint_auth_method",
                "access_token",
                "refresh_token",
            }
            return McpOAuthRevocationSnapshot(
                connection_id=connection.id,
                auth=copy.deepcopy(
                    {key: value for key, value in auth.items() if key in allowed}
                ),
            )
        except Exception:  # noqa: BLE001 - corrupt ciphertext cannot block local deny
            logger.warning(
                "mcp_oauth_revocation_snapshot_unavailable",
                extra={"connection_id": str(connection.id)},
            )
            return None


__all__ = [
    "McpConnectionTeardownService",
    "McpOAuthRevocationSnapshot",
]
