"""Select an EmailProvider from settings. Console cannot be chosen in production."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.notifications.console import ConsoleEmailProvider
from app.notifications.protocol import EmailProvider
from app.notifications.smtp import SmtpEmailProvider


def build_email_provider(settings: Settings | None = None) -> EmailProvider:
    cfg = settings or get_settings()
    kind = (cfg.email_provider or "").strip().lower() or "console"
    if kind == "console":
        return ConsoleEmailProvider(cfg)
    if kind == "smtp":
        return SmtpEmailProvider(cfg)
    raise AppError(
        ErrorCategory.VALIDATION,
        "Unknown email provider.",
        details={"email_provider": kind},
    )


def get_email_provider() -> EmailProvider:
    """FastAPI dependency. Tests override this to inject a recording adapter."""
    return build_email_provider()
