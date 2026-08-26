"""Atomic MCP write approval, lease, crash, scrub, and purge state machine."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.crypto import decrypt_json, encrypt_json
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.runtime_models import McpPendingToolCall, McpSurfaceDelivery


TERMINAL_PENDING_STATUSES = frozenset(
    {"denied", "expired", "executed", "outcome_unknown"}
)


@dataclass(frozen=True, slots=True)
class PendingDecision:
    pending_id: uuid.UUID
    status: str
    version: int
    enqueue_resume: bool


class McpApprovalService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def create_pending(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        grant_id: uuid.UUID,
        model_tool_call_id: str,
        idempotency_key: str,
        arguments: dict[str, Any],
        loop_state: dict[str, Any],
        initiated_by_user_id: uuid.UUID | None = None,
        surface_binding_id: uuid.UUID | None = None,
        external_principal_fingerprint: str | None = None,
        initiating_origin_digest: str | None = None,
        external_turn_handle_digest: str | None = None,
    ) -> McpPendingToolCall:
        if (initiated_by_user_id is None) == (surface_binding_id is None):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Exactly one MCP approval initiator is required.",
            )
        if initiated_by_user_id is not None and any(
            value is not None
            for value in (
                external_principal_fingerprint,
                initiating_origin_digest,
                external_turn_handle_digest,
            )
        ):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Workspace MCP approvals cannot carry an external principal.",
            )
        if surface_binding_id is not None:
            external_principal_fingerprint = _require_digest(
                external_principal_fingerprint,
                field="external principal fingerprint",
            )
            if initiating_origin_digest is not None:
                initiating_origin_digest = _require_digest(
                    initiating_origin_digest, field="origin digest"
                )
            if external_turn_handle_digest is not None:
                external_turn_handle_digest = _require_digest(
                    external_turn_handle_digest,
                    field="external turn handle digest",
                )
        argument_canonical = _bounded_json_object(
            arguments,
            max_bytes=int(self.settings.mcp_egress_max_request_bytes),
            label="MCP tool arguments",
        )
        _bounded_json_object(
            loop_state,
            max_bytes=256_000,
            label="MCP approval resume state",
        )
        clean_call_id = (model_tool_call_id or "").strip()
        clean_idempotency = (idempotency_key or "").strip()
        if not clean_call_id or not clean_idempotency:
            raise AppError(
                ErrorCategory.VALIDATION,
                "MCP model tool-call and idempotency IDs are required.",
            )
        if surface_binding_id is not None:
            self._lock_external_pending_cap(workspace_id)
        existing = self.db.scalar(
            select(McpPendingToolCall)
            .where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.idempotency_key == clean_idempotency,
            )
            .with_for_update()
        )
        if existing is not None:
            self._validate_existing_pending(
                existing,
                conversation_id=conversation_id,
                message_id=message_id,
                grant_id=grant_id,
                model_tool_call_id=clean_call_id,
                initiated_by_user_id=initiated_by_user_id,
                surface_binding_id=surface_binding_id,
                external_principal_fingerprint=external_principal_fingerprint,
                initiating_origin_digest=initiating_origin_digest,
                external_turn_handle_digest=external_turn_handle_digest,
                argument_canonical=argument_canonical,
            )
            return existing

        if surface_binding_id is not None:
            live_count = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(McpPendingToolCall)
                    .where(
                        McpPendingToolCall.workspace_id == workspace_id,
                        McpPendingToolCall.mcp_tool_surface_binding_id.is_not(None),
                        McpPendingToolCall.status.in_(
                            ("pending", "approved", "executing")
                        ),
                    )
                )
                or 0
            )
            if live_count >= int(
                self.settings.mcp_max_external_pending_per_workspace
            ):
                raise AppError(
                    ErrorCategory.MCP_EXTERNAL_TURN_PENDING,
                    "The Workspace has too many pending external MCP approvals.",
                    retryable=True,
                )
        now = datetime.now(timezone.utc)
        ttl = max(1, int(self.settings.mcp_tool_approval_ttl_seconds))
        purge_delay = max(ttl, ttl * 2)
        row_id = uuid.uuid4()
        inserted_id = self.db.scalar(
            insert(McpPendingToolCall)
            .values(
                id=row_id,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                message_id=message_id,
                mcp_tool_grant_id=grant_id,
                initiated_by_user_id=initiated_by_user_id,
                mcp_tool_surface_binding_id=surface_binding_id,
                model_tool_call_id=clean_call_id,
                external_principal_fingerprint=external_principal_fingerprint,
                initiating_origin_digest=initiating_origin_digest,
                external_turn_handle_digest=external_turn_handle_digest,
                arguments_encrypted=encrypt_json(arguments, settings=self.settings),
                loop_state_encrypted=encrypt_json(loop_state, settings=self.settings),
                status="pending",
                idempotency_key=clean_idempotency,
                version=1,
                resume_attempts=0,
                expires_at=now + timedelta(seconds=ttl),
                purge_after=now + timedelta(seconds=purge_delay),
            )
            .on_conflict_do_nothing()
            .returning(McpPendingToolCall.id)
        )
        if inserted_id is not None:
            row = self.db.get(McpPendingToolCall, inserted_id)
            assert row is not None
            return row

        # ON CONFLICT waits for a concurrent winner before returning. Re-read
        # the stable logical identity and return it only when every immutable
        # approval coordinate matches; never conflate a different live turn.
        existing = self.db.scalar(
            select(McpPendingToolCall)
            .where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.idempotency_key == clean_idempotency,
            )
            .with_for_update()
        )
        if existing is not None:
            self._validate_existing_pending(
                existing,
                conversation_id=conversation_id,
                message_id=message_id,
                grant_id=grant_id,
                model_tool_call_id=clean_call_id,
                initiated_by_user_id=initiated_by_user_id,
                surface_binding_id=surface_binding_id,
                external_principal_fingerprint=external_principal_fingerprint,
                initiating_origin_digest=initiating_origin_digest,
                external_turn_handle_digest=external_turn_handle_digest,
                argument_canonical=argument_canonical,
            )
            return existing
        if surface_binding_id is not None and self.db.scalar(
            select(McpPendingToolCall.id).where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.conversation_id == conversation_id,
                McpPendingToolCall.mcp_tool_surface_binding_id.is_not(None),
                McpPendingToolCall.status.in_(("pending", "approved", "executing")),
            )
        ):
            raise AppError(
                ErrorCategory.MCP_EXTERNAL_TURN_PENDING,
                "This external conversation already has a pending MCP write.",
                retryable=True,
            )
        raise AppError(
            ErrorCategory.CONFLICT,
            "The MCP approval identity conflicts with an existing request.",
        )

    def arguments_for_authorized_review(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
    ) -> dict[str, Any]:
        row = self._get(workspace_id, pending_id)
        if row.arguments_encrypted is None:
            return {}
        return decrypt_json(row.arguments_encrypted, settings=self.settings)

    def live_external_pending(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        exclude_message_id: uuid.UUID | None = None,
    ) -> McpPendingToolCall | None:
        """Return the live external write that serializes this conversation.

        External ingress already holds its exact session/chat generation lock.
        This zero-paid-lookup preflight prevents a newer read or write tool turn
        from interleaving while an earlier write is awaiting a Workspace
        operator or is executing.
        """

        predicates = [
            McpPendingToolCall.workspace_id == workspace_id,
            McpPendingToolCall.conversation_id == conversation_id,
            McpPendingToolCall.mcp_tool_surface_binding_id.is_not(None),
            McpPendingToolCall.status.in_(("pending", "approved", "executing")),
        ]
        if exclude_message_id is not None:
            predicates.append(McpPendingToolCall.message_id != exclude_message_id)
        return self.db.scalar(
            select(McpPendingToolCall)
            .where(*predicates)
            .order_by(McpPendingToolCall.created_at, McpPendingToolCall.id)
            .limit(1)
        )

    def decide_workspace_chat(
        self,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        pending_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        decision: str,
    ) -> PendingDecision:
        row = self._lock(workspace_id, pending_id)
        if (
            row.conversation_id != conversation_id
            or row.initiated_by_user_id != actor_user_id
            or row.mcp_tool_surface_binding_id is not None
        ):
            raise AppError(
                ErrorCategory.MCP_TOOL_NOT_GRANTED,
                "This MCP tool approval does not belong to the initiating user.",
            )
        return self._decide(row, actor_user_id=actor_user_id, decision=decision)

    def decide_external(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        operator_user_id: uuid.UUID,
        decision: str,
    ) -> PendingDecision:
        row = self._lock(workspace_id, pending_id)
        if row.mcp_tool_surface_binding_id is None or row.initiated_by_user_id is not None:
            raise AppError(
                ErrorCategory.MCP_TOOL_NOT_GRANTED,
                "This is not an external MCP approval.",
            )
        return self._decide(row, actor_user_id=operator_user_id, decision=decision)

    def claim_resume(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        lease_seconds: int = 90,
    ) -> McpPendingToolCall | None:
        row = self._lock(workspace_id, pending_id)
        now = datetime.now(timezone.utc)
        if row.status != "approved":
            return None
        if row.expires_at <= now:
            self._expire_locked(row, now)
            return None
        if row.gateway_dispatch_started_at is not None:
            row.status = "outcome_unknown"
            row.version += 1
            self._scrub(row, now)
            self.db.flush()
            return None
        row.status = "executing"
        row.resume_attempts += 1
        row.claim_lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
        row.execution_deadline = min(
            row.expires_at,
            now
            + timedelta(seconds=max(1, int(self.settings.mcp_total_turn_timeout_seconds))),
        )
        row.version += 1
        self.db.flush()
        return row

    def mark_gateway_dispatch_started(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
    ) -> None:
        row = self._lock(workspace_id, pending_id)
        now = datetime.now(timezone.utc)
        if (
            row.status != "executing"
            or row.gateway_dispatch_started_at is not None
            or row.execution_deadline is None
            or row.execution_deadline <= now
            or row.expires_at <= now
        ):
            raise AppError(
                ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN,
                "MCP write is not safe to dispatch.",
            )
        row.gateway_dispatch_started_at = now
        row.version += 1
        self.db.flush()

    def finish_execution(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        outcome_unknown: bool = False,
    ) -> None:
        row = self._lock(workspace_id, pending_id)
        if row.status in TERMINAL_PENDING_STATUSES:
            return
        if row.status != "executing":
            raise AppError(
                ErrorCategory.CONFLICT,
                "The MCP write was not claimed for execution.",
            )
        if not outcome_unknown and row.gateway_dispatch_started_at is None:
            raise AppError(
                ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN,
                "The MCP write dispatch was not durably marked.",
            )
        now = datetime.now(timezone.utc)
        row.status = "outcome_unknown" if outcome_unknown else "executed"
        row.executed_at = now
        row.claim_lease_expires_at = None
        row.version += 1
        self._scrub(row, now)
        self.db.flush()

    def cancel_before_dispatch(
        self,
        *,
        workspace_id: uuid.UUID,
        pending_id: uuid.UUID,
        status: str = "denied",
    ) -> None:
        """Terminate a resumed approval only while no gateway dispatch began."""

        if status not in {"denied", "expired"}:
            raise ValueError("Pre-dispatch cancellation must be denied or expired.")
        row = self._lock(workspace_id, pending_id)
        if row.status in TERMINAL_PENDING_STATUSES:
            return
        if row.status != "executing" or row.gateway_dispatch_started_at is not None:
            raise AppError(
                ErrorCategory.MCP_TOOL_OUTCOME_UNKNOWN,
                "The MCP write can no longer be cancelled safely.",
            )
        now = datetime.now(timezone.utc)
        row.status = status
        row.claim_lease_expires_at = None
        row.execution_deadline = None
        row.version += 1
        self._scrub(row, now)
        self.db.flush()

    def recover_stale_claims(self, *, limit: int = 100) -> tuple[int, int]:
        """Requeue only provably pre-dispatch claims; mark later loss unknown."""

        now = datetime.now(timezone.utc)
        rows = list(
            self.db.scalars(
                select(McpPendingToolCall)
                .where(
                    McpPendingToolCall.status == "executing",
                    McpPendingToolCall.claim_lease_expires_at < now,
                )
                .order_by(McpPendingToolCall.claim_lease_expires_at)
                .limit(max(1, min(limit, 500)))
                .with_for_update(skip_locked=True)
            ).all()
        )
        recovered = 0
        unknown = 0
        for row in rows:
            row.claim_lease_expires_at = None
            row.version += 1
            if row.expires_at <= now:
                self._expire_locked(row, now, increment_version=False)
            elif row.gateway_dispatch_started_at is None:
                row.status = "approved"
                row.resume_enqueued_at = None
                row.execution_deadline = None
                recovered += 1
            else:
                row.status = "outcome_unknown"
                self._scrub(row, now)
                unknown += 1
        self.db.flush()
        return recovered, unknown

    def expire_due(self, *, limit: int = 100) -> int:
        now = datetime.now(timezone.utc)
        rows = list(
            self.db.scalars(
                select(McpPendingToolCall)
                .where(
                    McpPendingToolCall.status.in_(("pending", "approved")),
                    McpPendingToolCall.expires_at <= now,
                )
                .order_by(McpPendingToolCall.expires_at)
                .limit(max(1, min(limit, 500)))
                .with_for_update(skip_locked=True)
            ).all()
        )
        for row in rows:
            self._expire_locked(row, now)
        self.db.flush()
        return len(rows)

    def purge_due(
        self,
        *,
        limit: int = 100,
        finalized_terminal_ids: tuple[uuid.UUID, ...] = (),
    ) -> int:
        """Purge only rows whose required terminal materialization ran first.

        Delivery rows linked to an approval remain as the durable proof that a
        WhatsApp pending/final revision was created.  Once both the approval
        retention window and every linked delivery deadline have elapsed, the
        outbox rows and approval are removed atomically in FK-safe order.
        """

        now = datetime.now(timezone.utc)
        safe_terminal_ids = tuple(dict.fromkeys(finalized_terminal_ids))
        finalization_safe = McpPendingToolCall.status == "executed"
        if safe_terminal_ids:
            finalization_safe = or_(
                finalization_safe,
                McpPendingToolCall.id.in_(safe_terminal_ids),
            )
        ids = list(
            self.db.scalars(
                select(McpPendingToolCall.id)
                .where(
                    McpPendingToolCall.status.in_(tuple(TERMINAL_PENDING_STATUSES)),
                    finalization_safe,
                    McpPendingToolCall.purge_after <= now,
                    McpPendingToolCall.arguments_encrypted.is_(None),
                    McpPendingToolCall.loop_state_encrypted.is_(None),
                    ~exists(
                        select(McpSurfaceDelivery.id).where(
                            McpSurfaceDelivery.mcp_pending_tool_call_id
                            == McpPendingToolCall.id,
                            or_(
                                McpSurfaceDelivery.status.in_(
                                    ("pending", "dispatching", "delivery_unknown")
                                ),
                                McpSurfaceDelivery.delivery_deadline > now,
                            ),
                        )
                    ),
                )
                .order_by(McpPendingToolCall.purge_after)
                .limit(max(1, min(limit, 500)))
            ).all()
        )
        if ids:
            self.db.execute(
                delete(McpSurfaceDelivery).where(
                    McpSurfaceDelivery.mcp_pending_tool_call_id.in_(ids)
                )
            )
            self.db.execute(delete(McpPendingToolCall).where(McpPendingToolCall.id.in_(ids)))
        return len(ids)

    def _decide(
        self,
        row: McpPendingToolCall,
        *,
        actor_user_id: uuid.UUID,
        decision: str,
    ) -> PendingDecision:
        normalized = (decision or "").strip().lower()
        if normalized not in {"approve", "deny"}:
            raise AppError(ErrorCategory.VALIDATION, "Decision must be approve or deny.")
        now = datetime.now(timezone.utc)
        if row.status in TERMINAL_PENDING_STATUSES:
            return PendingDecision(row.id, row.status, row.version, False)
        if row.status != "pending":
            if row.status in {"approved", "executing"} and normalized == "approve":
                return PendingDecision(row.id, row.status, row.version, False)
            raise AppError(
                ErrorCategory.CONFLICT,
                "The MCP approval has already been decided.",
            )
        if row.expires_at <= now:
            self._expire_locked(row, now)
            raise AppError(
                ErrorCategory.MCP_EXTERNAL_APPROVAL_REQUIRED,
                "The MCP approval has expired.",
            )
        row.decided_by_user_id = actor_user_id
        row.decided_at = now
        row.version += 1
        if normalized == "deny":
            row.status = "denied"
            self._scrub(row, now)
            self.db.flush()
            return PendingDecision(row.id, row.status, row.version, False)
        row.status = "approved"
        row.resume_requested_at = now
        self.db.flush()
        return PendingDecision(row.id, row.status, row.version, True)

    def _expire_locked(
        self,
        row: McpPendingToolCall,
        now: datetime,
        *,
        increment_version: bool = True,
    ) -> None:
        row.status = "expired"
        if increment_version:
            row.version += 1
        self._scrub(row, now)

    @staticmethod
    def _scrub(row: McpPendingToolCall, now: datetime) -> None:
        row.arguments_encrypted = None
        row.loop_state_encrypted = None
        row.claim_lease_expires_at = None
        row.execution_deadline = None
        row.purge_after = min(row.purge_after, now + timedelta(hours=1))

    def _validate_existing_pending(
        self,
        row: McpPendingToolCall,
        *,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        grant_id: uuid.UUID,
        model_tool_call_id: str,
        initiated_by_user_id: uuid.UUID | None,
        surface_binding_id: uuid.UUID | None,
        external_principal_fingerprint: str | None,
        initiating_origin_digest: str | None,
        external_turn_handle_digest: str | None,
        argument_canonical: bytes,
    ) -> None:
        expected = (
            conversation_id,
            message_id,
            grant_id,
            model_tool_call_id,
            initiated_by_user_id,
            surface_binding_id,
            external_principal_fingerprint,
            initiating_origin_digest,
            external_turn_handle_digest,
        )
        actual = (
            row.conversation_id,
            row.message_id,
            row.mcp_tool_grant_id,
            row.model_tool_call_id,
            row.initiated_by_user_id,
            row.mcp_tool_surface_binding_id,
            row.external_principal_fingerprint,
            row.initiating_origin_digest,
            row.external_turn_handle_digest,
        )
        if actual != expected:
            raise AppError(
                ErrorCategory.CONFLICT,
                "The MCP approval identity conflicts with an existing request.",
            )
        # Live approvals retain their encrypted authoritative arguments. An
        # idempotency replay may reuse them only when the canonical arguments
        # are byte-for-byte identical. Terminal scrubbed rows remain safe to
        # replay because they can never be dispatched again.
        if row.arguments_encrypted is not None:
            try:
                persisted = decrypt_json(
                    row.arguments_encrypted, settings=self.settings
                )
                persisted_canonical = _bounded_json_object(
                    persisted,
                    max_bytes=int(self.settings.mcp_egress_max_request_bytes),
                    label="Persisted MCP tool arguments",
                )
            except Exception as exc:  # encrypted state integrity boundary
                raise AppError(
                    ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                    "The MCP approval state is temporarily unavailable.",
                    retryable=True,
                ) from exc
            if persisted_canonical != argument_canonical:
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "The MCP approval identity conflicts with existing arguments.",
                )

    def _lock_external_pending_cap(self, workspace_id: uuid.UUID) -> None:
        """Serialize the workspace-wide external live-pending cap."""

        digest = hashlib.blake2b(
            f"mcp-external-pending:{workspace_id}".encode("utf-8"),
            digest_size=8,
            person=b"geemmcp",
        ).digest()
        key = int.from_bytes(digest, "big", signed=True)
        try:
            self.db.execute(select(func.pg_advisory_xact_lock(key)))
        except SQLAlchemyError as exc:
            raise AppError(
                ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
                "MCP external approval admission is temporarily unavailable.",
                retryable=True,
            ) from exc

    def _get(
        self, workspace_id: uuid.UUID, pending_id: uuid.UUID
    ) -> McpPendingToolCall:
        row = self.db.scalar(
            select(McpPendingToolCall).where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.id == pending_id,
            )
        )
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "MCP approval not found.")
        return row

    def _lock(
        self, workspace_id: uuid.UUID, pending_id: uuid.UUID
    ) -> McpPendingToolCall:
        row = self.db.scalar(
            select(McpPendingToolCall)
            .where(
                McpPendingToolCall.workspace_id == workspace_id,
                McpPendingToolCall.id == pending_id,
            )
            .with_for_update()
        )
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "MCP approval not found.")
        return row


def _bounded_json_object(
    value: dict[str, Any],
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    if not isinstance(value, dict):
        raise AppError(ErrorCategory.VALIDATION, f"{label} must be an object.")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"{label} must contain finite JSON values.",
        ) from exc
    if len(encoded) > max(1, int(max_bytes)):
        raise AppError(
            ErrorCategory.MCP_TOOL_RESULT_UNSUPPORTED,
            f"{label} exceeds the configured size limit.",
        )
    return encoded


def _require_digest(value: str | None, *, field: str) -> str:
    normalized = (value or "").strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise AppError(
            ErrorCategory.VALIDATION,
            f"A valid MCP {field} is required.",
        )
    return normalized


__all__ = ["McpApprovalService", "PendingDecision", "TERMINAL_PENDING_STATUSES"]
