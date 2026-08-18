"""Outbound notification adapters (email). Domain services depend on protocols only."""

from app.notifications.factory import build_email_provider, get_email_provider
from app.notifications.protocol import EmailMessage, EmailProvider

__all__ = [
    "EmailMessage",
    "EmailProvider",
    "build_email_provider",
    "get_email_provider",
]
