# MCP egress mTLS files

This directory is intentionally empty in git. Compose mounts each identity as
an individual secret; no service receives the other side's private key.
Provision certificates with mode `0644`; provision keys with mode `0400`/`0440`.
The gateway server key must be readable by container UID/GID `10001` (prefer
ownership `10001:10001` rather than a world-readable key):

- `ca/ca.crt` — client/server trust anchor
- `server/server.crt`, `server/server.key` — gateway server identity; SAN must contain
  `mcp-egress-gateway`
- `client/client.crt`, `client/client.key` — API/worker client identity

Production certificates must come from the deployment secret manager or
internal PKI and should use distinct client identities per environment. Never
copy the application JWT, connector credential encryption key, provider keys,
or a public web certificate into this boundary.

For local-only development, generate a short-lived dedicated CA and leaf
certificates with OpenSSL. Keep every generated file ignored by git and rotate
them before sharing a development environment.
