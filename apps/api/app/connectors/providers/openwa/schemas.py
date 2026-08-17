"""Typed OpenWA request/response DTOs — Geem subset only (Swagger 0.15.0)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenWASessionStatus(str, Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    QR_READY = "qr_ready"
    AUTHENTICATING = "authenticating"
    READY = "ready"
    DISCONNECTED = "disconnected"
    ACTION_REQUIRED = "action_required"
    FAILED = "failed"


KNOWN_OPENWA_SESSION_STATUSES: frozenset[str] = frozenset(
    s.value for s in OpenWASessionStatus
)

# Events Geem registers (never "*").
OPENWA_WEBHOOK_EVENTS: tuple[str, ...] = (
    "message.received",
    "session.status",
    "session.authenticated",
    "session.disconnected",
    "session.restriction",
)

OPENWA_TEXT_MAX_CHARS = 4096
OPENWA_SESSION_NAME_MIN = 3
OPENWA_SESSION_NAME_MAX = 50


class OpenWACreateSessionRequest(BaseModel):
    name: str = Field(min_length=OPENWA_SESSION_NAME_MIN, max_length=OPENWA_SESSION_NAME_MAX)


class OpenWASession(BaseModel):
    """Raw OpenWA session object — unknown statuses preserved via provider_status."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    status: str
    phone: str | None = None
    pushName: str | None = None
    connectedAt: str | None = None
    lastActive: str | None = None
    lastError: str | None = None
    engineLoaded: bool | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    restriction: dict[str, Any] | None = None

    @property
    def known_status(self) -> OpenWASessionStatus | None:
        try:
            return OpenWASessionStatus(self.status)
        except ValueError:
            return None


class OpenWAQrResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    qrCode: str
    status: str


class OpenWAPairingCodeRequest(BaseModel):
    phoneNumber: str = Field(min_length=6, max_length=15)


class OpenWAPairingCodeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pairingCode: str
    status: str


class OpenWACreateWebhookRequest(BaseModel):
    url: str
    events: list[str] = Field(default_factory=lambda: list(OPENWA_WEBHOOK_EVENTS))
    secret: str | None = None
    retryCount: int | None = Field(default=3, ge=0, le=5)


class OpenWAUpdateWebhookRequest(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    secret: str | None = None
    active: bool | None = None
    retryCount: int | None = Field(default=None, ge=0, le=5)


class OpenWAWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    sessionId: str
    url: str
    events: list[str]
    active: bool
    retryCount: float | int = 0
    createdAt: str | None = None
    updatedAt: str | None = None


class OpenWASendTextRequest(BaseModel):
    chatId: str
    text: str = Field(max_length=OPENWA_TEXT_MAX_CHARS)
    linkPreview: bool | None = False


class OpenWASendTextResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    messageId: str
    timestamp: float | int | None = None
