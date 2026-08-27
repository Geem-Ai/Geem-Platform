from __future__ import annotations

import importlib
import sys

import pytest


def _load_beat(monkeypatch: pytest.MonkeyPatch, **environment: str):
    for name in ("APP_ENV", "REDIS_URL", "MCP_CONNECTOR_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("app.worker.beat_app", None)
    return importlib.import_module("app.worker.beat_app")


def test_beat_starts_with_only_broker_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_beat(
        monkeypatch,
        APP_ENV="production",
        REDIS_URL="redis://redis:6379/0",
        MCP_CONNECTOR_ENABLED="false",
    )

    assert module.beat_app.conf.broker_url == "redis://redis:6379/0"
    assert module.beat_app.conf.enable_utc is True
    assert module.beat_app.conf.beat_schedule["poll-mcp-connections"]["task"] == (
        "poll_mcp_connections"
    )


def test_beat_refuses_mcp_enablement(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="refuses MCP_CONNECTOR_ENABLED=true"):
        _load_beat(
            monkeypatch,
            APP_ENV="production",
            REDIS_URL="redis://redis:6379/0",
            MCP_CONNECTOR_ENABLED="true",
        )


def test_production_beat_refuses_external_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="internal Redis"):
        _load_beat(
            monkeypatch,
            APP_ENV="production",
            REDIS_URL="rediss://external.example.invalid:6380/0",
            MCP_CONNECTOR_ENABLED="false",
        )


def test_beat_refuses_unrecognized_broker_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="REDIS_URL is invalid"):
        _load_beat(
            monkeypatch,
            APP_ENV="production",
            REDIS_URL="redis+unsafe://redis:6379/0",
            MCP_CONNECTOR_ENABLED="false",
        )
