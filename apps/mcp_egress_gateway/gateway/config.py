"""Environment-only configuration for the isolated egress gateway."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false.")


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be numeric.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    app_env: str = "production"
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443
    server_cert_file: str = "/run/secrets/mcp-egress/server.crt"
    server_key_file: str = "/run/secrets/mcp-egress/server.key"
    client_ca_file: str = "/run/secrets/mcp-egress/ca.crt"
    forward_proxy_url: str = ""
    allow_private_egress: bool = False
    deployment_networks: tuple[str, ...] = ()
    supported_protocol_versions: tuple[str, ...] = (
        "2026-07-28",
        "2025-11-25",
        "2024-11-05",
    )
    max_redirects: int = 3
    max_request_bytes: int = 65_536
    # A tools/list response contains the JSON Schema for every advertised
    # tool. Real-world inventories can exceed 64 KiB without being malformed.
    max_response_bytes: int = 262_144
    max_header_bytes: int = 16_384
    max_headers: int = 64
    max_discovered_tools: int = 512
    max_tool_pages: int = 64
    legacy_session_ttl_seconds: int = 300
    max_legacy_sessions: int = 64
    max_concurrent_operations: int = 128
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    total_timeout_seconds: float = 30.0

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() in {"local", "dev", "development", "test"}

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            app_env=os.getenv("APP_ENV", "production"),
            bind_host=os.getenv("EGRESS_BIND_HOST", "0.0.0.0"),
            bind_port=_env_int("EGRESS_BIND_PORT", 8443, minimum=1, maximum=65_535),
            server_cert_file=os.getenv(
                "EGRESS_SERVER_CERT_FILE", "/run/secrets/mcp-egress/server.crt"
            ),
            server_key_file=os.getenv(
                "EGRESS_SERVER_KEY_FILE", "/run/secrets/mcp-egress/server.key"
            ),
            client_ca_file=os.getenv(
                "EGRESS_CLIENT_CA_FILE", "/run/secrets/mcp-egress/ca.crt"
            ),
            forward_proxy_url=os.getenv("EGRESS_FORWARD_PROXY_URL", "").strip(),
            allow_private_egress=_env_bool("EGRESS_ALLOW_PRIVATE", False),
            deployment_networks=tuple(
                value.strip()
                for value in os.getenv("EGRESS_BLOCKED_NETWORKS", "").split(",")
                if value.strip()
            ),
            supported_protocol_versions=tuple(
                value.strip()
                for value in os.getenv(
                    "EGRESS_SUPPORTED_PROTOCOL_VERSIONS",
                    "2026-07-28,2025-11-25,2024-11-05",
                ).split(",")
                if value.strip()
            ),
            max_redirects=_env_int("EGRESS_MAX_REDIRECTS", 3, minimum=0, maximum=10),
            max_request_bytes=_env_int(
                "EGRESS_MAX_REQUEST_BYTES", 65_536, minimum=1, maximum=1_048_576
            ),
            max_response_bytes=_env_int(
                "EGRESS_MAX_RESPONSE_BYTES", 262_144, minimum=1, maximum=1_048_576
            ),
            max_header_bytes=_env_int(
                "EGRESS_MAX_HEADER_BYTES", 16_384, minimum=1_024, maximum=65_536
            ),
            max_headers=_env_int("EGRESS_MAX_HEADERS", 64, minimum=1, maximum=256),
            max_discovered_tools=_env_int(
                "EGRESS_MAX_DISCOVERED_TOOLS", 512, minimum=1, maximum=4_096
            ),
            max_tool_pages=_env_int(
                "EGRESS_MAX_TOOL_PAGES", 64, minimum=1, maximum=512
            ),
            legacy_session_ttl_seconds=_env_int(
                "EGRESS_LEGACY_SESSION_TTL_SECONDS",
                300,
                minimum=30,
                maximum=3_600,
            ),
            max_legacy_sessions=_env_int(
                "EGRESS_MAX_LEGACY_SESSIONS", 64, minimum=1, maximum=1_024
            ),
            max_concurrent_operations=_env_int(
                "EGRESS_MAX_CONCURRENT_OPERATIONS",
                128,
                minimum=1,
                maximum=2_048,
            ),
            connect_timeout_seconds=_env_float(
                "EGRESS_CONNECT_TIMEOUT_SECONDS", 5.0, minimum=0.1, maximum=60.0
            ),
            read_timeout_seconds=_env_float(
                "EGRESS_READ_TIMEOUT_SECONDS", 20.0, minimum=0.1, maximum=120.0
            ),
            total_timeout_seconds=_env_float(
                "EGRESS_TOTAL_TIMEOUT_SECONDS", 30.0, minimum=0.1, maximum=180.0
            ),
        )

    def validate_runtime(self) -> None:
        """Fail before listening if the mTLS/proxy boundary is incomplete."""

        if self.allow_private_egress and not self.is_local:
            raise RuntimeError("EGRESS_ALLOW_PRIVATE may only be enabled in local/test.")
        if (
            not self.supported_protocol_versions
            or self.supported_protocol_versions[0] != "2026-07-28"
            or len(self.supported_protocol_versions)
            != len(set(self.supported_protocol_versions))
            or not set(self.supported_protocol_versions).issubset(
                {"2026-07-28", "2025-11-25", "2024-11-05"}
            )
        ):
            raise RuntimeError(
                "EGRESS_SUPPORTED_PROTOCOL_VERSIONS contains an unreviewed revision."
            )
        for network in self.deployment_networks:
            try:
                ipaddress.ip_network(network, strict=False)
            except ValueError as exc:
                raise RuntimeError(
                    "EGRESS_BLOCKED_NETWORKS contains an invalid CIDR."
                ) from exc
        for label, value in (
            ("EGRESS_SERVER_CERT_FILE", self.server_cert_file),
            ("EGRESS_SERVER_KEY_FILE", self.server_key_file),
            ("EGRESS_CLIENT_CA_FILE", self.client_ca_file),
        ):
            if (
                not value
                or not os.path.isfile(value)
                or not os.access(value, os.R_OK)
            ):
                raise RuntimeError(
                    f"{label} must reference a readable mounted mTLS file."
                )
        if self.total_timeout_seconds < self.connect_timeout_seconds:
            raise RuntimeError(
                "EGRESS_TOTAL_TIMEOUT_SECONDS must cover the connect timeout."
            )
        if not self.is_local and not self.forward_proxy_url:
            raise RuntimeError(
                "EGRESS_FORWARD_PROXY_URL is required outside local/test so the gateway "
                "has no direct public route."
            )
        if self.forward_proxy_url:
            try:
                parsed = urlsplit(self.forward_proxy_url)
                proxy_port = parsed.port
            except ValueError as exc:
                raise RuntimeError(
                    "EGRESS_FORWARD_PROXY_URL must contain a valid port."
                ) from exc
            if (
                parsed.scheme != "http"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or proxy_port is None
            ):
                raise RuntimeError(
                    "EGRESS_FORWARD_PROXY_URL must be an http origin without user-info."
                )
