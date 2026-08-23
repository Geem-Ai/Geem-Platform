"""Allowlist + denylist sanitizer for audit metadata.

Never persist secrets. Prefer explicit allowlists at call sites; the denylist
is a fail-safe if a caller passes an unexpected key.
"""

from __future__ import annotations

from typing import Any

# Keys that must never appear in persisted audit metadata (case-insensitive).
BLOCKED_METADATA_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "current_password",
        "new_password",
        "old_password",
        "token",
        "raw_token",
        "refresh_token",
        "refreshtoken",
        "access_token",
        "accesstoken",
        "id_token",
        "jwt",
        "authorization",
        "cookie",
        "cookies",
        "secret",
        "secrets",
        "secret_hash",
        "plaintext",
        "api_key",
        "api_key_secret",
        "api_key_hash_pepper",
        "invitation_token",
        "invitation_token_hash_pepper",
        "token_hash",
        "code_verifier",
        "pkce",
        "credentials",
        "credentials_encrypted",
        "sync_state_encrypted",
        "config_encrypted",
        "webhook_secret",
        "webhook_routing_token",
        "webhook_routing_token_encrypted",
        "server_key",
        "client_key",
        "client_secret",
        "clickpay_server_key",
        "profile_id",
        "smtp_password",
        "smtp_username",
        "openwa_api_key",
        "delta_link",
        "sync_cursor",
        "system_instructions",
        "authorization_header",
        "body",
        "request_body",
        "headers",
        "cookie_header",
    }
)

_MAX_STRING_LEN = 500
_MAX_LIST_LEN = 50
_MAX_DEPTH = 4

# Safe keys for Platform Admin audit read views (unknown top-level keys are dropped).
READ_TIME_AUDIT_METADATA_ALLOWLIST = frozenset(
    {
        "action",
        "after",
        "after_status",
        "already_member",
        "amount",
        "app_id",
        "app_slug",
        "before",
        "before_status",
        "billing_type",
        "category_id",
        "code",
        "connector_key",
        "document_id",
        "expert_id",
        "failure",
        "gateway_config_id",
        "installation_id",
        "job_id",
        "kind",
        "knowledge_mode",
        "license_id",
        "message",
        "mode",
        "name",
        "new_status",
        "new_visibility",
        "old_status",
        "old_visibility",
        "permission_keys",
        "permissions_changed",
        "plan_id",
        "prefix",
        "price_amount",
        "reason",
        "reinstall",
        "reused",
        "role_id",
        "scopes",
        "slug",
        "status",
        "subscription_id",
        "summary",
        "system_key",
        "target_user_id",
        "test_mode",
        "workspace_id",
        "workspace_slug",
    }
)


def _norm_key(key: str) -> str:
    return key.lower().replace("-", "_")


def sanitize_audit_metadata(
    metadata: dict[str, Any] | None,
    *,
    allowlist: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe metadata dict with secrets stripped.

    Sanitizer failures must not raise to callers — they return ``{}``.
    """
    try:
        if not metadata:
            return {}
        return _scrub(metadata, depth=0, allowlist=allowlist)
    except Exception:  # noqa: BLE001 — never fail a mutation on metadata parsing
        return {}


def redact_audit_metadata_for_read(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Defensive read-time redaction for historical audit rows."""
    return sanitize_audit_metadata(
        metadata,
        allowlist=READ_TIME_AUDIT_METADATA_ALLOWLIST,
    )


def _scrub(value: Any, *, depth: int, allowlist: frozenset[str] | None) -> Any:
    if depth > _MAX_DEPTH:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, raw_val in value.items():
            key = str(raw_key)
            if _norm_key(key) in BLOCKED_METADATA_KEYS:
                continue
            if allowlist is not None and key not in allowlist:
                continue
            cleaned = _scrub(raw_val, depth=depth + 1, allowlist=None)
            if cleaned is not None:
                out[key] = cleaned
        return out
    if isinstance(value, (list, tuple)):
        return [
            _scrub(item, depth=depth + 1, allowlist=None)
            for item in list(value)[:_MAX_LIST_LEN]
        ]
    if isinstance(value, str):
        return value[:_MAX_STRING_LEN]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_STRING_LEN]
