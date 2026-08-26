"""Source-aware, fail-closed MCP grant resolution for model tool schemas."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.runtime_locks import (
    acquire_runtime_admission_fences,
    begin_runtime_admission_transaction,
)
from app.connectors.models import AppConnection
from app.connectors.types import (
    CONNECTION_USABLE_STATUSES,
    ConnectionHealth,
)
from app.conversations.invocation import (
    SOURCE_API,
    SOURCE_WORKSPACE,
    ChatInvocationContext,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import SessionLocal
from app.experts.models import ExpertType
from app.mcp.constants import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTORS_APP_SLUG,
)
from app.mcp.access_policy import is_mcp_access_denial
from app.mcp.models import McpServerTool, McpToolGrant
from app.mcp.repository import McpGrantRecord, McpRepository
from app.mcp.types import (
    McpCompatibilityStatus,
    McpGrantState,
    McpToolClassification,
    McpToolStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedMcpTool:
    """One exact approved tool plus its provider-facing function schema."""

    grant: McpToolGrant
    tool: McpServerTool
    connection: AppConnection
    provider_tool_schema: dict[str, Any]


class McpGrantResolver:
    """Resolve current grants without making zero-grant turns paid operations.

    The caller-provided session performs only the cheap source preflight.  A
    separate short session is opened for paid admission only when that query
    finds a candidate active grant for the exact source.
    """

    _SOURCE_FIELD = {
        SOURCE_WORKSPACE: "allow_workspace_chat",
        SOURCE_API: "allow_public_api",
    }

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    def resolve(
        self,
        invocation: ChatInvocationContext,
        expert_id: uuid.UUID,
    ) -> list[ResolvedMcpTool]:
        if not self.settings.mcp_connector_enabled:
            return []
        allow_field = self._SOURCE_FIELD.get(invocation.source)
        if allow_field is None:
            # Widget/channel require exact 13E surface bindings and therefore
            # cannot fall back to a broad Expert grant.
            return []
        if invocation.expert_id is not None and invocation.expert_id != expert_id:
            return []

        # This check intentionally precedes every paid-App lookup.  It is the
        # byte-identical zero-grant path used by ordinary Experts.
        if not McpRepository(self.db).has_eligible_source_grant(
            invocation.workspace_id,
            expert_id,
            allow_field=allow_field,
        ):
            return []

        gate_db = self.session_factory()
        try:
            begin_runtime_admission_transaction(gate_db)
            acquire_runtime_admission_fences(
                gate_db,
                workspace_id=invocation.workspace_id,
                app_slugs=(MCP_CONNECTORS_APP_SLUG,),
            )
            access = AppAccessService(gate_db).require_runtime_active(
                invocation.workspace_id,
                app_slug=MCP_CONNECTORS_APP_SLUG,
                entitlement_keys=(MCP_CONNECTIONS_ENTITLEMENT,),
            )
            repo = McpRepository(gate_db)
            expert = repo.get_expert(invocation.workspace_id, expert_id)
            if expert is None or expert.type != ExpertType.WORKSPACE.value:
                gate_db.commit()
                return []
            records = repo.list_grant_records(
                invocation.workspace_id,
                expert_id,
                active_only=True,
                for_share=True,
            )
            resolved: list[ResolvedMcpTool] = []
            for record in records:
                if not bool(getattr(record.grant, allow_field)):
                    continue
                if record.connection.app_installation_id != access.installation_id:
                    continue
                if not self._record_is_current(
                    record,
                    source=invocation.source,
                    decision_at=access.decision_at,
                ):
                    continue
                resolved.append(
                    ResolvedMcpTool(
                        grant=record.grant,
                        tool=record.tool,
                        connection=record.connection,
                        provider_tool_schema=self._provider_schema(record.tool),
                    )
                )
                if len(resolved) >= self.settings.mcp_max_tools_per_expert:
                    break
            gate_db.commit()
            return resolved
        except AppError as exc:
            self._rollback(gate_db)
            if is_mcp_access_denial(exc):
                return []
            raise
        except SQLAlchemyError as exc:
            self._rollback(gate_db)
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "MCP Connectors access is temporarily unavailable.",
                retryable=True,
            ) from exc
        finally:
            gate_db.close()

    def _record_is_current(
        self,
        record: McpGrantRecord,
        *,
        source: str,
        decision_at,
    ) -> bool:
        grant, tool, connection = record.grant, record.tool, record.connection
        if grant.state != McpGrantState.ACTIVE.value:
            return False
        if connection.status not in CONNECTION_USABLE_STATUSES:
            return False
        if connection.health == ConnectionHealth.FAILED.value:
            return False
        if connection.mcp_reauthorization_required:
            return False
        if tool.status != McpToolStatus.ACTIVE.value:
            return False
        if tool.compatibility_status != McpCompatibilityStatus.COMPATIBLE.value:
            return False
        if tool.classification not in {
            McpToolClassification.READ_ONLY.value,
            McpToolClassification.WRITE.value,
        }:
            return False
        if grant.approved_definition_hash != tool.definition_hash:
            return False
        if grant.approved_classification != tool.classification:
            return False
        if (
            not connection.mcp_principal_fingerprint
            or grant.approved_principal_fingerprint
            != connection.mcp_principal_fingerprint
        ):
            return False
        if grant.approved_credential_epoch != connection.mcp_credential_epoch:
            return False
        refreshed = connection.mcp_inventory_refreshed_at
        if refreshed is None:
            return False
        cutoff = decision_at - timedelta(
            seconds=self.settings.mcp_tool_inventory_ttl_seconds
        )
        if refreshed < cutoff:
            return False
        if (
            source == SOURCE_API
            and tool.classification == McpToolClassification.WRITE.value
            and not grant.unattended_write_allowed
        ):
            return False
        return True

    @staticmethod
    def _provider_schema(tool: McpServerTool) -> dict[str, Any]:
        function: dict[str, Any] = {
            "name": tool.llm_tool_name,
            "parameters": dict(tool.input_schema or {}),
        }
        description = (tool.description or tool.title or "").strip()
        if description:
            function["description"] = description
        return {"type": "function", "function": function}

    @staticmethod
    def _rollback(db: Session) -> None:
        try:
            db.rollback()
        except SQLAlchemyError:
            logger.error("mcp_resolver_rollback_failed")


__all__ = ["McpGrantResolver", "ResolvedMcpTool"]
