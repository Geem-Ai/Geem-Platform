from __future__ import annotations

import hashlib
from collections.abc import Callable

import pytest

from app.ops.validate_production_compose import (
    API_HEALTHCHECK,
    BOUNDARY_RUNTIME_CONTRACTS,
    CLOUDFLARED_COMMAND,
    MINIO_INIT_ENTRYPOINT,
    MINIO_INIT_IMAGE,
    MINIO_SERVER_ENTRYPOINT,
    POSTGRES_HEALTHCHECK,
    QDRANT_HEALTHCHECK,
    REDIS_HEALTHCHECK,
    UNREVIEWED_RUNTIME_FIELDS,
    ValidationOptions,
    validate_production_compose,
)


DIGEST = "sha256:" + ("a" * 64)
NETWORK_NAMES = (
    "application_data",
    "application_broker",
    "application_ingress",
    "application_provider_control",
    "mcp_egress_control",
    "mcp_proxy_control",
    "application_provider_egress",
    "mcp_public_egress",
    "public_egress",
)
BLOCKED_NETWORKS = ",".join(
    [*(f"10.80.{index}.0/24" for index in range(len(NETWORK_NAMES))), "172.17.0.0/16"]
)
MINIO_INIT_SCRIPT = MINIO_INIT_ENTRYPOINT[2]


def _image(name: str) -> str:
    return f"registry.example.invalid/geem/{name}@{DIGEST}"


def _client_secrets() -> list[dict[str, object]]:
    return [
        {
            "source": "mcp_egress_client_cert",
            "target": "/run/secrets/mcp-egress/client.crt",
        },
        {
            "source": "mcp_egress_client_key",
            "target": "/run/secrets/mcp-egress/client.key",
            "mode": 0o400,
        },
        {
            "source": "mcp_egress_ca_cert",
            "target": "/run/secrets/mcp-egress/ca.crt",
        },
    ]


def _server_secrets() -> list[dict[str, object]]:
    return [
        {
            "source": "mcp_egress_server_cert",
            "target": "/run/secrets/mcp-egress/server.crt",
        },
        {
            "source": "mcp_egress_server_key",
            "target": "/run/secrets/mcp-egress/server.key",
            "uid": "10001",
            "gid": "10001",
            "mode": 0o400,
        },
        {
            "source": "mcp_egress_ca_cert",
            "target": "/run/secrets/mcp-egress/ca.crt",
        },
    ]


def _app_environment(*, mcp_enabled: str) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "AUTH_REQUIRED": "true",
        "MCP_CONNECTOR_ENABLED": mcp_enabled,
        "DATABASE_URL": (
            "postgresql+psycopg://geem:prod-db-secret@postgres:5432/geem"
        ),
        "REDIS_URL": "redis://redis:6379/0",
        "QDRANT_URL": "http://qdrant:6333",
        "MINIO_ENDPOINT": "minio:9000",
        "MINIO_ACCESS_KEY": "prod-minio-user",
        "MINIO_SECRET_KEY": "prod-minio-secret",
        "MINIO_BUCKET": "documents",
        "MINIO_SECURE": "false",
        "MCP_EGRESS_GATEWAY_URL": "https://mcp-egress-gateway:8443",
        "MCP_EGRESS_CLIENT_CERT_FILE": "/run/secrets/mcp-egress/client.crt",
        "MCP_EGRESS_CLIENT_KEY_FILE": "/run/secrets/mcp-egress/client.key",
        "MCP_EGRESS_CA_CERT_FILE": "/run/secrets/mcp-egress/ca.crt",
        "HTTP_PROXY": "http://app-egress-proxy:3128",
        "HTTPS_PROXY": "http://app-egress-proxy:3128",
        "NO_PROXY": (
            "localhost,127.0.0.1,api,postgres,redis,qdrant,minio,mcp-egress-gateway"
        ),
    }


def _app_service(
    *, networks: list[str], mcp_enabled: str, command: list[str]
) -> dict[str, object]:
    return {
        "image": _image("api"),
        "networks": {name: None for name in networks},
        "environment": _app_environment(mcp_enabled=mcp_enabled),
        "command": command,
        "secrets": _client_secrets(),
    }


def _boundary_service(
    *, name: str, networks: list[str], user: str, environment: dict[str, str] | None = None
) -> dict[str, object]:
    contract = BOUNDARY_RUNTIME_CONTRACTS[name]
    service: dict[str, object] = {
        "image": _image(name),
        "networks": {network: None for network in networks},
        "user": user,
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": contract["pids_limit"],
        "mem_limit": contract["mem_limit"],
        "tmpfs": list(contract["tmpfs"]),
    }
    if environment is not None:
        service["environment"] = environment
    return service


def _gateway_environment() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "EGRESS_BIND_HOST": "0.0.0.0",
        "EGRESS_BIND_PORT": "8443",
        "EGRESS_SERVER_CERT_FILE": "/run/secrets/mcp-egress/server.crt",
        "EGRESS_SERVER_KEY_FILE": "/run/secrets/mcp-egress/server.key",
        "EGRESS_CLIENT_CA_FILE": "/run/secrets/mcp-egress/ca.crt",
        "EGRESS_FORWARD_PROXY_URL": "http://mcp-egress-proxy:3128",
        "EGRESS_ALLOW_PRIVATE": "false",
        "EGRESS_BLOCKED_NETWORKS": BLOCKED_NETWORKS,
        "EGRESS_SUPPORTED_PROTOCOL_VERSIONS": "2026-07-28,2025-11-25,2024-11-05",
        "EGRESS_MAX_REDIRECTS": "3",
        "EGRESS_MAX_DISCOVERED_TOOLS": "512",
        "EGRESS_MAX_TOOL_PAGES": "64",
        "EGRESS_LEGACY_SESSION_TTL_SECONDS": "300",
        "EGRESS_MAX_LEGACY_SESSIONS": "64",
        "EGRESS_MAX_CONCURRENT_OPERATIONS": "128",
        "EGRESS_MAX_REQUEST_BYTES": "65536",
        "EGRESS_MAX_RESPONSE_BYTES": "262144",
        "EGRESS_CONNECT_TIMEOUT_SECONDS": "5",
        "EGRESS_READ_TIMEOUT_SECONDS": "20",
        "EGRESS_TOTAL_TIMEOUT_SECONDS": "30",
    }


def _valid_config() -> dict[str, object]:
    services: dict[str, dict[str, object]] = {
        "postgres": {
            "image": _image("postgres"),
            "networks": {"application_data": None},
            "environment": {
                "POSTGRES_USER": "geem",
                "POSTGRES_PASSWORD": "prod-db-secret",
                "POSTGRES_DB": "geem",
            },
            "healthcheck": dict(POSTGRES_HEALTHCHECK),
            "volumes": [
                {
                    "type": "volume",
                    "source": "postgres_data",
                    "target": "/var/lib/postgresql/data",
                    "volume": {},
                }
            ],
        },
        "redis": {
            "image": _image("redis"),
            "networks": {"application_broker": None},
            "healthcheck": dict(REDIS_HEALTHCHECK),
            "volumes": [
                {
                    "type": "volume",
                    "source": "redis_data",
                    "target": "/data",
                    "volume": {},
                }
            ],
        },
        "qdrant": {
            "image": _image("qdrant"),
            "networks": {"application_data": None},
            "healthcheck": dict(QDRANT_HEALTHCHECK),
            "volumes": [
                {
                    "type": "volume",
                    "source": "qdrant_data",
                    "target": "/qdrant/storage",
                    "volume": {},
                }
            ],
        },
        "minio": {
            "image": _image("minio"),
            "networks": {"application_data": None},
            "environment": {
                "APP_ENV": "production",
                "MINIO_ROOT_USER": "prod-minio-user",
                "MINIO_ROOT_PASSWORD": "prod-minio-secret",
            },
            "entrypoint": list(MINIO_SERVER_ENTRYPOINT),
            "volumes": [
                {
                    "type": "volume",
                    "source": "minio_data",
                    "target": "/data",
                    "volume": {},
                }
            ],
        },
        "minio-init": {
            "image": MINIO_INIT_IMAGE,
            "networks": {"application_data": None},
            "environment": {
                "APP_ENV": "production",
                "MINIO_ACCESS_KEY": "prod-minio-user",
                "MINIO_SECRET_KEY": "prod-minio-secret",
                "MINIO_BUCKET": "documents",
            },
            "entrypoint": list(MINIO_INIT_ENTRYPOINT),
        },
        "api": _app_service(
            networks=[
                "application_data",
                "application_broker",
                "application_ingress",
                "application_provider_control",
                "mcp_egress_control",
            ],
            mcp_enabled="false",
            command=[
                "sh",
                "-c",
                (
                    "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 "
                    "--port 8000 --no-access-log"
                ),
            ],
        ),
        "worker": _app_service(
            networks=[
                "application_data",
                "application_broker",
                "application_provider_control",
                "mcp_egress_control",
            ],
            mcp_enabled="false",
            command=[
                "celery",
                "-A",
                "app.worker.celery_app",
                "worker",
                "--loglevel=INFO",
                "--concurrency=2",
            ],
        ),
        "beat": {
            "image": _image("api"),
            "networks": {"application_broker": None},
            "environment": {
                "APP_ENV": "production",
                "REDIS_URL": "redis://redis:6379/0",
                "MCP_CONNECTOR_ENABLED": "false",
            },
            "command": [
                "celery",
                "-A",
                "app.worker.beat_app:beat_app",
                "beat",
                "--loglevel=INFO",
                "--schedule",
                "/tmp/celerybeat-schedule",
            ],
            "deploy": {"replicas": 1},
        },
        "app-egress-proxy": _boundary_service(
            name="app-egress-proxy",
            networks=["application_provider_control", "application_provider_egress"],
            user="13:13",
        ),
        "mcp-egress-gateway": _boundary_service(
            name="mcp-egress-gateway",
            networks=["mcp_egress_control", "mcp_proxy_control"],
            user="10001:10001",
            environment=_gateway_environment(),
        ),
        "mcp-egress-proxy": _boundary_service(
            name="mcp-egress-proxy",
            networks=["mcp_proxy_control", "mcp_public_egress"],
            user="13:13",
            environment={
                "MCP_PROXY_BLOCKED_NETWORKS": BLOCKED_NETWORKS,
                "MCP_PROXY_REQUIRE_BLOCKED_NETWORKS": "true",
            },
        ),
        "workspace_web": {
            "image": _image("workspace-web"),
            "networks": {"application_ingress": None},
            "command": ["nginx", "-g", "daemon off;"],
        },
        "dashboard_web": {
            "image": _image("dashboard-web"),
            "networks": {"application_ingress": None},
            "command": ["nginx", "-g", "daemon off;"],
        },
        "landpage_web": {
            "image": _image("landpage-web"),
            "networks": {"application_ingress": None},
            "command": ["nginx", "-g", "daemon off;"],
        },
        "cloudflared": {
            **_boundary_service(
                name="cloudflared",
                networks=["application_ingress", "public_egress"],
                user="65532:65532",
            ),
            "command": list(CLOUDFLARED_COMMAND),
            "configs": [
                {
                    "source": "cloudflared_config",
                    "target": "/etc/cloudflared/config.yml",
                    "uid": "65532",
                    "gid": "65532",
                    "mode": 0o444,
                }
            ],
            "secrets": [
                {
                    "source": "cloudflared_credentials",
                    "target": "/etc/cloudflared/credentials.json",
                    "uid": "65532",
                    "gid": "65532",
                    "mode": 0o400,
                }
            ],
        },
    }
    for name, service in services.items():
        if name != "minio-init":
            service["restart"] = "unless-stopped"
    services["api"]["healthcheck"] = dict(API_HEALTHCHECK)
    services["mcp-egress-gateway"]["deploy"] = {"replicas": 1}
    services["mcp-egress-gateway"]["profiles"] = ["mcp"]
    services["mcp-egress-proxy"]["profiles"] = ["mcp"]
    services["mcp-egress-gateway"]["secrets"] = _server_secrets()
    services["mcp-egress-proxy"]["entrypoint"] = [
        "python3",
        "/usr/local/lib/geem/render_mcp_proxy_config.py",
    ]

    networks = {
        name: {
            "name": f"infra_{name}",
            "internal": index < 6,
            "ipam": {"config": [{"subnet": f"10.80.{index}.0/24"}]},
        }
        for index, name in enumerate(NETWORK_NAMES)
    }
    volumes = {
        name: {"name": f"infra_{name}", "external": True}
        for name in ("postgres_data", "redis_data", "qdrant_data", "minio_data")
    }
    secrets = {
        "mcp_egress_ca_cert": {"file": "/etc/geem/mcp-egress/ca/ca.crt"},
        "mcp_egress_server_cert": {
            "file": "/etc/geem/mcp-egress/server/server.crt"
        },
        "mcp_egress_server_key": {
            "file": "/etc/geem/mcp-egress/server/server.key"
        },
        "mcp_egress_client_cert": {
            "file": "/etc/geem/mcp-egress/client/client.crt"
        },
        "mcp_egress_client_key": {
            "file": "/etc/geem/mcp-egress/client/client.key"
        },
        "cloudflared_credentials": {
            "name": "infra_cloudflared_credentials",
            "file": "/etc/geem/cloudflared/credentials.json"
        },
    }
    return {
        "name": "infra",
        "services": services,
        "networks": networks,
        "volumes": volumes,
        "configs": {
            "cloudflared_config": {
                "name": "infra_cloudflared_config",
                "file": "/etc/geem/cloudflared/config.yml",
            }
        },
        "secrets": secrets,
    }


def _options(
    *,
    mcp_enabled: bool = False,
    ingress_services: frozenset[str] = frozenset({"cloudflared"}),
    allow_local_image_ids: bool = False,
) -> ValidationOptions:
    return ValidationOptions(
        project="infra",
        mcp_enabled=mcp_enabled,
        ingress_services=ingress_services,
        physical_volumes={
            "postgres_data": "infra_postgres_data",
            "redis_data": "infra_redis_data",
            "qdrant_data": "infra_qdrant_data",
            "minio_data": "infra_minio_data",
        },
        required_blocked_networks=(),
        allow_local_image_ids=allow_local_image_ids,
    )


def _services(config: dict[str, object]) -> dict[str, dict[str, object]]:
    return config["services"]  # type: ignore[return-value]


def _errors(config: dict[str, object], **options: object) -> list[str]:
    return validate_production_compose(config, _options(**options))  # type: ignore[arg-type]


def test_accepts_exact_digest_pinned_isolated_topology() -> None:
    assert _errors(_valid_config()) == []


def test_local_image_ids_require_explicit_single_host_opt_in() -> None:
    config = _valid_config()
    services = _services(config)
    local_ids: dict[str, str] = {}
    for service_name, service in services.items():
        service["pull_policy"] = "never"
        if service_name == "minio-init":
            continue
        identity = "api" if service_name in {"api", "worker", "beat"} else service_name
        local_id = "sha256:" + hashlib.sha256(identity.encode()).hexdigest()
        service["image"] = local_id
        local_ids[service_name] = local_id

    default_errors = _errors(config)
    assert any("api image is not pinned" in error for error in default_errors)
    assert any(
        "api overrides the reviewed image pull policy" in error
        for error in default_errors
    )
    assert _errors(config, allow_local_image_ids=True) == []
    assert local_ids["api"] == local_ids["worker"] == local_ids["beat"]

    del services["worker"]["pull_policy"]
    errors = _errors(config, allow_local_image_ids=True)
    assert any("worker must use pull_policy never" in error for error in errors)


def test_local_image_opt_in_still_rejects_tags_and_malformed_ids() -> None:
    config = _valid_config()
    for service in _services(config).values():
        service["pull_policy"] = "never"
    _services(config)["api"]["image"] = "geem/api:latest"

    errors = _errors(config, allow_local_image_ids=True)

    assert any("api image is not pinned" in error for error in errors)


def test_enabled_release_still_requires_beat_to_be_disabled() -> None:
    config = _valid_config()
    services = _services(config)
    services["api"]["environment"]["MCP_CONNECTOR_ENABLED"] = "true"  # type: ignore[index]
    services["worker"]["environment"]["MCP_CONNECTOR_ENABLED"] = "true"  # type: ignore[index]

    assert _errors(config, mcp_enabled=True) == []

    services["beat"]["environment"]["MCP_CONNECTOR_ENABLED"] = "true"  # type: ignore[index]
    errors = _errors(config, mcp_enabled=True)
    assert any("beat MCP_CONNECTOR_ENABLED" in error for error in errors)


def test_rejects_rogue_service_even_without_public_network_membership() -> None:
    config = _valid_config()
    _services(config)["rogue"] = {
        "image": _image("rogue"),
        "networks": {"application_data": None},
    }

    assert "rendered topology contains an unreviewed service" in _errors(config)


def test_ingress_flag_cannot_reclassify_a_core_service() -> None:
    config = _valid_config()
    del _services(config)["cloudflared"]

    errors = _errors(config, ingress_services=frozenset({"api"}))

    assert "--ingress-service cannot reclassify a core Geem service" in errors


@pytest.mark.parametrize(
    ("service_name", "networks"),
    [
        ("redis", {"application_data": None}),
        ("beat", {"application_data": None}),
        (
            "api",
            {
                "application_data": None,
                "application_ingress": None,
                "application_provider_control": None,
                "mcp_egress_control": None,
            },
        ),
        (
            "worker",
            {
                "application_data": None,
                "application_provider_control": None,
                "mcp_egress_control": None,
            },
        ),
    ],
)
def test_requires_the_dedicated_application_broker_network(
    service_name: str, networks: dict[str, None]
) -> None:
    config = _valid_config()
    _services(config)[service_name]["networks"] = networks

    assert any(
        f"{service_name} has an unexpected network membership" in error
        for error in _errors(config)
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("env_file", ["/run/secrets/application.env"], "must not receive an env_file"),
        ("environment", {"TOKEN": "secret"}, "must not receive environment values"),
        ("command", ["sh", "-c", "sleep infinity"], "exact reviewed tunnel command"),
        ("entrypoint", ["sh", "-c"], "exact reviewed tunnel command"),
        (
            "configs",
            [{"source": "tunnel", "target": "/config"}],
            "exact reviewed config mount",
        ),
        (
            "configs",
            [
                {
                    "source": "cloudflared_config",
                    "target": "/etc/cloudflared/config.yml",
                    "uid": "65532",
                    "gid": "65532",
                    "mode": 0o777,
                }
            ],
            "exact reviewed config mount",
        ),
        (
            "secrets",
            [
                {
                    "source": "mcp_egress_ca_cert",
                    "target": "/run/secrets/borrowed-ca.crt",
                }
            ],
            "exact reviewed credential mount",
        ),
        (
            "secrets",
            [
                {
                    "source": "cloudflared_credentials",
                    "target": "/etc/cloudflared/credentials.json",
                    "uid": "0",
                    "gid": "65532",
                    "mode": 0o400,
                }
            ],
            "exact reviewed credential mount",
        ),
    ],
)
def test_ingress_role_does_not_approve_runtime_or_secret_injection(
    field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    _services(config)["cloudflared"][field] = value

    assert any(expected in error for error in _errors(config))


def test_rejects_unreviewed_in_compose_ingress_name() -> None:
    config = _valid_config()
    services = _services(config)
    services["haproxy"] = services.pop("cloudflared")

    errors = _errors(config, ingress_services=frozenset({"haproxy"}))

    assert any(
        "requires the exact reviewed cloudflared ingress" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("declaration_kind", "name", "value", "expected"),
    [
        (
            "configs",
            "cloudflared_config",
            {"file": ""},
            "cloudflared config must use one non-empty absolute file source",
        ),
        (
            "secrets",
            "cloudflared_credentials",
            {"external": True},
            "cloudflared credentials must use one non-empty absolute file source",
        ),
    ],
)
def test_cloudflared_top_level_resources_require_exact_file_declarations(
    declaration_kind: str, name: str, value: object, expected: str
) -> None:
    config = _valid_config()
    config[declaration_kind][name] = value  # type: ignore[index]

    assert expected in _errors(config)


def test_external_ingress_mode_is_not_approved_by_this_release_contract() -> None:
    config = _valid_config()
    del _services(config)["cloudflared"]

    errors = _errors(config, ingress_services=frozenset())

    assert any(
        "requires the exact reviewed cloudflared ingress" in error
        for error in errors
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda config: _services(config)["mcp-egress-proxy"].update(
            {
                "volumes": [
                    {
                        "type": "volume",
                        "source": "postgres_data",
                        "target": "/dump",
                    }
                ]
            }
        ),
        lambda config: _services(config)["postgres"]["volumes"].append(  # type: ignore[union-attr]
            {
                "type": "volume",
                "source": "postgres_data",
                "target": "/duplicate",
            }
        ),
        lambda config: config["volumes"].update(  # type: ignore[union-attr]
            {"unreviewed_data": {"name": "infra_unreviewed_data", "external": True}}
        ),
        lambda config: _services(config)["postgres"]["volumes"][0].update(  # type: ignore[index]
            {"source": "redis_data"}
        ),
    ],
)
def test_rejects_extra_duplicate_or_incorrect_volume_mounts(
    mutation: Callable[[dict[str, object]], object],
) -> None:
    config = _valid_config()
    mutation(config)

    errors = _errors(config)

    assert any(
        "option-free datastore map" in error
        or "exactly the four reviewed datastore volumes" in error
        or "persistent mount changed logical volume identity" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("read_only", True),
        ("consistency", "cached"),
        ("bind", {"propagation": "rshared"}),
        ("tmpfs", {"size": 1024}),
    ],
)
def test_rejects_extra_persistent_mount_options(field: str, value: object) -> None:
    config = _valid_config()
    _services(config)["postgres"]["volumes"][0][field] = value  # type: ignore[index]

    assert any("option-free datastore map" in error for error in _errors(config))


@pytest.mark.parametrize(
    "volume_options",
    [
        {"nocopy": True},
        {"subpath": "tenant-a"},
        {"nocopy": False},
    ],
)
def test_rejects_persistent_volume_subpath_or_nocopy_options(
    volume_options: dict[str, object],
) -> None:
    config = _valid_config()
    _services(config)["postgres"]["volumes"][0]["volume"] = volume_options  # type: ignore[index]

    assert any("option-free datastore map" in error for error in _errors(config))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("driver", "local"),
        ("driver_opts", {"type": "none", "device": "/host/data"}),
        ("labels", {"unreviewed": "true"}),
    ],
)
def test_rejects_extra_top_level_volume_declaration_options(
    field: str, value: object
) -> None:
    config = _valid_config()
    config["volumes"]["postgres_data"][field] = value  # type: ignore[index]

    assert any(
        "postgres_data declaration must contain exactly name and external" in error
        for error in _errors(config)
    )


@pytest.mark.parametrize("service_name", ["postgres", "redis", "qdrant", "minio"])
def test_rejects_tmpfs_on_every_datastore(service_name: str) -> None:
    config = _valid_config()
    _services(config)[service_name]["tmpfs"] = ["/escape:size=1g,exec,suid,dev"]

    assert any(
        f"{service_name} must not receive tmpfs mounts" in error
        for error in _errors(config)
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda config: _services(config)["api"].update(
                {"network_mode": "service:mcp-egress-proxy"}
            ),
            "overrides Compose network isolation",
        ),
        (
            lambda config: _services(config)["mcp-egress-proxy"].update(
                {"entrypoint": ["squid", "-N", "-f", "/etc/squid/squid.conf"]}
            ),
            "bypasses the fail-closed policy renderer",
        ),
        (
            lambda config: _services(config)["redis"].update({"user": "root"}),
            "explicitly overrides its runtime identity to root",
        ),
        (
            lambda config: _services(config)["api"].update(
                {"command": ["uvicorn", "app.main:app"]}
            ),
            "api does not run the reviewed migrate-and-serve command",
        ),
        (
            lambda config: _services(config)["worker"].update(
                {"command": ["celery", "worker"]}
            ),
            "worker does not run the reviewed Celery worker application",
        ),
        (
            lambda config: _services(config)["worker"].update(
                {"configs": [{"source": "runtime", "target": "/runtime"}]}
            ),
            "receives an unreviewed runtime config mount",
        ),
    ],
)
def test_rejects_network_entrypoint_root_command_and_config_bypasses(
    mutation: Callable[[dict[str, object]], object], expected: str
) -> None:
    config = _valid_config()
    mutation(config)

    assert any(expected in error for error in _errors(config))


def test_rejects_external_boundary_membership() -> None:
    config = _valid_config()
    services = _services(config)
    services["app-egress-proxy"]["networks"] = {
        "application_provider_control": None,
        "mcp_public_egress": None,
    }

    errors = _errors(config)

    assert any("app-egress-proxy has an unexpected network membership" in e for e in errors)
    assert any("single-purpose boundary" in e for e in errors)


def test_rejects_undeclared_network() -> None:
    config = _valid_config()
    config["networks"]["rogue_egress"] = {  # type: ignore[index]
        "internal": False,
        "ipam": {"config": [{"subnet": "10.80.99.0/24"}]},
    }

    errors = _errors(config)

    assert "rendered topology contains an unreviewed network" in errors


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda config: config["networks"]["application_data"].update(  # type: ignore[index]
                {"internal": False}
            ),
            "application_data must be an internal network",
        ),
        (
            lambda config: config["networks"]["mcp_public_egress"].update(  # type: ignore[index]
                {"internal": True}
            ),
            "mcp_public_egress cannot be internal",
        ),
        (
            lambda config: config["networks"]["public_egress"].update(  # type: ignore[index]
                {"ipam": {"config": [{"subnet": "10.80.5.0/24"}]}}
            ),
            "production Compose networks contain overlapping IPAM subnets",
        ),
        (
            lambda config: config["networks"]["mcp_proxy_control"].update(  # type: ignore[index]
                {"ipam": {"config": []}}
            ),
            "mcp_proxy_control must declare exactly one explicit IPAM subnet",
        ),
    ],
)
def test_rejects_internal_external_overlapping_or_implicit_networks(
    mutation: Callable[[dict[str, object]], object], expected: str
) -> None:
    config = _valid_config()
    mutation(config)

    assert expected in _errors(config)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("name", "shared-host-network", "project-scoped network identity"),
        ("external", True, "unreviewed network definition fields"),
        ("driver", "host", "default bridge network driver"),
        ("attachable", True, "unreviewed network definition fields"),
        (
            "driver_opts",
            {"com.docker.network.bridge.name": "host0"},
            "unreviewed network definition fields",
        ),
    ],
)
def test_rejects_network_identity_driver_or_boundary_overrides(
    field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    config["networks"]["application_broker"][field] = value  # type: ignore[index]

    assert any(expected in error for error in _errors(config))


@pytest.mark.parametrize(
    "ipam",
    [
        {
            "driver": "custom",
            "config": [{"subnet": "10.80.1.0/24"}],
        },
        {
            "config": [
                {"subnet": "10.80.1.0/24", "gateway": "10.80.1.1"}
            ]
        },
    ],
)
def test_rejects_unreviewed_ipam_options(ipam: dict[str, object]) -> None:
    config = _valid_config()
    config["networks"]["application_broker"]["ipam"] = ipam  # type: ignore[index]

    assert any("exact subnet-only contract" in error for error in _errors(config))


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("aliases", ["redis-shadow"]),
        ("ipv4_address", "10.80.1.99"),
        ("ipv6_address", "fd00::99"),
        ("link_local_ips", ["169.254.1.1"]),
        ("mac_address", "02:42:ac:11:00:02"),
        ("driver_opts", {"com.docker.network.endpoint.exposedports": "80"}),
        ("priority", 1000),
        ("gw_priority", 1000),
        ("interface_name", "eth9"),
    ],
)
def test_rejects_all_per_service_network_attachment_options(
    option: str, value: object
) -> None:
    config = _valid_config()
    _services(config)["redis"]["networks"]["application_broker"] = {  # type: ignore[index]
        option: value
    }

    assert any("unreviewed per-network attachment options" in error for error in _errors(config))


def test_rejects_proxy_policy_drift_and_missing_deployment_coverage() -> None:
    config = _valid_config()
    _services(config)["mcp-egress-proxy"]["environment"][  # type: ignore[index]
        "MCP_PROXY_BLOCKED_NETWORKS"
    ] = "172.17.0.0/16"

    errors = _errors(config)

    assert any("identical non-empty blocked-network set" in error for error in errors)


@pytest.mark.parametrize(
    "script",
    [
        MINIO_INIT_SCRIPT.replace("set -eu\n", "set -u\n", 1),
        MINIO_INIT_SCRIPT.replace(
            (
                'timeout -k 2s 10s mc mb --ignore-existing "local/$${MINIO_BUCKET}"\n'
                'timeout -k 2s 10s mc anonymous set none "local/$${MINIO_BUCKET}"'
            ),
            (
                'timeout -k 2s 10s mc anonymous set none "local/$${MINIO_BUCKET}"\n'
                'timeout -k 2s 10s mc mb --ignore-existing "local/$${MINIO_BUCKET}"'
            ),
        ),
        MINIO_INIT_SCRIPT + "echo unreviewed-extra-command\n",
        MINIO_INIT_SCRIPT + 'mc rb --force "local/$${MINIO_BUCKET}"\n',
    ],
    ids=("missing-set-e", "reordered", "extra", "destructive"),
)
def test_rejects_any_minio_initializer_script_drift(script: str) -> None:
    config = _valid_config()
    _services(config)["minio-init"]["entrypoint"] = [
        "/bin/sh",
        "-c",
        script,
    ]

    assert "minio-init execution differs from its exact reviewed contract" in _errors(
        config
    )


@pytest.mark.parametrize(
    ("service_name", "field", "value", "expected"),
    [
        (
            "minio",
            "entrypoint",
            ["minio", "server", "/tmp"],
            "minio execution differs from its exact reviewed contract",
        ),
        (
            "minio",
            "command",
            ["minio", "server", "/data"],
            "minio execution differs from its exact reviewed contract",
        ),
        (
            "minio-init",
            "command",
            ["mc", "admin", "info", "local"],
            "minio-init execution differs from its exact reviewed contract",
        ),
    ],
)
def test_rejects_minio_command_or_entrypoint_override(
    service_name: str, field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    _services(config)[service_name][field] = value

    assert expected in _errors(config)


def test_rejects_different_digest_pinned_minio_initializer_image() -> None:
    config = _valid_config()
    _services(config)["minio-init"]["image"] = _image("different-minio-client")

    assert "minio-init does not use the exact reviewed image digest" in _errors(config)


@pytest.mark.parametrize(
    ("service_name", "source", "field", "value", "expected"),
    [
        (
            "api",
            "mcp_egress_client_key",
            "source",
            "wrong_client_key",
            "api does not have the exact MCP client PKI mounts",
        ),
        (
            "worker",
            "mcp_egress_client_key",
            "mode",
            0o444,
            "worker MCP client key is not mounted mode 0400",
        ),
        (
            "mcp-egress-gateway",
            "mcp_egress_server_key",
            "source",
            "wrong_server_key",
            "mcp-egress-gateway does not have the exact server PKI mounts",
        ),
        (
            "mcp-egress-gateway",
            "mcp_egress_server_key",
            "uid",
            "0",
            "mcp-egress-gateway server key ownership/mode is unsafe",
        ),
    ],
)
def test_rejects_wrong_secret_sources_modes_and_ownership(
    service_name: str, source: str, field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    mounts = _services(config)[service_name]["secrets"]
    mount = next(item for item in mounts if item["source"] == source)  # type: ignore[union-attr]
    mount[field] = value

    assert expected in _errors(config)


def test_rejects_missing_or_externalized_secret_file_declarations() -> None:
    config = _valid_config()
    secrets = config["secrets"]
    secrets["mcp_egress_client_key"] = {"file": ""}  # type: ignore[index]
    secrets["mcp_egress_server_key"] = {"external": True}  # type: ignore[index]

    errors = _errors(config)

    assert any("has no file source" in error for error in errors)
    assert any("cannot silently switch to external identity" in error for error in errors)


def test_rejects_unbound_top_level_secret_declaration() -> None:
    config = _valid_config()
    config["secrets"]["rogue_secret"] = {"file": "/etc/geem/rogue"}  # type: ignore[index]

    assert any("secret declarations differ" in error for error in _errors(config))


@pytest.mark.parametrize(
    ("key", "service_names", "malformed", "expected"),
    [
        (
            "DATABASE_URL",
            ("api", "worker"),
            "postgresql://geem:db-secret-do-not-print@postgres:bad/geem",
            "DATABASE_URL is malformed",
        ),
        (
            "REDIS_URL",
            ("api", "worker", "beat"),
            "redis://redis:redis-secret-do-not-print",
            "REDIS_URL is malformed",
        ),
        (
            "QDRANT_URL",
            ("api", "worker"),
            "http://qdrant:qdrant-secret-do-not-print",
            "QDRANT_URL is malformed",
        ),
    ],
)
def test_malformed_dependency_urls_are_rejected_without_leaking_values(
    key: str, service_names: tuple[str, ...], malformed: str, expected: str
) -> None:
    config = _valid_config()
    for service_name in service_names:
        _services(config)[service_name]["environment"][key] = malformed  # type: ignore[index]

    errors = _errors(config)

    assert expected in errors
    assert malformed not in "\n".join(errors)


def test_rejects_external_redis_and_qdrant_dependencies() -> None:
    config = _valid_config()
    for service_name in ("api", "worker", "beat"):
        _services(config)[service_name]["environment"][  # type: ignore[index]
            "REDIS_URL"
        ] = "rediss://cache.example.invalid:6379/0"
    for service_name in ("api", "worker"):
        _services(config)[service_name]["environment"][  # type: ignore[index]
            "QDRANT_URL"
        ] = "http://vectors.example.invalid:6333"

    errors = _errors(config)

    assert any("REDIS_URL must use its reviewed internal service identity" in e for e in errors)
    assert any("QDRANT_URL must use its reviewed internal service identity" in e for e in errors)


@pytest.mark.parametrize(
    "service_name",
    [
        "redis",
        "qdrant",
        "workspace_web",
        "dashboard_web",
        "landpage_web",
    ],
)
def test_rejects_environment_injection_into_environmentless_services(
    service_name: str,
) -> None:
    config = _valid_config()
    sentinel = "environment-secret-must-not-leak"
    _services(config)[service_name]["environment"] = {"UNREVIEWED": sentinel}

    errors = _errors(config)
    assert any(f"{service_name} must not receive environment values" in e for e in errors)
    assert sentinel not in "\n".join(errors)


def test_rejects_postgres_environment_outside_identity_allowlist() -> None:
    config = _valid_config()
    sentinel = "postgres-extra-secret-must-not-leak"
    _services(config)["postgres"]["environment"]["EXTRA_SECRET"] = sentinel  # type: ignore[index]

    errors = _errors(config)
    assert "postgres environment differs from its exact identity allowlist" in errors
    assert sentinel not in "\n".join(errors)


@pytest.mark.parametrize(
    "service_name",
    [
        "postgres",
        "redis",
        "qdrant",
        "minio",
        "minio-init",
        "beat",
        "app-egress-proxy",
        "mcp-egress-gateway",
        "mcp-egress-proxy",
        "workspace_web",
        "dashboard_web",
        "landpage_web",
        "cloudflared",
    ],
)
def test_rejects_env_file_outside_api_and_worker(service_name: str) -> None:
    config = _valid_config()
    _services(config)[service_name]["env_file"] = ["/run/secrets/unreviewed.env"]

    assert any(f"{service_name} must not receive an env_file" in e for e in _errors(config))


def test_api_and_worker_may_use_rendered_env_files() -> None:
    config = _valid_config()
    _services(config)["api"]["env_file"] = ["/etc/geem/api.env"]
    _services(config)["worker"]["env_file"] = ["/etc/geem/api.env"]

    assert _errors(config) == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda config: _services(config)["beat"]["environment"].update(
                {"DATABASE_URL": "postgresql://should-not-be-on-beat"}
            ),
            "beat environment exceeds its broker-only allowlist",
        ),
        (
            lambda config: _services(config)["beat"].update(
                {"command": ["celery", "-A", "app.worker.celery_app", "beat"]}
            ),
            "beat does not run the least-privilege Celery Beat application",
        ),
        (
            lambda config: _services(config)["beat"].update(
                {"image": _image("different-api")}
            ),
            "api, worker, and beat must use one exact application image digest",
        ),
        (
            lambda config: _services(config)["beat"].update(
                {"deploy": {"replicas": 2}}
            ),
            "beat must explicitly declare exactly one replica",
        ),
    ],
)
def test_rejects_beat_environment_command_image_or_replica_divergence(
    mutation: Callable[[dict[str, object]], object], expected: str
) -> None:
    config = _valid_config()
    mutation(config)

    assert expected in _errors(config)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        (
            "EGRESS_BIND_HOST",
            "127.0.0.1",
            "mcp-egress-gateway EGRESS_BIND_HOST differs from its reviewed value",
        ),
        (
            "EGRESS_BIND_PORT",
            "9443",
            "mcp-egress-gateway EGRESS_BIND_PORT differs from its reviewed value",
        ),
        (
            "EGRESS_SERVER_CERT_FILE",
            "/tmp/server.crt",
            "mcp-egress-gateway EGRESS_SERVER_CERT_FILE differs from its reviewed value",
        ),
        (
            "EGRESS_SERVER_KEY_FILE",
            "/tmp/server.key",
            "mcp-egress-gateway EGRESS_SERVER_KEY_FILE differs from its reviewed value",
        ),
        (
            "EGRESS_CLIENT_CA_FILE",
            "/tmp/ca.crt",
            "mcp-egress-gateway EGRESS_CLIENT_CA_FILE differs from its reviewed value",
        ),
        (
            "EGRESS_FORWARD_PROXY_URL",
            "http://app-egress-proxy:3128",
            "mcp-egress-gateway EGRESS_FORWARD_PROXY_URL differs from its reviewed value",
        ),
        (
            "EGRESS_ALLOW_PRIVATE",
            "true",
            "mcp-egress-gateway private egress must be disabled",
        ),
    ],
)
def test_rejects_gateway_critical_environment_drift(
    key: str, value: str, expected: str
) -> None:
    config = _valid_config()
    _services(config)["mcp-egress-gateway"]["environment"][key] = value  # type: ignore[index]

    assert expected in _errors(config)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        (
            "EGRESS_SUPPORTED_PROTOCOL_VERSIONS",
            "2024-11-05,2026-07-28",
            "protocol versions are not reviewed",
        ),
        (
            "EGRESS_MAX_REDIRECTS",
            "11",
            "EGRESS_MAX_REDIRECTS is outside its reviewed bound",
        ),
        (
            "EGRESS_TOTAL_TIMEOUT_SECONDS",
            "1",
            "total timeout is shorter than connect timeout",
        ),
    ],
)
def test_rejects_gateway_protocol_or_resource_bound_drift(
    key: str, value: str, expected: str
) -> None:
    config = _valid_config()
    _services(config)["mcp-egress-gateway"]["environment"][key] = value  # type: ignore[index]

    assert any(expected in error for error in _errors(config))


def test_rejects_gateway_environment_identity_or_replica_drift() -> None:
    config = _valid_config()
    gateway = _services(config)["mcp-egress-gateway"]
    del gateway["environment"]["EGRESS_MAX_REDIRECTS"]  # type: ignore[index]
    gateway["user"] = "10002:10002"
    gateway["deploy"] = {"replicas": 2}

    errors = _errors(config)

    assert any("environment differs from its exact least-privilege contract" in e for e in errors)
    assert any("does not use its reviewed unprivileged identity" in e for e in errors)
    assert any("must explicitly declare exactly one replica" in e for e in errors)


@pytest.mark.parametrize("field", ["command", "entrypoint"])
def test_rejects_gateway_command_or_entrypoint_override(field: str) -> None:
    config = _valid_config()
    _services(config)["mcp-egress-gateway"][field] = ["sh", "-c", "sleep infinity"]

    assert any(
        "mcp-egress-gateway overrides its immutable image execution contract" in e
        for e in _errors(config)
    )


@pytest.mark.parametrize("field", ["command", "entrypoint"])
@pytest.mark.parametrize(
    "service_name", ["postgres", "redis", "qdrant", "app-egress-proxy"]
)
def test_rejects_immutable_service_execution_override(
    service_name: str, field: str
) -> None:
    config = _valid_config()
    _services(config)[service_name][field] = ["sh", "-c", "sleep infinity"]

    assert any(
        f"{service_name} overrides its immutable image execution contract" in e
        for e in _errors(config)
    )


def test_rejects_mcp_proxy_command_override() -> None:
    config = _valid_config()
    _services(config)["mcp-egress-proxy"]["command"] = ["squid", "-z"]

    assert any(
        "mcp-egress-proxy overrides its reviewed renderer command" in e
        for e in _errors(config)
    )


@pytest.mark.parametrize(
    ("field", "value"),
    sorted(
        {
            "cgroup": "host",
            "cgroup_parent": "/docker/escape",
            "device_cgroup_rules": ["c 1:3 rwm"],
            "dns": ["169.254.169.254"],
            "dns_opt": ["use-vc"],
            "dns_search": ["internal.example"],
            "extra_hosts": ["metadata:169.254.169.254"],
            "external_links": ["outside:database"],
            "gpus": "all",
            "group_add": ["docker"],
            "isolation": "hyperv",
            "links": ["mcp-egress-proxy:internet"],
            "runtime": "unreviewed-runtime",
            "sysctls": {"net.ipv4.ip_forward": "1"},
            "userns_mode": "host",
            "uts": "host",
            "volumes_from": ["mcp-egress-proxy"],
        }.items()
    ),
)
def test_rejects_unreviewed_runtime_escape_fields(field: str, value: object) -> None:
    assert set(UNREVIEWED_RUNTIME_FIELDS) == {
        "cgroup",
        "cgroup_parent",
        "device_cgroup_rules",
        "dns",
        "dns_opt",
        "dns_search",
        "extra_hosts",
        "external_links",
        "gpus",
        "group_add",
        "isolation",
        "links",
        "runtime",
        "sysctls",
        "userns_mode",
        "uts",
        "volumes_from",
    }
    config = _valid_config()
    _services(config)["api"][field] = value

    assert any(f"uses the unreviewed runtime field {field}" in e for e in _errors(config))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pid", "host"),
        ("pid", "service:redis"),
        ("ipc", "host"),
        ("ipc", "shareable"),
        ("ipc", "service:redis"),
    ],
)
def test_rejects_every_pid_or_ipc_namespace_override(
    field: str, value: str
) -> None:
    config = _valid_config()
    _services(config)["api"][field] = value

    assert any(f"overrides the {field} namespace" in error for error in _errors(config))


def test_rejects_compose_api_socket_injection() -> None:
    config = _valid_config()
    _services(config)["api"]["use_api_socket"] = True

    assert any("requests Docker API socket access" in error for error in _errors(config))


@pytest.mark.parametrize(
    "service_name",
    [
        "app-egress-proxy",
        "cloudflared",
        "mcp-egress-gateway",
        "mcp-egress-proxy",
    ],
)
def test_boundary_security_options_are_an_exact_contract(service_name: str) -> None:
    config = _valid_config()
    _services(config)[service_name]["security_opt"] = [
        "no-new-privileges:true",
        "seccomp=unconfined",
    ]

    assert any(
        f"{service_name} security_opt must be exactly no-new-privileges:true" in error
        for error in _errors(config)
    )


@pytest.mark.parametrize(
    ("service_name", "field", "value", "expected"),
    [
        ("app-egress-proxy", "pids_limit", 4096, "pids_limit differs"),
        ("cloudflared", "mem_limit", "0", "mem_limit differs"),
        ("mcp-egress-gateway", "mem_limit", "0", "mem_limit differs"),
        (
            "mcp-egress-proxy",
            "tmpfs",
            ["/run:size=1g,exec,suid,dev"],
            "tmpfs mounts differ",
        ),
    ],
)
def test_boundary_resource_fields_are_exact_contracts(
    service_name: str, field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    _services(config)[service_name][field] = value

    assert any(expected in error and service_name in error for error in _errors(config))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("user", "root", "does not use its reviewed unprivileged identity"),
        ("read_only", False, "root filesystem must be read-only"),
        ("cap_drop", ["NET_ADMIN"], "must drop all Linux capabilities"),
    ],
)
def test_cloudflared_boundary_hardening_is_mandatory(
    field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    _services(config)["cloudflared"][field] = value

    assert any("cloudflared" in error and expected in error for error in _errors(config))


def test_non_boundary_service_cannot_disable_a_runtime_security_profile() -> None:
    config = _valid_config()
    _services(config)["api"]["security_opt"] = ["seccomp=unconfined"]

    assert any("api uses unreviewed security options" in error for error in _errors(config))


@pytest.mark.parametrize("service_name", ["api", "mcp-egress-gateway"])
def test_rejects_arbitrary_healthcheck_execution(service_name: str) -> None:
    config = _valid_config()
    _services(config)[service_name]["healthcheck"] = {
        "test": ["CMD-SHELL", "env >/tmp/stolen-environment"],
        "interval": "1s",
    }

    errors = _errors(config)
    assert any("healthcheck" in error and service_name in error for error in errors)


@pytest.mark.parametrize("field", ["post_start", "pre_stop"])
def test_rejects_privileged_root_lifecycle_hooks(field: str) -> None:
    config = _valid_config()
    _services(config)["api"][field] = [
        {
            "command": ["sh", "-c", "id"],
            "user": "root",
            "privileged": True,
        }
    ]

    assert any(f"uses the forbidden lifecycle hook {field}" in error for error in _errors(config))


def test_rejects_logging_driver_and_options_override() -> None:
    config = _valid_config()
    _services(config)["api"]["logging"] = {
        "driver": "syslog",
        "options": {"syslog-address": "tcp://collector.example.invalid:514"},
    }

    assert any("overrides the reviewed logging policy" in error for error in _errors(config))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("storage_opt", {"size": "100G"}),
        ("credential_spec", {"file": "/host/credential.json"}),
        ("shm_size", "1G"),
        ("annotations", {"runtime.example/escape": "true"}),
        ("provider", {"type": "external-runtime", "options": {}}),
    ],
)
def test_fail_closed_service_field_allowlist_rejects_provider_specific_fields(
    field: str, value: object
) -> None:
    config = _valid_config()
    _services(config)["api"][field] = value

    assert any(
        f"uses the unreviewed Compose service field {field}" in error
        for error in _errors(config)
    )


@pytest.mark.parametrize(
    ("service_name", "field", "value", "expected"),
    [
        (
            "mcp-egress-gateway",
            "profiles",
            ["disabled-boundary"],
            "must use exactly the mcp Compose profile",
        ),
        (
            "api",
            "profiles",
            ["optional"],
            "must not be gated behind a Compose profile",
        ),
        (
            "api",
            "restart",
            "no",
            "must use restart unless-stopped",
        ),
        (
            "minio-init",
            "restart",
            "always",
            "must remain a non-restarting one-shot service",
        ),
        (
            "api",
            "deploy",
            {"replicas": 1},
            "deploy contract differs from the reviewed topology",
        ),
    ],
)
def test_rejects_profile_or_restart_contract_drift(
    service_name: str, field: str, value: object, expected: str
) -> None:
    config = _valid_config()
    _services(config)[service_name][field] = value

    assert any(expected in error for error in _errors(config))


def test_rejects_api_worker_minio_identity_or_route_drift() -> None:
    config = _valid_config()
    api_environment = _services(config)["api"]["environment"]
    api_environment["MINIO_BUCKET"] = "wrong-bucket"  # type: ignore[index]
    api_environment["MINIO_SECURE"] = "true"  # type: ignore[index]
    worker_environment = _services(config)["worker"]["environment"]
    worker_environment["MINIO_ENDPOINT"] = "storage.example.invalid:9000"  # type: ignore[index]
    worker_environment["MINIO_SECRET_KEY"] = "wrong-secret"  # type: ignore[index]

    errors = _errors(config)

    assert any("api MinIO bucket does not match" in error for error in errors)
    assert any("api must use plain HTTP only" in error for error in errors)
    assert any("worker must use the internal minio endpoint" in error for error in errors)
    assert any("worker MinIO secret identity does not match" in error for error in errors)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        (
            "MCP_EGRESS_CLIENT_CERT_FILE",
            "/tmp/client.crt",
            "api MCP_EGRESS_CLIENT_CERT_FILE differs from its reviewed secret mount",
        ),
        (
            "MCP_EGRESS_CLIENT_KEY_FILE",
            "/tmp/client.key",
            "api MCP_EGRESS_CLIENT_KEY_FILE differs from its reviewed secret mount",
        ),
        (
            "MCP_EGRESS_CA_CERT_FILE",
            "/tmp/ca.crt",
            "api MCP_EGRESS_CA_CERT_FILE differs from its reviewed secret mount",
        ),
        (
            "NO_PROXY",
            "localhost,127.0.0.1",
            "api NO_PROXY differs from its reviewed internal routes",
        ),
        ("no_proxy", "*", "api receives an unreviewed proxy environment override"),
        (
            "ALL_PROXY",
            "http://unreviewed-proxy:3128",
            "api receives an unreviewed proxy environment override",
        ),
        (
            "all_proxy",
            "http://unreviewed-proxy:3128",
            "api receives an unreviewed proxy environment override",
        ),
    ],
)
def test_rejects_api_mcp_client_path_or_proxy_bypass_drift(
    key: str, value: str, expected: str
) -> None:
    config = _valid_config()
    _services(config)["api"]["environment"][key] = value  # type: ignore[index]

    assert expected in _errors(config)


def test_rejects_mutable_images_builds_ports_and_bind_mounts() -> None:
    config = _valid_config()
    _services(config)["api"].update(
        {
            "image": "geem/api:latest",
            "build": {"context": "."},
            "ports": [{"target": 8000, "published": "8000"}],
            "volumes": [{"type": "bind", "source": "/srv/geem", "target": "/app"}],
        }
    )

    errors = _errors(config)

    assert any("api still has a production build" in error for error in errors)
    assert any("api image is not pinned" in error for error in errors)
    assert any("api exposes or publishes" in error for error in errors)
    assert any("api has a production bind mount" in error for error in errors)


def test_errors_never_echo_database_or_minio_secrets() -> None:
    config = _valid_config()
    database_secret = "do-not-print-database-secret"
    minio_secret = "do-not-print-minio-secret"
    _services(config)["postgres"]["environment"][  # type: ignore[index]
        "POSTGRES_PASSWORD"
    ] = database_secret
    _services(config)["minio"]["environment"][  # type: ignore[index]
        "MINIO_ROOT_PASSWORD"
    ] = minio_secret

    errors = _errors(config)
    rendered_errors = "\n".join(errors)

    assert errors
    assert database_secret not in rendered_errors
    assert minio_secret not in rendered_errors
