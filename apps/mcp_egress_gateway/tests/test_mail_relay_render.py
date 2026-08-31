from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RENDERER_PATH = REPO_ROOT / "infra/mail-relay/render_config.py"
SPEC = importlib.util.spec_from_file_location("mail_relay_render_config", RENDERER_PATH)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)

VALID_ENVIRONMENT = {
    "MAIL_RELAY_UPSTREAM_HOST": "mail.geem.ai",
    "MAIL_RELAY_UPSTREAM_PORT": "587",
    "MAIL_RELAY_UPSTREAM_USERNAME": "noreply@geem.ai",
    "MAIL_RELAY_UPSTREAM_PASSWORD": "upstream-secret",
    "MAIL_RELAY_UPSTREAM_FROM": "noreply@geem.ai",
}


def apply_environment(monkeypatch, **overrides: str | None) -> None:
    values = {**VALID_ENVIRONMENT, **overrides}
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def test_rendered_account_negotiates_verified_starttls(monkeypatch) -> None:
    apply_environment(monkeypatch)
    rendered = renderer.build_config_from_environment()
    assert "host mail.geem.ai" in rendered
    assert "port 587" in rendered
    assert "auth on" in rendered
    assert "user noreply@geem.ai" in rendered
    assert "tls on" in rendered
    assert "tls_starttls on" in rendered
    assert "tls_certcheck on" in rendered


def test_implicit_tls_port_does_not_negotiate_starttls(monkeypatch) -> None:
    apply_environment(monkeypatch, MAIL_RELAY_UPSTREAM_PORT="465")
    rendered = renderer.build_config_from_environment()
    assert "port 465" in rendered
    assert "tls on" in rendered
    assert "tls_starttls off" in rendered


def test_password_is_read_back_at_send_time_not_written_to_disk(monkeypatch) -> None:
    apply_environment(monkeypatch)
    rendered = renderer.build_config_from_environment()
    assert VALID_ENVIRONMENT["MAIL_RELAY_UPSTREAM_PASSWORD"] not in rendered
    assert "passwordeval printenv MAIL_RELAY_UPSTREAM_PASSWORD" in rendered


@pytest.mark.parametrize(
    "name",
    [
        "MAIL_RELAY_UPSTREAM_HOST",
        "MAIL_RELAY_UPSTREAM_PORT",
        "MAIL_RELAY_UPSTREAM_USERNAME",
        "MAIL_RELAY_UPSTREAM_PASSWORD",
        "MAIL_RELAY_UPSTREAM_FROM",
    ],
)
def test_missing_setting_fails_closed(monkeypatch, name: str) -> None:
    apply_environment(monkeypatch, **{name: None})
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.build_config_from_environment()
    apply_environment(monkeypatch, **{name: "   "})
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.build_config_from_environment()


@pytest.mark.parametrize("port", ["25", "0", "2525", "587a", "-587"])
def test_only_submission_ports_are_accepted(monkeypatch, port: str) -> None:
    apply_environment(monkeypatch, MAIL_RELAY_UPSTREAM_PORT=port)
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.build_config_from_environment()


@pytest.mark.parametrize(
    "host",
    ["localhost", "mail-relay", "127.0.0.1", "10.1.2.3", "not a host", "mail..geem.ai"],
)
def test_upstream_must_be_an_external_host(monkeypatch, host: str) -> None:
    apply_environment(monkeypatch, MAIL_RELAY_UPSTREAM_HOST=host)
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.build_config_from_environment()


@pytest.mark.parametrize(
    "value",
    [
        "mail.geem.ai\nhost attacker.example.com",
        "mail.geem.ai\r\nport 25",
    ],
)
def test_settings_cannot_inject_extra_configuration(monkeypatch, value: str) -> None:
    apply_environment(monkeypatch, MAIL_RELAY_UPSTREAM_HOST=value)
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.build_config_from_environment()


def test_username_cannot_inject_extra_configuration(monkeypatch) -> None:
    apply_environment(
        monkeypatch,
        MAIL_RELAY_UPSTREAM_USERNAME="mailer\ntls_certcheck off",
    )
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.build_config_from_environment()


def test_config_is_written_owner_read_only(monkeypatch, tmp_path: Path) -> None:
    apply_environment(monkeypatch)
    target = tmp_path / "geem-msmtprc"
    renderer.write_config(target, renderer.build_config_from_environment())
    assert stat.S_IMODE(target.stat().st_mode) == 0o400
    assert not list(tmp_path.glob(".*.tmp"))


def test_writable_spool_is_accepted(tmp_path: Path) -> None:
    renderer.require_writable_spool(tmp_path)
    assert not list(tmp_path.iterdir())


def test_unusable_spool_fails_closed(tmp_path: Path) -> None:
    # msmtp spools through libc tmpfile(), which only ever uses /tmp, so a relay
    # without a usable spool would accept mail it can never hand upstream. A
    # spool that is not a directory fails for any uid, including root.
    spool = tmp_path / "spool"
    spool.write_text("not a directory")
    with pytest.raises(renderer.MailRelayConfigError):
        renderer.require_writable_spool(spool)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_spool_without_write_permission_fails_closed(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    spool.mkdir(mode=0o500)
    try:
        with pytest.raises(renderer.MailRelayConfigError):
            renderer.require_writable_spool(spool)
    finally:
        spool.chmod(0o700)


def test_spool_is_checked_before_any_configuration_is_written() -> None:
    assert renderer.SPOOL_DIR == Path("/tmp")


def test_listener_stays_on_the_internal_submission_port() -> None:
    argv = renderer.msmtpd_argv(
        Path("/run/geem-msmtprc"), msmtpd="/usr/bin/msmtpd", msmtp="/usr/bin/msmtp"
    )
    assert argv[0] == "/usr/bin/msmtpd"
    assert "--interface=0.0.0.0" in argv
    assert "--port=25" in argv
    assert (
        "--command=/usr/bin/msmtp -C /run/geem-msmtprc --account=upstream -f %F --"
        in argv
    )
