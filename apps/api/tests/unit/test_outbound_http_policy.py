"""Phase 13A outbound-target policy regression tests."""

from __future__ import annotations

import pytest

from app.common.outbound_http import (
    OutboundTargetBlocked,
    canonicalize_outbound_url,
    resolve_outbound_target,
)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://example.com", "scheme_blocked"),
        ("https://user:secret@example.com", "userinfo_blocked"),
        ("https://example.com/path#fragment", "fragment_blocked"),
        ("https://example.com\\@127.0.0.1/", "url_malformed"),
        ("https://example.com/%zz", "url_malformed"),
        ("https://example.com/mcp?api_key=secret", "query_credentials_blocked"),
        ("https://example.com/mcp?access%5Ftoken=secret", "query_credentials_blocked"),
        ("https://example.com/callback?code=secret", "query_credentials_blocked"),
        (
            "https://example.com/mcp?X-Goog-Credential=secret",
            "query_credentials_blocked",
        ),
        (
            "https://example.com/mcp?X-Goog-Signature=secret",
            "query_credentials_blocked",
        ),
        (
            "https://example.com/mcp?X-Amz-Security-Token=secret",
            "query_credentials_blocked",
        ),
        ("https://postgres:5432", "private_hostname"),
        ("https://qdrant:6333", "private_hostname"),
        ("https://metadata.google.internal", "metadata_target"),
        ("https://127.1", "ambiguous_ip_literal"),
        ("https://2130706433", "ambiguous_ip_literal"),
        ("https://0177.0.0.1", "ambiguous_ip_literal"),
        ("https://0x7f000001", "ambiguous_ip_literal"),
    ],
)
def test_url_layer_rejects_ambiguous_and_internal_forms(url: str, code: str) -> None:
    with pytest.raises(OutboundTargetBlocked) as raised:
        canonicalize_outbound_url(url)
    assert raised.value.code == code
    assert url not in str(raised.value)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "100.64.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "64:ff9b::5db8:d822",
        "64:ff9b:1::1",
        "2002:a00:1::",
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",
        "168.63.129.16",
    ],
)
def test_resolution_layer_rejects_private_metadata_and_mapped_addresses(address: str) -> None:
    with pytest.raises(OutboundTargetBlocked):
        resolve_outbound_target(
            "https://tools.example.com/mcp",
            resolver=lambda _host, _port: (address,),
        )


def test_every_dns_answer_must_be_public() -> None:
    with pytest.raises(OutboundTargetBlocked) as raised:
        resolve_outbound_target(
            "https://tools.example.com/mcp",
            resolver=lambda _host, _port: ("93.184.216.34", "10.0.0.7"),
        )
    assert raised.value.code == "private_target"


def test_validated_addresses_are_returned_for_pinned_connect() -> None:
    calls: list[tuple[str, int]] = []

    def resolver(host: str, port: int) -> tuple[str, ...]:
        calls.append((host, port))
        return ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946")

    target = resolve_outbound_target(
        "HTTPS://Example.COM.:443/a%20path?x=1",
        resolver=resolver,
    )
    assert calls == [("example.com", 443)]
    assert target.canonical.url == "https://example.com/a%20path?x=1"
    assert target.canonical.request_target == "/a%20path?x=1"
    assert target.connect_address == "93.184.216.34"
    assert tuple(str(item) for item in target.addresses) == (
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    )


def test_configured_deployment_cidr_is_always_blocked() -> None:
    with pytest.raises(OutboundTargetBlocked) as raised:
        resolve_outbound_target(
            "https://tools.example.com",
            deployment_networks=("93.184.216.0/24",),
            resolver=lambda _host, _port: ("93.184.216.34",),
        )
    assert raised.value.code == "deployment_target"


def test_local_private_mode_is_explicit_and_still_blocks_metadata() -> None:
    local = resolve_outbound_target(
        "http://mcp-test-server:8080/tools",
        allow_http=True,
        allow_private_egress=True,
        resolver=lambda _host, _port: ("172.20.0.15",),
    )
    assert local.connect_address == "172.20.0.15"

    with pytest.raises(OutboundTargetBlocked) as raised:
        resolve_outbound_target(
            "http://metadata.google.internal",
            allow_http=True,
            allow_private_egress=True,
            resolver=lambda _host, _port: ("169.254.169.254",),
        )
    assert raised.value.code == "metadata_target"


def test_ipv6_literal_is_canonicalized_with_brackets() -> None:
    target = canonicalize_outbound_url(
        "https://[2606:4700:4700::1111]:8443/mcp"
    )
    assert target.url == "https://[2606:4700:4700::1111]:8443/mcp"
    assert target.authority == "[2606:4700:4700::1111]:8443"
