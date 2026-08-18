"""Local/test email adapter. May print invitation URLs that contain raw tokens.

This adapter is forbidden outside local/test. ``assert_secure_settings`` and
``build_email_provider`` both refuse ``EMAIL_PROVIDER=console`` in non-local env.
"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.notifications.protocol import EmailMessage

logger = logging.getLogger("geem.email.console")


class ConsoleEmailProvider:
    """Writes the message to the process log. Not a production delivery channel."""

    def __init__(self, settings: Settings) -> None:
        if not settings.is_local:
            raise RuntimeError(
                "ConsoleEmailProvider cannot be used outside local/test. "
                "It may log invitation acceptance URLs that contain raw tokens. "
                "Set EMAIL_PROVIDER=smtp in non-local environments."
            )
        self._settings = settings

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email.console to=%s subject=%s\n%s",
            message.to,
            message.subject,
            message.text_body,
        )
