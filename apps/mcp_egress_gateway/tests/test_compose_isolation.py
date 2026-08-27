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
        "application_broker",
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


def test_production_runbooks_support_collision_safe_project_handoff() -> None:
    production = (
        REPO_ROOT / "docs/integrations/mcp-production-deployment.md"
    ).read_text()
    connectors = (REPO_ROOT / "docs/integrations/mcp-connectors.md").read_text()

    assert "GEEM_LEGACY_COMPOSE_PROJECT" in production
    assert "GEEM_LEGACY_GEEM_CONTAINER_IDS" in production
    assert "GEEM_LEGACY_POSTGRES_CONTAINER_ID" in production
    assert 'docker exec "$GEEM_LEGACY_POSTGRES_CONTAINER_ID" pg_dump' in production
    assert 'docker compose -p "$GEEM_LEGACY_COMPOSE_PROJECT"' not in production
    assert "com.docker.compose.project.working_dir" in production
    assert "com.docker.compose.project.config_files" in production
    assert "Compose-namespace transition, not a data copy" in production
    assert "Do not stop/remove a foreign container" in production
    assert "project='<approved-release-compose-project>'" in production
    assert "project='<approved-existing-compose-project>'" not in production
    assert "ExecStop=\nExecStopPost=" in production
    assert "GEEM_LEGACY_STOP_IDS" in production
    assert 'docker stop --time 60 "$container_id"' in production
    assert production.count("TimeoutStopSec=240") == 2

    identity_baseline = production.split(
        "After review, record only the exact Geem-owned legacy IDs", maxsplit=1
    )[1].split("Do not paste mount host paths", maxsplit=1)[0]
    checked_state_assignment = (
        'running=$(docker inspect "$container_id" --format \'{{.State.Running}}\')'
    )
    assert "set -eu" in identity_baseline
    assert checked_state_assignment in identity_baseline
    assert 'if [ "$(docker inspect' not in identity_baseline

    mount_inventory = production.split(
        "Record the exact live datastore mounts", maxsplit=1
    )[1].split("Store this redacted mapping", maxsplit=1)[0]
    assert "container_count=$((container_count + 1))" in mount_inventory
    assert 'docker inspect "$container_id" --format \'{{json .Mounts}}\'' in mount_inventory
    assert 'docker inspect "$container_ids"' not in mount_inventory

    backup = production.split(
        "A PostgreSQL custom-format example", maxsplit=1
    )[1].split("The restore drill is mandatory", maxsplit=1)[0]
    dump_call = 'docker exec "$GEEM_LEGACY_POSTGRES_CONTAINER_ID" pg_dump'
    dump_call_index = backup.index(dump_call)
    for required_check in (
        "com.docker.compose.project.working_dir",
        "com.docker.compose.project.config_files",
        "com.docker.compose.service",
        "{{.State.Running}}",
        "legacy postgres physical volume changed",
    ):
        assert backup.index(required_check) < dump_call_index

    handoff = production.split(
        "If the reviewed legacy `ExecStop` was not invoked", maxsplit=1
    )[1].split("Pre-Phase-13 datastores", maxsplit=1)[0]
    assert "GEEM_LEGACY_RUNNING_CONTAINER_IDS" in handoff
    assert "GEEM_LEGACY_NONRUNNING_CONTAINER_IDS" in handoff
    assert "for container_id in $GEEM_LEGACY_GEEM_CONTAINER_IDS; do" in handoff
    assert "legacy_running_after_handoff" in handoff
    assert checked_state_assignment in handoff
    assert 'if [ "$(docker inspect' not in handoff
    assert handoff.index('docker stop --time 60 "$container_id"') < handoff.index(
        'test -z "$legacy_running_after_handoff"'
    )

    migration = "geem-prod-compose run --rm --no-deps api alembic upgrade head"
    normal_start = "geem-prod-compose up -d --wait --wait-timeout 300"
    assert production.index(migration) < production.index(normal_start)
    production_words = " ".join(production.split())
    production_hold = (
        "Before any release-project start, prove that this control still serves"
    )
    production_first_start = "geem-prod-compose up -d \\ postgres redis"
    production_failure_test = (
        "Before accepting the supervisor, prove fail-start containment deliberately"
    )
    production_reboot = "Perform a controlled reboot in the maintenance plan."
    production_release = "release the independent ingress maintenance control"
    assert (
        production_words.index(production_hold)
        < production_words.index(production_first_start)
        < production_words.index(normal_start)
        < production_words.index(production_failure_test)
        < production_words.index(production_reboot)
        < production_words.index(production_release)
    )
    assert "unrelated host Cloudflared or Apache service" in production_words
    assert (
        "running `cloudflared` container is not an ingress-release event"
        in production_words
    )

    assert "legacy project label collides with another repository" in connectors
    production_procedure = connectors.split(
        "## Production deployment procedure", maxsplit=1
    )[1]
    assert production_procedure.count("geem_compose() {") == 1
    assert production_procedure.count("\ndocker compose \\") == 0
    helper_start = production_procedure.index("geem_compose() {")
    helper_end = production_procedure.index("\n}\n", helper_start)
    helper = production_procedure[helper_start:helper_end]
    assert '--project-name "$COMPOSE_PROJECT_NAME"' in helper
    connector_migration = (
        "geem_compose run --rm --no-deps api alembic upgrade head"
    )
    connector_start = "geem_compose up -d --wait --wait-timeout 300"
    assert production_procedure.index(
        connector_migration
    ) < production_procedure.index(connector_start)
    connector_words = " ".join(production_procedure.split())
    connector_hold = "Before the first release-project `geem_compose up`, prove"
    connector_first_start = "geem_compose up -d \\ postgres redis"
    assert (
        connector_words.index(connector_hold)
        < connector_words.index(connector_first_start)
        < connector_words.index(connector_migration)
        < connector_words.index(connector_start)
    )
    assert "The final `geem_compose up` starts `cloudflared`" in connector_words
    assert "a running tunnel is not authorization to release traffic" in connector_words
    assert "unrelated host Cloudflared or Apache service" in connector_words


def test_failure_test_manifest_is_activated_at_the_canonical_unit_path() -> None:
    production = (
        REPO_ROOT / "docs/integrations/mcp-production-deployment.md"
    ).read_text()
    connectors = (REPO_ROOT / "docs/integrations/mcp-connectors.md").read_text()
    production_words = " ".join(production.split())
    connector_words = " ".join(connectors.split())

    permanent_preservation = (
        "Before installing any deliberate-failure drop-in, preserve the exact "
        "approved permanent manifest bytes"
    )
    temporary_evidence = (
        "Create a separately named `root:root` mode-`0444` temporary evidence "
        "manifest"
    )
    temporary_includes_dropin = (
        "using the same exact path list as the permanent manifest plus this one "
        "exact drop-in"
    )
    temporary_staging = (
        "previously nonexistent staging file in `/etc/geem`, on the same "
        "filesystem as the canonical manifest"
    )
    temporary_activation = "then rename it over the canonical path"
    temporary_verification = (
        "remains `root:root` mode `0444`, and passes `sha256sum --check --strict`"
    )
    reload_for_failure = "Reload the one discovered system/user scope and start"
    failure_evidence = "deliberate readiness failure: zero project containers running"
    confirmed_failure = (
        "With the deliberate start job failed, the unit confirmed non-running, "
        "zero project containers running"
    )
    remove_only_dropin = "remove only that exact temporary drop-in"
    permanent_restore = (
        "Put the exact preserved permanent manifest bytes—not a regenerated manifest—"
        "into a new, previously nonexistent staging file in `/etc/geem`"
    )
    restored_verification = (
        "Require the restored canonical file to remain `root:root` mode `0444`, "
        "its checksum to equal the previously recorded permanent evidence checksum"
    )
    normal_start = "Only then reload the same scope and start normally"

    assert (
        production_words.index(permanent_preservation)
        < production_words.index(temporary_evidence)
        < production_words.index(temporary_includes_dropin)
        < production_words.index(temporary_staging)
        < production_words.index(temporary_activation)
        < production_words.index(temporary_verification)
        < production_words.index(reload_for_failure)
        < production_words.index(failure_evidence)
        < production_words.index(confirmed_failure)
        < production_words.index(remove_only_dropin)
        < production_words.index(permanent_restore)
        < production_words.index(restored_verification)
        < production_words.index(normal_start)
    )
    assert (
        "An alternate filename alone is not active because `ExecStartPre` checks "
        "only `/etc/geem/phase13-start-artifacts.sha256`"
        in production_words
    )
    assert (
        "a separately named test manifest is not active by itself"
        in connector_words
    )
    assert (
        "atomically install those temporary bytes at the canonical path before "
        "reload/start"
        in connector_words
    )
    assert (
        "previously nonexistent staging file on the canonical path's filesystem"
        in connector_words
    )
    assert "leave the canonical file `root:root` mode `0444`" in connector_words
    assert "failed/non-running test state is proven" in connector_words
    assert "do not regenerate the permanent manifest" in connector_words


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
