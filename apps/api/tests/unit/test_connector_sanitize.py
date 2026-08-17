"""Unit tests for connector public error sanitization."""

from __future__ import annotations

from app.connectors.sanitize import looks_technical, sanitize_error_message


def test_sanitize_keeps_friendly_message() -> None:
    assert sanitize_error_message("Missing credentials.") == "Missing credentials."


def test_sanitize_redacts_bearer_token() -> None:
    raw = "Authorization: Bearer ya29.a0AfH6SMC-secret-token"
    out = sanitize_error_message(raw)
    assert out is not None
    assert "ya29" not in out
    assert "secret" not in out.lower() or "[redacted]" in out


def test_sanitize_replaces_sqlalchemy_dump() -> None:
    raw = (
        "(psycopg.errors.CheckViolation) new row for relation "
        '"storage_usage_events" violates check constraint '
        '"ck_storage_usage_events_reason" DETAIL: Failing row contains '
        "(09874578-b779-488e-8440-a011315a63f9). [SQL: INSERT INTO "
        "storage_usage_events ...]"
    )
    assert looks_technical(raw) is True
    assert sanitize_error_message(raw) == "Something went wrong. Please try again."


def test_sanitize_replaces_long_traceback() -> None:
    raw = "x" * 300
    assert looks_technical(raw) is True
    assert sanitize_error_message(raw) == "Something went wrong. Please try again."


def test_sanitize_none_and_blank() -> None:
    assert sanitize_error_message(None) is None
    assert sanitize_error_message("   ") is None
