"""Phase 9F — OpenWA webhook verification helpers."""

from __future__ import annotations

import hashlib
import hmac
import json

from app.connectors.providers.openwa.webhook import (
    extract_idempotency_key,
    verify_openwa_signature,
)


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_verify_openwa_signature_accepts_valid_hmac() -> None:
    body = json.dumps({"event": "message.received"}).encode("utf-8")
    secret = "openwa-secret"

    assert verify_openwa_signature(
        raw_body=body,
        signature=_signature(secret, body),
        secret=secret,
    )


def test_verify_openwa_signature_rejects_invalid_hmac() -> None:
    body = b'{"event":"message.received"}'

    assert not verify_openwa_signature(
        raw_body=body,
        signature="sha256=deadbeef",
        secret="openwa-secret",
    )


def test_extract_idempotency_key_prefers_header_then_body() -> None:
    assert (
        extract_idempotency_key(
            headers={"x-openwa-idempotency-key": "evt-1"},
            payload={"idempotencyKey": "evt-2"},
        )
        == "evt-1"
    )
    assert (
        extract_idempotency_key(
            headers={},
            payload={"idempotency_key": "evt-3"},
        )
        == "evt-3"
    )
