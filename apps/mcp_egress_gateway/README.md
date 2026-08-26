# Geem MCP egress gateway

This is the Phase 13A security boundary for tenant-derived outbound HTTP. It is
an internal mTLS API, not a public service and not a general forward proxy.

- It receives only bounded operations under a hard concurrency limit.
- It resolves a target once and connects to the validated IP with the original
  hostname preserved for HTTP `Host`, TLS SNI, and certificate verification.
- Safe GET/HEAD redirects are bounded and fully revalidated. Cross-origin
  redirects lose every caller header except a small representation allowlist.
- It has no application datastore network or application credentials. MCP
  framing, negotiation, and result validation use the pinned official
  `mcp==2.0.0` SDK.
- In deployed environments it has no direct public route; it can reach only the
  dedicated deny-private forward proxy.
- Access logs are disabled. Logs contain operation IDs, categorical outcomes,
  timings, status, and an origin digest—never URL, headers, credentials, body,
  resolved IP, or response data.

The TLS listener is configured with `CERT_REQUIRED`; callers must present a
certificate issued by the mounted client CA. Provision `ca/ca.crt`, the
`server/` identity, and the `client/` identity outside git. Compose mounts each
file as a per-service secret, so neither side receives the other's private key.

## Internal API contract

All routes are available only on the mTLS listener. Unknown fields are
rejected, request/response/header sizes are capped, and errors never echo
tenant URLs, headers, or bodies.

`POST /v1/outbound` is the protocol-neutral Phase 13A primitive:

```json
{
  "operation_id": "opaque-id",
  "method": "GET|HEAD|POST",
  "url": "https://public.example/path",
  "headers": {"Authorization": "ephemeral value"},
  "body_base64": "optional",
  "follow_redirects": false
}
```

It returns `operation_id`, `status_code`, filtered `headers`, `body_base64`,
`redirects_followed`, and `final_origin_digest`. Redirect following is allowed
only for GET/HEAD; every hop is re-resolved and revalidated.

`POST /v1/target-validation` is a resolve-only creation preflight. Its strict
body contains only `operation_id`, `target_url`, `caller_binding`, and the two
deadline fields; credentials and operation payloads are not accepted. A target
is resolved and policy-checked again at real dispatch, so preflight never
creates a DNS-rebinding bypass.

`POST /v1/mcp` is the SDK-mediated MCP façade:

```json
{
  "operation_id": "opaque-id",
  "operation": "discover|tools_list|tools_call",
  "target_url": "https://public.example/mcp",
  "headers": {"Authorization": "ephemeral value"},
  "mode": "auto|legacy|2026-07-28",
  "caller_binding": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "session_handle": "optional-opaque-legacy-handle",
  "cursor": "tools_list-only",
  "tool_name": "tools_call-only",
  "arguments": {},
  "write": false,
  "deadline_seconds": 30.0,
  "deadline_unix_ms": 1787760000000
}
```

The API supplies both remaining duration and epoch deadline. The gateway uses
the earlier bound, charging connect/TLS transit, request-envelope ingestion,
session-lock wait, negotiation, and the operation itself to one budget. The
epoch value never extends the bounded duration under clock skew.

The response contains `negotiated_protocol_version`, `session_mode`,
`capabilities`, optional `server_info`, `supported_versions`, tools/cursor or
tool result, and (for legacy sessions) `session_handle` plus
`session_expires_in_seconds`. The API must reuse that handle with the same
caller-binding digest and canonical target for all legacy pagination/call
operations. The gateway owns at most 64 SDK sessions by default, serializes
each handle, and applies a non-sliding 300-second absolute lifetime. State is
intentionally in-memory: a missing handle after expiry or restart fails before
tool dispatch.
Revision `2025-11-25` uses initialized Streamable HTTP with the SDK-owned
session ID. Revision `2024-11-05` uses the SDK's endpoint-event HTTP+SSE
channel. Endpoint events are bounded and same-origin checked before any
credential-bearing POST; every SSE event/data message is independently capped,
and the live channel is owned by the same opaque session handle until close or
absolute expiry.

Explicitly close a legacy session when work finishes:

```json
{
  "operation_id": "opaque-id",
  "operation": "session_close",
  "caller_binding": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "session_handle": "opaque-legacy-handle",
  "mode": "legacy"
}
```

Tool calls never follow redirects or retry. A dispatched write that loses its
response, or receives a redirect, returns HTTP 409 with
`error.outcome_unknown=true`. Task-augmented calls, input-required multi-round
trips, and claimed extension results are rejected.
