from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_gateway_image_package_snapshot_imports_without_api_runtime(
    tmp_path: Path,
) -> None:
    """Exercise the exact minimal app package copied by the gateway image."""

    image_root = tmp_path / "image-root"
    app_package = image_root / "app"
    common_package = app_package / "common"
    common_package.mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "apps/mcp_egress_gateway/package_stubs/app/__init__.py",
        app_package / "__init__.py",
    )
    shutil.copy2(
        REPO_ROOT
        / "apps/mcp_egress_gateway/package_stubs/app/common/__init__.py",
        common_package / "__init__.py",
    )
    shutil.copy2(
        REPO_ROOT / "apps/api/app/common/outbound_http.py",
        common_package / "outbound_http.py",
    )

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(image_root), str(REPO_ROOT / "apps/mcp_egress_gateway")]
    )
    imported = subprocess.run(
        [sys.executable, "-c", "import gateway.main"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert imported.returncode == 0, imported.stderr


def test_rendered_compose_keeps_gateway_off_datastore_and_public_networks() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is unavailable")
    rendered = subprocess.run(
        [
            docker,
            "compose",
            "--profile",
            "mcp",
            "-f",
            str(REPO_ROOT / "infra/docker-compose.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(rendered.stdout)
    services = config["services"]
    networks = config["networks"]

    for name in (
        "application_data",
        "application_ingress",
        "application_provider_control",
        "mcp_egress_control",
        "mcp_proxy_control",
    ):
        assert networks[name]["internal"] is True

    gateway = services["mcp-egress-gateway"]
    proxy = services["mcp-egress-proxy"]
    app_proxy = services["app-egress-proxy"]
    assert set(gateway["networks"]) == {"mcp_egress_control", "mcp_proxy_control"}
    assert set(proxy["networks"]) == {"mcp_proxy_control", "public_egress"}
    assert set(app_proxy["networks"]) == {
        "application_provider_control",
        "public_egress",
    }
    assert gateway.get("ports") is None
    assert gateway["read_only"] is True
    assert gateway["cap_drop"] == ["ALL"]

    for name in ("postgres", "redis", "qdrant", "minio"):
        assert set(services[name]["networks"]) == {"application_data"}
    assert "mcp_egress_control" in services["api"]["networks"]
    assert "mcp_egress_control" in services["worker"]["networks"]
    assert all(
        networks[network].get("internal") is True
        for service_name in ("api", "worker")
        for network in services[service_name]["networks"]
    )
    assert {
        name
        for name, service in services.items()
        if "public_egress" in service.get("networks", {})
    } == {"app-egress-proxy", "mcp-egress-proxy"}

    gateway_environment = set(gateway.get("environment", {}))
    assert not gateway_environment.intersection(
        {
            "DATABASE_URL",
            "REDIS_URL",
            "QDRANT_URL",
            "MINIO_ENDPOINT",
            "OPENROUTER_API_KEY",
            "JWT_SECRET",
        }
    )
    assert services["api"]["environment"]["MCP_EGRESS_GATEWAY_URL"].startswith(
        "https://mcp-egress-gateway:"
    )
    assert services["worker"]["environment"]["MCP_EGRESS_GATEWAY_URL"].startswith(
        "https://mcp-egress-gateway:"
    )
    assert services["api"]["environment"]["HTTPS_PROXY"] == (
        "http://app-egress-proxy:3128"
    )
    assert services["worker"]["environment"]["HTTPS_PROXY"] == (
        "http://app-egress-proxy:3128"
    )

    api_secret_targets = {secret["target"] for secret in services["api"]["secrets"]}
    worker_secret_targets = {
        secret["target"] for secret in services["worker"]["secrets"]
    }
    gateway_secret_targets = {
        secret["target"] for secret in gateway["secrets"]
    }
    client_targets = {
        "/run/secrets/mcp-egress/client.crt",
        "/run/secrets/mcp-egress/client.key",
        "/run/secrets/mcp-egress/ca.crt",
    }
    server_targets = {
        "/run/secrets/mcp-egress/server.crt",
        "/run/secrets/mcp-egress/server.key",
        "/run/secrets/mcp-egress/ca.crt",
    }
    assert api_secret_targets == client_targets
    assert worker_secret_targets == client_targets
    assert gateway_secret_targets == server_targets


def test_uat_compose_starts_mcp_gateway_without_profile() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is unavailable")

    def render(*files: Path) -> dict:
        command = [docker, "compose"]
        for path in files:
            command.extend(("-f", str(path)))
        command.extend(("config", "--format", "json"))
        rendered = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(rendered.stdout)

    base_path = REPO_ROOT / "infra/docker-compose.yml"
    uat_path = REPO_ROOT / "infra/docker-compose.uat.yml"

    # Local development still opts into the isolated MCP stack explicitly.
    base_services = render(base_path)["services"]
    assert "mcp-egress-gateway" not in base_services
    assert "mcp-egress-proxy" not in base_services

    # UAT exposes MCP in the product UI, so its ordinary startup graph must be
    # complete even when operators do not remember a Compose profile flag.
    uat_services = render(base_path, uat_path)["services"]
    gateway = uat_services["mcp-egress-gateway"]
    assert "mcp-egress-proxy" in uat_services
    assert uat_services["api"]["depends_on"]["mcp-egress-gateway"] == {
        "condition": "service_started",
        "required": True,
    }
    assert set(gateway["networks"]) == {"mcp_egress_control", "public_egress"}
    assert gateway["environment"]["EGRESS_FORWARD_PROXY_URL"] == ""
    assert gateway.get("profiles") is None
    assert uat_services["mcp-egress-proxy"].get("profiles") is None


def test_deployed_proxy_is_connect_only_deny_private_and_has_no_access_log() -> None:
    config = (REPO_ROOT / "infra/mcp-egress/proxy/squid.conf").read_text()
    assert "acl CONNECT method CONNECT" in config
    assert "http_access deny blocked_destination" in config
    assert "http_access deny !CONNECT" in config
    assert "acl blocked_destination dst 169.254.0.0/16" in config
    assert "acl blocked_destination dst 10.0.0.0/8" in config
    assert "acl blocked_destination dst fc00::/7" in config
    assert "access_log none" in config

    app_config = (REPO_ROOT / "infra/app-egress/proxy/squid.conf").read_text()
    assert "acl fixed_provider dstdomain" in app_config
    assert "http_access allow fixed_provider" in app_config
    assert "http_access deny all" in app_config
    assert "access_log none" in app_config


def test_deployed_isolation_smoke_covers_live_release_boundaries() -> None:
    script = (REPO_ROOT / "infra/mcp-egress/verify-isolation.sh").read_text()

    assert "--cert /run/secrets/mcp-egress/client.crt" in script
    assert "gateway accepted a caller without a client certificate" in script
    assert "postgres:5432 redis:6379 qdrant:6333 minio:9000" in script
    assert "1.1.1.1" in script
    assert "CONNECT 10.0.0.1:443" in script
    assert "mcp-egress-proxy" in script
