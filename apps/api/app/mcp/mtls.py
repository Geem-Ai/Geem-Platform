"""TLS identity construction for the internal MCP egress gateway."""

from __future__ import annotations

import ssl

from app.core.config import Settings


def mcp_gateway_ssl_context(settings: Settings) -> ssl.SSLContext:
    """Return a verified client-authenticated TLS context for the gateway."""

    context = ssl.create_default_context(cafile=settings.mcp_egress_ca_cert_file)
    context.load_cert_chain(
        certfile=settings.mcp_egress_client_cert_file,
        keyfile=settings.mcp_egress_client_key_file,
    )
    return context


__all__ = ["mcp_gateway_ssl_context"]
