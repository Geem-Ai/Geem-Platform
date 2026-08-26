"""One-operation executor: validate, dispatch once, and revalidate redirects."""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.common.outbound_http import (
    OutboundTargetBlocked,
    ResolvedOutboundTarget,
    resolve_outbound_target,
    same_origin,
)

from .config import GatewaySettings
from .models import OutboundOperationRequest, OutboundOperationResponse
from .transport import GatewayTransportError, PinnedHttpTransport, TransportResponse


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CROSS_ORIGIN_SAFE_HEADERS = frozenset({"accept", "accept-language", "user-agent"})
_DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="egress-dns",
)


class Transport(Protocol):
    def send(
        self,
        *,
        target: ResolvedOutboundTarget,
        method: str,
        headers: dict[str, str],
        body: bytes,
        deadline: float,
    ) -> TransportResponse: ...


Resolver = Callable[[str, int], tuple[str, ...]]


@dataclass(slots=True)
class BoundedOutboundExecutor:
    settings: GatewaySettings
    transport: Transport
    resolver: Resolver | None = None

    @classmethod
    def build(cls, settings: GatewaySettings) -> "BoundedOutboundExecutor":
        return cls(settings=settings, transport=PinnedHttpTransport(settings))

    def execute(self, request: OutboundOperationRequest) -> OutboundOperationResponse:
        try:
            body = request.decoded_body(max_bytes=self.settings.max_request_bytes)
        except ValueError as exc:
            raise GatewayTransportError(
                "request_body_invalid", "The outbound request body is invalid."
            ) from exc
        if len(request.headers) > self.settings.max_headers:
            raise GatewayTransportError(
                "request_headers_too_large",
                "The outbound request headers exceed the configured limit.",
            )

        deadline = time.monotonic() + self.settings.total_timeout_seconds
        target = self._resolve(request.url, deadline=deadline)
        headers = dict(request.headers)
        redirects = 0

        while True:
            response = self.transport.send(
                target=target,
                method=request.method,
                headers=headers,
                body=body,
                deadline=deadline,
            )
            if request.method == "POST" and response.status_code in _REDIRECT_STATUSES:
                raise GatewayTransportError(
                    "outbound_redirect_ambiguous",
                    "A non-idempotent outbound redirect is outcome-ambiguous.",
                    dispatch_started=True,
                )
            location = response.headers.get("location")
            if (
                not request.follow_redirects
                or response.status_code not in _REDIRECT_STATUSES
                or not location
            ):
                result = OutboundOperationResponse(
                    operation_id=request.operation_id,
                    status_code=response.status_code,
                    headers=response.headers,
                    body_base64=base64.b64encode(response.body).decode("ascii"),
                    redirects_followed=redirects,
                    final_origin_digest=_origin_digest(target),
                )
                envelope_limit = (
                    ((self.settings.max_response_bytes + 2) // 3) * 4
                    + self.settings.max_header_bytes
                    + 16_384
                )
                if (
                    len(result.model_dump_json().encode("utf-8"))
                    > envelope_limit
                ):
                    raise GatewayTransportError(
                        "upstream_response_too_large",
                        "The normalized outbound response exceeds the configured limit.",
                    )
                return result
            if redirects >= self.settings.max_redirects:
                raise GatewayTransportError(
                    "redirect_limit_reached",
                    "The outbound redirect limit was reached.",
                )

            next_target = self._resolve_from_redirect(
                target,
                location,
                deadline=deadline,
            )
            if not same_origin(target.canonical, next_target.canonical):
                # A static secret may use any allowed custom header.  Preserve
                # only explicitly harmless representation headers across an
                # origin change rather than trying to guess which value is a
                # credential.
                headers = {
                    name: value
                    for name, value in headers.items()
                    if name.lower() in _CROSS_ORIGIN_SAFE_HEADERS
                }
            target = next_target
            redirects += 1

    def validate_target(
        self,
        target_url: str,
        *,
        deadline_seconds: float | None = None,
    ) -> str:
        """Resolve and policy-check a target without opening a socket."""

        budget = float(self.settings.total_timeout_seconds)
        if deadline_seconds is not None:
            budget = min(budget, max(0.001, float(deadline_seconds)))
        deadline = time.monotonic() + budget
        return _origin_digest(self._resolve(target_url, deadline=deadline))

    def _resolve(self, url: str, *, deadline: float) -> ResolvedOutboundTarget:
        kwargs: dict[str, object] = {}
        if self.resolver is not None:
            kwargs["resolver"] = self.resolver
        future = _DNS_EXECUTOR.submit(
            resolve_outbound_target,
            url,
            allow_http=self.settings.is_local and self.settings.allow_private_egress,
            allow_private_egress=(
                self.settings.is_local and self.settings.allow_private_egress
            ),
            deployment_networks=self.settings.deployment_networks,
            **kwargs,  # type: ignore[arg-type]
        )
        try:
            target = future.result(
                timeout=max(0.001, deadline - time.monotonic())
            )
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise GatewayTransportError(
                "operation_timeout",
                "The outbound target resolution exceeded its deadline.",
                retryable=True,
            ) from exc
        if not self.settings.is_local and target.canonical.port != 443:
            raise OutboundTargetBlocked(
                "port_blocked",
                "Only the reviewed public HTTPS port is allowed.",
            )
        return target

    def _resolve_from_redirect(
        self,
        current: ResolvedOutboundTarget,
        location: str,
        *,
        deadline: float,
    ) -> ResolvedOutboundTarget:
        from urllib.parse import urljoin

        return self._resolve(
            urljoin(current.canonical.url, location),
            deadline=deadline,
        )


def _origin_digest(target: ResolvedOutboundTarget) -> str:
    origin = "|".join(
        (
            target.canonical.scheme,
            target.canonical.host,
            str(target.canonical.port),
        )
    )
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()


__all__ = ["BoundedOutboundExecutor", "Transport"]
