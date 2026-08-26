"""Request-validation responses must never echo rejected request material."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.common.validation_errors import public_validation_errors
from app.mcp.schemas import McpServerCreateIn


def _safe_mcp_errors(body: dict) -> list[dict]:
    with pytest.raises(ValidationError) as raised:
        McpServerCreateIn.model_validate(body)
    return public_validation_errors(raised.value.errors())


def test_static_secret_is_absent_from_public_validation_details() -> None:
    secret = "static-secret-must-not-leak\nnext-header"
    errors = _safe_mcp_errors(
        {
            "display_name": "Tools",
            "server_url": "https://tools.example.com/mcp",
            "auth": {
                "mode": "static",
                "header_name": "Authorization",
                "secret": secret,
            },
        }
    )

    encoded = json.dumps(errors, default=str)
    assert secret not in encoded
    assert errors == [
        {
            "type": "value_error",
            "loc": ("auth", "static", "secret"),
            "msg": "Value error, Static MCP credential is invalid.",
        }
    ]


def test_oauth_model_error_cannot_echo_nested_client_secret() -> None:
    secret = "oauth-client-secret-must-not-leak\nnext-header"
    errors = _safe_mcp_errors(
        {
            "display_name": "Tools",
            "server_url": "https://tools.example.com/mcp",
            "auth": {
                "mode": "oauth",
                "strategy": "pre_registered",
                "client_id": "client-id",
                "client_secret": secret,
                "scopes": ["tools.read", "tools.write"],
            },
        }
    )

    encoded = json.dumps(errors, default=str)
    assert secret not in encoded
    assert all("input" not in error and "ctx" not in error for error in errors)
    assert errors[0]["loc"] == ("auth", "oauth")


def test_nested_input_and_exception_context_are_dropped_fail_closed() -> None:
    secret = "deep-list-secret-must-not-leak"
    errors = public_validation_errors(
        [
            {
                "type": "value_error",
                "loc": ("body", "auth"),
                "msg": "Invalid authentication payload.",
                "input": {"nested": [{"client_secret": secret}]},
                "ctx": {"error": ValueError(secret), "items": [secret]},
            }
        ]
    )

    encoded = json.dumps(errors, default=str)
    assert secret not in encoded
    assert errors == [
        {
            "type": "value_error",
            "loc": ("body", "auth"),
            "msg": "Invalid authentication payload.",
        }
    ]


def test_normal_validation_keeps_type_location_and_message() -> None:
    errors = _safe_mcp_errors(
        {
            "display_name": "",
            "server_url": "https://tools.example.com/mcp",
            "auth": {"mode": "none"},
        }
    )

    assert errors == [
        {
            "type": "string_too_short",
            "loc": ("display_name",),
            "msg": "String should have at least 1 character",
        }
    ]
