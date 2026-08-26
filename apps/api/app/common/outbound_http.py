"""Canonical outbound-target validation for tenant-controlled HTTP destinations.

The policy is intentionally transport agnostic.  It canonicalizes a URL, resolves
its host exactly once, rejects every non-public answer, and returns the validated
addresses that a caller must connect to directly.  Connecting to the hostname
again after this function returns would re-introduce a DNS-rebinding window.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urljoin, urlsplit, urlunsplit


MAX_OUTBOUND_URL_LENGTH = 2_048

_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_AMBIGUOUS_NUMERIC_HOST = re.compile(
    r"^(?:0[xX][0-9A-Fa-f]+|[0-9]+)"
    r"(?:\.(?:0[xX][0-9A-Fa-f]+|[0-9]+)){0,3}$"
)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

# Cloud metadata endpoints are denied even in explicit local-private mode.
# Most are already non-global, but keeping the ranges explicit prevents a
# future stdlib classification change from weakening the boundary.
_METADATA_NETWORKS: tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network, ...
] = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fd00:ec2::254/128"),
    ipaddress.ip_network("168.63.129.16/32"),
    ipaddress.ip_network("100.100.100.200/32"),
    ipaddress.ip_network("192.0.0.192/32"),
)
_TRANSITION_IPV6_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("2001::/32"),
    ipaddress.ip_network("2002::/16"),
)
_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "instance-data.ec2.internal",
    }
)
_PRIVATE_DNS_SUFFIXES = (
    ".internal",
    ".local",
    ".localdomain",
    ".localhost",
    ".home.arpa",
)
_CREDENTIAL_QUERY_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "auth",
        "code",
        "clientsecret",
        "key",
        "password",
        "passwd",
        "secret",
        "sig",
        "signature",
        "token",
        "xamzcredential",
        "xamzsecuritytoken",
        "xamzsignature",
        "xgoogcredential",
        "xgoogsignature",
    }
)

AddressResolver = Callable[[str, int], Sequence[str]]


class OutboundTargetBlocked(ValueError):
    """Safe, categorical target-policy failure.

    ``code`` is suitable for an internal API response or metric.  Messages do
    not include the tenant URL, resolved address, credentials, or query string.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CanonicalOutboundUrl:
    url: str
    scheme: str
    host: str
    port: int
    request_target: str

    @property
    def origin(self) -> tuple[str, str, int]:
        return (self.scheme, self.host, self.port)

    @property
    def authority(self) -> str:
        rendered_host = f"[{self.host}]" if ":" in self.host else self.host
        default_port = 443 if self.scheme == "https" else 80
        return rendered_host if self.port == default_port else f"{rendered_host}:{self.port}"


@dataclass(frozen=True, slots=True)
class ResolvedOutboundTarget:
    canonical: CanonicalOutboundUrl
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]

    @property
    def connect_address(self) -> str:
        """The already-validated address the transport must use.

        Phase 13 deliberately performs no automatic address retry: after bytes
        may have been dispatched, replay safety depends on tool classification.
        """

        return str(self.addresses[0])


def canonicalize_outbound_url(
    raw_url: str,
    *,
    allow_http: bool = False,
    allow_private_hostnames: bool = False,
) -> CanonicalOutboundUrl:
    """Return one unambiguous canonical URL or fail closed."""

    if not isinstance(raw_url, str) or not raw_url:
        raise OutboundTargetBlocked("url_missing", "An outbound URL is required.")
    if len(raw_url) > MAX_OUTBOUND_URL_LENGTH:
        raise OutboundTargetBlocked("url_too_long", "The outbound URL is too long.")
    if _CONTROL_OR_SPACE.search(raw_url) or "\\" in raw_url:
        raise OutboundTargetBlocked("url_malformed", "The outbound URL is malformed.")
    if _INVALID_PERCENT_ESCAPE.search(raw_url):
        raise OutboundTargetBlocked("url_malformed", "The outbound URL is malformed.")

    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
        host = parsed.hostname
    except ValueError as exc:
        raise OutboundTargetBlocked("url_malformed", "The outbound URL is malformed.") from exc

    scheme = parsed.scheme.lower()
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if scheme not in allowed_schemes:
        raise OutboundTargetBlocked(
            "scheme_blocked",
            "Only approved outbound URL schemes are allowed.",
        )
    if parsed.username is not None or parsed.password is not None:
        raise OutboundTargetBlocked(
            "userinfo_blocked",
            "Credentials are not allowed in an outbound URL.",
        )
    if parsed.fragment:
        raise OutboundTargetBlocked(
            "fragment_blocked",
            "Fragments are not allowed in an outbound URL.",
        )
    for query_name, _query_value in parse_qsl(
        parsed.query,
        keep_blank_values=True,
        strict_parsing=False,
    ):
        normalized_query_name = re.sub(r"[^a-z0-9]", "", query_name.lower())
        if normalized_query_name in _CREDENTIAL_QUERY_KEYS:
            raise OutboundTargetBlocked(
                "query_credentials_blocked",
                "Credentials are not allowed in an outbound URL query.",
            )
    if not host or "%" in parsed.netloc:
        raise OutboundTargetBlocked("host_invalid", "The outbound host is invalid.")

    host = _canonicalize_host(host)
    if host in _METADATA_HOSTS:
        raise OutboundTargetBlocked("metadata_target", "Metadata targets are blocked.")

    literal = _strict_ip_address(host)
    if literal is None:
        if _AMBIGUOUS_NUMERIC_HOST.fullmatch(host):
            raise OutboundTargetBlocked(
                "ambiguous_ip_literal",
                "Ambiguous numeric IP forms are blocked.",
            )
        labels = host.split(".")
        if any(not _DNS_LABEL.fullmatch(label) for label in labels):
            raise OutboundTargetBlocked("host_invalid", "The outbound host is invalid.")
        if not allow_private_hostnames:
            if len(labels) < 2 or any(host.endswith(suffix) for suffix in _PRIVATE_DNS_SUFFIXES):
                raise OutboundTargetBlocked(
                    "private_hostname",
                    "Private and single-label hostnames are blocked.",
                )

    resolved_port = port if port is not None else (443 if scheme == "https" else 80)
    if not 1 <= resolved_port <= 65_535:
        raise OutboundTargetBlocked("port_invalid", "The outbound port is invalid.")

    path = parsed.path or "/"
    # Retain existing escapes and delimiters, but make the request target ASCII.
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="%/:@!$&'()*+,;=?-._~")
    request_target = path + (f"?{query}" if query else "")

    rendered_host = f"[{host}]" if literal is not None and literal.version == 6 else host
    default_port = 443 if scheme == "https" else 80
    netloc = rendered_host if resolved_port == default_port else f"{rendered_host}:{resolved_port}"
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    return CanonicalOutboundUrl(
        url=canonical,
        scheme=scheme,
        host=host,
        port=resolved_port,
        request_target=request_target,
    )


def resolve_outbound_target(
    raw_url: str,
    *,
    allow_http: bool = False,
    allow_private_egress: bool = False,
    deployment_networks: Iterable[str] = (),
    resolver: AddressResolver | None = None,
) -> ResolvedOutboundTarget:
    """Canonicalize, resolve once, and validate every returned address."""

    target = canonicalize_outbound_url(
        raw_url,
        allow_http=allow_http,
        allow_private_hostnames=allow_private_egress,
    )
    blocked_networks = _parse_networks(deployment_networks)
    literal = _strict_ip_address(target.host)
    raw_addresses: Sequence[str]
    if literal is not None:
        raw_addresses = (str(literal),)
    else:
        resolve = resolver or system_address_resolver
        try:
            raw_addresses = resolve(target.host, target.port)
        except OutboundTargetBlocked:
            raise
        except Exception as exc:
            raise OutboundTargetBlocked(
                "dns_resolution_failed",
                "The outbound host could not be resolved safely.",
            ) from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for raw_address in raw_addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise OutboundTargetBlocked(
                "dns_answer_invalid",
                "The outbound host returned an invalid address.",
            ) from exc
        canonical_address = str(address)
        if canonical_address in seen:
            continue
        _validate_address(
            address,
            allow_private_egress=allow_private_egress,
            deployment_networks=blocked_networks,
        )
        seen.add(canonical_address)
        addresses.append(address)

    if not addresses:
        raise OutboundTargetBlocked(
            "dns_no_addresses",
            "The outbound host returned no usable addresses.",
        )
    return ResolvedOutboundTarget(target, tuple(addresses))


def canonicalize_redirect_url(
    current_url: str,
    location: str,
    *,
    allow_http: bool = False,
    allow_private_hostnames: bool = False,
) -> CanonicalOutboundUrl:
    """Resolve one redirect location and apply the complete URL policy again."""

    if not isinstance(location, str) or not location:
        raise OutboundTargetBlocked("redirect_invalid", "The redirect target is invalid.")
    return canonicalize_outbound_url(
        urljoin(current_url, location),
        allow_http=allow_http,
        allow_private_hostnames=allow_private_hostnames,
    )


def same_origin(left: CanonicalOutboundUrl, right: CanonicalOutboundUrl) -> bool:
    return left.origin == right.origin


def system_address_resolver(host: str, port: int) -> Sequence[str]:
    """Resolve TCP addresses without performing any connection."""

    try:
        records = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise OutboundTargetBlocked(
            "dns_resolution_failed",
            "The outbound host could not be resolved safely.",
        ) from exc
    return tuple(record[4][0] for record in records)


def _canonicalize_host(raw_host: str) -> str:
    host = raw_host.rstrip(".").lower()
    if not host or len(host) > 253:
        raise OutboundTargetBlocked("host_invalid", "The outbound host is invalid.")
    if "%" in host:  # IPv6 zone identifiers and percent-encoded host forms.
        raise OutboundTargetBlocked("host_invalid", "The outbound host is invalid.")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise OutboundTargetBlocked("host_invalid", "The outbound host is invalid.") from exc


def _strict_ip_address(
    host: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _parse_networks(
    values: Iterable[str],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError as exc:
            raise OutboundTargetBlocked(
                "deployment_network_invalid",
                "A configured deployment network is invalid.",
            ) from exc
    return tuple(networks)


def _validate_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private_egress: bool,
    deployment_networks: Sequence[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        raise OutboundTargetBlocked(
            "mapped_address_blocked",
            "IPv4-mapped IPv6 targets are blocked.",
        )
    if isinstance(address, ipaddress.IPv6Address) and any(
        address in network for network in _TRANSITION_IPV6_NETWORKS
    ):
        raise OutboundTargetBlocked(
            "transition_address_blocked",
            "IPv4 transition and translation targets are blocked.",
        )
    if any(
        address in network
        for network in _METADATA_NETWORKS
        if address.version == network.version
    ):
        raise OutboundTargetBlocked("metadata_target", "Metadata targets are blocked.")
    if any(
        address in network
        for network in deployment_networks
        if address.version == network.version
    ):
        raise OutboundTargetBlocked(
            "deployment_target",
            "Deployment-internal targets are blocked.",
        )
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        raise OutboundTargetBlocked("non_public_target", "Non-public targets are blocked.")
    if address.is_link_local:
        raise OutboundTargetBlocked("link_local_target", "Link-local targets are blocked.")
    if allow_private_egress:
        return
    if not address.is_global:
        raise OutboundTargetBlocked("private_target", "Private targets are blocked.")


__all__ = [
    "AddressResolver",
    "CanonicalOutboundUrl",
    "MAX_OUTBOUND_URL_LENGTH",
    "OutboundTargetBlocked",
    "ResolvedOutboundTarget",
    "canonicalize_outbound_url",
    "canonicalize_redirect_url",
    "resolve_outbound_target",
    "same_origin",
    "system_address_resolver",
]
