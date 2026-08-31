from __future__ import annotations

import ipaddress
import json
import os
import re
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
        "application_broker",
        "application_ingress",
        "application_provider_control",
        "mail_relay_control",
        "mcp_egress_control",
        "mcp_proxy_control",
    ):
        assert networks[name]["internal"] is True

    gateway = services["mcp-egress-gateway"]
    proxy = services["mcp-egress-proxy"]
    app_proxy = services["app-egress-proxy"]
    assert set(gateway["networks"]) == {"mcp_egress_control", "mcp_proxy_control"}
    assert set(proxy["networks"]) == {"mcp_proxy_control", "mcp_public_egress"}
    assert set(app_proxy["networks"]) == {
        "application_provider_control",
        "application_provider_egress",
    }
    assert gateway.get("ports") is None
    assert gateway["read_only"] is True
    assert gateway["cap_drop"] == ["ALL"]
    assert gateway["deploy"]["replicas"] == 1
    assert gateway["profiles"] == ["mcp"]
    assert proxy["profiles"] == ["mcp"]
    for name, service in services.items():
        if name not in {"mcp-egress-gateway", "mcp-egress-proxy"}:
            assert not service.get("profiles")
        if name == "minio-init":
            assert service.get("restart") is None
        else:
            assert service["restart"] == "unless-stopped"
    assert services["beat"]["environment"]["MCP_CONNECTOR_ENABLED"] == "false"
    assert set(services["beat"]["environment"]) == {
        "APP_ENV",
        "MCP_CONNECTOR_ENABLED",
        "REDIS_URL",
    }
    assert services["beat"]["command"][:4] == [
        "celery",
        "-A",
        "app.worker.beat_app:beat_app",
        "beat",
    ]
    assert services["beat"]["deploy"]["replicas"] == 1
    assert services["beat"].get("secrets") is None
    assert set(services["beat"]["networks"]) == {"application_broker"}
    assert proxy["environment"]["MCP_PROXY_BLOCKED_NETWORKS"] == (
        gateway["environment"]["EGRESS_BLOCKED_NETWORKS"]
    )
    assert proxy["environment"]["MCP_PROXY_REQUIRE_BLOCKED_NETWORKS"] == "false"
    assert proxy["entrypoint"] == [
        "python3",
        "/usr/local/lib/geem/render_mcp_proxy_config.py",
    ]

    for name in ("postgres", "qdrant", "minio"):
        assert set(services[name]["networks"]) == {"application_data"}
    assert set(services["redis"]["networks"]) == {"application_broker"}
    assert "application_broker" in services["api"]["networks"]
    assert "application_broker" in services["worker"]["networks"]
    assert services["postgres"]["healthcheck"]["test"] == ["CMD", "pg_isready"]
    assert services["redis"]["healthcheck"]["test"] == [
        "CMD",
        "redis-cli",
        "ping",
    ]
    assert services["qdrant"]["healthcheck"]["test"] == [
        "CMD",
        "bash",
        "-c",
        "exec 3<>/dev/tcp/127.0.0.1/6333",
    ]
    assert services["api"]["healthcheck"]["test"] == [
        "CMD",
        "curl",
        "-f",
        "http://localhost:8000/api/health/live",
    ]
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
    } == set()
    assert {
        name
        for name, service in services.items()
        if "application_provider_egress" in service.get("networks", {})
    } == {"app-egress-proxy"}
    assert {
        name
        for name, service in services.items()
        if "mcp_public_egress" in service.get("networks", {})
    } == {"mcp-egress-proxy"}

    # The relay owns the only credentialed submission route: api and worker may
    # reach it, but must never hold the upstream route themselves.
    mail_relay = services["mail-relay"]
    assert set(mail_relay["networks"]) == {"mail_relay_control", "mail_relay_egress"}
    assert mail_relay.get("ports") is None
    assert mail_relay["read_only"] is True
    assert mail_relay["cap_drop"] == ["ALL"]
    assert mail_relay["user"] == "10002:10002"
    # msmtp spools through libc tmpfile(), so /tmp must be writable or the
    # relay accepts mail it can never hand upstream.
    assert sorted(
        entry.split(":", maxsplit=1)[0] for entry in mail_relay["tmpfs"]
    ) == ["/run", "/tmp"]
    for entry in mail_relay["tmpfs"]:
        assert "uid=10002,gid=10002,mode=0700" in entry
    assert mail_relay["entrypoint"] == [
        "python3",
        "/usr/local/lib/geem/render_mail_relay_config.py",
    ]
    assert networks["mail_relay_egress"].get("internal") is not True
    assert {
        name
        for name, service in services.items()
        if "mail_relay_egress" in service.get("networks", {})
    } == {"mail-relay"}
    assert {
        name
        for name, service in services.items()
        if "mail_relay_control" in service.get("networks", {})
    } == {"api", "worker", "mail-relay"}
    assert set(mail_relay["environment"]) == {
        "MAIL_RELAY_UPSTREAM_HOST",
        "MAIL_RELAY_UPSTREAM_PORT",
        "MAIL_RELAY_UPSTREAM_USERNAME",
        "MAIL_RELAY_UPSTREAM_PASSWORD",
        "MAIL_RELAY_UPSTREAM_FROM",
    }

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


def test_minio_compose_allowlists_env_and_rejects_production_fallbacks(
    tmp_path: Path,
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is unavailable")

    environment = dict(os.environ)
    environment.update(
        {
            "APP_ENV": "production",
            "MINIO_ACCESS_KEY": "",
            "MINIO_SECRET_KEY": "",
            "JWT_SECRET": "must-not-reach-minio",
            "SECRETS_ENCRYPTION_KEY": "must-not-reach-minio",
            "OPENROUTER_API_KEY": "must-not-reach-minio",
        }
    )
    rendered = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            str(REPO_ROOT / "infra/docker-compose.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(rendered.stdout)["services"]

    assert set(services["minio"]["environment"]) == {
        "APP_ENV",
        "MINIO_ROOT_PASSWORD",
        "MINIO_ROOT_USER",
    }
    assert set(services["minio-init"]["environment"]) == {
        "APP_ENV",
        "MINIO_ACCESS_KEY",
        "MINIO_BUCKET",
        "MINIO_SECRET_KEY",
    }
    assert services["minio-init"]["image"] == (
        "quay.io/minio/mc@sha256:"
        "993e8c454a7ec632923f7e3e61adf1d473261da6354cefd641aedd33a2cfe112"
    )
    rendered_init_script = services["minio-init"]["entrypoint"][2]
    assert "until timeout -k 2s 5s mc alias set" in rendered_init_script
    assert (
        "--conn-read-deadline 4s --conn-write-deadline 4s"
        in rendered_init_script
    )
    assert (
        'timeout -k 2s 10s mc mb --ignore-existing "local/$${MINIO_BUCKET}"'
        in rendered_init_script
    )
    assert (
        'timeout -k 2s 10s mc anonymous set none "local/$${MINIO_BUCKET}"'
        in rendered_init_script
    )
    assert (
        'timeout -k 2s 10s mc stat "local/$${MINIO_BUCKET}" >/dev/null'
        in rendered_init_script
    )

    # Empty production credentials must remain empty after Compose rendering;
    # local-only defaults are applied inside the guarded container scripts.
    assert services["minio"]["environment"]["MINIO_ROOT_USER"] == ""
    assert services["minio"]["environment"]["MINIO_ROOT_PASSWORD"] == ""
    assert services["minio-init"]["environment"]["MINIO_ACCESS_KEY"] == ""
    assert services["minio-init"]["environment"]["MINIO_SECRET_KEY"] == ""

    for service_name in ("minio", "minio-init"):
        service = services[service_name]
        assert service["entrypoint"][:2] == ["/bin/sh", "-c"]
        script = service["entrypoint"][2]
        # `config` keeps the escaped form so the rendered model can be fed
        # back to Compose. The runtime command receives one literal `$`.
        assert "$${APP_ENV}" in script
        runtime_entrypoint = [
            *service["entrypoint"][:2],
            script.replace("$$", "$"),
        ]
        rejected = subprocess.run(
            runtime_entrypoint,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                **{
                    key: str(value)
                    for key, value in service["environment"].items()
                },
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert rejected.returncode != 0
        assert "non-default access key in production" in rejected.stderr

    fake_mc = tmp_path / "mc"
    fake_mc.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  alias) exit 0 ;;\n"
        "  mb) exit 23 ;;\n"
        "  anonymous) exit 99 ;;\n"
        "  *) exit 98 ;;\n"
        "esac\n"
    )
    fake_mc.chmod(0o755)
    fake_timeout = tmp_path / "timeout"
    fake_timeout.write_text(
        "#!/bin/sh\n"
        "[ \"$1\" = \"-k\" ] || exit 97\n"
        "shift 3\n"
        "exec \"$@\"\n"
    )
    fake_timeout.chmod(0o755)
    init_service = services["minio-init"]
    init_entrypoint = [
        *init_service["entrypoint"][:2],
        init_service["entrypoint"][2].replace("$$", "$"),
    ]
    failed_bucket_create = subprocess.run(
        init_entrypoint,
        env={
            "PATH": f"{tmp_path}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "APP_ENV": "production",
            "MINIO_ACCESS_KEY": "production-access",
            "MINIO_SECRET_KEY": "production-secret",
            "MINIO_BUCKET": "rag-documents",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    # `set -e` must propagate the bucket-creation failure. Reaching the
    # anonymous-policy command would instead return the fake command's 99.
    assert failed_bucket_create.returncode == 23


def test_minio_init_source_is_bounded_idempotent_and_fail_closed() -> None:
    compose = (REPO_ROOT / "infra/docker-compose.yml").read_text()
    minio_source = compose.split("\n  minio:\n", 1)[1].split(
        "\n  minio-init:\n", 1
    )[0]
    init_source = compose.split("\n  minio-init:\n", 1)[1].split(
        "\n  api:\n", 1
    )[0]

    for service_source in (minio_source, init_source):
        assert "env_file:" not in service_source
        assert "../.env" not in service_source
        assert "set -eu" in service_source
        assert "$${APP_ENV}" in service_source

    assert "|| true" not in init_source
    assert "exit 0" not in init_source
    assert "timeout -k 2s 10s mc mb --ignore-existing" in init_source
    assert "until timeout -k 2s 5s mc alias set" in init_source
    assert "--conn-read-deadline 4s --conn-write-deadline 4s" in init_source
    assert "attempts=$$((attempts + 1))" in init_source
    assert 'if [ "$${attempts}" -ge 30 ]' in init_source
    assert (
        'timeout -k 2s 10s mc anonymous set none "local/$${MINIO_BUCKET}"'
        in init_source
    )
    assert (
        'timeout -k 2s 10s mc stat "local/$${MINIO_BUCKET}" >/dev/null'
        in init_source
    )


def test_supported_compose_env_file_supplies_one_minio_identity(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is unavailable")
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        "APP_ENV=local\n"
        "MINIO_ACCESS_KEY=sentinel-minio-access\n"
        "MINIO_SECRET_KEY=sentinel-minio-secret\n"
        "MINIO_BUCKET=sentinel-minio-bucket\n"
    )

    rendered = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            str(env_file),
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
    services = json.loads(rendered.stdout)["services"]

    assert services["minio"]["environment"] == {
        "APP_ENV": "local",
        "MINIO_ROOT_PASSWORD": "sentinel-minio-secret",
        "MINIO_ROOT_USER": "sentinel-minio-access",
    }
    assert services["minio-init"]["environment"] == {
        "APP_ENV": "local",
        "MINIO_ACCESS_KEY": "sentinel-minio-access",
        "MINIO_BUCKET": "sentinel-minio-bucket",
        "MINIO_SECRET_KEY": "sentinel-minio-secret",
    }


def test_uat_systemd_uses_the_root_compose_environment() -> None:
    unit = (REPO_ROOT / "infra/systemd/geem-uat.user.service").read_text()

    assert unit.count("docker compose --env-file ../.env") == 2


def test_phase13_gate_runs_the_exact_minio_initializer_smoke() -> None:
    script_path = REPO_ROOT / "infra/minio/verify-init.sh"
    script = script_path.read_text()
    workflow = (
        REPO_ROOT / ".github/workflows/phase13-mcp-release-gate.yml"
    ).read_text()

    assert "--env-file /dev/null" in script
    assert "-f \"$REPO_ROOT/infra/docker-compose.yml\"" in script
    assert script.count("compose run --rm --no-deps minio-init") == 2
    assert 'mc anonymous set download "local/$MINIO_BUCKET"' in script
    assert '[ "$public_status" = "200" ]' in script
    assert "compose down --volumes --remove-orphans" in script
    assert "/dev/tcp/minio/9000" in script
    assert "--entrypoint /usr/bin/timeout minio-init" in script
    assert "127.0.0.1:9100" not in script
    assert '[ "$anonymous_status" = "403" ]' in script
    assert "sh infra/minio/verify-init.sh" in workflow


def test_phase13_gate_covers_shared_provider_and_the_full_migration_chain() -> None:
    workflow = (
        REPO_ROOT / ".github/workflows/phase13-mcp-release-gate.yml"
    ).read_text()

    assert "tests/unit/test_agent_*.py" in workflow
    assert "tests/unit/test_openrouter_contracts.py" in workflow
    assert "alembic upgrade head" in workflow
    assert "0041_openwa_binding_backfill (head)" in workflow
    full_api_job = workflow.split("api-full-regression:", maxsplit=1)[1].split(
        "gateway-and-compose:", maxsplit=1
    )[0]
    assert "tests/unit" in full_api_job
    assert "tests/integration" in full_api_job
    assert "phase13-api-regression-${{ github.sha }}" in workflow
    assert "phase13-gateway-regression-${{ github.sha }}" in workflow
    assert "Run the complete Workspace test suite" in workflow
    assert "phase13-workspace-regression-${{ github.sha }}" in workflow
    assert "Dashboard and marketing regression" in workflow
    assert "phase13-dashboard-regression-${{ github.sha }}" in workflow


def test_fresh_production_docs_replace_phase_upgrade_artifacts() -> None:
    deployment_path = REPO_ROOT / "docs/deployment.md"
    connectors_path = REPO_ROOT / "docs/integrations/mcp-connectors.md"
    obsolete_paths = (
        REPO_ROOT / "docs/integrations/mcp-production-deployment.md",
        REPO_ROOT / "docs/integrations/mcp-production-clean-slate.md",
        REPO_ROOT / "infra/cloudflared/config.maintenance.yml",
        REPO_ROOT / "infra/docker-compose.maintenance-ingress.yml",
    )

    assert deployment_path.is_file()
    assert connectors_path.is_file()
    for path in obsolete_paths:
        assert not path.exists()

    deployment = deployment_path.read_text()
    connectors = connectors_path.read_text()
    for obsolete_reference in (
        "mcp-production-deployment.md",
        "mcp-production-clean-slate.md",
        "config.maintenance.yml",
        "docker-compose.maintenance-ingress.yml",
        "--cloudflared-mode",
        "phase13-start-artifacts.sha256",
    ):
        assert obsolete_reference not in deployment
        assert obsolete_reference not in connectors


def test_fresh_deployment_is_geem_only_on_the_shared_host() -> None:
    deployment = (REPO_ROOT / "docs/deployment.md").read_text()
    words = " ".join(deployment.split())

    assert "**law-firm**" in deployment
    assert "remove only Docker objects that are proven to belong to Geem" in words
    assert "Remove only those exact container IDs" in words
    assert "delete only that exact tunnel UUID" in words
    assert "Never remove `infra_default` while any law-firm or unknown" in words
    assert (
        "Any law-firm identity, state, mount, or endpoint change is a failure"
        in words
    )

    for forbidden_global_action in (
        "apt remove docker*",
        "rm -rf /var/lib/docker",
        "docker system prune",
        "docker container prune",
        "docker image prune",
        "docker network prune",
        "docker volume prune",
        "docker compose down",
        "systemctl restart docker",
    ):
        assert forbidden_global_action in deployment

    assert "/opt/geem/releases/<full-sha>" in deployment
    assert "four new, empty, explicitly named datastore volumes" in words
    assert "one new locally managed Cloudflare Tunnel" in words
    assert "six proxied `geem.ai` DNS routes" in words
    assert "all six DNS record IDs target the new tunnel" in words


def test_cloudflare_maintenance_and_lifecycle_authority_are_separate() -> None:
    deployment = (REPO_ROOT / "docs/deployment.md").read_text()
    maintenance = deployment.split(
        "### Cloudflare maintenance credential", maxsplit=1
    )[1].split("### Cloudflare tunnel lifecycle credential", maxsplit=1)[0]
    lifecycle = deployment.split(
        "### Cloudflare tunnel lifecycle credential", maxsplit=1
    )[1].split("## Fixed production identities", maxsplit=1)[0]
    lifecycle_words = " ".join(lifecycle.split())

    assert "/etc/geem/cloudflare/maintenance.json" in maintenance
    assert "Zone -> Zone -> Read" in maintenance
    assert "Zone -> WAF -> Edit" in maintenance
    assert (
        "not** sufficient to list, delete, or create Cloudflare Tunnels"
        in maintenance
    )
    assert "cannot update DNS" in maintenance
    assert "Account -> Cloudflare Tunnel -> Edit" not in maintenance
    assert "Zone -> DNS -> Edit" not in maintenance

    assert "/etc/geem/cloudflare/tunnel-lifecycle.json" in lifecycle
    assert "Account -> Cloudflare Tunnel -> Edit" in lifecycle
    assert "Zone -> DNS -> Edit" in lifecycle
    assert "Zone -> Zone -> Read" in lifecycle
    assert "The WAF token does not fill that gap" in lifecycle_words
    assert "NXDOMAIN/no route" in deployment
    assert "unproxied production record is not protected by WAF" in deployment


def test_fresh_production_pki_requires_exact_identities_and_no_symlinks() -> None:
    readme = (REPO_ROOT / "infra/mcp-egress/pki/README.md").read_text()

    assert "DNS:mcp-egress-gateway'" in readme
    assert "TLSWebServerAuthentication'" in readme
    assert "TLSWebClientAuthentication'" in readme
    assert "'CA:TRUE,pathlen:0'" in readme
    assert readme.count("'CA:FALSE'") == 2
    assert "'CertificateSign,CRLSign'" in readme
    assert "test ! -L \"$component\"" in readme
    for destination in (
        "/etc/geem/mcp-egress/pki/ca/ca.crt",
        "/etc/geem/mcp-egress/pki/server/server.crt",
        "/etc/geem/mcp-egress/pki/server/server.key",
        "/etc/geem/mcp-egress/pki/client/client.crt",
        "/etc/geem/mcp-egress/pki/client/client.key",
    ):
        assert destination in readme


def test_fresh_production_hardening_template_is_complete() -> None:
    overlay = (
        REPO_ROOT / "infra/docker-compose.production-hardening.example.yml"
    ).read_text()

    assert overlay.count("\n    pull_policy: never") == 16
    assert overlay.count('\n    restart: "no"') == 15
    assert overlay.count("com.geem.production.install:") == 16
    required_subnets = (
        "APPLICATION_DATA_SUBNET",
        "APPLICATION_BROKER_SUBNET",
        "APPLICATION_INGRESS_SUBNET",
        "APPLICATION_PROVIDER_CONTROL_SUBNET",
        "APPLICATION_PROVIDER_EGRESS_SUBNET",
        "MAIL_RELAY_CONTROL_SUBNET",
        "MAIL_RELAY_EGRESS_SUBNET",
        "MCP_EGRESS_CONTROL_SUBNET",
        "MCP_PROXY_CONTROL_SUBNET",
        "MCP_PUBLIC_EGRESS_SUBNET",
        "PUBLIC_EGRESS_SUBNET",
    )
    for variable in required_subnets:
        assert overlay.count(f"${{{variable}:?required") == 1

    for volume in (
        "POSTGRES_VOLUME_NAME",
        "REDIS_VOLUME_NAME",
        "QDRANT_VOLUME_NAME",
        "MINIO_VOLUME_NAME",
    ):
        assert f"name: ${{{volume}:?required fresh Geem" in overlay
    assert overlay.count("external: true") == 4

    assert overlay.count("- /etc/geem/production.env") == 2
    assert "file: /etc/geem/cloudflared/config.yml" in overlay
    assert "file: /etc/geem/cloudflared/credentials.json" in overlay


def test_fresh_production_hardening_template_passes_rendered_validator() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is unavailable")

    def digest(character: str) -> str:
        return f"sha256:{character * 64}"

    environment = dict(os.environ)
    environment.update(
        {
            "POSTGRES_IMAGE": digest("1"),
            "REDIS_IMAGE": digest("2"),
            "QDRANT_IMAGE": digest("3"),
            "MINIO_IMAGE": digest("4"),
            "GEEM_API_IMAGE": digest("5"),
            "APP_EGRESS_PROXY_IMAGE": digest("6"),
            "MCP_EGRESS_GATEWAY_IMAGE": digest("7"),
            "MCP_EGRESS_PROXY_IMAGE": digest("8"),
            "WORKSPACE_WEB_IMAGE": digest("9"),
            "DASHBOARD_WEB_IMAGE": digest("a"),
            "LANDPAGE_WEB_IMAGE": digest("b"),
            "CLOUDFLARED_IMAGE": digest("c"),
            "MAIL_RELAY_IMAGE": digest("d"),
            "MAIL_RELAY_UPSTREAM_HOST": "mail.geem.ai",
            "MAIL_RELAY_UPSTREAM_PORT": "587",
            "MAIL_RELAY_UPSTREAM_USERNAME": "noreply@geem.ai",
            "MAIL_RELAY_UPSTREAM_PASSWORD": "not-a-default-submission-secret",
            "MAIL_RELAY_UPSTREAM_FROM": "noreply@geem.ai",
            "GEEM_INSTALL_ID": "geem-install-test-0001",
            "POSTGRES_USER": "geem",
            "POSTGRES_PASSWORD": "not-a-default-password",
            "POSTGRES_DB": "geem",
            "DATABASE_URL": (
                "postgresql+psycopg://geem:not-a-default-password@postgres:5432/geem"
            ),
            "MINIO_ACCESS_KEY": "geem-storage",
            "MINIO_SECRET_KEY": "not-a-default-minio-secret",
            "MINIO_BUCKET": "rag-documents",
            "MCP_CONNECTOR_ENABLED": "false",
            "MCP_EGRESS_BLOCKED_NETWORKS": (
                "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
            ),
            "MCP_EGRESS_PKI_DIR": "/etc/geem/mcp-egress/pki",
            "POSTGRES_VOLUME_NAME": "geem-fresh-postgres",
            "REDIS_VOLUME_NAME": "geem-fresh-redis",
            "QDRANT_VOLUME_NAME": "geem-fresh-qdrant",
            "MINIO_VOLUME_NAME": "geem-fresh-minio",
            "APPLICATION_DATA_SUBNET": "172.30.10.0/24",
            "APPLICATION_BROKER_SUBNET": "172.30.11.0/24",
            "APPLICATION_INGRESS_SUBNET": "172.30.12.0/24",
            "APPLICATION_PROVIDER_CONTROL_SUBNET": "172.30.13.0/24",
            "APPLICATION_PROVIDER_EGRESS_SUBNET": "172.30.14.0/24",
            "MCP_EGRESS_CONTROL_SUBNET": "172.30.15.0/24",
            "MCP_PROXY_CONTROL_SUBNET": "172.30.16.0/24",
            "MCP_PUBLIC_EGRESS_SUBNET": "172.30.17.0/24",
            "PUBLIC_EGRESS_SUBNET": "172.30.18.0/24",
            "MAIL_RELAY_CONTROL_SUBNET": "172.30.19.0/24",
            "MAIL_RELAY_EGRESS_SUBNET": "172.30.20.0/24",
        }
    )
    rendered = subprocess.run(
        [
            docker,
            "compose",
            "--project-name",
            "geem-production",
            "--env-file",
            "/dev/null",
            "--profile",
            "mcp",
            "-f",
            str(REPO_ROOT / "infra/docker-compose.yml"),
            "-f",
            str(REPO_ROOT / "infra/docker-compose.tunnel.yml"),
            "-f",
            str(
                REPO_ROOT
                / "infra/docker-compose.production-hardening.example.yml"
            ),
            "-f",
            str(
                REPO_ROOT
                / "apps/mcp_egress_gateway/tests/fixtures/production-no-env-files.yml"
            ),
            "config",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    validator_environment = dict(os.environ)
    validator_environment["PYTHONPATH"] = str(REPO_ROOT / "apps/api")
    validated = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.ops.validate_production_compose",
            "--project",
            "geem-production",
            "--install-id",
            "geem-install-test-0001",
            "--mcp-enabled",
            "false",
            "--allow-local-image-ids",
            "--ingress-service",
            "cloudflared",
            "--volume",
            "postgres_data=geem-fresh-postgres",
            "--volume",
            "redis_data=geem-fresh-redis",
            "--volume",
            "qdrant_data=geem-fresh-qdrant",
            "--volume",
            "minio_data=geem-fresh-minio",
            "--required-blocked-network",
            "10.0.0.0/8",
        ],
        cwd=REPO_ROOT,
        env=validator_environment,
        input=rendered.stdout,
        check=False,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr
    assert validated.stdout.strip() == "production Compose topology valid"


def test_fresh_tunnel_template_has_no_retired_tunnel_identity() -> None:
    config = (REPO_ROOT / "infra/cloudflared/config.yml").read_text()

    assert "tunnel: REPLACE_WITH_NEW_TUNNEL_UUID" in config
    assert "credentials-file: /etc/cloudflared/credentials.json" in config
    assert "e054f188-97ca-4cab-80da-020f0ae4385b" not in config
    assert config.count("  - hostname:") == 10
    for hostname in (
        "app-uat.geem.ai",
        "api-uat.geem.ai",
        "landpage-uat.geem.ai",
        "admin-uat.geem.ai",
    ):
        assert f"  - hostname: {hostname}\n    service: http_status:404" in config
        assert config.index(f"  - hostname: {hostname}") < config.index(
            '  - hostname: "*.geem.ai"'
        )
    assert config.rstrip().endswith("- service: http_status:404")


def test_production_systemd_starts_ingress_last_and_contains_stops() -> None:
    unit = (REPO_ROOT / "infra/systemd/geem-production.service").read_text()
    preflight = (REPO_ROOT / "infra/systemd/geem-production-preflight").read_text()
    verify = (REPO_ROOT / "infra/systemd/geem-production-verify").read_text()
    stop = (REPO_ROOT / "infra/systemd/geem-production-stop").read_text()
    deployment = (REPO_ROOT / "docs/deployment.md").read_text()
    connectors = (REPO_ROOT / "docs/integrations/mcp-connectors.md").read_text()

    start_lines = [
        line for line in unit.splitlines() if line.startswith("ExecStart=")
    ]
    assert len(start_lines) == 4
    assert start_lines[0].startswith(
        "ExecStart=/usr/local/sbin/geem-prod-compose up"
    )
    assert "cloudflared" not in start_lines[0]
    assert " mail-relay " in start_lines[0]
    assert start_lines[1] == (
        "ExecStart=/usr/local/sbin/geem-production-verify internal"
    )
    assert start_lines[2] == (
        "ExecStart=/usr/local/sbin/geem-prod-compose up -d --no-deps cloudflared"
    )
    assert start_lines[3] == (
        "ExecStart=/usr/local/sbin/geem-production-verify ingress"
    )
    assert (
        "ExecStartPre=/usr/local/sbin/geem-production-preflight" in unit
    )
    assert "ExecStop=/usr/local/sbin/geem-production-stop" in unit
    assert "ExecStopPost=/usr/local/sbin/geem-production-stop" in unit

    assert "internal|runtime|ingress" in verify
    assert "cloudflared started before internal verification" in verify
    # A stopped relay silently queues nothing and mail is lost, so managed
    # starts must require it exactly like every other always-on service.
    for artifact in (preflight, verify, stop):
        assert "mail-relay" in artifact
    assert "require_one_running cloudflared" in verify
    assert 'elif [ "$stage" = runtime ]; then' in verify
    assert "verify_internal_health" in verify
    assert "stability" in verify.lower()
    assert 'while [ "$check" -le 6 ]; do' in verify
    assert '[ "$check" -eq 6 ] || /usr/bin/sleep 5' in verify
    assert "/usr/bin/sleep" in verify

    assert "project=geem-production" in stop
    assert "install_file=/etc/geem/install-id" in stop
    assert "install_label=com.geem.production.install" in stop
    project_filter = "--filter \"label=com.docker.compose.project=$project\""
    ingress_filter = "stop_matching cloudflared"
    assert project_filter in stop
    assert '--filter "label=$install_label=$install_id"' in stop
    assert '--filter "label=com.docker.compose.service=$service"' in stop
    assert ingress_filter in stop
    assert stop.index(ingress_filter) < stop.index("stop_matching ''")
    assert '/usr/bin/docker stop --time 30 "$id"' in stop
    assert '&\n    pids="$pids $!"' in stop
    assert 'wait "$pid"' in stop
    assert "docker compose down" not in stop
    assert "prune" not in stop

    assert "manifest=/etc/geem/start-artifacts.sha256" in preflight
    assert "phase13-start-artifacts.sha256" not in preflight
    assert "arguments_file=/etc/geem/production-validator.args" in preflight
    assert "install_file=/etc/geem/install-id" in preflight
    assert '"$compose" config --format json \\\n  | /usr/bin/docker run' in preflight
    assert "--pull never --network none --read-only" in preflight
    assert '--expected-api-image "$api_image"' in preflight
    assert '--install-id "$install_id"' in preflight
    assert '-m app.ops.validate_production_compose "$@" \\' in preflight
    assert 'fail "validator argument file contains an unapproved flag"' in preflight
    assert (
        'fail "validator argument file must contain each volume exactly once"'
        in preflight
    )
    assert 'fail "validator argument file must contain a blocked network"' in preflight
    assert preflight.index('"$@" \\') < preflight.index('--project "$project"')
    assert 'require_file /etc/geem/production.env 0 0 600' in preflight
    assert (
        'require_file /etc/geem/cloudflared/credentials.json 0 65532 440'
        in preflight
    )
    assert (
        'require_file /etc/geem/mcp-egress/pki/server/server.key 0 10001 440'
        in preflight
    )
    assert 'startup checksum manifest must contain exactly 23 paths' in preflight

    validator_contract = deployment.split(
        "this validator contract:", maxsplit=1
    )[1].split("Do not save the rendered JSON", maxsplit=1)[0]
    assert "--allow-local-image-ids" in validator_contract
    assert "--ingress-service cloudflared" in validator_contract
    assert "--cloudflared-mode" not in validator_contract
    assert "/etc/geem/cloudflared/config.yml" in deployment
    assert "Do not put `--project`, `--allow-local-image-ids`," in deployment

    for document in (deployment, connectors):
        assert "/etc/geem/start-artifacts.sha256" in document
        assert "phase13-start-artifacts.sha256" not in document


def _preflight_manifest_gate() -> str:
    """Extract the shipped manifest-approval gate as a runnable sh program.

    The other preflight checks here assert on the script's text, which cannot
    see whether the shell actually agrees. This runs the real code: everything
    from the protected-path list through the duplicate check, stopping before
    the sha256sum verification that needs the live files to exist.
    """

    preflight = (REPO_ROOT / "infra/systemd/geem-production-preflight").read_text()
    start = preflight.index("protected_paths='")
    end = preflight.index('/usr/bin/sha256sum --check --strict --quiet "$manifest"')
    return (
        "set -eu\n"
        'fail() { echo "$1" >&2; exit 1; }\n'
        "manifest=$1\n" + preflight[start:end]
    )


def _run_manifest_gate(tmp_path: Path, paths: list[str]) -> subprocess.CompletedProcess:
    manifest = tmp_path / "start-artifacts.sha256"
    manifest.write_text("".join(f"{'a' * 64}  {path}\n" for path in paths))
    return subprocess.run(
        ["sh", "-c", _preflight_manifest_gate(), "gate", str(manifest)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _preflight_protected_paths() -> list[str]:
    preflight = (REPO_ROOT / "infra/systemd/geem-production-preflight").read_text()
    listing = re.search(r"protected_paths='\n(.*?)'", preflight, re.DOTALL)
    assert listing is not None
    return listing.group(1).split()


def test_production_preflight_approves_its_own_protected_paths(
    tmp_path: Path,
) -> None:
    """A manifest of exactly the protected paths must pass in a real shell."""

    paths = _preflight_protected_paths()
    assert len(paths) == 23

    result = _run_manifest_gate(tmp_path, paths)

    assert result.returncode == 0, result.stderr


def test_production_preflight_still_rejects_bad_manifests(tmp_path: Path) -> None:
    """The approval must stay exact, not merely permissive."""

    paths = _preflight_protected_paths()

    unapproved = _run_manifest_gate(tmp_path, paths[:-1] + ["/etc/geem/attacker"])
    assert unapproved.returncode != 0
    assert "unapproved path" in unapproved.stderr

    substring = _run_manifest_gate(
        tmp_path, paths[:-1] + [paths[-1] + ".attacker"]
    )
    assert substring.returncode != 0
    assert "unapproved path" in substring.stderr

    duplicated = _run_manifest_gate(tmp_path, paths[:-1] + [paths[0]])
    assert duplicated.returncode != 0
    assert "missing or duplicated" in duplicated.stderr

    short = _run_manifest_gate(tmp_path, paths[:-1])
    assert short.returncode != 0
    assert "exactly 23 paths" in short.stderr


def test_production_preflight_rejects_project_label_orphans_directly() -> None:
    preflight = (REPO_ROOT / "infra/systemd/geem-production-preflight").read_text()

    assert "project=geem-production" in preflight
    assert "com.geem.production.install" in preflight
    assert "/usr/bin/docker ps -aq" in preflight
    assert (
        '--filter "label=com.docker.compose.project=$project"'
        in preflight
    )
    assert 'index .Config.Labels "com.docker.compose.project"' in preflight
    assert 'index .Config.Labels "com.docker.compose.service"' in preflight
    assert '--filter "label=com.docker.compose.service=$service"' in preflight
    assert 'managed start requires every production container to be stopped' in preflight
    assert '/usr/bin/docker ps -q \\' in preflight
    assert '--filter "label=com.geem.production.install=$install_id"' in preflight
    for allowed_service in (
        "postgres",
        "redis",
        "qdrant",
        "minio",
        "minio-init",
        "api",
        "worker",
        "beat",
        "app-egress-proxy",
        "mcp-egress-gateway",
        "mcp-egress-proxy",
        "workspace_web",
        "dashboard_web",
        "landpage_web",
        "cloudflared",
    ):
        assert allowed_service in preflight
    assert "orphan" in preflight.lower()
    assert "duplicate" in preflight.lower() or "more than one" in preflight.lower()
    assert '[ "$count" -le 1 ]' in preflight
    assert "--remove-orphans" not in preflight


def test_deployment_pins_image_staging_and_persistent_artifacts() -> None:
    deployment = (REPO_ROOT / "docs/deployment.md").read_text()
    image_staging = deployment.split(
        "## 6. Retrieve and pin the CI-verified images", maxsplit=1
    )[1].split("## 7. Create the new Cloudflare Tunnel", maxsplit=1)[0]
    persistence = deployment.split(
        "## 10. Make the stack persistent", maxsplit=1
    )[1].split("## 11. Release traffic", maxsplit=1)[0]

    assert "pull --ignore-buildable --policy always" not in image_staging
    assert "\n  build --pull \\" not in image_staging
    assert "@sha256:" in image_staging
    assert "digest" in image_staging.lower()
    assert "Production image publication" in image_staging
    assert "production-images.yml" in image_staging
    assert "successful run" in image_staging.lower()
    assert "GHCR" in image_staging
    assert "Never run a production-host `docker build`" in image_staging
    assert "tag" in image_staging.lower()
    assert "source_sha" in image_staging
    assert "manifest.json.sha256" in image_staging

    assert "install" in persistence
    assert "0644" in persistence
    assert "0755" in persistence
    for source, destination in (
        (
            "infra/systemd/geem-production.service",
            "/etc/systemd/system/geem-production.service",
        ),
        (
            "infra/systemd/geem-production-preflight",
            "/usr/local/sbin/geem-production-preflight",
        ),
        (
            "infra/systemd/geem-production-verify",
            "/usr/local/sbin/geem-production-verify",
        ),
        (
            "infra/systemd/geem-production-stop",
            "/usr/local/sbin/geem-production-stop",
        ),
    ):
        assert source in persistence
        assert destination in persistence
    assert "/opt/geem/current/infra/mcp-egress/verify-isolation.sh" in persistence
    assert "/etc/geem/install-id" in persistence
    assert (
        "/opt/geem/current/infra/mcp-egress/proxy/static-deny-networks.txt"
        in persistence
    )


def test_production_publication_builds_and_verifies_exact_locked_images() -> None:
    workflow = (REPO_ROOT / ".github/workflows/production-images.yml").read_text()

    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", use) for use in uses)
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.head_sha" in workflow
    assert "platforms: linux/amd64" in workflow
    assert workflow.count("uses: docker/build-push-action@") == 8
    assert "python -m pytest -q -p no:cacheprovider tests/unit tests/integration" in workflow
    frontend_verification = workflow.split(
        "- name: Verify the exact published frontend images", maxsplit=1
    )[1].split("- name: Create exact-SHA production image manifest", maxsplit=1)[0]
    assert frontend_verification.count(
        "--tmpfs /run:rw,noexec,nosuid,nodev"
    ) == 3
    assert "(.images | length) == 8" in workflow
    assert "(.build_bases | length) == 5" in workflow
    assert "(.runtime_images | length) == 5" in workflow
    relay_verification = workflow.split(
        "- name: Verify the exact published mail relay image", maxsplit=1
    )[1].split("- name: Exercise the exact locked third-party runtimes", maxsplit=1)[0]
    # A relay that starts without a complete upstream account would submit mail
    # unauthenticated, so publication must prove the renderer fails closed.
    assert relay_verification.count("require_fail_closed") == 4
    assert "MAIL_RELAY_UPSTREAM_PORT=25" in relay_verification
    assert "not-a-real-secret /run/geem-msmtprc" in relay_verification
    assert "sha256sum manifest.json > manifest.json.sha256" in workflow
    assert "sha256sum --check manifest.json.sha256" in workflow

    for relative_path, expected_keys in (
        (
            "infra/images/production-build-bases.env",
            {
                "API_PYTHON_BASE_IMAGE",
                "MCP_GATEWAY_PYTHON_BASE_IMAGE",
                "PROXY_UBUNTU_BASE_IMAGE",
                "FRONTEND_NODE_BASE_IMAGE",
                "FRONTEND_NGINX_BASE_IMAGE",
            },
        ),
        (
            "infra/images/production-runtime-images.env",
            {
                "POSTGRES_RUNTIME_IMAGE",
                "REDIS_RUNTIME_IMAGE",
                "QDRANT_RUNTIME_IMAGE",
                "MINIO_RUNTIME_IMAGE",
                "CLOUDFLARED_RUNTIME_IMAGE",
            },
        ),
    ):
        records = {}
        for line in (REPO_ROOT / relative_path).read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", maxsplit=1)
            records[key] = value
        assert records.keys() == expected_keys
        assert all(
            re.fullmatch(r"[a-z0-9._:/-]+@sha256:[0-9a-f]{64}", value)
            for value in records.values()
        )


def test_mcp_enable_uses_managed_restart_and_runtime_verification() -> None:
    connectors = (REPO_ROOT / "docs/integrations/mcp-connectors.md").read_text()
    enable = connectors.split(
        "### 11. Enable production MCP only after RC sign-off",
        maxsplit=1,
    )[1].split("## Kubernetes or non-Compose equivalent", maxsplit=1)[0]

    preflight = "sudo /usr/local/sbin/geem-production-preflight"
    managed_stop = "sudo systemctl stop geem-production.service"
    managed_start = "sudo systemctl start geem-production.service"
    runtime_verify = "sudo /usr/local/sbin/geem-production-verify runtime"
    assert managed_stop in enable
    assert preflight in enable
    assert managed_start in enable
    assert runtime_verify in enable
    assert (
        enable.index(managed_stop)
        < enable.index(preflight)
        < enable.index(managed_start)
        < enable.index(runtime_verify)
    )
    assert "sudo systemctl restart geem-production.service" not in enable
    assert "Cloudflare WAF maintenance hold" in enable
    assert "sudo /usr/local/sbin/geem-production-verify internal" not in enable


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
    static_manifest = (
        REPO_ROOT / "infra/mcp-egress/proxy/static-deny-networks.txt"
    ).read_text()
    assert "acl CONNECT method CONNECT" in config
    assert "http_access deny blocked_destination" in config
    assert "http_access deny !CONNECT" in config
    assert "# __GEEM_STATIC_BLOCKS__" in config
    assert "169.254.0.0/16" in static_manifest
    assert "10.0.0.0/8" in static_manifest
    assert "8000::/1" in static_manifest
    assert "access_log none" in config

    app_config = (REPO_ROOT / "infra/app-egress/proxy/squid.conf").read_text()
    assert "acl fixed_provider dstdomain" in app_config
    assert "http_access allow fixed_provider" in app_config
    assert "http_access deny all" in app_config
    assert "access_log none" in app_config


def test_static_proxy_manifest_matches_api_policy_representatives() -> None:
    networks = tuple(
        ipaddress.ip_network(line, strict=True)
        for line in (
            REPO_ROOT / "infra/mcp-egress/proxy/static-deny-networks.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    blocked_addresses = (
        "10.0.0.1",
        "100.64.0.1",
        "168.63.129.16",
        "192.0.2.1",
        "5f00::1",
        "4000::1",
        "6000::1",
        "8000::1",
        "2001::1",
    )
    public_controls = ("1.1.1.1", "2606:4700:4700::1111")

    for address in blocked_addresses:
        parsed_address = ipaddress.ip_address(address)
        assert any(
            parsed_address.version == network.version
            and parsed_address in network
            for network in networks
        ), address

    for address in public_controls:
        parsed_address = ipaddress.ip_address(address)
        assert not any(
            parsed_address.version == network.version
            and parsed_address in network
            for network in networks
        ), address


def test_every_checked_in_api_launch_disables_uvicorn_request_line_logging() -> None:
    launch_files = (
        REPO_ROOT / "apps/api/Dockerfile",
        REPO_ROOT / "infra/docker-compose.yml",
        REPO_ROOT / "infra/docker-compose.tunnel.yml",
        REPO_ROOT / "docs/deployment.md",
        REPO_ROOT / "docs/development.md",
    )

    for path in launch_files:
        text = path.read_text(encoding="utf-8")
        assert "uvicorn" in text and "app.main:app" in text, path
        assert "--no-access-log" in text, path


def test_deployed_isolation_smoke_covers_live_release_boundaries() -> None:
    script = (REPO_ROOT / "infra/mcp-egress/verify-isolation.sh").read_text()

    assert "MCP_SMOKE_COMPOSE_WRAPPER" in script
    assert '"$COMPOSE_WRAPPER" "$@"' in script
    assert "require_exactly_one_running beat" in script
    assert "require_exactly_one_running mcp-egress-gateway" in script
    assert "--cert /run/secrets/mcp-egress/client.crt" in script
    assert "gateway accepted a caller without a client certificate" in script
    assert "postgres:5432 redis:6379 qdrant:6333 minio:9000" in script
    assert "require_unreachable beat postgres:5432 qdrant:6333 minio:9000" in script
    assert "for service in api worker beat mcp-egress-gateway" in script
    assert "1.1.1.1" in script
    assert 'os.getenv("EGRESS_BLOCKED_NETWORKS"' in script
    assert (
        "STATIC_DENY_MANIFEST=$REPO_ROOT/infra/mcp-egress/proxy/"
        "static-deny-networks.txt"
    ) in script
    assert 'done < "$STATIC_DENY_MANIFEST"' in script
    assert 'b" 403 "' in script
    assert 'b" 200 "' in script
    assert "mcp-egress-proxy" in script
