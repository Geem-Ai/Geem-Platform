"""API-key request/response DTOs. The full secret appears only on create."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api_keys.scopes import DEFAULT_SCOPES


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] | None = None
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Name is required.")
        return cleaned


class ApiKeyOut(BaseModel):
    """Safe identifying fields. Never includes the secret or hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    prefix: str
    last_four: str
    scopes: list[str]
    created_by: uuid.UUID | None
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateResponse(ApiKeyOut):
    key: str = Field(
        description="Full API secret. Returned once at creation; store it securely."
    )


def to_api_key_out(row: object) -> ApiKeyOut:
    scopes = getattr(row, "scopes") or list(DEFAULT_SCOPES)
    if not isinstance(scopes, list):
        scopes = list(DEFAULT_SCOPES)
    return ApiKeyOut(
        id=getattr(row, "id"),
        workspace_id=getattr(row, "workspace_id"),
        name=getattr(row, "name"),
        prefix=getattr(row, "key_prefix"),
        last_four=getattr(row, "last_four"),
        scopes=[str(s) for s in scopes],
        created_by=getattr(row, "created_by"),
        last_used_at=_utc(getattr(row, "last_used_at")),
        expires_at=_utc(getattr(row, "expires_at")),
        revoked_at=_utc(getattr(row, "revoked_at")),
        created_at=_utc(getattr(row, "created_at")),
        updated_at=_utc(getattr(row, "updated_at")),
    )
