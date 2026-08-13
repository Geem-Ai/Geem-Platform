"""Canonical usage metric names for period counters and storage events."""

from __future__ import annotations

from enum import StrEnum


class UsageMetric(StrEnum):
    AI_TOKENS = "ai_tokens"
    STORAGE_BYTES = "storage_bytes"
    EXPERTS = "experts"


class StorageUsageReason(StrEnum):
    UPLOAD = "upload"
    DELETE = "delete"
    RECOMPUTE = "recompute"
    ADJUST = "adjust"
    RESERVE = "reserve"
    RELEASE = "release"
    RESTORE = "restore"


class StorageReservationStatus(StrEnum):
    RESERVED = "reserved"
    FINALIZED = "finalized"
    RELEASED = "released"


class CreditLedgerEntryType(StrEnum):
    GRANT = "grant"
    CONSUME = "consume"
    RESERVE = "reserve"
    RELEASE = "release"
    EXPIRE = "expire"
    ADJUST = "adjust"


class AiUsageReservationStatus(StrEnum):
    RESERVED = "reserved"
    SETTLED = "settled"
    RELEASED = "released"
