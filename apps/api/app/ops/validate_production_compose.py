"""Fail-closed validation for Geem's rendered production Compose topology.

The command consumes ``docker compose config --format json`` on stdin.  It is
deliberately read-only and uses only the Python standard library so operators
can run it from the exact, digest-pinned API image with no network, mounts,
Docker socket, or production environment injected into the validator process.

Validation errors identify fields and services, but never echo environment
values because the rendered Compose document can contain secrets.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit


REQUIRED_SERVICES = frozenset(
    {
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
    }
)

INTERNAL_NETWORKS = frozenset(
    {
        "application_data",
        "application_broker",
        "application_ingress",
        "application_provider_control",
        "mcp_egress_control",
        "mcp_proxy_control",
    }
)
APP_PUBLIC_NETWORK = "application_provider_egress"
MCP_PUBLIC_NETWORK = "mcp_public_egress"
INGRESS_PUBLIC_NETWORK = "public_egress"
EXTERNAL_NETWORKS = frozenset(
    {APP_PUBLIC_NETWORK, MCP_PUBLIC_NETWORK, INGRESS_PUBLIC_NETWORK}
)
REQUIRED_NETWORKS = INTERNAL_NETWORKS | EXTERNAL_NETWORKS

EXPECTED_SERVICE_NETWORKS: dict[str, frozenset[str]] = {
    "postgres": frozenset({"application_data"}),
    "redis": frozenset({"application_broker"}),
    "qdrant": frozenset({"application_data"}),
    "minio": frozenset({"application_data"}),
    "minio-init": frozenset({"application_data"}),
    "api": frozenset(
        {
            "application_data",
            "application_broker",
            "application_ingress",
            "application_provider_control",
            "mcp_egress_control",
        }
    ),
    "worker": frozenset(
        {
            "application_data",
            "application_broker",
            "application_provider_control",
            "mcp_egress_control",
        }
    ),
    "beat": frozenset({"application_broker"}),
    "app-egress-proxy": frozenset(
        {"application_provider_control", APP_PUBLIC_NETWORK}
    ),
    "mcp-egress-gateway": frozenset({"mcp_egress_control", "mcp_proxy_control"}),
    "mcp-egress-proxy": frozenset({"mcp_proxy_control", MCP_PUBLIC_NETWORK}),
    "workspace_web": frozenset({"application_ingress"}),
    "dashboard_web": frozenset({"application_ingress"}),
    "landpage_web": frozenset({"application_ingress"}),
}

PERSISTENT_MOUNTS = {
    "postgres_data": ("postgres", "/var/lib/postgresql/data"),
    "redis_data": ("redis", "/data"),
    "qdrant_data": ("qdrant", "/qdrant/storage"),
    "minio_data": ("minio", "/data"),
}

MINIO_ENV_KEYS = frozenset({"APP_ENV", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"})
MINIO_INIT_ENV_KEYS = frozenset(
    {
        "APP_ENV",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
    }
)
GATEWAY_ENV_KEYS = frozenset(
    {
        "APP_ENV",
        "EGRESS_BIND_HOST",
        "EGRESS_BIND_PORT",
        "EGRESS_SERVER_CERT_FILE",
        "EGRESS_SERVER_KEY_FILE",
        "EGRESS_CLIENT_CA_FILE",
        "EGRESS_FORWARD_PROXY_URL",
        "EGRESS_ALLOW_PRIVATE",
        "EGRESS_BLOCKED_NETWORKS",
        "EGRESS_SUPPORTED_PROTOCOL_VERSIONS",
        "EGRESS_MAX_REDIRECTS",
        "EGRESS_MAX_DISCOVERED_TOOLS",
        "EGRESS_MAX_TOOL_PAGES",
        "EGRESS_LEGACY_SESSION_TTL_SECONDS",
        "EGRESS_MAX_LEGACY_SESSIONS",
        "EGRESS_MAX_CONCURRENT_OPERATIONS",
        "EGRESS_MAX_REQUEST_BYTES",
        "EGRESS_MAX_RESPONSE_BYTES",
        "EGRESS_CONNECT_TIMEOUT_SECONDS",
        "EGRESS_READ_TIMEOUT_SECONDS",
        "EGRESS_TOTAL_TIMEOUT_SECONDS",
    }
)

MCP_CLIENT_SECRET_BINDINGS = frozenset(
    {
        ("mcp_egress_client_cert", "/run/secrets/mcp-egress/client.crt"),
        ("mcp_egress_client_key", "/run/secrets/mcp-egress/client.key"),
        ("mcp_egress_ca_cert", "/run/secrets/mcp-egress/ca.crt"),
    }
)
MCP_SERVER_SECRET_BINDINGS = frozenset(
    {
        ("mcp_egress_server_cert", "/run/secrets/mcp-egress/server.crt"),
        ("mcp_egress_server_key", "/run/secrets/mcp-egress/server.key"),
        ("mcp_egress_ca_cert", "/run/secrets/mcp-egress/ca.crt"),
    }
)
MCP_SECRET_NAMES = frozenset(
    {
        "mcp_egress_client_cert",
        "mcp_egress_client_key",
        "mcp_egress_server_cert",
        "mcp_egress_server_key",
        "mcp_egress_ca_cert",
    }
)
CLOUDFLARED_CONFIG_NAME = "cloudflared_config"
CLOUDFLARED_CREDENTIALS_NAME = "cloudflared_credentials"
CLOUDFLARED_COMMAND = (
    "tunnel",
    "--protocol",
    "http2",
    "--config",
    "/etc/cloudflared/config.yml",
    "run",
)

DIGEST_IMAGE_RE = re.compile(r"^[^\s]+@sha256:[0-9a-f]{64}$")
LOCAL_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Exact scripts rendered from infra/docker-compose.yml. The production
# validator runs in an isolated image and therefore cannot read the repository;
# keeping these contracts explicit makes any execution change a reviewed code
# change instead of accepting shell fragments by substring.
MINIO_INIT_IMAGE = (
    "quay.io/minio/mc@sha256:"
    "993e8c454a7ec632923f7e3e61adf1d473261da6354cefd641aedd33a2cfe112"
)
MINIO_SERVER_ENTRYPOINT = (
    "/bin/sh",
    "-c",
    """set -eu
case "$${APP_ENV}" in
  local|dev|development|test)
    export MINIO_ROOT_USER="$${MINIO_ROOT_USER:-minio}"
    export MINIO_ROOT_PASSWORD="$${MINIO_ROOT_PASSWORD:-change-me}"
    ;;
  production)
    if [ -z "$${MINIO_ROOT_USER}" ] || [ "$${MINIO_ROOT_USER}" = "minio" ]; then
      echo "MinIO requires a non-default access key in production" >&2
      exit 1
    fi
    if [ -z "$${MINIO_ROOT_PASSWORD}" ] || [ "$${MINIO_ROOT_PASSWORD}" = "change-me" ]; then
      echo "MinIO requires a non-default secret key in production" >&2
      exit 1
    fi
    ;;
  *)
    echo "MinIO refuses unsupported APP_ENV" >&2
    exit 1
    ;;
esac
exec minio server /data --console-address ":9001"
""",
)

MINIO_INIT_ENTRYPOINT = (
    "/bin/sh",
    "-c",
    """set -eu
case "$${APP_ENV}" in
  local|dev|development|test)
    MINIO_ACCESS_KEY="$${MINIO_ACCESS_KEY:-minio}"
    MINIO_SECRET_KEY="$${MINIO_SECRET_KEY:-change-me}"
    ;;
  production)
    if [ -z "$${MINIO_ACCESS_KEY}" ] || [ "$${MINIO_ACCESS_KEY}" = "minio" ]; then
      echo "MinIO initialization requires a non-default access key in production" >&2
      exit 1
    fi
    if [ -z "$${MINIO_SECRET_KEY}" ] || [ "$${MINIO_SECRET_KEY}" = "change-me" ]; then
      echo "MinIO initialization requires a non-default secret key in production" >&2
      exit 1
    fi
    ;;
  *)
    echo "MinIO initialization refuses unsupported APP_ENV" >&2
    exit 1
    ;;
esac

attempts=0
until timeout -k 2s 5s mc alias set \\
  --conn-read-deadline 4s --conn-write-deadline 4s \\
  local http://minio:9000 "$${MINIO_ACCESS_KEY}" "$${MINIO_SECRET_KEY}" \\
  >/dev/null 2>&1; do
  attempts=$$((attempts + 1))
  if [ "$${attempts}" -ge 30 ]; then
    echo "MinIO did not become ready before the initialization deadline" >&2
    exit 1
  fi
  sleep 2
done

timeout -k 2s 10s mc mb --ignore-existing "local/$${MINIO_BUCKET}"
timeout -k 2s 10s mc anonymous set none "local/$${MINIO_BUCKET}"
timeout -k 2s 10s mc stat "local/$${MINIO_BUCKET}" >/dev/null
""",
)

# These Compose fields can join another namespace, alter the container runtime,
# grant device/group access, or bypass the reviewed name-resolution and service
# graph. Production has no approved use for them; reject them on every service.
UNREVIEWED_RUNTIME_FIELDS = frozenset(
    {
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
)
BOUNDARY_SERVICES = frozenset(
    {
        "app-egress-proxy",
        "cloudflared",
        "mcp-egress-gateway",
        "mcp-egress-proxy",
    }
)
EXACT_BOUNDARY_SECURITY_OPT = ("no-new-privileges:true",)
SQUID_TMPFS = (
    "/run:size=8m,noexec,nosuid,nodev,uid=13,gid=13,mode=0750",
    "/var/log/squid:size=8m,noexec,nosuid,nodev,uid=13,gid=13,mode=0750",
    "/var/spool/squid:size=8m,noexec,nosuid,nodev,uid=13,gid=13,mode=0750",
)
BOUNDARY_RUNTIME_CONTRACTS = {
    "app-egress-proxy": {
        "user": "13:13",
        "pids_limit": 64,
        "mem_limit": "134217728",
        "tmpfs": SQUID_TMPFS,
    },
    "cloudflared": {
        "user": "65532:65532",
        "pids_limit": 64,
        "mem_limit": "134217728",
        "tmpfs": (),
    },
    "mcp-egress-gateway": {
        "user": "10001:10001",
        "pids_limit": 128,
        "mem_limit": "268435456",
        "tmpfs": ("/tmp:size=16m,noexec,nosuid,nodev",),
    },
    "mcp-egress-proxy": {
        "user": "13:13",
        "pids_limit": 64,
        "mem_limit": "134217728",
        "tmpfs": SQUID_TMPFS,
    },
}

# Production service definitions are an exact topology, not a permissive
# Compose policy. Any newly introduced service field requires an explicit code
# review here before the rendered release can pass validation.
REVIEWED_SERVICE_FIELDS = frozenset(
    {
        "cap_drop",
        "command",
        "configs",
        "depends_on",
        "deploy",
        "entrypoint",
        "env_file",
        "environment",
        "healthcheck",
        "image",
        "mem_limit",
        "networks",
        "pids_limit",
        "profiles",
        "pull_policy",
        "read_only",
        "restart",
        "secrets",
        "security_opt",
        "tmpfs",
        "user",
        "volumes",
    }
)

API_HEALTHCHECK = {
    "test": ["CMD", "curl", "-f", "http://localhost:8000/api/health/live"],
    "timeout": "5s",
    "interval": "10s",
    "retries": 10,
    "start_period": "3m0s",
}
POSTGRES_HEALTHCHECK = {
    "test": ["CMD", "pg_isready"],
    "timeout": "5s",
    "interval": "5s",
    "retries": 10,
}
QDRANT_HEALTHCHECK = {
    "test": ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/6333"],
    "timeout": "5s",
    "interval": "10s",
    "retries": 10,
    "start_period": "10s",
}
REDIS_HEALTHCHECK = {
    "test": ["CMD", "redis-cli", "ping"],
    "timeout": "3s",
    "interval": "5s",
    "retries": 10,
}
REVIEWED_HEALTHCHECKS = {
    "api": API_HEALTHCHECK,
    "postgres": POSTGRES_HEALTHCHECK,
    "qdrant": QDRANT_HEALTHCHECK,
    "redis": REDIS_HEALTHCHECK,
}
MCP_PROFILE_SERVICES = frozenset({"mcp-egress-gateway", "mcp-egress-proxy"})


@dataclass(frozen=True)
class ValidationOptions:
    project: str
    mcp_enabled: bool
    ingress_services: frozenset[str]
    physical_volumes: Mapping[str, str]
    required_blocked_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()
    allow_local_image_ids: bool = False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _environment(service: Mapping[str, Any]) -> dict[str, Any]:
    value = service.get("environment")
    if isinstance(value, Mapping):
        return dict(value)
    result: dict[str, Any] = {}
    for item in _sequence(value):
        if isinstance(item, str) and "=" in item:
            key, item_value = item.split("=", 1)
            result[key] = item_value
    return result


def _service_networks(service: Mapping[str, Any]) -> frozenset[str]:
    value = service.get("networks")
    if isinstance(value, Mapping):
        return frozenset(str(name) for name in value)
    return frozenset(str(name) for name in _sequence(value))


def _has_empty_network_attachments(service: Mapping[str, Any]) -> bool:
    value = service.get("networks")
    if not isinstance(value, Mapping):
        return False
    return all(
        attachment is None
        or (isinstance(attachment, Mapping) and not attachment)
        for attachment in value.values()
    )


def _secret_bindings(service: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    bindings: set[tuple[str, str]] = set()
    for item in _sequence(service.get("secrets")):
        if isinstance(item, str):
            bindings.add((item, item))
        elif isinstance(item, Mapping):
            source = item.get("source")
            target = item.get("target") or source
            if source and target:
                bindings.add((str(source), str(target)))
    return frozenset(bindings)


def _has_exact_resource_binding(
    service: Mapping[str, Any],
    *,
    field: str,
    source: str,
    target: str,
    uid: str,
    gid: str,
    mode: int,
) -> bool:
    items = _sequence(service.get(field))
    if len(items) != 1 or not isinstance(items[0], Mapping):
        return False
    binding = items[0]
    return (
        set(binding) == {"source", "target", "uid", "gid", "mode"}
        and binding.get("source") == source
        and binding.get("target") == target
        and str(binding.get("uid")) == uid
        and str(binding.get("gid")) == gid
        and _mode_matches(binding.get("mode"), mode)
    )


def _is_exact_absolute_file_declaration(value: Any, *, name: str) -> bool:
    declaration = _mapping(value)
    source = declaration.get("file")
    return (
        set(declaration) == {"file", "name"}
        and declaration.get("name") == name
        and isinstance(source, str)
        and source.startswith("/")
        and len(source) > 1
    )


def _secret_mount(
    service: Mapping[str, Any], source: str
) -> Mapping[str, Any] | None:
    matches = [
        item
        for item in _sequence(service.get("secrets"))
        if isinstance(item, Mapping) and item.get("source") == source
    ]
    return matches[0] if len(matches) == 1 else None


def _mode_matches(value: Any, expected: int) -> bool:
    """Accept the equivalent forms emitted by Compose/YAML JSON renderers."""

    if isinstance(value, int):
        return value == expected
    return str(value).strip().lower() in {
        f"0{expected:o}",
        f"0o{expected:o}",
        str(expected),
    }


def _mode_is_0400(value: Any) -> bool:
    return _mode_matches(value, 0o400)


def _is_bool(value: Any, expected: bool) -> bool:
    if isinstance(value, bool):
        return value is expected
    normalized = str(value).strip().lower()
    return normalized == ("true" if expected else "false")


def _normalized_shell(value: Any) -> str:
    return " ".join(str(value or "").split())


def _parse_networks(value: Any) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] | None:
    if value is None:
        return ()
    if not isinstance(value, str):
        return None
    parsed: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    try:
        for raw in value.split(","):
            item = raw.strip()
            if item:
                parsed.append(ipaddress.ip_network(item, strict=False))
    except ValueError:
        return None
    return tuple(dict.fromkeys(parsed))


def _network_subnets(
    definition: Mapping[str, Any],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] | None:
    configs = _sequence(_mapping(definition.get("ipam")).get("config"))
    parsed: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    try:
        for config in configs:
            subnet = _mapping(config).get("subnet")
            if subnet:
                parsed.append(ipaddress.ip_network(str(subnet), strict=False))
    except ValueError:
        return None
    return tuple(dict.fromkeys(parsed))


def _is_covered(
    candidate: ipaddress.IPv4Network | ipaddress.IPv6Network,
    blocked: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    return any(
        candidate.version == boundary.version and candidate.subnet_of(boundary)
        for boundary in blocked
    )


def _validate_database_identity(
    services: Mapping[str, Mapping[str, Any]], errors: list[str]
) -> None:
    postgres_env = _environment(services["postgres"])
    user = postgres_env.get("POSTGRES_USER")
    password = postgres_env.get("POSTGRES_PASSWORD")
    database = postgres_env.get("POSTGRES_DB")
    if not all(isinstance(value, str) and value for value in (user, password, database)):
        errors.append("postgres must receive non-empty user, password, and database values")
        return
    if password == "rag":
        errors.append("postgres still uses the checked-in development password")

    urls = [_environment(services[name]).get("DATABASE_URL") for name in ("api", "worker")]
    if not all(isinstance(value, str) and value for value in urls):
        errors.append("api and worker must each receive DATABASE_URL")
        return
    if len(set(urls)) != 1:
        errors.append("api and worker do not use one database identity")
        return
    try:
        parsed = urlsplit(str(urls[0]))
        port = parsed.port
    except ValueError:
        errors.append("DATABASE_URL is malformed")
        return
    if not parsed.scheme.startswith("postgresql"):
        errors.append("DATABASE_URL is not PostgreSQL")
        return
    if parsed.hostname != "postgres" or (port not in (None, 5432)):
        errors.append("DATABASE_URL must use the internal postgres service on port 5432")
    if unquote(parsed.username or "") != user or unquote(parsed.password or "") != password:
        errors.append("DATABASE_URL credentials do not match the postgres service")
    if unquote(parsed.path.lstrip("/")) != database:
        errors.append("DATABASE_URL database does not match POSTGRES_DB")


def _validate_internal_dependencies(
    services: Mapping[str, Mapping[str, Any]], errors: list[str]
) -> None:
    expectations = (
        ("REDIS_URL", ("redis",), "redis", 6379, ("api", "worker", "beat")),
        ("QDRANT_URL", ("http",), "qdrant", 6333, ("api", "worker")),
    )
    for key, schemes, expected_host, expected_port, service_names in expectations:
        values = [_environment(services[name]).get(key) for name in service_names]
        if not all(isinstance(value, str) and value for value in values):
            errors.append(f"{key} must be present on every required application process")
            continue
        if len(set(values)) != 1:
            errors.append(f"{key} differs across application processes")
            continue
        try:
            parsed = urlsplit(str(values[0]))
            port = parsed.port
        except ValueError:
            errors.append(f"{key} is malformed")
            continue
        if (
            parsed.scheme not in schemes
            or parsed.hostname != expected_host
            or port not in (None, expected_port)
        ):
            errors.append(f"{key} must use its reviewed internal service identity")


def _validate_minio_identity(
    services: Mapping[str, Mapping[str, Any]], errors: list[str]
) -> None:
    server = _environment(services["minio"])
    initializer = _environment(services["minio-init"])
    access_key = server.get("MINIO_ROOT_USER")
    secret_key = server.get("MINIO_ROOT_PASSWORD")
    if not isinstance(access_key, str) or not access_key or access_key == "minio":
        errors.append("minio must receive a non-default root user")
    if not isinstance(secret_key, str) or not secret_key or secret_key == "change-me":
        errors.append("minio must receive a non-default root password")

    init_access = initializer.get("MINIO_ACCESS_KEY", initializer.get("MINIO_ROOT_USER"))
    init_secret = initializer.get("MINIO_SECRET_KEY", initializer.get("MINIO_ROOT_PASSWORD"))
    if init_access != access_key or init_secret != secret_key:
        errors.append("minio-init credentials do not match the minio service")
    bucket = initializer.get("MINIO_BUCKET")
    if not isinstance(bucket, str) or not bucket:
        errors.append("minio-init must receive a non-empty bucket name")

    bucket = initializer.get("MINIO_BUCKET")
    for service_name in ("api", "worker"):
        environment = _environment(services[service_name])
        if environment.get("MINIO_ACCESS_KEY") != access_key:
            errors.append(f"{service_name} MinIO access identity does not match minio")
        if environment.get("MINIO_SECRET_KEY") != secret_key:
            errors.append(f"{service_name} MinIO secret identity does not match minio")
        if environment.get("MINIO_ENDPOINT") != "minio:9000":
            errors.append(f"{service_name} must use the internal minio endpoint")
        if environment.get("MINIO_BUCKET") != bucket:
            errors.append(f"{service_name} MinIO bucket does not match minio-init")
        if not _is_bool(environment.get("MINIO_SECURE"), False):
            errors.append(f"{service_name} must use plain HTTP only on the internal MinIO route")


def _validate_persistent_mounts(
    services: Mapping[str, Mapping[str, Any]],
    volumes: Mapping[str, Any],
    options: ValidationOptions,
    errors: list[str],
) -> None:
    if set(options.physical_volumes) != set(PERSISTENT_MOUNTS):
        errors.append("physical-volume arguments must name exactly the four Geem datastores")
        return
    if set(volumes) != set(PERSISTENT_MOUNTS):
        errors.append("production must declare exactly the four reviewed datastore volumes")

    expected_attachments = {
        (service_name, logical, target)
        for logical, (service_name, target) in PERSISTENT_MOUNTS.items()
    }
    actual_attachments: list[tuple[str, str, str]] = []
    invalid_mount = False
    for service_name, service in services.items():
        for mount in _sequence(service.get("volumes")):
            if not isinstance(mount, Mapping) or mount.get("type") != "volume":
                invalid_mount = True
                continue
            source = mount.get("source")
            target = mount.get("target")
            if not isinstance(source, str) or not isinstance(target, str):
                invalid_mount = True
                continue
            mount_keys = frozenset(mount)
            exact_keys = {"type", "source", "target"}
            exact_rendered_keys = exact_keys | {"volume"}
            if mount_keys not in {frozenset(exact_keys), frozenset(exact_rendered_keys)}:
                invalid_mount = True
            if "volume" in mount:
                volume_options = mount.get("volume")
                if not isinstance(volume_options, Mapping) or volume_options:
                    invalid_mount = True
            actual_attachments.append((service_name, source, target))
    if invalid_mount or set(actual_attachments) != expected_attachments:
        errors.append(
            "production volume attachments differ from the exact option-free datastore map"
        )
    if len(actual_attachments) != len(set(actual_attachments)):
        errors.append("production contains a duplicate volume attachment")

    for logical, (service_name, target) in PERSISTENT_MOUNTS.items():
        matches = [
            mount
            for mount in _sequence(services[service_name].get("volumes"))
            if isinstance(mount, Mapping) and mount.get("target") == target
        ]
        if len(matches) != 1:
            errors.append(f"{service_name} must have exactly one persistent mount at {target}")
            continue
        mount = matches[0]
        if mount.get("type") != "volume" or mount.get("source") != logical:
            errors.append(f"{service_name} persistent mount changed logical volume identity")
        declaration = _mapping(volumes.get(logical))
        if set(declaration) != {"name", "external"}:
            errors.append(
                f"{logical} declaration must contain exactly name and external"
            )
        if declaration.get("name") != options.physical_volumes[logical]:
            errors.append(f"{logical} physical engine-volume identity changed")
        if declaration.get("external") is not True:
            errors.append(f"{logical} must be declared external in production")


def validate_production_compose(config: Any, options: ValidationOptions) -> list[str]:
    """Return secret-safe validation errors for a rendered Compose document."""

    errors: list[str] = []
    if not isinstance(config, Mapping):
        return ["rendered Compose document must be a JSON object"]
    services_raw = _mapping(config.get("services"))
    services = {str(name): _mapping(value) for name, value in services_raw.items()}
    networks = _mapping(config.get("networks"))
    volumes = _mapping(config.get("volumes"))
    configs = _mapping(config.get("configs"))
    secrets = _mapping(config.get("secrets"))

    if config.get("name") != options.project:
        errors.append("rendered Compose project does not match --project")
    expected_services = REQUIRED_SERVICES | options.ingress_services
    missing_services = expected_services - set(services)
    if missing_services:
        errors.append("required production services are missing")
    unexpected_services = set(services) - expected_services
    if unexpected_services:
        errors.append("rendered topology contains an unreviewed service")
    missing_networks = REQUIRED_NETWORKS - set(networks)
    if missing_networks:
        errors.append("required production networks are missing")
    unexpected_networks = set(networks) - REQUIRED_NETWORKS
    if unexpected_networks:
        errors.append("rendered topology contains an unreviewed network")
    if missing_services or missing_networks or unexpected_services or unexpected_networks:
        return errors
    if options.ingress_services & REQUIRED_SERVICES:
        errors.append("--ingress-service cannot reclassify a core Geem service")
        return errors
    if options.ingress_services != {"cloudflared"}:
        errors.append(
            "this production topology requires the exact reviewed cloudflared ingress"
        )
        return errors

    # The ingress flag approves one complete, fixed Cloudflared contract. It
    # cannot be used to bless an arbitrary public service or credential mount.
    for ingress in options.ingress_services:
        service = services[ingress]
        if service.get("env_file"):
            errors.append(f"{ingress} ingress must not receive an env_file")
        if _environment(service):
            errors.append(f"{ingress} ingress must not receive environment values")
        if (
            tuple(str(item) for item in _sequence(service.get("command")))
            != CLOUDFLARED_COMMAND
            or service.get("entrypoint") is not None
        ):
            errors.append("cloudflared does not run the exact reviewed tunnel command")
        if not _has_exact_resource_binding(
            service,
            field="configs",
            source=CLOUDFLARED_CONFIG_NAME,
            target="/etc/cloudflared/config.yml",
            uid="65532",
            gid="65532",
            mode=0o444,
        ):
            errors.append("cloudflared does not have the exact reviewed config mount")
        if not _has_exact_resource_binding(
            service,
            field="secrets",
            source=CLOUDFLARED_CREDENTIALS_NAME,
            target="/etc/cloudflared/credentials.json",
            uid="65532",
            gid="65532",
            mode=0o400,
        ):
            errors.append("cloudflared does not have the exact reviewed credential mount")
        if service.get("volumes"):
            errors.append("cloudflared ingress must not receive volume or bind mounts")

    has_cloudflared = "cloudflared" in options.ingress_services
    expected_secret_names = MCP_SECRET_NAMES | (
        {CLOUDFLARED_CREDENTIALS_NAME} if has_cloudflared else set()
    )
    expected_config_names = {CLOUDFLARED_CONFIG_NAME} if has_cloudflared else set()
    if not MCP_SECRET_NAMES.issubset(secrets):
        errors.append("production is missing a reviewed MCP PKI secret source")
    if set(secrets) != expected_secret_names:
        errors.append("production secret declarations differ from reviewed service bindings")
    if set(configs) != expected_config_names:
        errors.append("production config declarations differ from reviewed service bindings")
    for name in MCP_SECRET_NAMES:
        declaration = _mapping(secrets.get(name))
        if not isinstance(declaration.get("file"), str) or not declaration.get("file"):
            errors.append("an MCP PKI secret declaration has no file source")
        if declaration.get("external") is True:
            errors.append("MCP PKI file secrets cannot silently switch to external identity")
    if has_cloudflared:
        if not _is_exact_absolute_file_declaration(
            secrets.get(CLOUDFLARED_CREDENTIALS_NAME),
            name=f"{options.project}_{CLOUDFLARED_CREDENTIALS_NAME}",
        ):
            errors.append(
                "cloudflared credentials must use one non-empty absolute file source"
            )
        if not _is_exact_absolute_file_declaration(
            configs.get(CLOUDFLARED_CONFIG_NAME),
            name=f"{options.project}_{CLOUDFLARED_CONFIG_NAME}",
        ):
            errors.append(
                "cloudflared config must use one non-empty absolute file source"
            )
    expected_networks = dict(EXPECTED_SERVICE_NETWORKS)
    for ingress in options.ingress_services:
        expected_networks[ingress] = frozenset(
            {"application_ingress", INGRESS_PUBLIC_NETWORK}
        )
    for name, expected in expected_networks.items():
        if _service_networks(services[name]) != expected:
            errors.append(f"{name} has an unexpected network membership")
        if not _has_empty_network_attachments(services[name]):
            errors.append(f"{name} has unreviewed per-network attachment options")

    expected_external_members = {
        APP_PUBLIC_NETWORK: {"app-egress-proxy"},
        MCP_PUBLIC_NETWORK: {"mcp-egress-proxy"},
        INGRESS_PUBLIC_NETWORK: set(options.ingress_services),
    }
    for network_name, expected_members in expected_external_members.items():
        actual_members = {
            name
            for name, service in services.items()
            if network_name in _service_networks(service)
        }
        if actual_members != expected_members:
            errors.append(
                f"{network_name} membership does not match its single-purpose boundary"
            )

    declared_subnets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for name in REQUIRED_NETWORKS:
        definition = _mapping(networks[name])
        unexpected_fields = set(definition) - {"name", "internal", "driver", "ipam"}
        if unexpected_fields:
            errors.append(f"{name} contains unreviewed network definition fields")
        if definition.get("name") != f"{options.project}_{name}":
            errors.append(f"{name} overrides its project-scoped network identity")
        if definition.get("driver") not in (None, "bridge"):
            errors.append(f"{name} must use the default bridge network driver")
        if name in INTERNAL_NETWORKS and definition.get("internal") is not True:
            errors.append(f"{name} must be an internal network")
        if name in EXTERNAL_NETWORKS and definition.get("internal") is True:
            errors.append(f"{name} cannot be internal")
        ipam = _mapping(definition.get("ipam"))
        ipam_configs = _sequence(ipam.get("config"))
        if (
            set(ipam) != {"config"}
            or len(ipam_configs) != 1
            or not isinstance(ipam_configs[0], Mapping)
            or set(ipam_configs[0]) != {"subnet"}
        ):
            errors.append(f"{name} IPAM differs from the exact subnet-only contract")
        subnets = _network_subnets(definition)
        if subnets is None:
            errors.append(f"{name} has invalid IPAM subnet syntax")
        elif len(subnets) != 1:
            errors.append(f"{name} must declare exactly one explicit IPAM subnet")
        else:
            declared_subnets.extend(subnets)
    for index, left in enumerate(declared_subnets):
        for right in declared_subnets[index + 1 :]:
            if left.version == right.version and left.overlaps(right):
                errors.append("production Compose networks contain overlapping IPAM subnets")

    for name, service in services.items():
        for field in sorted(set(service) - REVIEWED_SERVICE_FIELDS):
            errors.append(f"{name} uses the unreviewed Compose service field {field}")
        if service.get("build"):
            errors.append(f"{name} still has a production build definition")
        image = service.get("image")
        image_is_registry_digest = (
            isinstance(image, str) and DIGEST_IMAGE_RE.fullmatch(image) is not None
        )
        image_is_permitted_local_id = (
            options.allow_local_image_ids
            and isinstance(image, str)
            and LOCAL_IMAGE_ID_RE.fullmatch(image) is not None
        )
        if not image_is_registry_digest and not image_is_permitted_local_id:
            errors.append(f"{name} image is not pinned to an immutable sha256 digest")
        pull_policy = service.get("pull_policy")
        if options.allow_local_image_ids:
            if pull_policy != "never":
                errors.append(
                    f"{name} must use pull_policy never in local-image deployment mode"
                )
        elif pull_policy is not None:
            errors.append(f"{name} overrides the reviewed image pull policy")
        if service.get("ports") or service.get("expose"):
            errors.append(f"{name} exposes or publishes a container port")
        if service.get("privileged") is True:
            errors.append(f"{name} is privileged")
        if service.get("cap_add"):
            errors.append(f"{name} adds Linux capabilities")
        if service.get("devices"):
            errors.append(f"{name} receives a host device")
        runtime_user = str(service.get("user") or "").split(":", 1)[0].lower()
        if runtime_user in {"0", "root"}:
            errors.append(f"{name} explicitly overrides its runtime identity to root")
        if service.get("configs") and name not in options.ingress_services:
            errors.append(f"{name} receives an unreviewed runtime config mount")
        deploy = _mapping(service.get("deploy"))
        for field_value in (deploy.get("replicas"), service.get("scale")):
            if field_value is None:
                continue
            try:
                replica_count = int(field_value)
            except (TypeError, ValueError):
                replica_count = 0
            if replica_count < 1:
                errors.append(f"{name} has a disabled or invalid replica count")
        if "network_mode" in service and service.get("network_mode") is not None:
            errors.append(f"{name} overrides Compose network isolation")
        for field in ("pid", "ipc"):
            if field in service and service.get(field) is not None:
                errors.append(f"{name} overrides the {field} namespace")
        if "use_api_socket" in service and service.get("use_api_socket") is not None:
            errors.append(f"{name} requests Docker API socket access")
        for field in ("post_start", "pre_stop"):
            if service.get(field):
                errors.append(f"{name} uses the forbidden lifecycle hook {field}")
        if service.get("logging"):
            errors.append(f"{name} overrides the reviewed logging policy")
        for field in UNREVIEWED_RUNTIME_FIELDS:
            if field in service and service.get(field) not in (None, False, ""):
                errors.append(f"{name} uses the unreviewed runtime field {field}")
        security_options = tuple(
            str(item).strip().lower()
            for item in _sequence(service.get("security_opt"))
        )
        if (
            name not in BOUNDARY_SERVICES
            and security_options
            and security_options != EXACT_BOUNDARY_SECURITY_OPT
        ):
            errors.append(f"{name} uses unreviewed security options")
        if (
            name not in BOUNDARY_SERVICES
            and "tmpfs" in service
            and service.get("tmpfs") is not None
        ):
            errors.append(f"{name} must not receive tmpfs mounts")
        for mount in _sequence(service.get("volumes")):
            if isinstance(mount, Mapping) and mount.get("type") == "bind":
                errors.append(f"{name} has a production bind mount")
            if isinstance(mount, Mapping) and str(mount.get("source", "")).endswith("docker.sock"):
                errors.append(f"{name} receives the Docker socket")

    for name, expected_healthcheck in REVIEWED_HEALTHCHECKS.items():
        if _mapping(services[name].get("healthcheck")) != expected_healthcheck:
            errors.append(f"{name} healthcheck differs from its exact reviewed contract")
    for name in set(services) - set(REVIEWED_HEALTHCHECKS):
        if services[name].get("healthcheck"):
            errors.append(f"{name} must not override its immutable image healthcheck")

    for name, service in services.items():
        profiles = tuple(str(value) for value in _sequence(service.get("profiles")))
        if name in MCP_PROFILE_SERVICES:
            if profiles != ("mcp",):
                errors.append(f"{name} must use exactly the mcp Compose profile")
        elif profiles:
            errors.append(f"{name} must not be gated behind a Compose profile")

        if name == "minio-init":
            if service.get("restart") is not None:
                errors.append("minio-init must remain a non-restarting one-shot service")
        elif service.get("restart") != "unless-stopped":
            errors.append(f"{name} must use restart unless-stopped")

        expected_deploy = {"replicas": 1} if name in {"beat", "mcp-egress-gateway"} else {}
        if _mapping(service.get("deploy")) != expected_deploy:
            errors.append(f"{name} deploy contract differs from the reviewed topology")

    for name, service in services.items():
        if name not in {"api", "worker"} and service.get("env_file"):
            errors.append(f"{name} must not receive an env_file")

    postgres_environment = _environment(services["postgres"])
    if set(postgres_environment) != {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    }:
        errors.append("postgres environment differs from its exact identity allowlist")
    for name in (
        "redis",
        "qdrant",
        "workspace_web",
        "dashboard_web",
        "landpage_web",
    ):
        if _environment(services[name]):
            errors.append(f"{name} must not receive environment values")

    for name in ("api", "worker"):
        environment = _environment(services[name])
        if environment.get("APP_ENV") != "production":
            errors.append(f"{name} APP_ENV must be production")
        if not _is_bool(environment.get("AUTH_REQUIRED"), True):
            errors.append(f"{name} AUTH_REQUIRED must be true")
        if not _is_bool(environment.get("MCP_CONNECTOR_ENABLED"), options.mcp_enabled):
            errors.append(f"{name} MCP_CONNECTOR_ENABLED has the wrong fail-closed value")

    beat_env = _environment(services["beat"])
    if set(beat_env) != {"APP_ENV", "REDIS_URL", "MCP_CONNECTOR_ENABLED"}:
        errors.append("beat environment exceeds its broker-only allowlist")
    if beat_env.get("APP_ENV") != "production":
        errors.append("beat APP_ENV must be production")
    if not _is_bool(beat_env.get("MCP_CONNECTOR_ENABLED"), False):
        errors.append("beat MCP_CONNECTOR_ENABLED has the wrong fail-closed value")

    api_parts = list(_sequence(services["api"].get("command")))
    expected_api_shell = (
        "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 "
        "--port 8000 --no-access-log"
    )
    if not (
        len(api_parts) == 3
        and api_parts[0] in {"sh", "/bin/sh"}
        and api_parts[1] == "-c"
        and _normalized_shell(api_parts[2]) == expected_api_shell
        and not services["api"].get("entrypoint")
    ):
        errors.append("api does not run the reviewed migrate-and-serve command")
    expected_worker_command = [
        "celery",
        "-A",
        "app.worker.celery_app",
        "worker",
        "--loglevel=INFO",
        "--concurrency=2",
    ]
    if (
        list(_sequence(services["worker"].get("command"))) != expected_worker_command
        or services["worker"].get("entrypoint")
    ):
        errors.append("worker does not run the reviewed Celery worker application")
    expected_beat_command = [
        "celery",
        "-A",
        "app.worker.beat_app:beat_app",
        "beat",
        "--loglevel=INFO",
        "--schedule",
        "/tmp/celerybeat-schedule",
    ]
    if (
        list(_sequence(services["beat"].get("command"))) != expected_beat_command
        or services["beat"].get("entrypoint")
    ):
        errors.append("beat does not run the least-privilege Celery Beat application")

    for name in ("postgres", "redis", "qdrant", "app-egress-proxy", "mcp-egress-gateway"):
        if services[name].get("command") or services[name].get("entrypoint"):
            errors.append(f"{name} overrides its immutable image execution contract")
    if services["mcp-egress-proxy"].get("command"):
        errors.append("mcp-egress-proxy overrides its reviewed renderer command")

    if not (
        services["api"].get("image")
        == services["worker"].get("image")
        == services["beat"].get("image")
    ):
        errors.append("api, worker, and beat must use one exact application image digest")

    for name in ("workspace_web", "dashboard_web", "landpage_web"):
        if list(_sequence(services[name].get("command"))) != [
            "nginx",
            "-g",
            "daemon off;",
        ]:
            errors.append(f"{name} does not run the reviewed production web server")
        if services[name].get("entrypoint"):
            errors.append(f"{name} overrides its immutable image entrypoint")

    least_privilege_services = (
        "minio",
        "minio-init",
        "mcp-egress-gateway",
        "mcp-egress-proxy",
        "app-egress-proxy",
    )
    for name in least_privilege_services:
        if services[name].get("env_file"):
            errors.append(f"{name} inherits a whole-application env_file")

    minio_env = _environment(services["minio"])
    if set(minio_env) != MINIO_ENV_KEYS:
        errors.append("minio environment differs from its least-privilege allowlist")
    if minio_env.get("APP_ENV") != "production":
        errors.append("minio APP_ENV must be production")
    minio_init_env = _environment(services["minio-init"])
    if set(minio_init_env) != MINIO_INIT_ENV_KEYS:
        errors.append("minio-init environment differs from its least-privilege allowlist")
    if minio_init_env.get("APP_ENV") != "production":
        errors.append("minio-init APP_ENV must be production")
    gateway_keys = set(_environment(services["mcp-egress-gateway"]))
    if gateway_keys != GATEWAY_ENV_KEYS:
        errors.append(
            "mcp-egress-gateway environment differs from its exact least-privilege contract"
        )
    proxy_keys = set(_environment(services["mcp-egress-proxy"]))
    if proxy_keys - {"MCP_PROXY_BLOCKED_NETWORKS", "MCP_PROXY_REQUIRE_BLOCKED_NETWORKS"}:
        errors.append(
            "mcp-egress-proxy receives environment keys outside its least-privilege allowlist"
        )
    if _environment(services["app-egress-proxy"]):
        errors.append("app-egress-proxy must not receive application environment values")
    if services["mcp-egress-proxy"].get("entrypoint") != [
        "python3",
        "/usr/local/lib/geem/render_mcp_proxy_config.py",
    ]:
        errors.append("mcp-egress-proxy bypasses the fail-closed policy renderer")
    if (
        tuple(_sequence(services["minio"].get("entrypoint")))
        != MINIO_SERVER_ENTRYPOINT
        or services["minio"].get("command") is not None
    ):
        errors.append("minio execution differs from its exact reviewed contract")
    if (
        tuple(_sequence(services["minio-init"].get("entrypoint")))
        != MINIO_INIT_ENTRYPOINT
        or services["minio-init"].get("command") is not None
    ):
        errors.append("minio-init execution differs from its exact reviewed contract")
    if services["minio-init"].get("image") != MINIO_INIT_IMAGE:
        errors.append("minio-init does not use the exact reviewed image digest")

    for name in ("api", "worker"):
        if _secret_bindings(services[name]) != MCP_CLIENT_SECRET_BINDINGS:
            errors.append(f"{name} does not have the exact MCP client PKI mounts")
        client_key = _secret_mount(services[name], "mcp_egress_client_key")
        if client_key is None or not _mode_is_0400(client_key.get("mode")):
            errors.append(f"{name} MCP client key is not mounted mode 0400")
    if _secret_bindings(services["beat"]):
        errors.append("beat must not receive secret mounts")
    if _secret_bindings(services["mcp-egress-gateway"]) != MCP_SERVER_SECRET_BINDINGS:
        errors.append("mcp-egress-gateway does not have the exact server PKI mounts")
    server_key = _secret_mount(services["mcp-egress-gateway"], "mcp_egress_server_key")
    if server_key is None or (
        not _mode_is_0400(server_key.get("mode"))
        or str(server_key.get("uid")) != "10001"
        or str(server_key.get("gid")) != "10001"
    ):
        errors.append("mcp-egress-gateway server key ownership/mode is unsafe")
    for name in REQUIRED_SERVICES - {"api", "worker", "mcp-egress-gateway"}:
        if _secret_bindings(services[name]):
            errors.append(f"{name} must not receive secret mounts")

    for name, contract in BOUNDARY_RUNTIME_CONTRACTS.items():
        if name not in services:
            continue
        service = services[name]
        if str(service.get("user")) != contract["user"]:
            errors.append(f"{name} does not use its reviewed unprivileged identity")
        if service.get("pids_limit") != contract["pids_limit"]:
            errors.append(f"{name} pids_limit differs from its reviewed bound")
        if str(service.get("mem_limit")) != contract["mem_limit"]:
            errors.append(f"{name} mem_limit differs from its reviewed bound")
        if tuple(str(item) for item in _sequence(service.get("tmpfs"))) != contract[
            "tmpfs"
        ]:
            errors.append(f"{name} tmpfs mounts differ from the reviewed contract")
        if service.get("read_only") is not True:
            errors.append(f"{name} root filesystem must be read-only")
        if set(str(item).upper() for item in _sequence(service.get("cap_drop"))) != {"ALL"}:
            errors.append(f"{name} must drop all Linux capabilities")
        security_options = tuple(
            str(item).strip().lower()
            for item in _sequence(service.get("security_opt"))
        )
        if security_options != EXACT_BOUNDARY_SECURITY_OPT:
            errors.append(
                f"{name} security_opt must be exactly no-new-privileges:true"
            )

    gateway = services["mcp-egress-gateway"]
    gateway_env = _environment(gateway)
    fixed_gateway_values = {
        "APP_ENV": "production",
        "EGRESS_BIND_HOST": "0.0.0.0",
        "EGRESS_BIND_PORT": "8443",
        "EGRESS_SERVER_CERT_FILE": "/run/secrets/mcp-egress/server.crt",
        "EGRESS_SERVER_KEY_FILE": "/run/secrets/mcp-egress/server.key",
        "EGRESS_CLIENT_CA_FILE": "/run/secrets/mcp-egress/ca.crt",
        "EGRESS_FORWARD_PROXY_URL": "http://mcp-egress-proxy:3128",
    }
    for key, expected_value in fixed_gateway_values.items():
        if str(gateway_env.get(key)) != expected_value:
            errors.append(f"mcp-egress-gateway {key} differs from its reviewed value")
    if not _is_bool(gateway_env.get("EGRESS_ALLOW_PRIVATE"), False):
        errors.append("mcp-egress-gateway private egress must be disabled")
    protocol_versions = tuple(
        value.strip()
        for value in str(gateway_env.get("EGRESS_SUPPORTED_PROTOCOL_VERSIONS") or "").split(",")
        if value.strip()
    )
    reviewed_protocol_versions = {"2026-07-28", "2025-11-25", "2024-11-05"}
    if (
        not protocol_versions
        or protocol_versions[0] != "2026-07-28"
        or len(protocol_versions) != len(set(protocol_versions))
        or not set(protocol_versions).issubset(reviewed_protocol_versions)
    ):
        errors.append("mcp-egress-gateway protocol versions are not reviewed")
    integer_limits = {
        "EGRESS_MAX_REDIRECTS": (0, 10),
        "EGRESS_MAX_REQUEST_BYTES": (1, 1_048_576),
        "EGRESS_MAX_RESPONSE_BYTES": (1, 1_048_576),
        "EGRESS_MAX_DISCOVERED_TOOLS": (1, 4_096),
        "EGRESS_MAX_TOOL_PAGES": (1, 512),
        "EGRESS_LEGACY_SESSION_TTL_SECONDS": (30, 3_600),
        "EGRESS_MAX_LEGACY_SESSIONS": (1, 1_024),
        "EGRESS_MAX_CONCURRENT_OPERATIONS": (1, 2_048),
    }
    for key, (minimum, maximum) in integer_limits.items():
        try:
            value = int(gateway_env.get(key))
        except (TypeError, ValueError):
            value = minimum - 1
        if not minimum <= value <= maximum:
            errors.append(f"mcp-egress-gateway {key} is outside its reviewed bound")
    timeout_limits = {
        "EGRESS_CONNECT_TIMEOUT_SECONDS": (0.1, 60.0),
        "EGRESS_READ_TIMEOUT_SECONDS": (0.1, 120.0),
        "EGRESS_TOTAL_TIMEOUT_SECONDS": (0.1, 180.0),
    }
    parsed_timeouts: dict[str, float] = {}
    for key, (minimum, maximum) in timeout_limits.items():
        try:
            value = float(gateway_env.get(key))
        except (TypeError, ValueError):
            value = minimum - 1.0
        parsed_timeouts[key] = value
        if not minimum <= value <= maximum:
            errors.append(f"mcp-egress-gateway {key} is outside its reviewed bound")
    if parsed_timeouts["EGRESS_TOTAL_TIMEOUT_SECONDS"] < parsed_timeouts[
        "EGRESS_CONNECT_TIMEOUT_SECONDS"
    ]:
        errors.append("mcp-egress-gateway total timeout is shorter than connect timeout")
    deploy = _mapping(gateway.get("deploy"))
    try:
        replicas = int(deploy.get("replicas"))
    except (TypeError, ValueError):
        replicas = 0
    if replicas != 1:
        errors.append("mcp-egress-gateway must explicitly declare exactly one replica")
    if gateway.get("scale") not in (None, 1, "1"):
        errors.append("mcp-egress-gateway scale conflicts with the single-replica requirement")

    beat_deploy = _mapping(services["beat"].get("deploy"))
    try:
        beat_replicas = int(beat_deploy.get("replicas"))
    except (TypeError, ValueError):
        beat_replicas = 0
    if beat_replicas != 1:
        errors.append("beat must explicitly declare exactly one replica")
    if services["beat"].get("scale") not in (None, 1, "1"):
        errors.append("beat scale conflicts with the single-replica requirement")

    gateway_blocks = _parse_networks(gateway_env.get("EGRESS_BLOCKED_NETWORKS"))
    proxy_env = _environment(services["mcp-egress-proxy"])
    proxy_blocks = _parse_networks(proxy_env.get("MCP_PROXY_BLOCKED_NETWORKS"))
    if gateway_blocks is None or proxy_blocks is None:
        errors.append("gateway or proxy custom blocked-network syntax is invalid")
    elif not gateway_blocks or set(gateway_blocks) != set(proxy_blocks):
        errors.append("gateway and proxy must receive one identical non-empty blocked-network set")
    else:
        for subnet in (*declared_subnets, *options.required_blocked_networks):
            if not _is_covered(subnet, gateway_blocks):
                errors.append(
                    "the blocked-network policy does not cover every required deployment subnet"
                )
                break
    if not _is_bool(proxy_env.get("MCP_PROXY_REQUIRE_BLOCKED_NETWORKS"), True):
        errors.append("mcp-egress-proxy must require a non-empty custom blocked-network policy")

    for name in ("api", "worker"):
        environment = _environment(services[name])
        if environment.get("MCP_EGRESS_GATEWAY_URL") != "https://mcp-egress-gateway:8443":
            errors.append(f"{name} must use the internal MCP gateway")
        expected_client_paths = {
            "MCP_EGRESS_CLIENT_CERT_FILE": "/run/secrets/mcp-egress/client.crt",
            "MCP_EGRESS_CLIENT_KEY_FILE": "/run/secrets/mcp-egress/client.key",
            "MCP_EGRESS_CA_CERT_FILE": "/run/secrets/mcp-egress/ca.crt",
        }
        for key, expected_value in expected_client_paths.items():
            if environment.get(key) != expected_value:
                errors.append(f"{name} {key} differs from its reviewed secret mount")
        if environment.get("HTTP_PROXY") != "http://app-egress-proxy:3128":
            errors.append(f"{name} must use the fixed-provider HTTP proxy")
        if environment.get("HTTPS_PROXY") != "http://app-egress-proxy:3128":
            errors.append(f"{name} must use the fixed-provider HTTPS proxy")
        no_proxy = {
            item.strip().casefold()
            for item in str(environment.get("NO_PROXY") or "").split(",")
            if item.strip()
        }
        required_no_proxy = {
            "localhost",
            "127.0.0.1",
            "api",
            "postgres",
            "redis",
            "qdrant",
            "minio",
            "mcp-egress-gateway",
        }
        if "*" in no_proxy or not required_no_proxy.issubset(no_proxy):
            errors.append(f"{name} NO_PROXY differs from its reviewed internal routes")
        if any(
            key in environment
            for key in ("http_proxy", "https_proxy", "all_proxy", "ALL_PROXY", "no_proxy")
        ):
            errors.append(f"{name} receives an unreviewed proxy environment override")

    _validate_database_identity(services, errors)
    _validate_internal_dependencies(services, errors)
    _validate_minio_identity(services, errors)
    _validate_persistent_mounts(services, volumes, options, errors)
    return errors


def _parse_named_values(values: Sequence[str], flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        name, separator, target = value.partition("=")
        if not separator or not name or not target or name in result:
            raise ValueError(f"{flag} values must be unique NAME=VALUE pairs")
        result[name] = target
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--mcp-enabled", required=True, choices=("true", "false"))
    parser.add_argument(
        "--ingress-service",
        action="append",
        default=[],
        help=(
            "pass cloudflared for the required reviewed in-Compose ingress contract"
        ),
    )
    parser.add_argument(
        "--volume",
        action="append",
        default=[],
        help="Required logical=physical engine-volume identity; repeat for all four datastores",
    )
    parser.add_argument(
        "--required-blocked-network",
        action="append",
        default=[],
        help="Additional host/VPC/corporate CIDR that both egress layers must cover",
    )
    parser.add_argument(
        "--allow-local-image-ids",
        action="store_true",
        help=(
            "Permit local content-addressed sha256 image IDs for the explicit "
            "single-host clean-slate deployment path"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        physical_volumes = _parse_named_values(arguments.volume, "--volume")
        required_blocks = tuple(
            ipaddress.ip_network(value, strict=False)
            for value in arguments.required_blocked_network
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        config = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("production Compose validation failed: stdin is not valid JSON", file=sys.stderr)
        return 2

    options = ValidationOptions(
        project=arguments.project,
        mcp_enabled=arguments.mcp_enabled == "true",
        ingress_services=frozenset(arguments.ingress_service),
        physical_volumes=physical_volumes,
        required_blocked_networks=required_blocks,
        allow_local_image_ids=arguments.allow_local_image_ids,
    )
    try:
        errors = validate_production_compose(config, options)
    except Exception:
        # The input may contain secrets. Never allow an unexpected parser or
        # library exception to echo a value or traceback into an operator log.
        print("production Compose validation failed internally", file=sys.stderr)
        return 2
    if errors:
        print("production Compose validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("production Compose topology valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
