# Phase 13 MCP Connectors: production-PC upgrade and deployment

This is the execution entry point for upgrading an existing Geem production
machine that predates Phase 13. It covers source acquisition, backups,
configuration, migrations, isolated egress, persistent startup, verification,
release gating, and rollback.

Use this guide together with the detailed
[MCP configuration and isolation runbook](./mcp-connectors.md). The linked
sections of that runbook are mandatory parts of this procedure. The normative
product and protocol contract remains the
[Phase 13 plan](../../.cursor/plans/mcp.plan.md).

> **STOP — current release state:** upgrading the code and database does not
> authorize publishing MCP Connectors. Keep `MCP_CONNECTOR_ENABLED=false` and
> the production catalog row `coming_soon` until every blocker and release gate
> in this document is closed in a production-equivalent release-candidate
> environment.

## What this procedure installs

Phase 13 is not a configuration-only change. It adds or changes:

- API schemas, connector management, OAuth, grants, approvals, quotas, runtime
  execution, delivery, retention, audit, and worker tasks;
- PostgreSQL migrations `0036` through `0040`;
- Workspace, Widget, WhatsApp, and Platform Admin integration points;
- an mTLS MCP egress gateway and a separate CONNECT-only egress proxy;
- a fixed-provider proxy for ordinary API/worker HTTPS traffic;
- Compose networks, secrets, images, frontend builds, and operational tests.

The Phase 13 runtime implementation starts at commit `65d4c71`. The minimum
reviewed runtime baseline when this document was written is:

```text
d2839326c85edff0c8e7b061f190e640aaf3dc49
```

That baseline includes the required follow-up safety fixes through tool-free
MCP response handling. The actual production release must be an explicitly
approved descendant that also contains this production guide and any later
release fixes. Do not deploy only the first Phase 13 commit and do not
cherry-pick this feature. Record the actual immutable full SHA in the deployment
evidence.

## Cursor execution contract

Cursor may follow this document on the production host, but it must work in two
separate modes:

1. **Audit mode:** read-only discovery, evidence collection, and a proposed
   host-specific change set.
2. **Execution mode:** mutations only after an operator has reviewed that
   proposal, supplied every required input, confirmed the backup, and opened a
   maintenance window.

Cursor must stop and ask the operator when any required value or decision is
unknown. It must never infer or invent secrets, certificate policy, deployment
CIDRs, public domains, plan prices, release-candidate infrastructure, remote MCP
credentials, or external-service identifiers.

Cursor must not:

- use `git reset --hard`, discard a dirty worktree, delete volumes, or force a
  divergent branch to match the remote;
- print `.env`, private keys, tokens, raw `docker compose config`, container
  environments, connector arguments/results, or sensitive URLs;
- rotate `JWT_SECRET`, `SECRETS_ENCRYPTION_KEY`, database credentials, or PKI as
  an incidental part of the upgrade;
- attach API, worker, Beat, or the MCP gateway to `public_egress`;
- enable the connector before the live isolation and dependency canaries pass;
- publish the paid App, change signed prices, approve writes, or reconcile an
  ambiguous external result without explicit operator authorization;
- treat the UAT overlay as production isolation evidence; or
- downgrade the database schema as the normal rollback mechanism.

Stop the deployment if the worktree is dirty or divergent, a backup cannot be
verified, the production overlay is incomplete, the encryption identity is
uncertain, a required dependency loses connectivity, or any security probe
fails.

## Required operator inputs

Record these values in the change ticket before execution. Store secrets in the
deployment secret manager, not in the ticket.

| Input | Required decision or evidence |
| --- | --- |
| Repository root | Exact absolute path on the production host |
| Release reference | Approved immutable full commit SHA |
| Current state | Current full SHA, branch, worktree status, and running image IDs |
| Release images | Approved prebuilt image digest manifest, or approved resolved base/output digests for a local build |
| Compose identity | One project name and the exact ordered Compose file list |
| Hardening overlay | Absolute deployment-owned path outside the Git checkout |
| Deployment topology | Cloudflare tunnel, aaPanel/Nginx, or another reviewed ingress |
| Public hosts | Exact API, Workspace, Platform Admin, marketing, CIMD, and tunnel hosts |
| Data backup | Verified PostgreSQL dump plus MinIO, Qdrant, Redis, and configuration recovery point |
| Encryption identity | Whether ciphertext currently uses explicit `SECRETS_ENCRYPTION_KEY` or the existing `JWT_SECRET` fallback |
| Datastore credentials | Existing production identities and the approved rotation plan, if any |
| PKI | Per-environment CA/leaf issuance owner, secret path, expiry, and rotation owner |
| Network policy | Docker, host bridge, VPC, corporate, metadata, and deployment-owned CIDRs |
| Fixed providers | Every production HTTP(S), SMTP, telemetry, billing, storage, OAuth, and messaging dependency |
| Product release | Signed SAR prices, one default plan, RC environment, and release owner |
| Canary fixtures | Controlled public HTTPS/443 MCP servers and OAuth credentials |
| Operations | Maintenance window, rollback owner, monitoring destination, and alert owner |

## 0. Read-only host inventory

Run this stage before modifying Git, `.env`, services, networks, or the
database. Replace the placeholders; do not paste secret-bearing output into the
change ticket.

```bash
export GEEM_DEPLOY_ROOT=/absolute/path/to/Geem
export GEEM_COMPOSE_PROJECT=<existing-compose-project-name>
export GEEM_RELEASE_REF=<approved-full-commit-sha>
export GEEM_PRODUCTION_OVERLAY=/etc/geem/docker-compose.production-hardening.yml

cd "$GEEM_DEPLOY_ROOT"
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline

docker version
docker compose version
for required_command in docker openssl curl timeout systemctl; do
  command -v "$required_command" >/dev/null || {
    printf 'required command is missing: %s\n' "$required_command" >&2
    exit 1
  }
done
df -h "$GEEM_DEPLOY_ROOT"
free -h
```

Requirements:

- `git status --short` prints nothing. If it prints anything, stop and review
  each production-owned change; do not stash or reset it automatically.
- Docker Engine and modern Compose V2 must be present. The checked-in overlays
  use profiles plus `!reset`/`!override`; the later `config --quiet` command is
  the authoritative compatibility gate.
- Disk space must cover parallel old/new images, builds, database migration,
  and rollback artifacts.
- OpenSSL, curl, systemd, and GNU coreutils `timeout` must be available. Node.js
  22 is required if the host builds a static Workspace or Platform Admin bundle
  outside Compose.

Inventory the real supervisor and topology. Examples:

```bash
systemctl show geem-stack --no-pager \
  -p FragmentPath -p ActiveState -p UnitFileState || true
systemctl --user show geem-stack --no-pager \
  -p FragmentPath -p ActiveState -p UnitFileState || true
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker ps --format '{{.Names}} project={{.Label "com.docker.compose.project"}}'
docker compose ls
docker network ls
docker volume ls
```

Record immutable running image identities before a build can retag local image
names:

```bash
for container_id in $(docker ps -q \
  --filter "label=com.docker.compose.project=$GEEM_COMPOSE_PROJECT"); do
  docker inspect "$container_id" --format \
    'container={{.Name}} service={{index .Config.Labels "com.docker.compose.service"}} image_id={{.Image}} image_ref={{.Config.Image}}'
  image_id=$(docker inspect "$container_id" --format '{{.Image}}')
  docker image inspect "$image_id" --format 'repo_digests={{json .RepoDigests}}'
done
```

`GEEM_COMPOSE_PROJECT` must equal the project label on the running production
containers. An older unit without `-p` normally derives the project name from
its working-directory basename; do not assume it is `geem-prod`. Changing the
project name silently selects different Compose networks and named volumes and
can start an empty database. If a project-name or volume-name migration is
required, stop and use a separately reviewed data migration plan.

Determine whether production uses a system unit or a user unit and use the same
scope for every later `status`, `disable`, `enable`, `restart`, and reboot test.
Open the reported unit file in a non-recorded editor for manual review. Do not
print or paste it until any inline environment values or secret-bearing command
arguments have been redacted.

Pause CI auto-deploys, repository watchers, unattended service restarts, and
planned reboots before fetching the new source. Record how they will be resumed.
The Phase 13 base Compose file mounts MCP client certificate files into API and
worker even while the feature flag is false. A pull followed by an automatic
recreate can therefore fail before MCP is enabled if PKI is not provisioned.

Determine whether the machine currently uses:

- `infra/docker-compose.yml` plus `docker-compose.tunnel.yml`;
- a deployment-owned aaPanel/Nginx Compose file; or
- another orchestrator.

Do not combine those topologies blindly. This guide's canonical Compose path is
the base file, tunnel overlay, and a deployment-owned production-hardening
overlay applied last. If the host remains on a different topology, it must
implement the same network, secret, process, and isolation contract before
proceeding.

## 1. Create and verify the rollback point

Keep MCP disabled and the App unpublished. Quiesce writes or use the
organization's consistent snapshot procedure.

Back up and verify restoration/readability for:

- PostgreSQL, including schema and data;
- MinIO objects and configuration;
- Qdrant collections/snapshots;
- Redis if session/Celery recovery is required;
- `.env`, deployment-owned Compose files, Nginx/Cloudflare configuration,
  proxy policies, the Compose wrapper, systemd units, and frontend deployment
  configuration;
- the current full Git SHA and the IDs/digests of running images; and
- PKI through the approved secret manager. Never copy a CA private key or leaf
  private key into the repository or an ordinary support archive.

A PostgreSQL example, adapted to the current production project and role, is:

```bash
export GEEM_BACKUP_DIR=<approved-existing-absolute-backup-directory>
export GEEM_BACKUP_FILE="$GEEM_BACKUP_DIR/geem-before-phase13-<change-id>.sql"
test -d "$GEEM_BACKUP_DIR" && test -w "$GEEM_BACKUP_DIR" || {
  printf '%s\n' 'approved backup directory is unavailable; stopping' >&2
  exit 1
}
test ! -e "$GEEM_BACKUP_FILE" || {
  printf '%s\n' 'backup target already exists; choose a new immutable name' >&2
  exit 1
}
umask 077
set -o noclobber
cd "$GEEM_DEPLOY_ROOT/infra"
if ! docker compose -p "$GEEM_COMPOSE_PROJECT" \
  -f <current-production-compose-file> \
  exec -T postgres pg_dump -U <production-db-role> <production-db-name> \
  > "$GEEM_BACKUP_FILE"; then
  printf '%s\n' 'pg_dump failed; preserve and mark the partial target invalid' >&2
  exit 1
fi
test -s "$GEEM_BACKUP_FILE" || {
  printf '%s\n' 'pg_dump produced an empty file; mark the target invalid' >&2
  exit 1
}
```

The operator must verify that the dump is non-empty and can be read by
`pg_restore --list` for a custom-format dump or by an approved SQL validation
for a plain dump. A command completing successfully is not, by itself, restore
evidence. If `pg_dump` fails, mark the partial target invalid and choose a new
immutable filename after correcting the cause; never overwrite it silently.

### Preserve encryption-key continuity

Existing encrypted billing and connector data uses
`SECRETS_ENCRYPTION_KEY` when set; otherwise it is derived from the existing
`JWT_SECRET`. Do not add a different explicit encryption key during this
upgrade if the deployment previously used the fallback. Doing so makes existing
ciphertext unreadable.

Keep the current effective encryption identity unchanged. A move from the
`JWT_SECRET` fallback to a dedicated key requires a separately reviewed
decrypt/re-encrypt migration and is outside this deployment procedure.

## 2. Fetch and fast-forward to the approved release

Fetch first, inspect the target, and fast-forward only. Do not use an unbounded
`git pull` on production.

```bash
cd "$GEEM_DEPLOY_ROOT"
test -z "$(git status --porcelain)" || {
  printf '%s\n' 'production worktree is not clean; stopping' >&2
  exit 1
}
printf '%s' "$GEEM_RELEASE_REF" | grep -Eq '^[0-9a-f]{40}$' || {
  printf '%s\n' 'release reference must be a full lowercase commit SHA' >&2
  exit 1
}
git fetch --prune origin
git cat-file -e "${GEEM_RELEASE_REF}^{commit}"
git show --no-patch --format='%H %ad %s' --date=iso-strict "$GEEM_RELEASE_REF"
git merge-base --is-ancestor HEAD "$GEEM_RELEASE_REF" || {
  printf '%s\n' 'release is not a fast-forward from production; stopping' >&2
  exit 1
}
git merge --ff-only "$GEEM_RELEASE_REF"
git rev-parse HEAD
test "$(git rev-parse HEAD)" = "$(git rev-parse "${GEEM_RELEASE_REF}^{commit}")"
```

If the ancestor check or fast-forward fails, stop for a reviewed reconciliation.
Never reset the production checkout to make the command pass.

Verify that the deployed reference includes the complete runtime baseline and
required artifacts:

```bash
git merge-base --is-ancestor \
  d2839326c85edff0c8e7b061f190e640aaf3dc49 HEAD || exit 1
for required_file in \
  apps/api/migrations/versions/0040_mcp_external_surfaces.py \
  apps/mcp_egress_gateway/Dockerfile \
  infra/mcp-egress/verify-isolation.sh \
  infra/app-egress/proxy/squid.conf \
  docs/integrations/mcp-connectors.md \
  docs/integrations/mcp-production-deployment.md; do
  test -f "$required_file" || {
    printf 'missing Phase 13 artifact: %s\n' "$required_file" >&2
    exit 1
  }
done
```

Require the exact approved full SHA in `GEEM_RELEASE_REF`; the minimum baseline
above is only an ancestry floor. Record the release's test evidence instead of
editing history or cherry-picking old commits.

Before approving that target for production, attach CI evidence for the exact
SHA: MCP API unit/integration tests, gateway tests, Compose isolation tests,
Workspace MCP tests/build, and the normal application regression suite. Do not
install ad hoc development dependencies on the production machine merely to
replace missing release CI evidence.

## 3. Select one final production Compose topology

The checked-in `infra/docker-compose.yml` is a development topology source. It
contains development datastore credentials, source bind mounts, reload/dev
commands, and host-published ports. The tunnel overlay does not remove all of
those properties.

Create a deployment-owned file outside the Git checkout, for example:

```text
/etc/geem/docker-compose.production-hardening.yml
```

It is intentionally not committed because its domains, ingress, credentials,
and host policy belong to the deployment. Keeping it outside the checkout also
preserves the clean-worktree gate for future upgrades. Back it up with the other
deployment configuration. Cursor may draft it only from the operator-supplied
values and the actual current topology. It must satisfy every item in
[Create the production hardening overlay](./mcp-connectors.md#5-create-the-production-hardening-overlay),
including:

- secret-backed, matching PostgreSQL and MinIO credentials;
- no development credential, bind mount, reload server, or Vite/Astro dev
  process;
- approved immutable image references/digests for every production service, or
  a separately approved local-build manifest with resolved base/output digests;
- no unreviewed host ports and no MCP gateway/proxy host port;
- API on application data, ingress, fixed-provider control, and MCP control
  networks only;
- worker on application data, fixed-provider control, and MCP control networks
  only, with no ingress network;
- Beat on application data only, with `MCP_CONNECTOR_ENABLED=false`, no MCP
  client key, and no MCP control network;
- gateway on MCP control and proxy control only;
- MCP proxy on proxy control and public egress only;
- only the fixed-provider proxy, MCP proxy, and Cloudflared on public egress;
- exact production API, Workspace, Platform Admin, CIMD, frontend-build, and
  tunnel domains; and
- the same final file order in every build, up, exec, ps, stop, rollback, CI,
  aaPanel, and systemd command.

The final overlay must preserve the existing production volume identities. If
the current deployment uses explicit external volume names, reproduce those
names deliberately in the final topology. Before any recreate, compare the
running containers' mounts with the merged Compose volume declarations. A new
empty `<project>_postgres_data`, `minio_data`, or `qdrant_data` volume is a stop
condition, not a fresh-install opportunity.

After the file exists, create a persistent deployment-owned wrapper at
`/usr/local/sbin/geem-prod-compose` and use it for the rest of the procedure,
future releases, systemd, and rollback. Do not rely on a shell function or
session-only environment variables. Replace every placeholder below with the
recorded value:

```bash
#!/bin/sh
exec <absolute-path-reported-by-command-v-docker> compose \
    --project-name '<existing-compose-project-name>' \
    --env-file '/absolute/path/to/Geem/.env' \
    --profile mcp \
    -f '/absolute/path/to/Geem/infra/docker-compose.yml' \
    -f '/absolute/path/to/Geem/infra/docker-compose.tunnel.yml' \
    -f '/etc/geem/docker-compose.production-hardening.yml' \
    "$@"
```

Create it through the approved configuration-management/editor workflow, then:

```bash
sudo chown root:root /usr/local/sbin/geem-prod-compose
sudo chmod 0755 /usr/local/sbin/geem-prod-compose
sh -n /usr/local/sbin/geem-prod-compose
geem-prod-compose config --quiet
```

`config --quiet` must pass before any Phase 13 container is created. Never run
plain `docker compose config` in a logged production session because expanded
configuration can contain secrets.

When a linked section of `mcp-connectors.md` shows a relative
`docker-compose.production-hardening.yml`, substitute
`$GEEM_PRODUCTION_OVERLAY` and use `geem-prod-compose`. Do not execute a
shortened example that drops the project name, environment file, profile, or
an overlay.

If the production host does not use the Geem tunnel overlay, replace it with a
reviewed deployment-owned production overlay and update the wrapper once. Do
not retain a file whose domains or ingress do not match the host.

## 4. Merge Phase 13 configuration without replacing `.env`

Back up `.env`, preserve all current secret values, and merge the Phase 13 keys
from [`.env.example`](../../.env.example). Do not overwrite the file with the
example.

The initial state must remain closed:

```dotenv
MCP_CONNECTOR_ENABLED=false
MCP_SUPPORTED_PROTOCOL_VERSIONS=2026-07-28,2025-11-25,2024-11-05
MCP_CLIENT_METADATA_URL=https://<public-api-host>/api/connectors/oauth/mcp_remote/client-metadata.json

MCP_EGRESS_PKI_DIR=/approved/host/secret/path/mcp-egress
MCP_EGRESS_GATEWAY_URL=https://mcp-egress-gateway:8443
MCP_EGRESS_APP_ENV=production
MCP_EGRESS_PROXY_URL=http://mcp-egress-proxy:3128
MCP_EGRESS_CLIENT_CERT_FILE=/run/secrets/mcp-egress/client.crt
MCP_EGRESS_CLIENT_KEY_FILE=/run/secrets/mcp-egress/client.key
MCP_EGRESS_CA_CERT_FILE=/run/secrets/mcp-egress/ca.crt
MCP_EGRESS_BLOCKED_NETWORKS=<reviewed-comma-separated-cidrs>
MCP_ALLOW_PRIVATE_EGRESS=false

MCP_EGRESS_MAX_REQUEST_BYTES=65536
MCP_EGRESS_MAX_RESPONSE_BYTES=262144
MCP_EGRESS_CONNECT_TIMEOUT_SECONDS=5
MCP_EGRESS_READ_TIMEOUT_SECONDS=20
MCP_EGRESS_TOTAL_TIMEOUT_SECONDS=30
MCP_LEGACY_SESSION_TTL_SECONDS=300
MCP_MAX_LEGACY_SESSIONS=64
MCP_MAX_TOOL_PAGES=64
MCP_MAX_CONCURRENT_OPERATIONS=128
MCP_MAX_TOOL_ITERATIONS=5
MCP_MAX_TOOLS_PER_EXPERT=32
MCP_MAX_DISCOVERED_TOOLS=512
MCP_TOOL_INVENTORY_TTL_SECONDS=300
MCP_TOOL_CALL_TIMEOUT_SECONDS=20
MCP_TOTAL_TURN_TIMEOUT_SECONDS=120
MCP_TOOL_RESULT_MAX_BYTES=32768
MCP_TOOL_RESULT_MAX_CHARS=8000
MCP_MAX_REDIRECTS=3
MCP_TOOL_APPROVAL_TTL_SECONDS=900
MCP_MAX_EXTERNAL_PENDING_PER_WORKSPACE=100
MCP_TOOL_PROVIDER_CAPABILITY_MATRIX='{"<exact-primary-model>":["function_calling","parallel_tool_calls_false"],"<exact-fallback-model>":["function_calling","parallel_tool_calls_false"]}'
```

Leave `MCP_CLIENT_METADATA_URL` empty if CIMD is not enabled. If enabled, it
must exactly match the public production API host and OAuth registration.

The two model IDs in `MCP_TOOL_PROVIDER_CAPABILITY_MATRIX` must exactly match
`OPENROUTER_CHAT_MODEL` and `OPENROUTER_CHAT_FALLBACK_MODEL`. Keep the existing
OpenRouter key private. Do not add a model capability merely to pass startup;
the model/provider combination must have reviewed tool-calling evidence.

Run duplicate and closed-state checks that never print values:

```bash
require_one_env_key() {
  awk -F= -v key="$1" '
    $1 == key { count += 1 }
    END { exit(count == 1 ? 0 : 1) }
  ' "$GEEM_DEPLOY_ROOT/.env" || {
    printf 'missing or duplicate environment key: %s\n' "$1" >&2
    exit 1
  }
}

require_exact_env_value() {
  awk -v wanted="$1=$2" '
    $0 == wanted { exact += 1 }
    END { exit(exact == 1 ? 0 : 1) }
  ' "$GEEM_DEPLOY_ROOT/.env" || {
    printf 'environment key does not have the required closed value: %s\n' "$1" >&2
    exit 1
  }
}

for key in \
  APP_ENV AUTH_REQUIRED \
  MCP_CONNECTOR_ENABLED MCP_SUPPORTED_PROTOCOL_VERSIONS \
  MCP_EGRESS_PKI_DIR MCP_EGRESS_GATEWAY_URL MCP_EGRESS_APP_ENV \
  MCP_EGRESS_PROXY_URL MCP_EGRESS_BLOCKED_NETWORKS \
  MCP_ALLOW_PRIVATE_EGRESS MCP_TOOL_PROVIDER_CAPABILITY_MATRIX; do
  require_one_env_key "$key"
done

require_exact_env_value APP_ENV production
require_exact_env_value AUTH_REQUIRED true
require_exact_env_value MCP_CONNECTOR_ENABLED false
require_exact_env_value MCP_EGRESS_APP_ENV production
require_exact_env_value MCP_ALLOW_PRIVATE_EGRESS false
require_exact_env_value MCP_EGRESS_GATEWAY_URL https://mcp-egress-gateway:8443
require_exact_env_value MCP_EGRESS_PROXY_URL http://mcp-egress-proxy:3128
require_exact_env_value MCP_SUPPORTED_PROTOCOL_VERSIONS \
  2026-07-28,2025-11-25,2024-11-05
```

Review non-empty values for the PKI directory, blocked-network inventory, exact
model IDs, and capability matrix without copying them into logs. Repeat these
checks after the second network-policy pass and before enabling MCP.

## 5. Provision and validate production mTLS PKI

Use the deployment's internal PKI or secret manager. Cursor must not invent a
production CA or place its private key on this host merely to complete setup.

The host path configured by `MCP_EGRESS_PKI_DIR` must contain:

```text
ca/ca.crt
server/server.crt
server/server.key
client/client.crt
client/client.key
```

The server leaf SAN must contain `mcp-egress-gateway`; server and client leaves
must have the correct EKUs. Certificates are `0644`, private keys are
`0400`/`0440`, and the gateway server key must be readable by container UID/GID
`10001`. API and worker receive only the client identity. Gateway receives only
the server identity and client CA. Beat receives none.

Run every chain, SAN, expiry, key-match, and permissions check in
[Provision dedicated mTLS PKI](./mcp-connectors.md#2-provision-dedicated-mtls-pki).
All checks must pass before Compose recreates API or worker, because the updated
base topology mounts the client files even while MCP is disabled.

Do not resume an automatic deployment, repository watcher, or reboot path yet.
Resume it only after the final hardening overlay, full closed topology, and
persistent supervisor have passed stages 7–9.

## 6. Inventory networks and outbound dependencies

### Deployment networks

Set `MCP_EGRESS_BLOCKED_NETWORKS` to every deployment-owned Docker, VPC, host
bridge, corporate, internal-public, and metadata range. The value cannot be
copied from an example.

Plan a two-pass rollout while MCP remains disabled. The first pass is completed
in stage 7, where the new Phase 13 networks are actually created:

1. Render the final topology and provision the closed boundary.
2. Inspect every actual Compose network subnet.
3. Add any newly allocated subnet to `MCP_EGRESS_BLOCKED_NETWORKS`.
4. Add equivalent explicit deny rules to the MCP proxy policy.
5. Rebuild/recreate the proxy and gateway.
6. Rerun the rendered-topology review and all live parity probes.

Follow [Inventory and block deployment networks](./mcp-connectors.md#4-inventory-and-block-deployment-networks)
and [Deployment-specific address-policy parity](./mcp-connectors.md#deployment-specific-address-policy-parity)
without omission. The Python policy and Squid layer must independently reject
the reviewed non-global and deployment-specific ranges.

### Deployment-owned proxy policy

Do not edit tracked `infra/*/proxy/squid.conf` files directly on the production
machine. Policy changes must either:

1. be committed, tested, and included in the approved release SHA; or
2. live in a root-owned, non-secret deployment configuration outside the Git
   checkout and be mounted read-only over `/etc/squid/squid.conf` by
   `$GEEM_PRODUCTION_OVERLAY`.

For deployment-specific MCP CIDRs, an external policy must start from the exact
approved release's `infra/mcp-egress/proxy/squid.conf`, add every reviewed deny
before the final allow, and be mounted only into `mcp-egress-proxy`. A custom
fixed-provider policy must start from `infra/app-egress/proxy/squid.conf`,
retain default-deny behavior, and be mounted only into `app-egress-proxy`.
Example override shape:

```yaml
services:
  mcp-egress-proxy:
    volumes:
      - /etc/geem/mcp-egress-squid.conf:/etc/squid/squid.conf:ro

  app-egress-proxy:
    volumes:
      - /etc/geem/app-egress-squid.conf:/etc/squid/squid.conf:ro
```

Omit the app-proxy mount when the checked-in fixed-provider list exactly matches
production. Keep external proxy policies root-owned and non-writable by the
container user, validate their syntax, record their checksums, and merge every
future upstream policy change deliberately. Never put credentials in a proxy
policy.

### Fixed-provider dependencies

The updated API and worker have no direct public route. Reviewed external
HTTPS/443 uses `app-egress-proxy`, whose allowlist is intentionally restricted;
plain external HTTP is denied. A provider that cannot use HTTPS/443 needs a
separately reviewed egress path. Inventory and canary every enabled dependency,
including:

- OpenRouter;
- ClickPay or another active billing path;
- Google Drive and Microsoft OneDrive OAuth/API hosts;
- OpenWA/WhatsApp;
- public telemetry collectors;
- email delivery; and
- any other configured production integration.

Tenant-selected MCP/OAuth hosts must never be added to the fixed-provider
allowlist; they belong behind the MCP gateway.

Compare the effective configured hostnames—not only default values—with
`infra/app-egress/proxy/squid.conf`. A custom OpenRouter base URL, billing host,
OpenWA host, OAuth host, or external OTLP collector remains unreachable until
its exact egress design and proxy policy are reviewed, rebuilt, and canaried.

Raw external SMTP is not carried by the HTTP CONNECT policy used by API and
worker. If production email uses an external SMTP server, provide a separately
reviewed internal mail relay or a dedicated least-privilege SMTP egress
boundary. Do not attach API/worker to `public_egress`, and do not pretend adding
an SMTP hostname to the HTTPS proxy allowlist fixes `smtplib` traffic. Login,
verification, invitation, and reset-email canaries must pass before promotion.

## 7. Build, migrate, seed, and start with MCP disabled

Confirm again that the effective shared value is
`MCP_CONNECTOR_ENABLED=false` and the final Beat override is also false.

Prefer immutable prebuilt application/gateway/proxy/frontend image digests tied
to the approved release manifest. The current Dockerfiles and Compose sources
contain mutable base/image tags, so an in-place build is not reproducible from
the Git SHA alone. Do not run the following fallback until the release owner has
recorded and approved every resolved base image digest and the resulting image
digests for this deployment:

```bash
geem-prod-compose config --quiet
geem-prod-compose build
```

Validate the effective merged topology without printing or storing the rendered
JSON. Keep this pipeline intact; never insert `tee` or redirect its first
command to a file:

```bash
geem-prod-compose config --format json \
  | geem-prod-compose run --rm --no-deps -T api python -c '
import json
import sys

config = json.load(sys.stdin)
services = config["services"]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def environment(service):
    return services[service].get("environment") or {}

def networks(service):
    return set((services[service].get("networks") or {}).keys())

def is_false(value):
    return str(value).strip().lower() == "false"

require(config.get("name") == "<existing-compose-project-name>", "wrong Compose project")
require(is_false(environment("api").get("MCP_CONNECTOR_ENABLED")), "API MCP must be disabled")
require(is_false(environment("worker").get("MCP_CONNECTOR_ENABLED")), "worker MCP must be disabled")
require(is_false(environment("beat").get("MCP_CONNECTOR_ENABLED")), "Beat MCP must be disabled")
require(environment("mcp-egress-gateway").get("APP_ENV") == "production", "gateway must be production")
require(is_false(environment("mcp-egress-gateway").get("EGRESS_ALLOW_PRIVATE")), "private egress must be disabled")
require(str(environment("mcp-egress-gateway").get("EGRESS_BLOCKED_NETWORKS") or "").strip(), "custom blocked networks are empty")
require(networks("api") == {"application_data", "application_ingress", "application_provider_control", "mcp_egress_control"}, "wrong API networks")
require(networks("worker") == {"application_data", "application_provider_control", "mcp_egress_control"}, "wrong worker networks")
require(networks("beat") == {"application_data"}, "wrong Beat networks")
require(networks("mcp-egress-gateway") == {"mcp_egress_control", "mcp_proxy_control"}, "wrong gateway networks")
require(networks("mcp-egress-proxy") == {"mcp_proxy_control", "public_egress"}, "wrong MCP proxy networks")
public_members = {name for name in services if "public_egress" in networks(name)}
expected_public_members = {
    "app-egress-proxy",
    "mcp-egress-proxy",
    "cloudflared",
}
require(public_members == expected_public_members, "wrong public-egress membership")
require(not services["mcp-egress-gateway"].get("ports"), "gateway publishes a host port")
require(not services["mcp-egress-proxy"].get("ports"), "MCP proxy publishes a host port")
require(not services["beat"].get("secrets"), "Beat received a secret mount")
print("effective closed topology valid")
'
```

Replace the project placeholder inside the validator with the preserved project
name. The example `expected_public_members` set is for the checked-in
Cloudflared topology. For aaPanel/Nginx or another ingress, replace that set
with the exact reviewed Compose services that legitimately require
`public_egress`; if ingress runs outside Compose, do not invent a member for it.
The two egress proxies remain required. A validation failure must not be
bypassed.

Before maintenance, force the new image to validate the enabled MCP settings
and mounted client PKI in an isolated one-off container. This does not start a
tool call or enable the running application:

```bash
geem-prod-compose run --rm --no-deps \
  -e MCP_CONNECTOR_ENABLED=true \
  api python -c \
  'from app.core.config import get_settings; get_settings(); print("MCP settings valid")'
```

Enter the approved maintenance response, drain active application/worker work,
and disable the recorded system or user supervisor so it cannot recreate the
old topology. Do not invoke the checked-in unit's `ExecStop`: it also stops the
datastores. Instead, use the exact recorded pre-upgrade Compose project and file
set to stop only `api`, `worker`, and `beat`.

Disable the discovered system unit with `sudo systemctl disable geem-stack`, or
the discovered user unit with `systemctl --user disable geem-stack`; run only
the applicable command. Also pause aaPanel/CI automation.

```bash
<recorded-pre-upgrade-compose-command-and-files> stop api worker beat
```

The placeholder must be replaced with the command captured in stage 0,
including its existing project identity and every old overlay. Do not use the
new wrapper for this one pre-cutover stop.

Pre-Phase-13 datastores use the implicit project default network; Phase 13 moves
them to `application_data`. The next command is therefore a controlled,
volume-preserving datastore container/network transition. It must retain the
recorded project name, named volume identities, and production credentials:

```bash
geem-prod-compose up -d \
  postgres redis qdrant minio minio-init \
  app-egress-proxy mcp-egress-proxy mcp-egress-gateway
```

Compare all datastore mounts with the recorded pre-upgrade mounts. Stop if any
container selected a new or empty volume. Wait boundedly for PostgreSQL before
running Alembic:

```bash
timeout 180 sh -c '
  until /usr/local/sbin/geem-prod-compose exec -T postgres \
    pg_isready -U "$1" -d "$2"; do
    sleep 2
  done
' sh '<production-db-role>' '<production-db-name>'
```

Now complete the second network-policy pass from stage 6: inspect the actual
new subnets, add them to `MCP_EGRESS_BLOCKED_NETWORKS`, update the approved MCP
proxy policy, and recreate the closed boundary before starting API or worker:

The earlier API settings-validation container plus the foundation services must
have instantiated all six logical networks: `application_data`,
`application_ingress`, `application_provider_control`, `mcp_egress_control`,
`mcp_proxy_control`, and `public_egress`. Confirm each project-labeled network
exists and inspect its assigned subnet. If any is absent, stop and correct the
topology rather than finalizing an incomplete CIDR list.

```bash
geem-prod-compose config --quiet
geem-prod-compose up -d --force-recreate \
  mcp-egress-proxy mcp-egress-gateway
```

Do not continue until the datastore mounts and application/gateway/proxy
network memberships match the recorded final design.

Apply the migration explicitly, then start the complete final topology. The API
also runs `alembic upgrade head` before Uvicorn, so its subsequent pass should
be a no-op:

```bash
geem-prod-compose run --rm --no-deps api alembic upgrade head
geem-prod-compose up -d
geem-prod-compose ps
```

Verify the live database explicitly:

```bash
geem-prod-compose exec -T api alembic current
geem-prod-compose exec -T api alembic heads
```

The current head must include `0040_mcp_external_surfaces`. Do not enable MCP if
the current revision and repository head differ.

Migrations do not seed the App Catalog row, and ordinary API startup does not
run the catalog seed. First check through Platform Admin or an approved
read-only database/API inspection whether slug `mcp-connectors` already exists.

The minimum baseline has no MCP-only seed CLI. If the actual approved release
still lacks one, the following command reconciles the **entire** App Catalog and
can update metadata/plans for non-MCP products:

```bash
geem-prod-compose exec -T api python -m app.apps_catalog.seed
```

Run it only after backing up the catalog, reviewing the target release's full
`APP_SPECS` diff against production, and receiving explicit product/release-owner
approval. Otherwise stop and deploy a reviewed MCP-only seeding command; do not
use ad hoc SQL or call private seed helpers from a production shell.

Verify through Platform Admin or a read-only database/API inspection that:

- slug `mcp-connectors` exists exactly once;
- status is `coming_soon`;
- connector is `mcp_remote` / `tool_source`; and
- no zero-priced or placeholder MCP plan was manufactured.

The production seed intentionally creates no MCP plans. Signed plan pricing is
a later Platform Admin and release-owner action.

Confirm that API, worker, Beat, Workspace, Platform Admin, gateway, both
proxies, and the ingress service use the new images/configuration. If the host
serves static frontend bundles outside Compose, also run the established
Node.js 22 `npm ci`/production build and atomically deploy the Workspace and
Platform Admin outputs. Do not leave an old frontend talking to the new API.

## 8. Prove the closed production boundary

Run every inspection and probe in these sections of the isolation runbook:

1. [Render safely, migrate, and start the boundary](./mcp-connectors.md#6-render-safely-migrate-and-start-the-boundary)
2. [Prove positive datastore controls](./mcp-connectors.md#7-prove-positive-datastore-controls)
3. [Run the live isolation gate](./mcp-connectors.md#8-run-the-live-isolation-gate)
4. [Deployment-specific address-policy parity](./mcp-connectors.md#deployment-specific-address-policy-parity)

Those links define mandatory assertions and probe bodies. Their examples assume
a relative hardening file. Execute each equivalent Compose operation through
`geem-prod-compose` and the external production overlay; do not copy a raw
command that selects a different project or omits an overlay. For the checked-in
`verify-isolation.sh`, export the exact project name first because the script
builds its own single-file Compose command:

```bash
export COMPOSE_PROJECT_NAME=<existing-compose-project-name>
MCP_SMOKE_COMPOSE_FILE="$GEEM_DEPLOY_ROOT/infra/docker-compose.yml" \
MCP_SMOKE_ENV_FILE="$GEEM_DEPLOY_ROOT/.env" \
  "$GEEM_DEPLOY_ROOT/infra/mcp-egress/verify-isolation.sh"
```

Required evidence includes:

- merged runtime networks exactly match the documented network map;
- no MCP gateway/proxy host port exists;
- API can reach live PostgreSQL, Redis, Qdrant, and MinIO endpoints;
- gateway cannot resolve or connect to those same live endpoints;
- valid application mTLS succeeds and a caller without a client certificate
  fails at TLS;
- API, worker, and gateway cannot open a direct public socket;
- MCP proxy denies private, metadata, every configured deployment CIDR,
  documentation/benchmark, IPv6, mapped, and transition ranges;
- one controlled public HTTPS/443 MCP canary succeeds, proving negative tests
  are not merely a general outage;
- the static Compose-isolation test passes in its gateway dependency
  environment; and
- billing, storage OAuth, messaging, email, and other fixed-provider canaries
  still pass through their intended boundaries.

The checked-in `verify-isolation.sh` is necessary but intentionally incomplete:
it accepts one Compose file and addresses only its built-in probe set. Review
the actual multi-file merged topology separately and retain the full custom
CIDR/parity evidence. A failed parity probe is a release blocker, not a reason
to weaken policy.

## 9. Make the topology persistent before enabling MCP

The checked-in `infra/systemd/geem-stack.service` is not production-ready for
Phase 13: it uses host-specific paths, the legacy `docker-compose` command, and
omits the MCP profile, hardening overlay, and MCP services.

Create or update the deployment-owned supervisor so its start and stop commands
use:

- modern `docker compose`;
- the exact project name and `.env` path;
- `--profile mcp`;
- the exact final ordered Compose file set;
- both `mcp-egress-gateway` and `mcp-egress-proxy`; and
- every required API, worker, Beat, frontend/admin, proxy, datastore, and
  ingress service.

An illustrative **system-unit** command shape is below. Preserve Docker/network
ordering and an unlimited or reviewed migration-aware start timeout. Replace
every path and user with the reviewed production value; do not copy it verbatim:

```ini
[Unit]
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/absolute/path/to/Geem/infra
ExecStart=/usr/local/sbin/geem-prod-compose up -d
ExecStop=/usr/local/sbin/geem-prod-compose stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

If stage 0 found a **user unit**, it cannot rely on the system unit's
`Requires=docker.service` ordering. Use an explicit, bounded Docker-readiness
check and enable it for the user manager's boot target. Resolve the actual
absolute paths with `command -v` and review them before installing the unit:

```ini
[Unit]
Description=Geem production stack

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/absolute/path/to/Geem/infra
ExecStartPre=/usr/bin/timeout 120 /bin/sh -c 'until /usr/bin/docker info >/dev/null 2>&1; do /usr/bin/sleep 2; done'
ExecStart=/usr/local/sbin/geem-prod-compose up -d
ExecStop=/usr/local/sbin/geem-prod-compose stop
TimeoutStartSec=0

[Install]
WantedBy=default.target
```

For a user unit that must start before an interactive login, confirm the
deployment account's linger state with `loginctl show-user
<deployment-user> -p Linger`. If it is not enabled, enabling it with
`sudo loginctl enable-linger <deployment-user>` is a reviewed host change, not
an implicit Cursor action. Verify after reboot that the user manager started
the unit without a login session.

After review, use exactly the scope discovered in stage 0. For a system unit:

```bash
sudo systemctl daemon-reload
sudo systemctl enable geem-stack
sudo systemctl restart geem-stack
```

For a user unit, use these instead—never both sets:

```bash
systemctl --user daemon-reload
systemctl --user enable geem-stack
systemctl --user restart geem-stack
```

Perform a controlled reboot in the maintenance plan. After reboot, repeat
readiness, process, network, no-host-port, mTLS, direct-public, proxy-deny, and
fixed-provider canaries. MCP is not production-ready if it works only after a
manual Compose command.

## 10. Configure monitoring and routine operations

Before enablement or publication, configure concrete destinations and owners
for the alerts listed in
[Runtime operations and observability](./mcp-connectors.md#runtime-operations-and-observability),
including:

- gateway/proxy absence or restart loops;
- mTLS failures and certificate expiry within the rotation window;
- capacity, timeout, size, redirect, and blocked-target outcomes;
- stale grants and compatibility changes;
- approval backlog, quota denials, and paid-access failures;
- `outcome_unknown` and delivery-unknown records; and
- any successful direct-public or gateway-to-datastore probe.

Record the PKI rotation owner and rehearse rotation. Certificates are loaded at
process start; replacing a host file without recreating gateway, API, and worker
does not complete rotation.

## 11. Resolve all release blockers

For the minimum baseline `d2839326c85edff0c8e7b061f190e640aaf3dc49` and every
approved descendant, do not publish until all of the following are fixed and
covered by tests/evidence:

- persistent production startup includes the exact MCP profile, services,
  environment, project, and hardening overlay;
- Beat remains explicitly MCP-disabled without client PKI or an MCP network;
- Workspace WhatsApp surface binding uses the exact internal
  `ChannelBinding.id`, not `AppConnection.id`, and has E2E coverage;
- the proxy independently denies every reviewed non-global and
  deployment-specific range, including the custom CIDR set;
- the development base/tunnel topology is fully overridden by the reviewed
  production-hardening overlay;
- application, gateway, proxy, frontend, datastore, and ingress images are
  pinned by an approved digest manifest rather than unresolved mutable tags;
- the existing database has an approved MCP catalog-row creation path; a broad
  all-App seed is not run without catalog diff review and owner approval;
- external SMTP and any other non-HTTP dependency has a reviewed egress path;
  and
- the gateway runs as one replica while legacy sessions are in memory, unless
  strict session affinity for every legacy handle is proven; and
- all intended monitoring, certificate-expiry alerts, and response owners are
  active.

If a later approved release fixes a blocker, retain the commit, test, and live
evidence that closes it. Do not simply remove the checklist item.

## 12. Enable API and worker only

Only after stages 0–11 pass may the operator change the shared deployment value
to:

```dotenv
MCP_CONNECTOR_ENABLED=true
```

The final Compose overlay must continue forcing Beat to false. Recreate API and
worker only. Before recreation, prove the **post-enable merged configuration**;
checking the old running Beat container is insufficient because it still has
its pre-edit environment:

```bash
geem-prod-compose config --format json \
  | geem-prod-compose run --rm --no-deps -T api python -c '
import json
import sys

from app.core.config import get_settings

services = json.load(sys.stdin)["services"]

def enabled(service):
    value = (services[service].get("environment") or {}).get("MCP_CONNECTOR_ENABLED")
    return str(value).strip().lower() == "true"

if not enabled("api") or not enabled("worker") or enabled("beat"):
    raise SystemExit("post-enable API/worker/Beat flags are unsafe")
gateway = services["mcp-egress-gateway"].get("environment") or {}
if gateway.get("APP_ENV") != "production":
    raise SystemExit("gateway is not in production mode")
if str(gateway.get("EGRESS_ALLOW_PRIVATE")).strip().lower() != "false":
    raise SystemExit("private egress is enabled")
get_settings()
print("post-enable settings valid; Beat remains disabled")
'
```

Then recreate API and worker:

```bash
geem-prod-compose up -d --no-deps --force-recreate api worker
geem-prod-compose ps api worker beat mcp-egress-gateway mcp-egress-proxy
curl --fail --silent --show-error https://<public-api-host>/api/health/ready
```

Startup must validate the internal gateway/proxy origins, readable client PKI,
protocol order, timeouts, provider key, exact model IDs, and capability matrix.
Do not weaken a startup assertion to make the service start.

Keep the production catalog row `coming_soon`; this stage proves runtime
configuration only.

## 13. Release-candidate and paid-product gate

Infrastructure enablement grants no tenant access. Use a separate
production-topology RC environment and isolated catalog/database to:

1. Configure exactly the signed monthly SAR plans below and one default through
   Platform Admin.
2. Deliberately publish only the RC row.
3. Test checkout, payment fulfillment, renewal, installation, expiry,
   uninstall, connection limits, daily tool quotas, and no stale positive
   access.
4. Test no-auth, static-header, and OAuth server connection flows.
5. Test complete discovery/pagination, classification, definition pinning,
   grants, and read-only calls.
6. Test Workspace Chat, public API, Widget, and direct WhatsApp only after the
   exact binding blocker is fixed.
7. Test write approval, expiry, tamper denial, one-dispatch behavior,
   `outcome_unknown`, delivery-unknown, and reconciliation.
8. Test zero-grant/zero-binding legacy behavior and a controlled reboot.

| Plan code | Connections | Tool calls/day |
| --- | ---: | ---: |
| `mcp-starter` | 1 | 200 |
| `mcp-team` | 3 | 1,000 |
| `mcp-scale` | 10 | 5,000 |

After RC sign-off, an authorized Platform Admin must configure the same three
signed plans in the **production** catalog while its row remains `coming_soon`.
Independently verify positive monthly SAR prices, Starter/Team/Scale order,
exact limits, and exactly one default. The isolated RC database does not create
production plans.

Only after that production comparison and all other gates pass may an
authorized Platform Admin publish the production row. Follow publication with
a bounded read-only production canary. Never use zero/placeholder prices or
temporarily bypass publication checks.

## 14. Emergency disable and rollback

The normal rollback is a product/runtime disable, not a schema downgrade.

For immediate containment:

1. Move the catalog row to `coming_soon` or unpublish it.
2. Set `MCP_CONNECTOR_ENABLED=false` in the preserved production `.env`.
3. Keep the Beat override false.
4. Force-recreate only API and worker with the same final Compose wrapper and
   `--no-deps`; the already-running dependency closure must not be recreated.
5. Stop gateway/proxy too if the boundary itself is suspected.
6. Confirm new discovery and dispatch fail closed.

```bash
geem-prod-compose up -d --no-deps --force-recreate api worker
```

For a suspected gateway/proxy boundary only, first pause CI/aaPanel automation
and disable the discovered system or user supervisor so the services cannot
return after a reboot or automated `up`. Then run:

```bash
geem-prod-compose stop mcp-egress-gateway mcp-egress-proxy
```

Keep that containment in place until a reviewed boundary release is deployed.
Do not stop the boundary during a routine disable when pending cleanup or OAuth
revocation still needs it.

Before a planned application-code rollback, deny/expire pending approvals,
reconcile ambiguous writes/deliveries, revoke bindings and grants, and perform
best-effort OAuth revocation. Preserve the gateway while cleanup requires it.

Return to the recorded prior SHA/image only if the release owner confirms it is
compatible with the upgraded schema. Restore PostgreSQL or other state only
under the tested disaster-recovery plan. Do not run an Alembic downgrade merely
to turn MCP off.

## Production evidence checklist

- [ ] Operator input table is complete; no value was guessed.
- [ ] Current and target full SHAs, image digests, and final Compose file order are recorded.
- [ ] Worktree was clean and the source update was a reviewed fast-forward.
- [ ] PostgreSQL, MinIO, Qdrant, Redis/configuration recovery points are verified.
- [ ] Effective encryption identity is unchanged.
- [ ] Modern Compose accepts the complete merged topology.
- [ ] Deployment-owned hardening overlay removes dev credentials, mounts, commands, and ports.
- [ ] Per-environment mTLS chains, SAN/EKU, key matches, permissions, and expiry pass.
- [ ] `MCP_EGRESS_BLOCKED_NETWORKS` and independent proxy denies cover actual deployment ranges.
- [ ] API/worker have no direct public route; fixed-provider and non-HTTP dependency canaries pass.
- [ ] Alembic current/head includes `0040_mcp_external_surfaces`.
- [ ] Approved catalog-row creation/reconciliation ran; `mcp-connectors` is unique and `coming_soon` with no placeholder plans.
- [ ] Workspace and Platform Admin production artifacts match the backend release.
- [ ] Positive datastore and negative gateway isolation controls pass against the same live services.
- [ ] Full mTLS, no-port, direct-public, custom parity, static topology, and public MCP canaries pass.
- [ ] Persistent startup and a controlled reboot preserve the exact topology.
- [ ] Every release blocker is closed with code/test/live evidence.
- [ ] API/worker enablement leaves Beat disabled and production unpublished.
- [ ] Separate RC paid lifecycle, all intended surfaces, approvals, ambiguity handling, and rollback pass.
- [ ] Monitoring, alert ownership, PKI rotation, and emergency disable are operational.

## Source-of-truth references

- [Detailed MCP configuration/isolation/operations runbook](./mcp-connectors.md)
- [General production deployment guide](../deployment.md)
- [Phase 13 product and protocol plan](../../.cursor/plans/mcp.plan.md)
- [Application settings and startup assertions](../../apps/api/app/core/config.py)
- [MCP catalog seed](../../apps/api/app/apps_catalog/seed.py)
- [MCP migrations](../../apps/api/migrations/versions)
- [Base Compose topology](../../infra/docker-compose.yml)
- [Production tunnel overlay](../../infra/docker-compose.tunnel.yml)
- [MCP live isolation smoke](../../infra/mcp-egress/verify-isolation.sh)
- [MCP proxy policy](../../infra/mcp-egress/proxy/squid.conf)
- [Fixed-provider proxy policy](../../infra/app-egress/proxy/squid.conf)
- [PKI layout contract](../../infra/mcp-egress/pki/README.md)
- [Gateway runtime contract](../../apps/mcp_egress_gateway/README.md)
