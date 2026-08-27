from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RENDERER_PATH = REPO_ROOT / "infra/mcp-egress/proxy/render_config.py"
MANIFEST_PATH = REPO_ROOT / "infra/mcp-egress/proxy/static-deny-networks.txt"
SPEC = importlib.util.spec_from_file_location("mcp_proxy_render_config", RENDERER_PATH)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)
STATIC_NETWORKS = renderer.parse_static_manifest(MANIFEST_PATH.read_text())

EXPECTED_STATIC_NETWORKS = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "168.63.129.16/32",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.88.99.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "::/3",
    "2001::/23",
    "2001:db8::/32",
    "2002::/16",
    "3fff::/20",
    "4000::/2",
    "8000::/1",
)


def policy_template() -> str:
    return (
        f"{renderer.STATIC_TEMPLATE_MARKER}\n"
        f"{renderer.TEMPLATE_MARKER}\n"
        "http_access deny blocked_destination\n"
    )


def test_networks_are_validated_canonicalized_and_deduplicated() -> None:
    assert renderer.parse_networks(
        "172.19.4.9/16, 2001:db8::1/48,172.19.0.0/16"
    ) == ("172.19.0.0/16", "2001:db8::/48")


def test_invalid_network_cannot_inject_squid_syntax() -> None:
    with pytest.raises(renderer.ProxyPolicyError):
        renderer.parse_networks("172.19.0.0/16\nhttp_access allow all")


def test_static_manifest_cannot_inject_squid_syntax() -> None:
    with pytest.raises(renderer.ProxyPolicyError):
        renderer.parse_static_manifest(
            "10.0.0.0/8\nhttp_access allow all\n"
        )


def test_production_policy_requires_deployment_networks() -> None:
    with pytest.raises(renderer.ProxyPolicyError):
        renderer.render_policy(
            policy_template(),
            (),
            static_networks=STATIC_NETWORKS,
            require_networks=True,
        )


def test_rendered_policy_adds_only_data_acl_entries_before_access_rules() -> None:
    rendered = renderer.render_policy(
        policy_template(),
        ("172.19.0.0/16", "fd00:1234::/48"),
        static_networks=STATIC_NETWORKS,
        require_networks=True,
    )
    assert renderer.STATIC_TEMPLATE_MARKER not in rendered
    assert renderer.TEMPLATE_MARKER not in rendered
    assert "acl blocked_destination dst 10.0.0.0/8" in rendered
    assert "acl blocked_destination dst 8000::/1" in rendered
    assert "acl blocked_destination dst 172.19.0.0/16" in rendered
    assert "acl blocked_destination dst fd00:1234::/48" in rendered
    assert rendered.index("172.19.0.0/16") < rendered.index("http_access deny")


def test_deployed_proxy_image_uses_the_fail_closed_renderer() -> None:
    dockerfile = (REPO_ROOT / "infra/mcp-egress/proxy/Dockerfile").read_text()
    squid = (REPO_ROOT / "infra/mcp-egress/proxy/squid.conf").read_text()
    assert "render_mcp_proxy_config.py" in dockerfile
    assert (
        "COPY static-deny-networks.txt "
        "/etc/geem/mcp-egress/static-deny-networks.txt"
    ) in dockerfile
    assert 'ENTRYPOINT ["python3"' in dockerfile
    assert squid.count(renderer.STATIC_TEMPLATE_MARKER) == 1
    assert squid.count(renderer.TEMPLATE_MARKER) == 1
    assert squid.index(renderer.STATIC_TEMPLATE_MARKER) < squid.index(
        renderer.TEMPLATE_MARKER
    )
    assert squid.index(renderer.TEMPLATE_MARKER) < squid.index(
        "http_access deny blocked_destination"
    )
    assert renderer.SQUID_BINARY == "/usr/sbin/squid"
    assert renderer.STATIC_DENY_MANIFEST == Path(
        "/etc/geem/mcp-egress/static-deny-networks.txt"
    )
    assert "MCP_PROXY_TEMPLATE" not in RENDERER_PATH.read_text()
    assert "MCP_PROXY_RENDERED_CONFIG" not in RENDERER_PATH.read_text()


def test_static_deny_manifest_is_the_reviewed_conservative_policy() -> None:
    assert STATIC_NETWORKS == EXPECTED_STATIC_NETWORKS


def test_every_manifest_network_is_rendered_as_data() -> None:
    template = (REPO_ROOT / "infra/mcp-egress/proxy/squid.conf").read_text()
    rendered = renderer.render_policy(
        template,
        (),
        static_networks=STATIC_NETWORKS,
        require_networks=False,
    )
    assert renderer.STATIC_TEMPLATE_MARKER not in rendered
    assert renderer.TEMPLATE_MARKER not in rendered
    for network in STATIC_NETWORKS:
        assert f"acl blocked_destination dst {network}" in rendered


@pytest.mark.parametrize(
    "network",
    [
        "192.88.99.0/24",
        "2001:db8::/32",
        "3fff::/20",
        "4000::/2",
        "8000::/1",
    ],
)
def test_static_proxy_policy_independently_denies_special_ranges(network: str) -> None:
    assert network in STATIC_NETWORKS
