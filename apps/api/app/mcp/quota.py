"""Atomic, invocation-backed daily MCP tool-call admission."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.apps_catalog.access import RuntimeAppAccessSnapshot
from app.apps_catalog.mcp_product import (
    MCP_CONNECTORS_APP_SLUG,
    MCP_TOOL_CALLS_DAILY_ENTITLEMENT,
    MCP_TOOL_CALLS_USAGE_METRIC,
)
from app.core.errors import AppError, ErrorCategory
from app.mcp.runtime_models import McpToolInvocation
from app.usage.models import UsagePeriodCounter
from app.usage.periods import PeriodType, period_containing


@dataclass(frozen=True, slots=True)
class McpToolAdmissionReceipt:
    invocation_id: uuid.UUID
    admission_id: str
    period_start: datetime
    period_end: datetime
    used: int
    limit: int
    should_dispatch: bool


class McpToolQuotaService:
    """Create one durable invocation and charge one daily unit atomically."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def admit_in_transaction(
        self,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        grant_id: uuid.UUID,
        tool_id: uuid.UUID,
        connection_id: uuid.UUID,
        invocation_source: str,
        model_tool_call_id: str,
        request_id: str,
        admission_id: str,
        arguments: dict[str, Any],
        access: RuntimeAppAccessSnapshot,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        initiated_by_user_id: uuid.UUID | None = None,
        api_key_id: uuid.UUID | None = None,
        surface_binding_id: uuid.UUID | None = None,
        external_principal_fingerprint: str | None = None,
    ) -> McpToolAdmissionReceipt:
        if access.workspace_id != workspace_id or access.app_slug != MCP_CONNECTORS_APP_SLUG:
            self._unavailable(RuntimeError("MCP access snapshot mismatch"))
        aid = (admission_id or "").strip()
        rid = (request_id or "").strip()
        call_id = (model_tool_call_id or "").strip()
        if not aid or not rid or not call_id:
            raise AppError(
                ErrorCategory.VALIDATION,
                "MCP admission, request, and model tool-call IDs are required.",
            )

        limit = access.entitlement(MCP_TOOL_CALLS_DAILY_ENTITLEMENT)
        if limit <= 0:
            self._unavailable(RuntimeError("Invalid MCP tool-call entitlement"))
        window = period_containing(access.decision_at, PeriodType.DAILY)
        existing = self.db.scalar(
            select(McpToolInvocation)
            .where(
                McpToolInvocation.workspace_id == workspace_id,
                or_(
                    McpToolInvocation.admission_id == aid,
                    (
                        (McpToolInvocation.request_id == rid)
                        & (McpToolInvocation.model_tool_call_id == call_id)
                    ),
                ),
            )
            .with_for_update()
        )
        if existing is not None:
            return self._duplicate_receipt(
                existing,
                workspace_id=workspace_id,
                expert_id=expert_id,
                grant_id=grant_id,
                tool_id=tool_id,
                connection_id=connection_id,
                invocation_source=invocation_source,
                model_tool_call_id=call_id,
                request_id=rid,
                admission_id=aid,
                argument_hash=_argument_hash(arguments),
                conversation_id=conversation_id,
                message_id=message_id,
                initiated_by_user_id=initiated_by_user_id,
                api_key_id=api_key_id,
                surface_binding_id=surface_binding_id,
                external_principal_fingerprint=external_principal_fingerprint,
                current_limit=limit,
            )

        argument_hash = _argument_hash(arguments)
        invocation_id = uuid.uuid4()
        try:
            inserted_id = self.db.scalar(
                insert(McpToolInvocation)
                .values(
                    id=invocation_id,
                    workspace_id=workspace_id,
                    expert_id=expert_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    mcp_tool_grant_id=grant_id,
                    app_connection_id=connection_id,
                    mcp_server_tool_id=tool_id,
                    invocation_source=invocation_source,
                    initiated_by_user_id=initiated_by_user_id,
                    api_key_id=api_key_id,
                    mcp_tool_surface_binding_id=surface_binding_id,
                    external_principal_fingerprint=external_principal_fingerprint,
                    model_tool_call_id=call_id,
                    request_id=rid,
                    idempotency_key=aid,
                    admission_id=aid,
                    argument_hash=argument_hash,
                    status="admitted",
                    response_summary={},
                )
                .on_conflict_do_nothing()
                .returning(McpToolInvocation.id)
            )
        except SQLAlchemyError as exc:
            self._unavailable(exc)
        if inserted_id is None:
            concurrent = self.db.scalar(
                select(McpToolInvocation)
                .where(
                    McpToolInvocation.workspace_id == workspace_id,
                    or_(
                        McpToolInvocation.admission_id == aid,
                        (
                            (McpToolInvocation.request_id == rid)
                            & (McpToolInvocation.model_tool_call_id == call_id)
                        ),
                    ),
                )
                .with_for_update()
            )
            if concurrent is None:
                self._unavailable(RuntimeError("Concurrent MCP admission conflict"))
            return self._duplicate_receipt(
                concurrent,
                workspace_id=workspace_id,
                expert_id=expert_id,
                grant_id=grant_id,
                tool_id=tool_id,
                connection_id=connection_id,
                invocation_source=invocation_source,
                model_tool_call_id=call_id,
                request_id=rid,
                admission_id=aid,
                argument_hash=argument_hash,
                conversation_id=conversation_id,
                message_id=message_id,
                initiated_by_user_id=initiated_by_user_id,
                api_key_id=api_key_id,
                surface_binding_id=surface_binding_id,
                external_principal_fingerprint=external_principal_fingerprint,
                current_limit=limit,
            )
        invocation = self.db.get(McpToolInvocation, inserted_id)
        if invocation is None:
            self._unavailable(RuntimeError("MCP admission receipt was not persisted"))

        try:
            self.db.execute(
                insert(UsagePeriodCounter)
                .values(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    metric=MCP_TOOL_CALLS_USAGE_METRIC,
                    period_type=PeriodType.DAILY.value,
                    period_start=window.start,
                    period_end=window.end,
                    used=0,
                    reserved=0,
                )
                .on_conflict_do_nothing(constraint="uq_usage_period_counter")
            )
            charged = self.db.execute(
                update(UsagePeriodCounter)
                .where(
                    UsagePeriodCounter.workspace_id == workspace_id,
                    UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
                    UsagePeriodCounter.period_type == PeriodType.DAILY.value,
                    UsagePeriodCounter.period_start == window.start,
                    UsagePeriodCounter.period_end == window.end,
                    UsagePeriodCounter.used >= 0,
                    UsagePeriodCounter.reserved >= 0,
                    UsagePeriodCounter.used + UsagePeriodCounter.reserved < limit,
                )
                .values(used=UsagePeriodCounter.used + 1)
                .returning(UsagePeriodCounter.used)
            ).one_or_none()
        except SQLAlchemyError as exc:
            self._unavailable(exc)
        if charged is None:
            used, reserved = self._counter_state(
                workspace_id,
                window.start,
                expected_period_end=window.end,
                require_existing=True,
            )
            if used + reserved < limit:
                self._unavailable(RuntimeError("MCP quota increment was not atomic"))
            self.db.delete(invocation)
            self.db.flush()
            retry_after = max(
                1,
                math.ceil((window.end - access.decision_at).total_seconds()),
            )
            raise AppError(
                ErrorCategory.MCP_TOOL_LIMIT_REACHED,
                "MCP Connectors daily tool-call limit reached.",
                details={
                    "metric": MCP_TOOL_CALLS_USAGE_METRIC,
                    "limit": limit,
                    "used": used,
                    "remaining": 0,
                    "reset_at": window.end.isoformat(),
                },
                retryable=True,
                headers={"Retry-After": str(retry_after)},
            )

        invocation.quota_period_start = window.start
        invocation.quota_charged_at = access.decision_at
        self.db.flush()
        return McpToolAdmissionReceipt(
            invocation_id=invocation.id,
            admission_id=aid,
            period_start=window.start,
            period_end=window.end,
            used=int(charged[0]),
            limit=limit,
            should_dispatch=True,
        )

    def mark_dispatch_started(self, invocation_id: uuid.UUID, *, at: datetime) -> None:
        row = self.db.scalar(
            select(McpToolInvocation)
            .where(McpToolInvocation.id == invocation_id)
            .with_for_update()
        )
        if (
            row is None
            or row.status != "admitted"
            or row.gateway_dispatch_started_at is not None
            or row.quota_period_start is None
            or row.quota_charged_at is None
        ):
            raise AppError(
                ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN,
                "MCP tool invocation is not safe to dispatch.",
            )
        row.gateway_dispatch_started_at = at
        row.status = "dispatching"
        self.db.flush()

    def _counter_used(
        self,
        workspace_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> int:
        used, _reserved = self._counter_state(
            workspace_id,
            period_start,
            expected_period_end=period_end,
            require_existing=False,
        )
        return used

    def _counter_state(
        self,
        workspace_id: uuid.UUID,
        period_start: datetime,
        *,
        expected_period_end: datetime,
        require_existing: bool,
    ) -> tuple[int, int]:
        try:
            row = self.db.execute(
                select(
                    UsagePeriodCounter.period_end,
                    UsagePeriodCounter.used,
                    UsagePeriodCounter.reserved,
                ).where(
                    UsagePeriodCounter.workspace_id == workspace_id,
                    UsagePeriodCounter.metric == MCP_TOOL_CALLS_USAGE_METRIC,
                    UsagePeriodCounter.period_type == PeriodType.DAILY.value,
                    UsagePeriodCounter.period_start == period_start,
                )
            ).one_or_none()
        except SQLAlchemyError as exc:
            self._unavailable(exc)
        if row is None:
            if require_existing:
                self._unavailable(RuntimeError("Missing MCP quota counter"))
            return 0, 0
        if (
            row.period_end != expected_period_end
            or int(row.used) < 0
            or int(row.reserved) < 0
        ):
            self._unavailable(RuntimeError("Invalid MCP quota counter"))
        return int(row.used), int(row.reserved)

    def _duplicate_receipt(
        self,
        row: McpToolInvocation,
        *,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        grant_id: uuid.UUID,
        tool_id: uuid.UUID,
        connection_id: uuid.UUID,
        invocation_source: str,
        model_tool_call_id: str,
        request_id: str,
        admission_id: str,
        argument_hash: str,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        initiated_by_user_id: uuid.UUID | None,
        api_key_id: uuid.UUID | None,
        surface_binding_id: uuid.UUID | None,
        external_principal_fingerprint: str | None,
        current_limit: int,
    ) -> McpToolAdmissionReceipt:
        expected = (
            workspace_id,
            expert_id,
            grant_id,
            tool_id,
            connection_id,
            invocation_source,
            model_tool_call_id,
            request_id,
            admission_id,
            argument_hash,
            conversation_id,
            message_id,
            initiated_by_user_id,
            api_key_id,
            surface_binding_id,
            external_principal_fingerprint,
        )
        actual = (
            row.workspace_id,
            row.expert_id,
            row.mcp_tool_grant_id,
            row.mcp_server_tool_id,
            row.app_connection_id,
            row.invocation_source,
            row.model_tool_call_id,
            row.request_id,
            row.admission_id,
            row.argument_hash,
            row.conversation_id,
            row.message_id,
            row.initiated_by_user_id,
            row.api_key_id,
            row.mcp_tool_surface_binding_id,
            row.external_principal_fingerprint,
        )
        if actual != expected or row.quota_period_start is None:
            raise AppError(
                ErrorCategory.CONFLICT,
                "The MCP admission identity conflicts with an existing request.",
            )
        original_window = period_containing(row.quota_period_start, PeriodType.DAILY)
        used = self._counter_used(
            workspace_id,
            original_window.start,
            original_window.end,
        )
        return McpToolAdmissionReceipt(
            invocation_id=row.id,
            admission_id=row.admission_id,
            period_start=original_window.start,
            period_end=original_window.end,
            used=used,
            limit=current_limit,
            # A duplicate is never permission to perform another egress.
            should_dispatch=False,
        )

    @staticmethod
    def _unavailable(exc: Exception) -> NoReturn:
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "MCP tool-call metering is temporarily unavailable.",
            retryable=True,
        ) from exc


def _argument_hash(arguments: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            arguments,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppError(
            ErrorCategory.VALIDATION,
            "MCP tool arguments must be JSON serializable.",
        ) from exc
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["McpToolAdmissionReceipt", "McpToolQuotaService"]
