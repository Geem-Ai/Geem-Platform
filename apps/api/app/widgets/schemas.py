"""Chat Widget API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WidgetExpertOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str


class WidgetInstanceOut(BaseModel):
    id: uuid.UUID
    status: str
    expert_id: uuid.UUID | None = None
    expert: WidgetExpertOut | None = None
    title: str
    subtitle: str | None = None
    greeting: str | None = None
    logo_url: str | None = None
    locale: str
    position: str
    primary_color: str
    text_color: str
    allowed_origins: list[str] = Field(default_factory=list)
    embed_script_url: str
    embed_html: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WidgetUpdateIn(BaseModel):
    expert_id: uuid.UUID | None = None
    title: str | None = Field(None, max_length=128)
    subtitle: str | None = Field(None, max_length=256)
    greeting: str | None = Field(None, max_length=2000)
    logo_url: str | None = Field(None, max_length=1024)
    locale: str | None = Field(None, max_length=8)
    position: str | None = Field(None, max_length=32)
    primary_color: str | None = Field(None, max_length=16)
    text_color: str | None = Field(None, max_length=16)
    allowed_origins: list[str] | None = None

    @field_validator("locale")
    @classmethod
    def _locale(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in ("ar", "en"):
            raise ValueError("locale must be 'ar' or 'en'")
        return normalized

    @field_validator("position")
    @classmethod
    def _position(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower().replace("_", "-")
        if normalized not in ("bottom-right", "bottom-left"):
            raise ValueError("position must be bottom-right or bottom-left")
        return normalized

    @field_validator("primary_color", "text_color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        if value is None:
            return value
        raw = value.strip()
        if not raw.startswith("#") or len(raw) not in (4, 7):
            raise ValueError("color must be a hex value like #0e2f44")
        return raw.lower()


class WidgetBootstrapOut(BaseModel):
    widget_id: uuid.UUID
    title: str
    subtitle: str | None = None
    greeting: str | None = None
    logo_url: str | None = None
    locale: str
    position: str
    primary_color: str
    text_color: str
    mcp_tools_enabled: bool = False
    tool_transport: Literal["fetch_sse"] | None = None
    mcp_public_audience_disclosure: str | None = None


class WidgetMessageIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    # Opaque HMAC token (``uuid.sig``) issued by the API; max fits signed form.
    session_id: str | None = Field(None, max_length=128)


class WidgetMessageOut(BaseModel):
    """Public visitor reply — never includes RAG citations (private knowledge)."""

    answer: str
    session_id: str | None = None


class WidgetMcpTurnIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    client_turn_id: str = Field(
        ...,
        min_length=32,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        repr=False,
    )
    session_token: str | None = Field(None, max_length=2048, repr=False)


class WidgetMcpTurnStatusIn(BaseModel):
    turn_handle: str = Field(
        ...,
        min_length=32,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        repr=False,
    )


class WidgetMcpTurnStatusOut(BaseModel):
    turn_handle: str = Field(repr=False)
    status: str
    answer: str | None = None
    session_token: str | None = Field(None, repr=False)
