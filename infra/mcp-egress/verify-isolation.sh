#!/bin/sh
set -eu

# Phase 13A deployed-boundary smoke gate. Run only after the base application
# and the `mcp` profile are healthy. It intentionally tests the actual Compose
# network namespaces and mounted certificates; unit tests cannot substitute for
# this check.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE=${MCP_SMOKE_COMPOSE_FILE:-$REPO_ROOT/infra/docker-compose.yml}
ENV_FILE=${MCP_SMOKE_ENV_FILE:-$REPO_ROOT/.env}

compose() {
  docker compose --env-file "$ENV_FILE" --profile mcp -f "$COMPOSE_FILE" "$@"
}

fail() {
  echo "MCP egress isolation smoke failed: $1" >&2
  exit 1
}

require_running() {
  service=$1
  compose ps --status running --services | grep -Fx "$service" >/dev/null \
    || fail "service '$service' is not running"
}

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
[ -f "$COMPOSE_FILE" ] || fail "Compose file is missing"
[ -f "$ENV_FILE" ] || fail "environment file is missing"

for service in api worker mcp-egress-gateway mcp-egress-proxy; do
  require_running "$service"
done

# The trusted application identity must be accepted by the gateway listener.
health=$(compose exec -T api curl -fsS \
  --connect-timeout 5 \
  --max-time 10 \
  --cert /run/secrets/mcp-egress/client.crt \
  --key /run/secrets/mcp-egress/client.key \
  --cacert /run/secrets/mcp-egress/ca.crt \
  https://mcp-egress-gateway:8443/health/live) \
  || fail "valid application mTLS identity was rejected"
case "$health" in
  *'"status":"ok"'*) ;;
  *) fail "gateway health response was invalid" ;;
esac

# The same internal route without a client certificate must fail at TLS.
if compose exec -T api curl -fsS \
  --connect-timeout 5 \
  --max-time 10 \
  --cacert /run/secrets/mcp-egress/ca.crt \
  https://mcp-egress-gateway:8443/health/live >/dev/null 2>&1; then
  fail "gateway accepted a caller without a client certificate"
fi

# All datastore-capable application processes and the gateway must lack a
# direct public route. Use a literal public IP so proxy/DNS configuration
# cannot accidentally make this test pass for the wrong reason.
for service in api worker mcp-egress-gateway; do
  if compose exec -T "$service" python -c \
    'import socket; s = socket.create_connection(("1.1.1.1", 443), 3); s.close()' \
    >/dev/null 2>&1; then
    fail "$service has an unexpected direct public route"
  fi
done

# The gateway must be unable to resolve or connect to every application
# datastore service. Each probe is alarm-bounded so a broken DNS path cannot
# hang a deployment indefinitely.
compose exec -T mcp-egress-gateway python - \
  postgres:5432 redis:6379 qdrant:6333 minio:9000 <<'PY' \
  || fail "gateway reached an application datastore"
import signal
import socket
import sys


class ProbeTimeout(Exception):
    pass


def timed_out(_signum, _frame):
    raise ProbeTimeout()


signal.signal(signal.SIGALRM, timed_out)
for endpoint in sys.argv[1:]:
    host, raw_port = endpoint.rsplit(":", 1)
    connection = None
    try:
        signal.alarm(3)
        connection = socket.create_connection((host, int(raw_port)), 2)
    except (OSError, ProbeTimeout):
        continue
    finally:
        signal.alarm(0)
        if connection is not None:
            connection.close()
    raise SystemExit(f"unexpected datastore reachability: {endpoint}")
PY

# Squid is the sole public bridge for the gateway and must independently deny
# private destinations even if application validation regresses.
compose exec -T mcp-egress-gateway python - mcp-egress-proxy 3128 <<'PY' \
  || fail "dedicated proxy accepted a private CONNECT target"
import socket
import sys

proxy = socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)
try:
    proxy.settimeout(3)
    proxy.sendall(
        b"CONNECT 10.0.0.1:443 HTTP/1.1\r\n"
        b"Host: 10.0.0.1:443\r\n"
        b"Connection: close\r\n\r\n"
    )
    status = proxy.recv(256).split(b"\r\n", 1)[0]
finally:
    proxy.close()
if status.startswith(b"HTTP/") and b" 200 " in status:
    raise SystemExit("private CONNECT unexpectedly succeeded")
if not status.startswith(b"HTTP/"):
    raise SystemExit("proxy returned no HTTP denial response")
PY

echo "MCP egress mTLS and network-isolation smoke passed"
