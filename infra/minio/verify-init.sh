#!/bin/sh
set -eu

# Exercise the exact MinIO and minio-init services declared by the base
# Compose file. The project name and named volume are disposable, and the
# fixed credentials below exist only for this isolated CI fixture.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
RUN_ID=${GITHUB_RUN_ID:-local}
RUN_ATTEMPT=${GITHUB_RUN_ATTEMPT:-0}
COMPOSE_PROJECT="geem-minio-init-$RUN_ID-$RUN_ATTEMPT-$$"

export APP_ENV=test
export MINIO_ACCESS_KEY=phase13-smoke-access
export MINIO_SECRET_KEY=phase13-smoke-secret-not-production
export MINIO_BUCKET=phase13-init-smoke

compose() {
  docker compose \
    --project-name "$COMPOSE_PROJECT" \
    --env-file /dev/null \
    -f "$REPO_ROOT/infra/docker-compose.yml" \
    "$@"
}

cleanup() {
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}

fail() {
  echo "MinIO initializer smoke failed: $1" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
trap cleanup EXIT HUP INT TERM

# The initializer itself owns the bounded readiness retry, bucket creation,
# anonymous-policy removal, and final authenticated stat. Run it once to create
# the bucket, then deliberately add a public object through the same pinned mc
# image so the second unchanged initializer must reconcile real policy drift.
compose up --detach minio || fail "could not start disposable MinIO"
compose run --rm --no-deps minio-init \
  || fail "first initializer execution failed"

compose run --rm --no-deps --entrypoint /bin/sh minio-init -ec '
  set -eu
  timeout -k 2s 5s mc alias set \
    --conn-read-deadline 4s --conn-write-deadline 4s \
    local http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" \
    >/dev/null 2>&1
  printf "%s\n" "phase13-minio-policy-probe" \
    | timeout -k 2s 10s mc pipe "local/$MINIO_BUCKET/policy-probe.txt" \
      >/dev/null
  timeout -k 2s 10s mc anonymous set download "local/$MINIO_BUCKET" \
    >/dev/null
' || fail "could not seed anonymous-policy drift"

anonymous_probe_status() {
  # application_data is intentionally internal, so host-published ports are
  # not a portable probe boundary. Use Bash's TCP transport from the exact
  # pinned mc image on the same internal network, without S3 credentials.
  compose run --rm --no-deps \
    --entrypoint /usr/bin/timeout minio-init \
    -k 2s 10s /usr/bin/bash -ec '
      exec 3<>/dev/tcp/minio/9000
      printf "GET /%s/policy-probe.txt HTTP/1.1\r\nHost: minio\r\nConnection: close\r\n\r\n" \
        "$MINIO_BUCKET" >&3
      IFS=" " read -r protocol status reason <&3
      case "$protocol" in
        HTTP/*) ;;
        *) exit 1 ;;
      esac
      case "$status" in
        [0-9][0-9][0-9]) printf "%s\n" "$status" ;;
        *) exit 1 ;;
      esac
    '
}

public_status=$(anonymous_probe_status) \
  || fail "seeded anonymous policy was not reachable"
[ "$public_status" = "200" ] \
  || fail "could not prove seeded anonymous policy (HTTP $public_status)"

compose run --rm --no-deps minio-init \
  || fail "idempotent policy-reconciling initializer execution failed"

# Both initializer executions ended with an authenticated `mc stat`, proving
# the existing bucket remains. Verify independently and without credentials
# that the object which was public is private after reconciliation.
anonymous_status=$(anonymous_probe_status) \
  || fail "anonymous policy probe did not receive an HTTP response"
[ "$anonymous_status" = "403" ] \
  || fail "bucket allowed anonymous access (HTTP $anonymous_status)"

echo "MinIO initializer idempotency and private-bucket smoke passed"
