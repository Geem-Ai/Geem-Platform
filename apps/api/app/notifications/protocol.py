"""Email delivery contract. Domain services must not know console vs SMTP vs ESP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


@runtime_checkable
class EmailProvider(Protocol):
    def send(self, message: EmailMessage) -> None: ...
