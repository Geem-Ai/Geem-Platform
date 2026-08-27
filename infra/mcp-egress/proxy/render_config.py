"""Render static and deployment CIDRs into the MCP Squid policy and start Squid.

The gateway validates tenant targets in Python, but Squid is an independent
network boundary and must enforce the tracked static deny policy plus the same
deployment-owned CIDRs. Values are parsed as networks and rendered as data-only
ACL entries; raw environment text is never copied into the Squid configuration.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import subprocess


STATIC_TEMPLATE_MARKER = "# __GEEM_STATIC_BLOCKS__"
TEMPLATE_MARKER = "# __GEEM_DEPLOYMENT_BLOCKS__"
DEFAULT_TEMPLATE = Path("/etc/squid/squid.conf")
STATIC_DENY_MANIFEST = Path(
    "/etc/geem/mcp-egress/static-deny-networks.txt"
)
DEFAULT_OUTPUT = Path("/run/geem-mcp-squid.conf")
SQUID_BINARY = "/usr/sbin/squid"


class ProxyPolicyError(RuntimeError):
    """Raised when the proxy policy cannot be rendered safely."""


def parse_bool(name: str, raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ProxyPolicyError(f"{name} must be true or false")


def _parse_network_values(
    values: list[str],
    *,
    strict: bool,
    error_message: str,
) -> tuple[str, ...]:
    networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        try:
            networks.add(ipaddress.ip_network(candidate, strict=strict))
        except ValueError as exc:
            raise ProxyPolicyError(error_message) from exc
    ordered = sorted(
        networks,
        key=lambda network: (
            network.version,
            int(network.network_address),
            network.prefixlen,
        ),
    )
    return tuple(str(network) for network in ordered)


def parse_networks(raw: str) -> tuple[str, ...]:
    return _parse_network_values(
        raw.split(","),
        strict=False,
        error_message="MCP_PROXY_BLOCKED_NETWORKS contains an invalid CIDR",
    )


def parse_static_manifest(raw: str) -> tuple[str, ...]:
    values = [
        line
        for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    networks = _parse_network_values(
        values,
        strict=True,
        error_message="The static MCP proxy deny manifest contains an invalid CIDR",
    )
    if not networks:
        raise ProxyPolicyError("The static MCP proxy deny manifest is empty")
    return networks


def _acl_lines(networks: tuple[str, ...]) -> str:
    return "\n".join(
        f"acl blocked_destination dst {network}" for network in networks
    )


def render_policy(
    template: str,
    networks: tuple[str, ...],
    *,
    static_networks: tuple[str, ...],
    require_networks: bool,
) -> str:
    if template.count(STATIC_TEMPLATE_MARKER) != 1:
        raise ProxyPolicyError(
            "Squid static-policy template marker is missing or duplicated"
        )
    if template.count(TEMPLATE_MARKER) != 1:
        raise ProxyPolicyError(
            "Squid deployment-policy template marker is missing or duplicated"
        )
    if not static_networks:
        raise ProxyPolicyError("The static MCP proxy deny manifest is empty")
    if require_networks and not networks:
        raise ProxyPolicyError(
            "MCP proxy deployment CIDRs are required by production policy"
        )
    rendered_acl = _acl_lines(networks)
    if not rendered_acl:
        rendered_acl = "# No additional deployment CIDRs configured."
    return template.replace(
        STATIC_TEMPLATE_MARKER,
        _acl_lines(static_networks),
    ).replace(TEMPLATE_MARKER, rendered_acl)


def write_policy(path: Path, content: str) -> None:
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


def main() -> None:
    networks = parse_networks(os.getenv("MCP_PROXY_BLOCKED_NETWORKS", ""))
    require_networks = parse_bool(
        "MCP_PROXY_REQUIRE_BLOCKED_NETWORKS",
        os.getenv("MCP_PROXY_REQUIRE_BLOCKED_NETWORKS"),
    )
    try:
        template = DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProxyPolicyError("Squid policy template is unreadable") from exc
    try:
        static_manifest = STATIC_DENY_MANIFEST.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProxyPolicyError("Static MCP proxy deny manifest is unreadable") from exc
    rendered = render_policy(
        template,
        networks,
        static_networks=parse_static_manifest(static_manifest),
        require_networks=require_networks,
    )
    write_policy(DEFAULT_OUTPUT, rendered)
    subprocess.run(
        [SQUID_BINARY, "-k", "parse", "-f", str(DEFAULT_OUTPUT)],
        check=True,
        timeout=10,
    )
    os.execv(
        SQUID_BINARY,
        [SQUID_BINARY, "-N", "-f", str(DEFAULT_OUTPUT)],
    )


if __name__ == "__main__":
    main()
