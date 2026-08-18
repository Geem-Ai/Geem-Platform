"""Phase 10A — invitation tokens, status, email adapters, DTO safety."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.notifications.console import ConsoleEmailProvider
from app.notifications.factory import build_email_provider
from app.notifications.protocol import EmailMessage
from app.workspaces.invitation_schemas import InvitationOut
from app.workspaces.invitation_tokens import (
    generate_invitation_token,
    hash_invitation_token,
    hashes_equal,
)
from app.workspaces.invitation_urls import invitation_accept_url
from app.workspaces.models import InvitationStatus, WorkspaceInvitation


def _local_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, app_env="test", **kwargs)


def test_invitation_token_hash_is_hmac_not_raw() -> None:
    settings = _local_settings(jwt_secret="test-jwt-secret-not-for-production")
    raw = generate_invitation_token()
    digest = hash_invitation_token(raw, settings=settings)
    assert digest != raw
    assert raw not in digest
    assert len(digest) == 64
    assert hashes_equal(digest, hash_invitation_token(raw, settings=settings))
    other = hash_invitation_token(generate_invitation_token(), settings=settings)
    assert not hashes_equal(digest, other)


def test_invitation_hash_uses_invite_namespace() -> None:
    settings = _local_settings(jwt_secret="test-jwt-secret-not-for-production")
    raw = "same-secret"
    invite = hash_invitation_token(raw, settings=settings)
    from app.api_keys.security import hash_api_key

    api = hash_api_key(raw, settings=settings)
    assert invite != api


def test_invitation_accept_url_uses_workspace_web_url() -> None:
    settings = _local_settings(workspace_web_url="https://app.example.test/")
    url = invitation_accept_url("abc+token", settings=settings)
    assert url.startswith("https://app.example.test/invitations/accept?")
    assert "token=abc%2Btoken" in url or "token=abc+token" in url


def test_invitation_accept_url_requires_frontend_base_in_non_local() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        workspace_web_url="",
        api_key_hash_pepper="b" * 40,
    )
    with pytest.raises(AppError) as exc:
        invitation_accept_url("tok", settings=settings)
    assert exc.value.category == ErrorCategory.EMAIL_DELIVERY_FAILED


def test_console_provider_forbidden_outside_local() -> None:
    production = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        api_key_hash_pepper="b" * 40,
        email_provider="console",
    )
    with pytest.raises(RuntimeError, match="ConsoleEmailProvider"):
        ConsoleEmailProvider(production)
    with pytest.raises(RuntimeError, match="local"):
        build_email_provider(production)


def test_console_provider_sends_without_raising() -> None:
    settings = _local_settings()
    provider = ConsoleEmailProvider(settings)
    provider.send(EmailMessage(to="a@example.com", subject="Hi", text_body="body"))


def test_smtp_starttls_uses_verified_context(monkeypatch) -> None:
    import ssl

    from app.notifications.smtp import SmtpEmailProvider

    captured: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None) -> None:
            captured["host"] = host
            captured["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, *, context=None):
            captured["context"] = context

        def login(self, user, password):
            captured["login"] = (user, password)

        def send_message(self, msg):
            captured["sent"] = True

    monkeypatch.setattr("app.notifications.smtp.smtplib.SMTP", FakeSMTP)
    settings = _local_settings(
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@geem.ai",
        smtp_username="mailer",
        smtp_password="secret",
        smtp_use_tls=True,
    )
    SmtpEmailProvider(settings).send(
        EmailMessage(to="a@example.com", subject="Invite", text_body="body")
    )
    ctx = captured["context"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert captured["sent"] is True
    assert captured["login"] == ("mailer", "secret")


def test_smtp_starttls_can_skip_certificate_verification(monkeypatch) -> None:
    import ssl

    from app.notifications.smtp import SmtpEmailProvider

    captured: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, *, context=None):
            captured["context"] = context

        def login(self, user, password):
            pass

        def send_message(self, msg):
            captured["sent"] = True

    monkeypatch.setattr("app.notifications.smtp.smtplib.SMTP", FakeSMTP)
    settings = _local_settings(
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@geem.ai",
        smtp_use_tls=True,
        smtp_tls_verify=False,
    )
    SmtpEmailProvider(settings).send(
        EmailMessage(to="a@example.com", subject="Invite", text_body="body")
    )
    ctx = captured["context"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False
    assert captured["sent"] is True


def test_smtp_provider_rejects_cleartext_outside_local() -> None:
    from app.notifications.smtp import SmtpEmailProvider

    production = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        api_key_hash_pepper="b" * 40,
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@geem.ai",
        smtp_use_tls=False,
    )
    with pytest.raises(AppError) as exc:
        SmtpEmailProvider(production)
    assert exc.value.category == ErrorCategory.EMAIL_DELIVERY_FAILED


def test_smtp_provider_rejects_unverified_tls_outside_local() -> None:
    from app.notifications.smtp import SmtpEmailProvider

    production = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
        api_key_hash_pepper="b" * 40,
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@geem.ai",
        smtp_use_tls=True,
        smtp_tls_verify=False,
    )
    with pytest.raises(AppError) as exc:
        SmtpEmailProvider(production)
    assert exc.value.category == ErrorCategory.EMAIL_DELIVERY_FAILED


def test_invitation_out_schema_excludes_secrets() -> None:
    fields = InvitationOut.model_fields
    assert "token_hash" not in fields
    assert "token" not in fields
    dumped = InvitationOut.model_json_schema()
    blob = str(dumped).lower()
    assert "token_hash" not in blob


def test_derived_invitation_status() -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    row = WorkspaceInvitation(
        email="a@example.com",
        role="member",
        token_hash="a" * 64,
        expires_at=now + timedelta(hours=1),
    )
    assert row.derived_status(now=now) == InvitationStatus.PENDING
    row.accepted_at = now
    assert row.derived_status(now=now) == InvitationStatus.ACCEPTED
    row.accepted_at = None
    row.revoked_at = now
    assert row.derived_status(now=now) == InvitationStatus.REVOKED
    row.revoked_at = None
    row.expires_at = now - timedelta(seconds=1)
    assert row.derived_status(now=now) == InvitationStatus.EXPIRED


def test_invitation_email_template_is_bilingual_and_escapes_html() -> None:
    from datetime import datetime, timezone

    from app.workspaces.invitation_email import render_invitation_email

    content = render_invitation_email(
        workspace_name='Acme <script>alert("x")</script>',
        role="admin",
        accept_url="https://app.example.test/invitations/accept?token=abc+token",
        expires_at=datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
        invitee_email="join@example.com",
        inviter_email="owner@example.com",
    )
    assert "Acme <script>" in content.subject
    assert "Accept: https://app.example.test/invitations/accept?token=abc+token" in content.text_body
    assert "Role: Admin" in content.text_body
    assert "الدور: مشرف" in content.text_body
    assert "join@example.com" in content.text_body
    assert "<script>" not in content.html_body
    assert "Acme &lt;script&gt;" in content.html_body
    assert "Accept invitation" in content.html_body
    assert "قبول الدعوة" in content.html_body
    assert 'href="https://app.example.test/invitations/accept?token=abc+token"' in content.html_body
    assert "owner@example.com" in content.html_body
    assert 'src="https://geem.ai/assets/geem-avatar.webp"' in content.html_body
    assert 'href="https://geem.ai"' in content.html_body
    assert 'href="https://geem.ai/support"' in content.html_body
    assert "Website: https://geem.ai" in content.text_body
    assert "Support: https://geem.ai/support" in content.text_body
