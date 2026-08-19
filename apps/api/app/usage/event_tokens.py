"""Shared SQL expressions over ``usage_events`` token fields.

``billed_tokens`` already recorded on the event is authoritative. Rollups
and API summaries must not re-apply family multipliers.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, cast, func

from app.db.models import UsageEvent


def billed_tokens_expr():
    """Prefer ``cost_metadata.billed_tokens``; else input + output columns."""
    from_meta = cast(UsageEvent.cost_metadata["billed_tokens"].astext, BigInteger)
    fallback = func.coalesce(cast(UsageEvent.input_tokens, BigInteger), 0) + func.coalesce(
        cast(UsageEvent.output_tokens, BigInteger), 0
    )
    return func.coalesce(from_meta, fallback)
