#!/bin/sh
set -eu

# MCP deployed-boundary smoke gate. Run only after the base application
# and the `mcp` profile are healthy. It intentionally tests the actual Compose
# network namespaces and mounted certificates; unit tests cannot substitute for
# this check.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE=${MCP_SMOKE_COMPOSE_FILE:-$REPO_ROOT/infra/docker-compose.yml}
ENV_FILE=${MCP_SMOKE_ENV_FILE:-$REPO_ROOT/.env}
STATIC_DENY_MANIFEST=$REPO_ROOT/infra/mcp-egress/proxy/static-deny-networks.txt
COMPOSE_WRAPPER=${MCP_SMOKE_COMPOSE_WRAPPER:-}
COMPOSE_PROJECT=${MCP_SMOKE_COMPOSE_PROJECT:-}
PUBLIC_CANARY=${MCP_SMOKE_PUBLIC_CANARY:-1.1.1.1:443}

compose() {
  if [ -n "$COMPOSE_WRAPPER" ]; then
    "$COMPOSE_WRAPPER" "$@"
  elif [ -n "$COMPOSE_PROJECT" ]; then
    docker compose --project-name "$COMPOSE_PROJECT" \
      --env-file "$ENV_FILE" --profile mcp -f "$COMPOSE_FILE" "$@"
  else
    docker compose --env-file "$ENV_FILE" --profile mcp -f "$COMPOSE_FILE" "$@"
  fi
}

fail() {
  echo "MCP egress isolation smoke failed: $1" >&2
  exit 1
}

require_running() {
  service=$1
  running_ids=$(compose ps -q --status running "$service") \
    || fail "could not inspect service '$service'"
  [ -n "$running_ids" ] || fail "service '$service' is not running"
}

require_exactly_one_running() {
  service=$1
  running_ids=$(compose ps -q --status running "$service") \
    || fail "could not inspect service '$service'"
  count=0
  for _container_id in $running_ids; do
    count=$((count + 1))
  done
  [ "$count" -eq 1 ] \
    || fail "service '$service' must have exactly one running container (found $count)"
}

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
if [ -n "$COMPOSE_WRAPPER" ]; then
  case "$COMPOSE_WRAPPER" in
    /*) ;;
    *) fail "Compose wrapper must be an absolute path" ;;
  esac
  [ -x "$COMPOSE_WRAPPER" ] || fail "Compose wrapper is not executable"
else
  [ -f "$COMPOSE_FILE" ] || fail "Compose file is missing"
  [ -f "$ENV_FILE" ] || fail "environment file is missing"
fi
[ -r "$STATIC_DENY_MANIFEST" ] \
  || fail "tracked static proxy deny manifest is missing"

for service in api worker app-egress-proxy mcp-egress-proxy; do
  require_running "$service"
done
require_exactly_one_running beat
require_exactly_one_running mcp-egress-gateway

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
for service in api worker beat mcp-egress-gateway; do
  if compose exec -T "$service" python -c \
    'import socket; s = socket.create_connection(("1.1.1.1", 443), 3); s.close()' \
    >/dev/null 2>&1; then
    fail "$service has an unexpected direct public route"
  fi
done

# Prove a source container cannot resolve or connect to any supplied endpoint.
# Each probe is alarm-bounded so a broken DNS path cannot hang a deployment.
require_unreachable() {
  source_service=$1
  shift
  compose exec -T "$source_service" python - "$@" <<'PY' \
    || fail "$source_service reached a forbidden application service"
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
}

# The gateway cannot reach any application datastore. Beat can reach Redis only
# over application_broker and is separately proven unable to reach the SQL,
# vector, or object-storage data plane.
require_unreachable mcp-egress-gateway \
  postgres:5432 redis:6379 qdrant:6333 minio:9000
require_unreachable beat postgres:5432 qdrant:6333 minio:9000

# Squid is the sole public bridge for the gateway. Require one positive CONNECT
# canary first, then an explicit 403 for every CIDR in the tracked static deny
# manifest and every deployment CIDR supplied to the gateway. A timeout/502/503
# is not proof that the ACL denied a target.
set -- mcp-egress-proxy 3128
while IFS= read -r static_network || [ -n "$static_network" ]; do
  case "$static_network" in
    ''|'#'*) continue ;;
  esac
  set -- "$@" "$static_network"
done < "$STATIC_DENY_MANIFEST"
[ "$#" -gt 2 ] || fail "tracked static proxy deny manifest is empty"

compose exec -T \
  -e "GEEM_MCP_PUBLIC_CANARY=$PUBLIC_CANARY" \
  mcp-egress-gateway python - "$@" <<'PY' \
  || fail "dedicated proxy positive/negative policy canaries failed"
import ipaddress
import os
import socket
import sys


def authority(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def connect_status(host: str, port: int) -> bytes:
    proxy = socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)
    try:
        proxy.settimeout(5)
        target = authority(host, port).encode("ascii")
        proxy.sendall(
            b"CONNECT " + target + b" HTTP/1.1\r\n"
            b"Host: " + target + b"\r\n"
            b"Connection: close\r\n\r\n"
        )
        status = proxy.recv(256).split(b"\r\n", 1)[0]
    finally:
        proxy.close()
    if not status.startswith(b"HTTP/"):
        raise SystemExit("proxy returned no HTTP response")
    return status


canary = os.environ["GEEM_MCP_PUBLIC_CANARY"]
if canary.startswith("["):
    host, separator, raw_port = canary[1:].partition("]:")
else:
    host, separator, raw_port = canary.rpartition(":")
if not separator or not raw_port.isdecimal():
    raise SystemExit("public canary must be HOST:PORT or [IPV6]:PORT")
canary_status = connect_status(host, int(raw_port))
if b" 200 " not in canary_status:
    raise SystemExit("public CONNECT canary did not succeed")

denied = [ipaddress.ip_network(value, strict=True) for value in sys.argv[3:]]
if not denied:
    raise SystemExit("static proxy deny manifest is empty")
for value in os.getenv("EGRESS_BLOCKED_NETWORKS", "").split(","):
    if value.strip():
        denied.append(ipaddress.ip_network(value.strip(), strict=False))
for network in dict.fromkeys(denied):
    target = str(network.network_address)
    denial_status = connect_status(target, 443)
    if b" 403 " not in denial_status:
        raise SystemExit("blocked-network CONNECT was not rejected by policy")
PY

echo "MCP egress mTLS and network-isolation smoke passed"
