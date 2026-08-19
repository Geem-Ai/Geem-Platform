"""Optional SMTP adapter. Credentials must never appear in API responses or logs."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage as StdlibEmailMessage
from email.utils import formataddr

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.notifications.protocol import EmailMessage

logger = logging.getLogger("geem.email.smtp")


class SmtpEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self._host = (settings.smtp_host or "").strip()
        self._port = int(settings.smtp_port)
        self._username = (settings.smtp_username or "").strip()
        self._password = settings.smtp_password or ""
        self._from_email = (settings.smtp_from_email or "").strip()
        self._from_name = (settings.smtp_from_name or "Geem").strip() or "Geem"
        self._use_tls = bool(settings.smtp_use_tls)
        self._tls_verify = bool(settings.smtp_tls_verify)
        self._timeout = float(settings.smtp_timeout_seconds)
        self._is_local = settings.is_local
        if not self._host or not self._from_email:
            raise AppError(
                ErrorCategory.EMAIL_DELIVERY_FAILED,
                "SMTP is not configured.",
            )
        if not self._use_tls and not self._is_local:
            raise AppError(
                ErrorCategory.EMAIL_DELIVERY_FAILED,
                "SMTP TLS is required outside local/test.",
            )

    def send(self, message: EmailMessage) -> None:
        payload = StdlibEmailMessage()
        payload["Subject"] = message.subject
        payload["From"] = formataddr((self._from_name, self._from_email))
        payload["To"] = message.to
        payload.set_content(message.text_body, charset="utf-8")
        if message.html_body:
            payload.add_alternative(message.html_body, subtype="html", charset="utf-8")
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls:
                    smtp.starttls(context=self._ssl_context())
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(payload)
        except AppError:
            raise
        except Exception as exc:
            logger.warning(
                "email.smtp_failed",
                extra={"smtp_host": self._host, "smtp_port": self._port},
            )
            raise AppError(
                ErrorCategory.EMAIL_DELIVERY_FAILED,
                "Unable to send email.",
                retryable=True,
            ) from exc

    def _ssl_context(self) -> ssl.SSLContext:
        if self._tls_verify:
            return ssl.create_default_context()
        logger.warning(
            "email.smtp_tls_verify_disabled",
            extra={"smtp_host": self._host, "smtp_port": self._port},
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
