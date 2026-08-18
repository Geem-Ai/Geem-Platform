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
