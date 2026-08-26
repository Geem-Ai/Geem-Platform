"""Strict request and redacted response schemas for MCP connections and grants."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.mcp.constants import (
    MCP_FORBIDDEN_AUTH_HEADERS,
    MCP_STATIC_HEADER_ALLOWLIST,
)

_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class McpNoAuthIn(_StrictModel):
    mode: Literal["none"]


class McpStaticAuthIn(_StrictModel):
    mode: Literal["static"]
    header_name: str = Field(default="Authorization", min_length=1, max_length=64)
    secret: SecretStr = Field(min_length=1, max_length=8_192)

    @field_validator("header_name")
    @classmethod
    def _validate_header_name(cls, value: str) -> str:
        cleaned = value.strip()
        lowered = cleaned.casefold()
        if (
            not _HEADER_NAME.fullmatch(cleaned)
            or lowered in MCP_FORBIDDEN_AUTH_HEADERS
            or lowered not in MCP_STATIC_HEADER_ALLOWLIST
            or lowered.startswith("mcp-")
        ):
            raise ValueError("Static MCP authentication header is not allowed.")
        return cleaned

    @field_validator("secret")
    @classmethod
    def _validate_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.strip() or "\r" in raw or "\n" in raw:
            raise ValueError("Static MCP credential is invalid.")
        return SecretStr(raw.strip())


class McpOAuthAuthIn(_StrictModel):
    mode: Literal["oauth"]
    strategy: Literal["cimd", "pre_registered", "dynamic_registration"]
    expected_issuer: str | None = Field(default=None, max_length=2_048)
    client_id: str | None = Field(default=None, max_length=512)
    client_secret: SecretStr | None = Field(default=None, max_length=8_192)
    scopes: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value:
            scope = item.strip()
            if not scope or len(scope) > 256 or any(ch.isspace() for ch in scope):
                raise ValueError("OAuth scopes must be non-empty tokens.")
            if scope not in out:
                out.append(scope)
        return out

    @model_validator(mode="after")
    def _strategy_requirements(self) -> McpOAuthAuthIn:
        if self.strategy == "pre_registered" and not self.client_id:
            raise ValueError("pre_registered OAuth requires client_id.")
        if self.client_secret is not None:
            raw = self.client_secret.get_secret_value()
            if not raw.strip() or "\r" in raw or "\n" in raw:
                raise ValueError("OAuth client_secret is invalid.")
        return self


class McpOAuthStartIn(_StrictModel):
    return_path: str | None = Field(default=None, max_length=512)


class McpOAuthReauthorizeIn(McpOAuthStartIn):
    scopes: list[str] | None = Field(default=None, max_length=64)

    @field_validator("scopes")
    @classmethod
    def _validate_optional_scopes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return McpOAuthAuthIn._validate_scopes(value)


class McpOAuthStartOut(BaseModel):
    authorization_url: str


class McpAuthStatusOut(BaseModel):
    connection_id: uuid.UUID
    auth_mode: str
    strategy: str | None = None
    status: str
    issuer: str | None = None
    resource_url: str | None = None
    external_identity_label: str | None = None
    credential_epoch: int
    reauthorization_required: bool
    redacted_credential: str | None = None


McpAuthIn = Annotated[
    McpNoAuthIn | McpStaticAuthIn | McpOAuthAuthIn,
    Field(discriminator="mode"),
]


class McpServerCreateIn(_StrictModel):
    display_name: str = Field(min_length=1, max_length=200)
    server_url: str = Field(min_length=1, max_length=2_048)
    resource_uri: str | None = Field(default=None, max_length=2_048)
    auth: McpAuthIn

    @field_validator("display_name")
    @classmethod
    def _clean_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("display_name is required.")
        return cleaned


class McpServerAuthOut(BaseModel):
    mode: str
    strategy: str | None = None
    header_name: str | None = None
    secret_hint: str | None = None
    issuer_host: str | None = None
    reauthorization_required: bool = False


class McpServerOut(BaseModel):
    id: uuid.UUID
    display_name: str
    endpoint_host: str | None = None
    status: str
    health: str
    auth: McpServerAuthOut
    protocol_version: str | None = None
    session_mode: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    credential_epoch: int
    external_identity_label: str | None = None
    inventory_refreshed_at: datetime | None = None
    discovered_tool_count: int = 0
    created_at: datetime
    updated_at: datetime


class McpServerListOut(BaseModel):
    items: list[McpServerOut]
    total: int
    limit: int
    offset: int


class McpDiscoverOut(BaseModel):
    server: McpServerOut
    generation: int
    tools_seen: int
    tools_created: int
    tools_updated: int
    tools_withdrawn: int
    complete: bool
    warnings: list[str] = Field(default_factory=list)


class McpToolOut(BaseModel):
    id: uuid.UUID
    app_connection_id: uuid.UUID
    tool_name: str
    llm_tool_name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any]
    protocol_version: str
    compatibility_status: str
    compatibility_reason: str | None = None
    classification: str
    definition_hash: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    discovery_generation: int


class McpToolListOut(BaseModel):
    items: list[McpToolOut]
    total: int
    limit: int
    offset: int


class McpToolClassificationIn(_StrictModel):
    classification: Literal["read_only", "write", "unknown"]


class McpGrantCreateIn(_StrictModel):
    tool_id: uuid.UUID
    allow_workspace_chat: bool = True
    allow_public_api: bool = False
    unattended_write_allowed: bool = False
    outbound_data_acknowledged: bool = False
    unattended_write_risk_acknowledged: bool = False


class McpToolGrantOut(BaseModel):
    id: uuid.UUID
    expert_id: uuid.UUID
    app_connection_id: uuid.UUID
    tool_id: uuid.UUID
    tool_name: str
    llm_tool_name: str
    connection_display_name: str
    state: str
    approved_definition_hash: str | None = None
    approved_classification: str | None = None
    approved_credential_epoch: int | None = None
    allow_workspace_chat: bool
    allow_public_api: bool
    unattended_write_allowed: bool
    outbound_data_acknowledged_at: datetime | None = None
    unattended_write_acknowledged_at: datetime | None = None
    approved_by_user_id: uuid.UUID | None = None
    approved_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class McpToolGrantListOut(BaseModel):
    items: list[McpToolGrantOut]


__all__ = [
    "McpAuthIn",
    "McpDiscoverOut",
    "McpGrantCreateIn",
    "McpNoAuthIn",
    "McpAuthStatusOut",
    "McpOAuthReauthorizeIn",
    "McpOAuthStartIn",
    "McpOAuthStartOut",
    "McpOAuthAuthIn",
    "McpServerAuthOut",
    "McpServerCreateIn",
    "McpServerListOut",
    "McpServerOut",
    "McpStaticAuthIn",
    "McpToolClassificationIn",
    "McpToolGrantListOut",
    "McpToolGrantOut",
    "McpToolListOut",
    "McpToolOut",
]
