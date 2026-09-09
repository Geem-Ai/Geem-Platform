"""Recording / failing email adapters for tests. Never used in production."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

from app.notifications.protocol import EmailMessage


@dataclass
class RecordingEmailProvider:
    messages: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


@dataclass
class FailingEmailProvider:
    error: Exception = field(default_factory=lambda: RuntimeError("smtp unavailable"))

    def send(self, message: EmailMessage) -> None:
        raise self.error


def deliver_email_tasks_inline(monkeypatch, provider) -> None:
    """Run the notification tasks in-process with ``provider``.

    Production hands verification and reset mail to the worker, so tests drive
    the real task body instead of a live broker.
    """
    from app.notifications import enqueue as email_enqueue
    from app.notifications import tasks as email_tasks

    monkeypatch.setattr(
        email_tasks, "build_email_provider", lambda settings=None: provider
    )
    monkeypatch.setattr(
        email_enqueue,
        "enqueue_email_verification",
        lambda user_id: email_tasks.send_email_verification.apply(args=[str(user_id)]),
    )
    monkeypatch.setattr(
        email_enqueue,
        "enqueue_password_reset",
        lambda user_id: email_tasks.send_password_reset.apply(args=[str(user_id)]),
    )


def token_from_invite_email(message: EmailMessage) -> str:
    url = url_from_invite_email(message)
    token = parse_qs(urlparse(url).query).get("token", [""])[0]
    if not token:
        raise AssertionError("invitation email Accept URL is missing a token")
    return unquote(token)


def url_from_invite_email(message: EmailMessage) -> str:
    blobs = [message.text_body]
    if message.html_body:
        blobs.append(message.html_body)
    for blob in blobs:
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("Accept: "):
                return stripped.split(" ", 1)[1].strip()
            if "/invitations/accept" in stripped and "token=" in stripped:
                start = stripped.find("http")
                if start < 0:
                    continue
                candidate = stripped[start:].split('"', 1)[0].split("<", 1)[0].strip()
                if "token=" in candidate:
                    return candidate
    raise AssertionError("invitation email is missing an Accept URL")


def token_from_verify_email(message: EmailMessage) -> str:
    url = url_from_verify_email(message)
    token = parse_qs(urlparse(url).query).get("token", [""])[0]
    if not token:
        raise AssertionError("verification email URL is missing a token")
    return unquote(token)


def url_from_verify_email(message: EmailMessage) -> str:
    blobs = [message.text_body]
    if message.html_body:
        blobs.append(message.html_body)
    for blob in blobs:
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("Verify your email:"):
                continue
            if "/verify-email" in stripped and "token=" in stripped:
                start = stripped.find("http")
                if start < 0:
                    continue
                candidate = stripped[start:].split('"', 1)[0].split("<", 1)[0].strip()
                if "token=" in candidate:
                    return candidate
    raise AssertionError("verification email is missing a verify URL")


def token_from_reset_email(message: EmailMessage) -> str:
    url = url_from_reset_email(message)
    token = parse_qs(urlparse(url).query).get("token", [""])[0]
    if not token:
        raise AssertionError("password reset email URL is missing a token")
    return unquote(token)


def url_from_reset_email(message: EmailMessage) -> str:
    blobs = [message.text_body]
    if message.html_body:
        blobs.append(message.html_body)
    for blob in blobs:
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("Reset your password:"):
                continue
            if "/reset-password" in stripped and "token=" in stripped:
                start = stripped.find("http")
                if start < 0:
                    continue
                candidate = stripped[start:].split('"', 1)[0].split("<", 1)[0].strip()
                if "token=" in candidate:
                    return candidate
    raise AssertionError("password reset email is missing a reset URL")
