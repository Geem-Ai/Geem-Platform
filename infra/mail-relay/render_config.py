"""Render the mail-relay submission account from the environment and start msmtpd.

The application tier has no public default route, so it submits mail in the
clear to this relay over an internal network and the relay owns the only
credentialed TLS hop to the upstream submission host. Every value is validated
before it reaches the configuration file, and the password is never written to
disk: msmtp reads it back through ``passwordeval`` at send time.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import shutil


DEFAULT_OUTPUT = Path("/run/geem-msmtprc")
# msmtp spools each message through libc ``tmpfile()``, which always uses /tmp
# and ignores TMPDIR, so the image needs a writable /tmp tmpfs to send at all.
SPOOL_DIR = Path("/tmp")
TLS_TRUST_FILE = "/etc/ssl/certs/ca-certificates.crt"
LISTEN_INTERFACE = "0.0.0.0"
LISTEN_PORT = 25
ACCOUNT_NAME = "upstream"
PASSWORD_VARIABLE = "MAIL_RELAY_UPSTREAM_PASSWORD"
# Submission ports only. Port 25 upstream would be unauthenticated relaying and
# 465/587 are the only ports the reviewed providers accept credentials on.
SUBMISSION_PORTS = (587, 465)
HOSTNAME_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
MAILBOX = re.compile(r"^[^\s@,<>\"]+@[^\s@,<>\"]+\.[a-z]{2,}$", re.IGNORECASE)


class MailRelayConfigError(RuntimeError):
    """Raised when the relay configuration cannot be rendered safely."""


def require_value(name: str) -> str:
    """Read one required setting and reject anything a config file cannot hold."""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        raise MailRelayConfigError(f"{name} is required")
    value = raw.strip()
    if any(character in value for character in ("\n", "\r", "\0")):
        raise MailRelayConfigError(f"{name} contains an unsupported control character")
    return value


def parse_host(value: str) -> str:
    if value.casefold() in {"localhost", "localhost.localdomain"}:
        raise MailRelayConfigError(
            "MAIL_RELAY_UPSTREAM_HOST must be the external submission host"
        )
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise MailRelayConfigError(
                "MAIL_RELAY_UPSTREAM_HOST must be the external submission host"
            )
        return value
    if len(value) > 253 or "." not in value:
        raise MailRelayConfigError("MAIL_RELAY_UPSTREAM_HOST is not a resolvable host")
    if not all(HOSTNAME_LABEL.match(label) for label in value.rstrip(".").split(".")):
        raise MailRelayConfigError("MAIL_RELAY_UPSTREAM_HOST is not a resolvable host")
    return value


def parse_port(value: str) -> int:
    try:
        port = int(value, 10)
    except ValueError as exc:
        raise MailRelayConfigError(
            "MAIL_RELAY_UPSTREAM_PORT must be a submission port"
        ) from exc
    if port not in SUBMISSION_PORTS:
        raise MailRelayConfigError(
            "MAIL_RELAY_UPSTREAM_PORT must be a submission port"
        )
    return port


def parse_mailbox(name: str, value: str) -> str:
    if not MAILBOX.match(value):
        raise MailRelayConfigError(f"{name} must be a single mail address")
    return value


def render_config(
    *,
    host: str,
    port: int,
    username: str,
    from_address: str,
) -> str:
    """Build the msmtp account. Port 465 is implicit TLS, 587 negotiates it."""

    starttls = "on" if port == 587 else "off"
    return "\n".join(
        (
            "# Rendered by the Geem mail relay. Do not edit; it is recreated at start.",
            "defaults",
            "logfile -",
            f"tls_trust_file {TLS_TRUST_FILE}",
            "",
            f"account {ACCOUNT_NAME}",
            f"host {host}",
            f"port {port}",
            f"from {from_address}",
            "auth on",
            f"user {username}",
            f"passwordeval printenv {PASSWORD_VARIABLE}",
            "tls on",
            f"tls_starttls {starttls}",
            "tls_certcheck on",
            "",
            f"account default : {ACCOUNT_NAME}",
            "",
        )
    )


def write_config(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o400)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_config_from_environment() -> str:
    host = parse_host(require_value("MAIL_RELAY_UPSTREAM_HOST"))
    port = parse_port(require_value("MAIL_RELAY_UPSTREAM_PORT"))
    username = require_value("MAIL_RELAY_UPSTREAM_USERNAME")
    from_address = parse_mailbox(
        "MAIL_RELAY_UPSTREAM_FROM", require_value("MAIL_RELAY_UPSTREAM_FROM")
    )
    require_value(PASSWORD_VARIABLE)
    return render_config(
        host=host,
        port=port,
        username=username,
        from_address=from_address,
    )


def resolve_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MailRelayConfigError(f"{name} is missing from the relay image")
    return path


def msmtpd_argv(config_path: Path, *, msmtpd: str, msmtp: str) -> list[str]:
    return [
        msmtpd,
        f"--interface={LISTEN_INTERFACE}",
        f"--port={LISTEN_PORT}",
        "--log=/dev/stderr",
        f"--command={msmtp} -C {config_path} --account={ACCOUNT_NAME} -f %F --",
    ]


def require_writable_spool(path: Path = SPOOL_DIR) -> None:
    """Refuse to accept mail we could not spool. msmtp reports this as a 5xx."""

    probe = path / f".geem-spool-probe.{os.getpid()}"
    try:
        probe.touch(mode=0o600)
    except OSError as exc:
        raise MailRelayConfigError(f"{path} must be writable to spool mail") from exc
    probe.unlink(missing_ok=True)


def main() -> None:
    msmtpd = resolve_binary("msmtpd")
    msmtp = resolve_binary("msmtp")
    require_writable_spool()
    write_config(DEFAULT_OUTPUT, build_config_from_environment())
    os.execv(msmtpd, msmtpd_argv(DEFAULT_OUTPUT, msmtpd=msmtpd, msmtp=msmtp))


if __name__ == "__main__":
    main()
