"""DTOs for atomic AI usage reservations (Phase 5B)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CreditAllocation:
    grant_id: uuid.UUID
    amount: int

    def as_dict(self) -> dict[str, Any]:
        return {"grant_id": str(self.grant_id), "amount": int(self.amount)}


@dataclass(frozen=True, slots=True)
class AiUsageReservationDTO:
    id: uuid.UUID
    workspace_id: uuid.UUID
    request_id: str
    status: str
    estimated_tokens: int
    included_reserved: int
    credit_reserved: int
    actual_tokens: int | None
    included_settled: int
    credit_settled: int
    credit_allocations: list[CreditAllocation] = field(default_factory=list)
    undercharged_tokens: int = 0
