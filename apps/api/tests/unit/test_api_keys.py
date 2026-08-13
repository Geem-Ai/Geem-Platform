from __future__ import annotations

import hashlib
import hmac
import logging
from uuid import uuid4

import pytest

from app.api_keys.models import ApiKey
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.service import CreatedApiKey
from app.core.logging import JsonFormatter
from app.api_keys.scopes import DEFAULT_SCOPES, SCOPE_CHAT_WRITE, normalize_scopes
from app.api_keys.security import (
    API_KEY_PREFIX,
    display_prefix,
    generate_api_key_secret,
    hash_api_key,
    hashes_equal,
    last_four,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def test_generate_secret_has_geem_prefix_and_entropy() -> None:
    secret = generate_api_key_secret()
    assert secret.startswith(API_KEY_PREFIX)
    random_part = secret[len(API_KEY_PREFIX) :]
    # token_urlsafe(32) is 32 bytes of entropy; encoded length is ≥ 43.
    assert len(random_part) >= 43
    assert display_prefix(secret).startswith(API_KEY_PREFIX)
    assert last_four(secret) == secret[-4:]
    assert len(display_prefix(secret)) < len(secret)


def test_hash_is_deterministic_hmac_and_differs_by_pepper() -> None:
    secret = generate_api_key_secret()
    a = Settings(_env_file=None, api_key_hash_pepper="pepper-a" + "x" * 24)
    b = Settings(_env_file=None, api_key_hash_pepper="pepper-b" + "x" * 24)
    ha = hash_api_key(secret, settings=a)
    hb = hash_api_key(secret, settings=b)
    assert ha != hb
    assert ha == hash_api_key(secret, settings=a)
    assert secret not in ha
    expected = hmac.new(
        a.effective_api_key_hash_pepper.encode("utf-8"),
        secret.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert ha == expected
    assert hashes_equal(ha, expected)
    assert not hashes_equal(ha, hb)


def test_normalize_scopes_default_unknown_and_duplicates() -> None:
    assert normalize_scopes(None) == list(DEFAULT_SCOPES)
    assert normalize_scopes([]) == list(DEFAULT_SCOPES)
    assert normalize_scopes([SCOPE_CHAT_WRITE]) == [SCOPE_CHAT_WRITE]
    assert normalize_scopes([SCOPE_CHAT_WRITE, SCOPE_CHAT_WRITE]) == [SCOPE_CHAT_WRITE]
    with pytest.raises(AppError) as exc:
        normalize_scopes(["chat:write", "admin:destroy"])
    assert exc.value.category == ErrorCategory.VALIDATION
    assert "admin:destroy" in exc.value.details["unknown_scopes"]


def test_created_api_key_repr_omits_plaintext() -> None:
    secret = "geem_sk_this-is-the-one-time-secret-value"
    row = ApiKey(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Production",
        key_prefix="geem_sk_this-is",
        last_four="alue",
        secret_hash="a" * 64,
        scopes=["chat:write"],
    )
    created = CreatedApiKey(row=row, plaintext=secret)
    dumped = repr(created)
    assert secret not in dumped
    assert "plaintext" not in dumped
    assert created.plaintext == secret


def test_json_formatter_includes_api_key_audit_fields() -> None:
    record = logging.LogRecord(
        name="geem.security",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="api_key.created",
        args=(),
        exc_info=None,
    )
    record.security_event = "api_key.created"
    record.api_key_id = "11111111-1111-1111-1111-111111111111"
    record.workspace_id = "22222222-2222-2222-2222-222222222222"
    record.user_id = "33333333-3333-3333-3333-333333333333"
    record.prefix = "geem_sk_abcd1234"
    record.scopes = ["chat:write"]
    payload = JsonFormatter().format(record)
    assert "11111111-1111-1111-1111-111111111111" in payload
    assert "api_key_id" in payload
    assert "geem_sk_abcd1234" in payload
    assert "chat:write" in payload
    assert "plaintext" not in payload
    assert "secret_hash" not in payload


def test_principal_rate_limit_keys_and_no_secret() -> None:
    principal = ApiKeyPrincipal(
        api_key_id=uuid4(),
        workspace_id=uuid4(),
        scopes=(SCOPE_CHAT_WRITE,),
        key_prefix="geem_sk_abcd1234",
        name="Production",
    )
    assert principal.rate_limit_key == f"api_key:{principal.api_key_id}"
    assert principal.workspace_rate_limit_key("chat") == f"ws:{principal.workspace_id}:chat"
    assert principal.has_scope(SCOPE_CHAT_WRITE)
    assert not principal.has_scope("admin:write")
    dumped = repr(principal)
    assert "geem_sk_" in dumped  # prefix only
    assert "secret" not in dumped.lower() or "secret_hash" not in dumped
