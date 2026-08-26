from __future__ import annotations

from types import SimpleNamespace

import app.mcp.gateway_client as gateway_client_module
import app.mcp.mtls as mtls_module
import app.mcp.oauth as oauth_module
from app.mcp.gateway_client import HttpMcpGatewayClient
from app.mcp.mtls import mcp_gateway_ssl_context
from app.mcp.oauth import HttpMcpOAuthGateway


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        mcp_egress_gateway_url="https://mcp-egress-gateway:8443",
        mcp_egress_client_cert_file="/run/secrets/mcp-egress/client.crt",
        mcp_egress_client_key_file="/run/secrets/mcp-egress/client.key",
        mcp_egress_ca_cert_file="/run/secrets/mcp-egress/ca.crt",
        mcp_egress_total_timeout_seconds=30,
        mcp_egress_connect_timeout_seconds=5,
        mcp_egress_read_timeout_seconds=20,
    )


def test_mcp_gateway_ssl_context_loads_ca_and_client_identity(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class FakeContext:
        def load_cert_chain(self, *, certfile: str, keyfile: str) -> None:
            observed["certfile"] = certfile
            observed["keyfile"] = keyfile

    context = FakeContext()

    def create_default_context(*, cafile: str):
        observed["cafile"] = cafile
        return context

    monkeypatch.setattr(mtls_module.ssl, "create_default_context", create_default_context)

    assert mcp_gateway_ssl_context(_settings()) is context  # type: ignore[arg-type]
    assert observed == {
        "cafile": "/run/secrets/mcp-egress/ca.crt",
        "certfile": "/run/secrets/mcp-egress/client.crt",
        "keyfile": "/run/secrets/mcp-egress/client.key",
    }


def test_internal_gateway_clients_pass_loaded_ssl_context_to_httpx(monkeypatch) -> None:
    context = object()
    constructed: list[dict] = []

    class DummyHttpClient:
        def close(self) -> None:
            pass

    def build_http_client(**kwargs):
        constructed.append(kwargs)
        return DummyHttpClient()

    monkeypatch.setattr(
        gateway_client_module,
        "mcp_gateway_ssl_context",
        lambda _settings: context,
    )
    monkeypatch.setattr(
        oauth_module,
        "mcp_gateway_ssl_context",
        lambda _settings: context,
    )
    monkeypatch.setattr(gateway_client_module.httpx, "Client", build_http_client)

    runtime = HttpMcpGatewayClient(_settings())  # type: ignore[arg-type]
    oauth = HttpMcpOAuthGateway(_settings())  # type: ignore[arg-type]

    assert len(constructed) == 2
    assert all(kwargs["verify"] is context for kwargs in constructed)
    assert all("cert" not in kwargs for kwargs in constructed)
    runtime.close()
    oauth.close()
