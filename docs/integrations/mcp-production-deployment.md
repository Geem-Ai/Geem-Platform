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
- PostgreSQL migrations `0036` through `0041`;
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
- attach API, worker, Beat, or the MCP gateway to `public_egress`,
  `application_provider_egress`, or `mcp_public_egress`;
- enable the connector before the live isolation and dependency canaries pass;
- publish the paid App, change signed prices, approve writes, or reconcile an
  ambiguous external result without explicit operator authorization;
- treat the UAT overlay as production isolation evidence; or
- downgrade the database schema as the normal rollback mechanism.

Stop the deployment if the worktree is dirty or divergent, a backup cannot be
verified, the production overlay is incomplete, the encryption identity is
uncertain, a required dependency loses connectivity, or any security probe
fails.

An unexpected secret exposure, successful forbidden network probe, unknown
image, evidence of unauthorized access, or unexplained production mutation is
an incident, not a deployment warning. Stop the rollout, preserve redacted
evidence, prevent automation from recreating affected workloads, and invoke the
organization's incident-response process. Do not rotate credentials, delete
containers/logs, or resume deployment until the incident commander approves a
contained recovery plan; an uncoordinated rotation can break encryption,
datastore access, OAuth revocation, or forensic evidence.

## Required operator inputs

Record these values in the change ticket before execution. Store secrets in the
deployment secret manager, not in the ticket.

| Input | Required decision or evidence |
| --- | --- |
| Repository root | Exact absolute path on the production host |
| Release reference | Approved immutable full commit SHA |
| Current state | Current full SHA, branch, worktree status, and running image IDs |
| Release images | Signed/approved registry manifest mapping every service and host platform to an immutable image digest |
| Compose identity | One project name and the exact ordered Compose file list |
| Hardening overlay | Absolute deployment-owned path outside the Git checkout |
| Deployment topology | The checked-in Cloudflare tunnel plus the required hardening overlay; any other ingress is a stop condition for this release |
| Public hosts | Exact API, Workspace, Platform Admin, marketing, CIMD, and tunnel hosts |
| Data backup | New immutable recovery-set ID plus successful PostgreSQL, MinIO, Qdrant, Redis, configuration, and secret-manager restore evidence |
| Encryption identity | Whether ciphertext currently uses explicit `SECRETS_ENCRYPTION_KEY` or the existing `JWT_SECRET` fallback |
| Datastore credentials | Existing production identities and the approved rotation plan, if any |
| PKI | Per-environment CA/leaf issuance owner, secret path, expiry, and rotation owner |
| Network policy | Docker, host bridge, VPC, corporate, metadata, and deployment-owned CIDRs |
| Fixed providers | Every production HTTP(S), SMTP, telemetry, billing, storage, OAuth, and messaging dependency |
| Product release | Signed SAR prices, one default plan, RC environment, and release owner |
| Canary fixtures | Controlled public HTTPS/443 MCP servers and OAuth credentials |
| Operations | Maintenance window, rollback owner, legacy-supervisor transition, monitoring destination, alert owner, and incident commander |

## 0. Read-only host inventory

Run this stage before modifying Git, `.env`, services, networks, or the
database. Replace the placeholders; do not paste secret-bearing output into the
change ticket.

```bash
export GEEM_DEPLOY_ROOT=/absolute/path/to/Geem
export GEEM_COMPOSE_PROJECT=<existing-compose-project-name>
export GEEM_RELEASE_REF=<approved-full-commit-sha>
export GEEM_PRODUCTION_OVERLAY=/etc/geem/docker-compose.production-hardening.yml
export GEEM_PUBLIC_API_ORIGIN=<approved-public-api-https-origin-without-trailing-slash>

cd "$GEEM_DEPLOY_ROOT"
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline

docker version
docker compose version
for required_command in docker openssl curl timeout systemctl python3; do
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
- OpenSSL, curl, systemd, and GNU coreutils `timeout` must be available.
- `GEEM_PUBLIC_API_ORIGIN` is the one approved public API origin for the whole
  release. It must be an HTTPS origin with no path, query, fragment, userinfo,
  or trailing slash. Use that same value for `APP_URL`, CIMD, OAuth callback
  registration, RC/production probes, and operator API examples; do not type a
  host literal again later in the procedure.

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

Capture the exact project-labelled container inventory, including stopped and
one-shot containers. An unlabelled container may belong to another stack, but
every container carrying this project label is in scope and must have a
non-empty Compose service label:

```bash
project_container_ids=$(docker ps -aq \
  --filter "label=com.docker.compose.project=$GEEM_COMPOSE_PROJECT")
for container_id in $project_container_ids; do
  docker inspect "$container_id" --format \
    'id={{.Id}} name={{.Name}} project={{index .Config.Labels "com.docker.compose.project"}} service={{index .Config.Labels "com.docker.compose.service"}} image={{.Config.Image}} status={{.State.Status}}'
  test -n "$(docker inspect "$container_id" --format \
    '{{index .Config.Labels "com.docker.compose.service"}}')" || {
    printf 'project-labelled container has no Compose service label: %s\n' \
      "$container_id" >&2
    exit 1
  }
done
```

Store this redacted inventory as the pre-change baseline. Do not infer
ownership from a name prefix, and do not omit exited containers: a stale
one-shot or prior `compose run` container can otherwise survive the handoff.

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

Keep `image_ref`, local `image_id`, and `repo_digests` as three distinct
fields. A local image ID is not a registry digest, and an empty `RepoDigests`
array is not reproducible release provenance. For a multi-platform image,
record both the approved top-level registry manifest digest and the resolved
host-platform child manifest/config digest.

Record the exact live datastore mounts before selecting a new Compose file.
Each service must resolve to exactly one running container, and each destination
below must resolve to exactly one expected persistent source:

```bash
for service_and_destination in \
  postgres:/var/lib/postgresql/data \
  redis:/data \
  qdrant:/qdrant/storage \
  minio:/data; do
  service=${service_and_destination%%:*}
  destination=/${service_and_destination#*/}
  container_ids=$(docker ps -q \
    --filter "label=com.docker.compose.project=$GEEM_COMPOSE_PROJECT" \
    --filter "label=com.docker.compose.service=$service")
  test "$(printf '%s\n' "$container_ids" | sed '/^$/d' | wc -l)" -eq 1 || {
    printf 'expected exactly one running %s container\n' "$service" >&2
    exit 1
  }
  docker inspect "$container_ids" --format '{{json .Mounts}}' \
    | python3 -c '
import json
import sys

service, destination = sys.argv[1:]
mounts = [
    mount
    for mount in json.load(sys.stdin)
    if mount.get("Destination") == destination
]
if len(mounts) != 1:
    raise SystemExit(
        f"{service} must have exactly one persistent mount at {destination}"
    )
mount = mounts[0]
if mount.get("Type") != "volume" or not mount.get("Name"):
    raise SystemExit(
        f"{service} must use one named Docker volume at {destination}"
    )
source = mount.get("Source")
name = mount.get("Name")
print(
    f"service={service} type=volume source={source} "
    f"destination={destination} volume={name}"
)
' "$service" "$destination"
done
```

Store this redacted mapping in the change evidence. An absent, duplicate,
anonymous, bind-mounted, or unexpected source is a stop condition. The engine
source can reveal a host path; keep it out of public tickets.

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

Do not combine those topologies. This release guide and its validator approve
only the base file, the checked-in Cloudflare tunnel overlay, and a
deployment-owned production-hardening overlay applied last. If the host uses
aaPanel/Nginx or another ingress, stop. That topology needs its own reviewed,
tested release contract; omitting Cloudflared here would leave the internal-only
application ingress with no approved serving path.

## 1. Create and verify the rollback point

Keep MCP disabled and the App unpublished. Quiesce writes or use the
organization's consistent snapshot procedure.

Create one new recovery set with a unique change/release ID. The staging and
final paths must both be previously nonexistent, on the same filesystem, and
outside the Git checkout. Never reuse a failed name or write directly into a
prior recovery set:

```bash
set -euo pipefail
umask 077
export GEEM_BACKUP_ROOT=<approved-existing-absolute-backup-directory>
export GEEM_RECOVERY_ID=<unique-change-id-and-approved-release-sha>
export GEEM_BACKUP_STAGING="$GEEM_BACKUP_ROOT/.incomplete-$GEEM_RECOVERY_ID"
export GEEM_BACKUP_FINAL="$GEEM_BACKUP_ROOT/$GEEM_RECOVERY_ID"
test -d "$GEEM_BACKUP_ROOT" && test -w "$GEEM_BACKUP_ROOT" || {
  printf '%s\n' 'approved backup directory is unavailable; stopping' >&2
  exit 1
}
test ! -e "$GEEM_BACKUP_STAGING" && test ! -e "$GEEM_BACKUP_FINAL" || {
  printf '%s\n' 'recovery-set name already exists; choose a new immutable name' >&2
  exit 1
}
mkdir -m 0700 "$GEEM_BACKUP_STAGING"
printf '%s\n' incomplete > "$GEEM_BACKUP_STAGING/STATUS"
```

Any failure leaves the staging directory marked `incomplete`. Preserve it for
diagnosis according to retention policy; do not rename it to the final path,
delete evidence, or rerun into it. Capture all of the following under the same
consistency boundary:

- **PostgreSQL:** roles/ownership needed by the application plus a custom-format
  schema-and-data dump. A plain non-empty file or successful `pg_dump` exit is
  insufficient.
- **MinIO:** every application bucket, object version, delete marker, object
  metadata, lifecycle/retention setting, and the required service-account/IAM
  configuration. `mc mirror` by itself is not a complete recovery point because
  it need not preserve versions, delete markers, or server configuration. Use a
  storage-level consistent snapshot or a documented version-aware export.
- **Qdrant:** a full-storage snapshot when supported, or every collection
  snapshot plus the complete alias mapping and collection/cluster settings
  required to reconstruct the service. Per-collection snapshots alone do not
  prove alias recovery.
- **Redis:** record the persistence mode and capture a supported RDB/AOF recovery
  artifact when sessions, queues, locks, rate counters, or Celery state must
  survive rollback. Use `redis-cli --rdb` or a storage snapshot taken after a
  confirmed persistence barrier; never copy a live, changing RDB/AOF file.
- **Deployment configuration:** `.env`, deployment-owned Compose files,
  proxy/firewall policies, Nginx/Cloudflare configuration, the Compose wrapper,
  systemd units/drop-ins, frontend release pointers, and automation state.
  Encrypt this secret-bearing component and restrict its access.
- **Release identity:** current full Git SHA, Compose project/file order,
  datastore mount source/destination map, database role/database identity,
  image reference/ID/RepoDigests, and the approved registry manifest.
- **Secret recovery:** version identifiers and tested recovery authority for
  encryption keys, datastore credentials, tunnel/OAuth/provider credentials,
  and PKI. Never copy CA or leaf private keys into Git or a support archive.

A PostgreSQL custom-format example, adapted to the exact recorded pre-upgrade
Compose command, role, and database, is:

```bash
set -euo pipefail
set -o noclobber
umask 077
export GEEM_POSTGRES_DUMP="$GEEM_BACKUP_STAGING/postgres.dump"
export GEEM_PG_RESTORE=<absolute-path-to-matching-approved-pg_restore>
test ! -e "$GEEM_POSTGRES_DUMP" || exit 1
cd "$GEEM_DEPLOY_ROOT/infra"
if ! docker compose -p "$GEEM_COMPOSE_PROJECT" \
  -f <current-production-compose-file> \
  exec -T postgres pg_dump -Fc \
    -U <production-db-role> <production-db-name> \
  > "$GEEM_POSTGRES_DUMP"; then
  printf '%s\n' 'pg_dump failed; preserve and mark the partial target invalid' >&2
  exit 1
fi
test -s "$GEEM_POSTGRES_DUMP" || {
  printf '%s\n' 'pg_dump produced an empty file; mark the target invalid' >&2
  exit 1
}
"$GEEM_PG_RESTORE" --list "$GEEM_POSTGRES_DUMP" >/dev/null || {
  printf '%s\n' 'pg_restore could not parse the custom-format dump' >&2
  exit 1
}
```

The restore drill is mandatory and runs in a disposable, network-isolated
environment that cannot address production. Restore PostgreSQL into a new empty
database and verify migrations, ownership, extensions, row-count invariants,
and application read canaries. Restore MinIO, Qdrant, and Redis into empty
instances and verify object/version inventories, Qdrant aliases/search canaries,
and Redis load/application invariants. Also rehearse configuration, secret, and
image recovery. Merely listing or checksum-reading an artifact is not a restore
test.

After every component passes, generate a manifest containing component type,
capture timestamp, source identity, consistency method, artifact checksum/size,
encryption/key-version reference, restore-test result, retention class, and
operator approval. Do not include secret values. Mark `STATUS` complete, then
atomically rename the staging directory to `GEEM_BACKUP_FINAL`. Copy/commit the
set to the approved immutable or WORM backup store and verify its independent
checksum. Local permissions alone are not immutability. MODE 2 stops until the
final recovery set and its restore evidence are approved.

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
  apps/api/migrations/versions/0041_openwa_binding_backfill.py \
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

The exact-SHA release must also publish an approved registry manifest. For
every application, worker/Beat, frontend, gateway, proxy, datastore, and ingress
service it records: service name, source SHA, registry/repository, immutable
`image@sha256:...` reference, OS/architecture, top-level multi-platform manifest
digest (when present), resolved platform child manifest/config digest, build
provenance/SBOM reference, and signature/attestation verification result. Pull
those immutable references before maintenance and verify the running host
platform resolves to the recorded child digest. Mutable tags, a local image ID,
or an unverified `RepoDigests` entry do not satisfy this gate. Production must
not rebuild or retag the release in place.

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
- no whole-application `env_file` on Beat, MinIO, `minio-init`, the MCP gateway,
  or either proxy; each receives only its explicit least-privilege variables;
- no development credential, bind mount, reload server, or Vite/Astro dev
  process;
- no host bind mount. Cloudflared uses the exact `cloudflared_config` Compose
  config and `cloudflared_credentials` Compose secret contract documented in
  the linked overlay; proxy policy remains immutable image content;
- the exact immutable registry references from the approved release manifest
  for every production service, with no production `build:` fallback;
- no host ports on any production service;
- API on application data, application broker, ingress, fixed-provider control,
  and MCP control networks only;
- worker on application data, application broker, fixed-provider control, and
  MCP control networks only, with no ingress network;
- Redis on the dedicated internal application broker network only;
- Beat on the application broker network only, running
  `app.worker.beat_app:beat_app` with
  exactly `APP_ENV=production`, internal `REDIS_URL`, and
  `MCP_CONNECTOR_ENABLED=false`; it has no `env_file`, database/Qdrant/MinIO/
  provider/MCP variables, source mount, secret mount, or other network;
- `beat.deploy.replicas: 1`, with exactly one live scheduler after every start
  and reboot; duplicate Beat instances are unsafe;
- gateway on MCP control and proxy control only;
- exactly one gateway replica while legacy sessions remain in memory;
- MCP proxy on proxy control and its dedicated `mcp_public_egress` only;
- fixed-provider proxy on provider control and its dedicated
  `application_provider_egress` only;
- Cloudflared alone on `public_egress`; no egress-capable bridge is shared by
  ingress, app proxy, and MCP proxy;
- exact production API, Workspace, Platform Admin, CIMD, frontend-build, and
  tunnel domains;
- exactly one explicit, non-overlapping IPAM subnet for each of the nine logical
  networks; inability to allocate them is a stop condition; and
- the same final file order in every pull, up, exec, ps, stop, rollback, CI,
  aaPanel, and systemd command.

The final overlay must preserve the existing production volume identities and
declare all four as `external: true` with their exact recorded physical engine
names. This prevents a changed project/path from manufacturing new datastore
volumes. Before any recreate, compare the
running containers' exact mount type/source/destination/volume name with the
merged Compose volume declarations for PostgreSQL, Redis, Qdrant, and MinIO.
Each datastore destination must have exactly one expected persistent source.
A new, anonymous, duplicate, or empty `<project>_postgres_data`, `redis_data`,
`minio_data`, or `qdrant_data` volume is a stop condition, not a fresh-install
opportunity. Prove database role, database name, and the credential identity in
`DATABASE_URL` still select the existing database without printing values.

Any shell program embedded in Compose YAML is parsed once by Compose and again
inside the container. Escape every container-shell dollar sign as `$$`,
including variables, `${parameter:?checks}`, and arithmetic such as
`$$((attempts + 1))`. A single `$` is host-side Compose interpolation and can
silently erase a fail-closed check.

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
```

The Cloudflared form is not discretionary: when it is the in-Compose ingress,
the merged service must run as `65532:65532`, use the fixed HTTP/2 command,
mount `/etc/cloudflared/config.yml` read-only from `cloudflared_config` mode
`0444`, mount `/etc/cloudflared/credentials.json` from
`cloudflared_credentials` mode `0400`, and use a read-only root filesystem,
`cap_drop: [ALL]`, `no-new-privileges`, `pids_limit: 64`, and `mem_limit: 128m`.
The two top-level resources use absolute deployment-owned file paths and no
Cloudflared environment or bind mount. The linked overlay fragment is the
authoritative YAML shape. Local Compose does not remap ownership/mode for
file-backed configs and secrets, so the linked host-side `root:65532` ownership,
`0440` file modes, directory traversal, UID/GID 65532 readability, and
non-writability checks are also mandatory before start.

At this point only wrapper syntax is checked. Do not run `config --quiet` until
the stage-4 environment merge, stage-5 PKI, stage-6 CIDR/IPAM policy, immutable
image references, credentials, and physical volume identities are populated.
The stage-7 `config --quiet` gate must pass before any Phase 13 container is
created. Never run
plain `docker compose config` in a logged production session because expanded
configuration can contain secrets.

When a linked section of `mcp-connectors.md` shows a relative
`docker-compose.production-hardening.yml`, substitute
`$GEEM_PRODUCTION_OVERLAY` and use `geem-prod-compose`. Do not execute a
shortened example that drops the project name, environment file, profile, or
an overlay.

If the production host does not use the checked-in Geem tunnel overlay, stop
this procedure. Do not improvise a replacement or omit the tunnel; obtain a
separately reviewed ingress contract and validator change first.

## 4. Merge Phase 13 configuration without replacing `.env`

Back up `.env`, preserve all current secret values, and merge the Phase 13 keys
from [`.env.example`](../../.env.example). Do not overwrite the file with the
example.

The initial state must remain closed:

```dotenv
MCP_CONNECTOR_ENABLED=false
MCP_SUPPORTED_PROTOCOL_VERSIONS=2026-07-28,2025-11-25,2024-11-05
APP_URL=<exact-value-of-GEEM_PUBLIC_API_ORIGIN>
MCP_CLIENT_METADATA_URL=<exact-value-of-GEEM_PUBLIC_API_ORIGIN>/api/connectors/oauth/mcp_remote/client-metadata.json

MCP_EGRESS_PKI_DIR=/approved/host/secret/path/mcp-egress
MCP_EGRESS_GATEWAY_URL=https://mcp-egress-gateway:8443
MCP_EGRESS_APP_ENV=production
MCP_EGRESS_PROXY_URL=http://mcp-egress-proxy:3128
MCP_EGRESS_CLIENT_CERT_FILE=/run/secrets/mcp-egress/client.crt
MCP_EGRESS_CLIENT_KEY_FILE=/run/secrets/mcp-egress/client.key
MCP_EGRESS_CA_CERT_FILE=/run/secrets/mcp-egress/ca.crt
MCP_EGRESS_BLOCKED_NETWORKS=<reviewed-comma-separated-cidrs>
MCP_ALLOW_PRIVATE_EGRESS=false
MCP_PROXY_REQUIRE_BLOCKED_NETWORKS=true

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
  APP_ENV AUTH_REQUIRED APP_URL MCP_CLIENT_METADATA_URL \
  MCP_CONNECTOR_ENABLED MCP_SUPPORTED_PROTOCOL_VERSIONS \
  MCP_EGRESS_PKI_DIR MCP_EGRESS_GATEWAY_URL MCP_EGRESS_APP_ENV \
  MCP_EGRESS_PROXY_URL MCP_EGRESS_BLOCKED_NETWORKS \
  MCP_ALLOW_PRIVATE_EGRESS MCP_PROXY_REQUIRE_BLOCKED_NETWORKS \
  MCP_TOOL_PROVIDER_CAPABILITY_MATRIX; do
  require_one_env_key "$key"
done

require_exact_env_value APP_ENV production
require_exact_env_value AUTH_REQUIRED true
require_exact_env_value APP_URL "$GEEM_PUBLIC_API_ORIGIN"
require_exact_env_value MCP_CONNECTOR_ENABLED false
require_exact_env_value MCP_EGRESS_APP_ENV production
require_exact_env_value MCP_ALLOW_PRIVATE_EGRESS false
require_exact_env_value MCP_PROXY_REQUIRE_BLOCKED_NETWORKS true
require_exact_env_value MCP_EGRESS_GATEWAY_URL https://mcp-egress-gateway:8443
require_exact_env_value MCP_EGRESS_PROXY_URL http://mcp-egress-proxy:3128
require_exact_env_value MCP_SUPPORTED_PROTOCOL_VERSIONS \
  2026-07-28,2025-11-25,2024-11-05

metadata_url=$(awk -F= '$1 == "MCP_CLIENT_METADATA_URL" {print substr($0, index($0, "=") + 1)}' \
  "$GEEM_DEPLOY_ROOT/.env")
test -z "$metadata_url" || \
  test "$metadata_url" = \
    "$GEEM_PUBLIC_API_ORIGIN/api/connectors/oauth/mcp_remote/client-metadata.json" || {
  printf 'MCP client metadata URL is not derived from the approved API origin\n' >&2
  exit 1
}
```

Review non-empty values for the PKI directory, blocked-network inventory, exact
model IDs, and capability matrix without copying them into logs. Repeat these
checks after the atomic network-policy release and before enabling MCP.

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

Prefer explicit, non-overlapping IPAM subnets in the reviewed production
overlay so the final network set is known before any boundary service starts.
Build one canonical, normalized, sorted CIDR manifest containing all nine final
Compose subnets plus Docker defaults, host bridges, VPC/cloud, corporate,
internal-public, metadata, and other deployment-owned ranges. Give it a change
ID and checksum.

Treat the application blocked-network value and the independent proxy ACL as
one atomic policy release:

1. Generate both from the same approved CIDR manifest.
2. Prove the normalized sets are equal before start; comments/order may differ,
   but no CIDR may be missing from either layer.
3. Record the manifest and both policy checksums in release evidence.
4. Apply the `.env`/secret-manager value, proxy policy, overlay, and immutable
   proxy/gateway images in one stopped-boundary change.
5. Recreate proxy and gateway together, then rerun both parity probe suites.

Explicit IPAM is mandatory because the exact-image validator must prove policy
coverage before start. If the deployment cannot allocate reviewed deterministic
subnets, stop and redesign the topology; do not start a boundary with an
unknown or partially blocked network set.

Follow [Inventory and block deployment networks](./mcp-connectors.md#4-inventory-and-block-deployment-networks)
and [Deployment-specific address-policy parity](./mcp-connectors.md#deployment-specific-address-policy-parity)
without omission. The Python policy and Squid layer must independently reject
the reviewed non-global and deployment-specific ranges.

### Deployment-owned proxy policy

Do not edit tracked `infra/*/proxy/squid.conf` files directly on the production
machine or mount a host replacement over the approved image. The MCP proxy
image contains the reviewed broad policy and a fail-closed renderer. Set the
same canonical value in both layers and require it in production:

```yaml
services:
  mcp-egress-proxy:
    environment:
      MCP_PROXY_BLOCKED_NETWORKS: ${MCP_EGRESS_BLOCKED_NETWORKS:?required}
      MCP_PROXY_REQUIRE_BLOCKED_NETWORKS: "true"
```

The renderer parses canonical CIDRs as data and inserts only validated Squid ACL
lines; raw environment text is never interpreted as configuration. The
repository validator proves that gateway `EGRESS_BLOCKED_NETWORKS` and proxy
`MCP_PROXY_BLOCKED_NETWORKS` are identical, non-empty, cover every explicit
Compose subnet plus every repeated `--required-blocked-network`, and that the
require flag is true. Record the proxy image/template digest and canonical set
checksum.

A fixed-provider allowlist change must be committed, tested, built into an
approved digest-pinned `app-egress-proxy` image, and included in the release
manifest. Do not use a host bind mount to bypass image provenance. Never put
credentials in either proxy policy.

Before the first Phase 13 start, an absent logical network is expected and will
be created from the already reviewed explicit IPAM; any network that already
exists must resolve to exactly one project-labeled object and match the approved
manifest. Multiple matches are always fatal. After creation, rerun the inventory
with `GEEM_REQUIRE_ALL_NETWORKS=true`, require exactly one for all nine, and
compare every actual subnet with the canonical CIDR manifest. An IPAM drift
requires a new atomic policy release, not an in-place edit to only one layer.

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
boundary. Do not attach API/worker to any public-egress network, and do not
pretend adding an SMTP hostname to the HTTPS proxy allowlist fixes `smtplib`
traffic. Login,
verification, invitation, and reset-email canaries must pass before promotion.

## 7. Pull, migrate, reconcile, and start with MCP disabled

Confirm again that API and worker receive `MCP_CONNECTOR_ENABLED=false`. Beat
must independently retain its exact broker-only command and three-variable
environment with the MCP value false; it must not inherit the shared `.env`.

Pull the exact registry digest references from the approved release manifest.
The final overlay must replace every mutable `image:` and every `build:` entry;
production is not a build host. Verify signature/attestation, host-platform
resolution, and the resolved child/config digest before maintenance:

```bash
geem-prod-compose config --quiet
geem-prod-compose pull
<approved-registry-manifest-verifier> \
  --release "$GEEM_RELEASE_REF" \
  --compose-wrapper /usr/local/sbin/geem-prod-compose
```

Validate the effective merged topology with the repository-owned validator in
the exact digest-pinned API image. It creates no Compose service or deployment
network and receives no deployment environment/`--env-file`, secret, host
mount, or Docker socket.
Keep the pipe intact; never insert `tee`, a redirect, `docker compose run`, or a
support logger. Replace the ingress and four physical-volume values with the
stage-0 evidence:

```bash
export GEEM_API_IMAGE=<approved-api-image-at-sha256-digest>
geem-prod-compose config --format json \
  | docker run --rm -i --pull never --network none --read-only \
      --cap-drop ALL --security-opt no-new-privileges:true \
      --entrypoint python "$GEEM_API_IMAGE" \
      -m app.ops.validate_production_compose \
      --project "$GEEM_COMPOSE_PROJECT" \
      --mcp-enabled false \
      --ingress-service cloudflared \
      --volume postgres_data=<recorded-postgres-engine-volume> \
      --volume redis_data=<recorded-redis-engine-volume> \
      --volume qdrant_data=<recorded-qdrant-engine-volume> \
      --volume minio_data=<recorded-minio-engine-volume> \
      --required-blocked-network <reviewed-host-vpc-or-corporate-cidr>
```

The validator is release code from `GEEM_API_IMAGE`, so its image digest must
match the approved registry manifest and `--pull never` must not substitute a
tag. Pass `--ingress-service cloudflared` exactly once for the reviewed
in-Compose tunnel. External or alternate ingress is not approved by this release;
stop instead of omitting the flag. Repeat
`--required-blocked-network` for every non-Compose host/VPC/corporate range in
the canonical manifest. The validator enforces the closed flags, exact network
map, internal networks, public membership, datastore mount identity,
least-privilege environments/secrets, exactly one declared Beat replica, one
gateway replica, no unsafe
ports/build/dev commands/mounts, and immutable images. A validation failure must
not be bypassed.

Before any `up`, compare every existing project-labelled container with the
exact service set from the fully rendered release. This gate allows a release
service to be absent before first start, but permits no unknown service label,
empty label, or duplicate container for a service:

```bash
expected_services=$(mktemp)
actual_services=$(mktemp)
trap 'rm -f "$expected_services" "$actual_services"' EXIT HUP INT TERM

geem-prod-compose config --services | LC_ALL=C sort -u > "$expected_services"
for container_id in $(docker ps -aq \
  --filter "label=com.docker.compose.project=$GEEM_COMPOSE_PROJECT"); do
  service=$(docker inspect "$container_id" --format \
    '{{index .Config.Labels "com.docker.compose.service"}}')
  test -n "$service" || {
    printf 'project-labelled container has no service label: %s\n' \
      "$container_id" >&2
    exit 1
  }
  printf '%s\n' "$service" >> "$actual_services"
done
LC_ALL=C sort -o "$actual_services" "$actual_services"

test -z "$(uniq -d "$actual_services")" || {
  printf 'duplicate project service containers exist\n' >&2
  uniq -d "$actual_services" >&2
  exit 1
}
test -z "$(comm -13 "$expected_services" "$actual_services")" || {
  printf 'unexpected project service containers exist\n' >&2
  comm -13 "$expected_services" "$actual_services" >&2
  exit 1
}
printf 'project container inventory: no duplicate or unexpected services\n'
rm -f "$expected_services" "$actual_services"
trap - EXIT HUP INT TERM
```

If this gate finds an orphan, record its exact container ID, service label,
image identity, state, networks, and mounts. Obtain explicit review for that
specific ID and its data consequences, then stop and remove only the approved
container, without `-v`, before rerunning the gate. The approved retirement is
an exact-ID operation, for example:

```bash
container_id='<approved-exact-container-id>'
test "$(docker inspect "$container_id" --format \
  '{{index .Config.Labels "com.docker.compose.project"}}')" = \
  "$GEEM_COMPOSE_PROJECT"
docker stop --time 60 "$container_id"
docker rm "$container_id"
```

Never use
`compose down --remove-orphans`, `compose up --remove-orphans`, a name glob, or
a bulk removal command: this handoff requires an auditable per-container
retirement decision. After the final start, require zero unexpected
project-labelled containers and exactly one container for every required
long-running service plus the reviewed successful one-shot.

Enter the approved maintenance window, drain active application/worker work,
and pause aaPanel, CI, timers, watchers, and every other recorded recreator. A
legacy systemd unit must become **inactive** before its file is replaced;
`disable` alone only removes boot links and leaves an active unit in control.

Review and checksum the actual unit and its drop-ins first. Then use the exact
scope discovered in stage 0 to disable and stop it: `sudo systemctl disable
geem-stack` followed by `sudo systemctl stop geem-stack` for a system unit, or
the corresponding `systemctl --user` commands for a user unit. Never run both.
The stop may intentionally stop the whole old stack; writes are already
quiesced and the next start must select the same recorded volumes. If the
legacy `ExecStop` is unknown, secret-bearing, destructive, or selects a
different project/file set, stop before invoking it and use a separately
reviewed transition/drop-in plan. Do not overwrite or daemon-reload an active
legacy unit and hope its old stop action disappears.

Confirm the old unit is disabled and inactive. If its reviewed stop action did
not stop API, worker, and Beat, use the exact recorded pre-upgrade Compose
project and file set to stop only those services:

```bash
<recorded-pre-upgrade-compose-command-and-files> stop api worker beat
```

The placeholder must be replaced with the command captured in stage 0,
including its existing project identity and every old overlay. Do not use the
new wrapper for this one pre-cutover stop, and do not run it concurrently with
an active legacy unit.

Pre-Phase-13 datastores use the implicit project default network; Phase 13 moves
them to `application_data`. The next command is therefore a controlled,
volume-preserving datastore container/network transition. It must retain the
recorded project name, named volume identities, and production credentials.
Run it only after the final CIDR manifest, application value, proxy policy, and
overlay passed the atomic stage-6 review:

```bash
geem-prod-compose up -d \
  postgres redis qdrant minio minio-init \
  app-egress-proxy mcp-egress-proxy mcp-egress-gateway
```

Compare all datastore mounts with the recorded pre-upgrade mounts. Stop if any
container selected a new or empty volume. Rerun the exact stage-0
type/source/destination/volume-name inventory and require a byte-for-byte match
for all four physical sources and destinations. Separately prove the stored
PostgreSQL role/database identity and the parsed (redacted) `DATABASE_URL`
identity agree with the pre-upgrade record. Wait boundedly for PostgreSQL before
running Alembic:

```bash
timeout 180 sh -c '
  until /usr/local/sbin/geem-prod-compose exec -T postgres \
    pg_isready -U "$1" -d "$2"; do
    sleep 2
  done
' sh '<production-db-role>' '<production-db-name>'
```

The exact-image validator already proved that all nine declared IPAM subnets
are explicit, non-overlapping, and covered identically by gateway and proxy.
Do not change the overlay or CIDR manifest after that gate.

Apply the migration explicitly, then start the complete final topology. The API
also runs `alembic upgrade head` before Uvicorn, so its subsequent pass should
be a no-op:

```bash
geem-prod-compose run --rm --no-deps api alembic upgrade head
geem-prod-compose up -d --wait --wait-timeout 300
geem-prod-compose ps
```

Now require all nine actual logical networks to exist, with each logical label
resolving to exactly one project network. Compare every assigned subnet with
the declared IPAM and approved CIDR manifest, then compare every live service
membership and datastore mount with the final design. Zero/multiple matches,
missing subnets, overlap, drift, or an unexpected member stops the deployment
and the boundary remains unavailable; never patch only `.env` or only Squid.
Rerun the linked inventory command with
`GEEM_REQUIRE_ALL_NETWORKS=true` for this post-start gate.

`--wait` is a finite startup gate, not complete application evidence: services
without healthchecks are only proven running. Follow it with the explicit
readiness, one-shot completion, network, mTLS, datastore, and dependency probes
in stages 8–10. `minio-init` must exit zero after a fail-closed credential,
bucket, and policy check; a swallowed `mc` failure is a stop condition.

Verify the live database explicitly:

```bash
geem-prod-compose exec -T api alembic current
geem-prod-compose exec -T api alembic heads
```

The current head must include `0041_openwa_binding_backfill`. Do not enable MCP
if the current revision and repository head differ.

Migrations do not seed the App Catalog row, and ordinary API startup does not
run the catalog seed. First check through Platform Admin or an approved
read-only database/API inspection whether slug `mcp-connectors` already exists.

Use only the reviewed MCP-scoped reconciler from the approved release. First
run and review its dry-run, then back up the affected catalog/category rows:

```bash
geem-prod-compose exec -T api \
  python -m app.apps_catalog.reconcile_mcp --dry-run
```

Obtain a separate production mutation approval for exactly that reviewed
change. Only then apply it, and verify in a distinct command:

```bash
geem-prod-compose exec -T api \
  python -m app.apps_catalog.reconcile_mcp --apply
geem-prod-compose exec -T api \
  python -m app.apps_catalog.reconcile_mcp --verify
```

The command may create the automation category only when missing and otherwise
changes only `mcp-connectors`; it preserves existing MCP status, plans,
entitlements, and extra product data. A broad `app.apps_catalog.seed`, ad hoc
SQL, or private helper call is not an approved production substitute.

Because status is preserved, any pre-existing row whose status is not
`coming_soon` is a stop condition. Obtain a separate Platform Admin lifecycle
approval and correct that state before enabling API or worker; otherwise an
already-published row could become live as soon as the runtime flag changes.

Verify through Platform Admin or a read-only database/API inspection that:

- slug `mcp-connectors` exists exactly once;
- status is `coming_soon`;
- connector is `mcp_remote` / `tool_source`; and
- no zero-priced or placeholder MCP plan was manufactured.

The MCP reconciler intentionally creates no plans. Signed plan pricing is a
later Platform Admin and release-owner action.

Confirm that API, worker, Beat, Workspace, Platform Admin, marketing, gateway,
both proxies, and Cloudflared use the new digest-pinned Compose images and
configuration. This release does not permit Workspace, Platform Admin, or
marketing static bundles to be served outside Compose: all three frontends and
Cloudflared are validator-required services. Stop if the host still has an
outside-Compose frontend or alternate ingress instead of trying to update it in
parallel.

## 8. Prove the closed production boundary

Run every inspection and probe in these sections of the isolation runbook:

1. [Render safely, migrate, and start the boundary](./mcp-connectors.md#6-render-safely-migrate-and-start-the-boundary)
2. [Prove positive datastore controls](./mcp-connectors.md#7-prove-positive-datastore-controls)
3. [Run the live isolation gate](./mcp-connectors.md#8-run-the-live-isolation-gate)
4. [Deployment-specific address-policy parity](./mcp-connectors.md#deployment-specific-address-policy-parity)

Those links define mandatory assertions and probe bodies. Their examples assume
a relative hardening file. Execute each equivalent Compose operation through
`geem-prod-compose` and the external production overlay; do not copy a raw
command that selects a different project or omits an overlay. Run the checked-in
smoke through the persistent wrapper so it inspects the same project, profile,
environment file, and complete overlay set:

```bash
MCP_SMOKE_COMPOSE_WRAPPER=/usr/local/sbin/geem-prod-compose \
  "$GEEM_DEPLOY_ROOT/infra/mcp-egress/verify-isolation.sh"
```

Required evidence includes:

- merged runtime networks exactly match the documented network map;
- provider proxy, MCP proxy, and ingress are each the sole member of their own
  external-route network; no shared public bridge exists;
- no MCP gateway/proxy host port exists;
- API can reach live PostgreSQL, Redis, Qdrant, and MinIO endpoints;
- gateway cannot resolve or connect to those same live endpoints;
- valid application mTLS succeeds and a caller without a client certificate
  fails at TLS;
- API, worker, Beat, and gateway cannot open a direct public socket;
- MCP proxy denies private, metadata, every configured deployment CIDR,
  documentation/benchmark, IPv6, mapped, and transition ranges;
- gateway and proxy each return explicit 403 policy denials for a representative
  address in every deployment CIDR; timeout/5xx is not denial evidence;
- one controlled public HTTPS/443 target returns an explicit proxy CONNECT HTTP
  200 and passes the gateway/MCP canary, proving negative tests are not a
  general outage;
- the static Compose-isolation test passes in its gateway dependency
  environment; and
- billing, storage OAuth, messaging, email, and other fixed-provider canaries
  still pass through their intended boundaries.

The checked-in `verify-isolation.sh` is necessary but intentionally incomplete:
its built-in probes do not replace the exact-image rendered-topology validator
or full custom CIDR/parity evidence. A failed parity probe is a release blocker,
not a reason to weaken policy. Production must not use the script's single-file
development fallback.

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

Create a root-owned `/usr/local/sbin/geem-prod-readiness` that exits nonzero
unless, within a fixed deadline:

- every required long-running service resolves to exactly one running container,
  including exactly one Beat scheduler;
- every declared healthcheck is healthy and every required one-shot exits zero;
- API public readiness and internal datastore canaries pass;
- Beat can reach Redis but cannot resolve or connect to PostgreSQL, Qdrant, or
  MinIO;
- gateway mTLS succeeds and the no-client-certificate check fails;
- the exact network cardinality/membership and datastore mounts still match;
  and
- gateway/proxy have no host ports and forbidden direct-public probes fail.

The script must use the persistent Compose wrapper, print only categorical
results, and never print environments or raw merged configuration. Test both a
success and a deliberately missing-service failure before installing it.

Create a second root-owned executable,
`/usr/local/sbin/geem-prod-prestart`. It is part of the approved release
artifact, not a session helper. Before every `up`, it must:

1. run `geem-prod-compose config --quiet`;
2. stream `geem-prod-compose config --format json` into the validator from the
   exact approved API image digest with `--pull never`, no network, read-only
   root, no capabilities, and no Docker socket or host mounts;
3. pass literal, reviewed values for the project, the single `cloudflared`
   ingress, all four physical volumes, the closed MCP flag, and every canonical
   non-Compose blocked CIDR; and
4. rerun the exact project-label inventory gate, rejecting empty labels,
   duplicates, and unexpected services before Compose can create anything.

Store those arguments as quoted literals inside this root-owned script. Do not
read them from the invoking shell or an unchecksummed environment file. The
script's validator command has this mandatory shape; replace every placeholder
and repeat the CIDR flag as required by the approved manifest:

```bash
#!/bin/sh
set -eu

compose=/usr/local/sbin/geem-prod-compose
docker=/usr/bin/docker
api_image='<approved-api-image-reference-at-sha256-digest>'
project='<approved-existing-compose-project>'

"$compose" config --quiet
"$compose" config --format json \
  | "$docker" run --rm -i --pull never --network none --read-only \
      --cap-drop ALL --security-opt no-new-privileges:true \
      --entrypoint python "$api_image" \
      -m app.ops.validate_production_compose \
      --project "$project" \
      --mcp-enabled false \
      --ingress-service cloudflared \
      --volume postgres_data='<recorded-postgres-engine-volume>' \
      --volume redis_data='<recorded-redis-engine-volume>' \
      --volume qdrant_data='<recorded-qdrant-engine-volume>' \
      --volume minio_data='<recorded-minio-engine-volume>' \
      --required-blocked-network '<reviewed-non-compose-cidr-1>' \
      --required-blocked-network '<reviewed-non-compose-cidr-n>'

expected_services=$(mktemp)
actual_services=$(mktemp)
trap 'rm -f "$expected_services" "$actual_services"' EXIT HUP INT TERM
"$compose" config --services | LC_ALL=C sort -u > "$expected_services"
for container_id in $("$docker" ps -aq \
  --filter "label=com.docker.compose.project=$project"); do
  service=$("$docker" inspect "$container_id" --format \
    '{{index .Config.Labels "com.docker.compose.service"}}')
  test -n "$service" || exit 1
  printf '%s\n' "$service" >> "$actual_services"
done
LC_ALL=C sort -o "$actual_services" "$actual_services"
test -z "$(uniq -d "$actual_services")"
test -z "$(comm -13 "$expected_services" "$actual_services")"
printf 'pre-start topology validation: passed\n'
```

When production MCP is later enabled, updating the literal
`--mcp-enabled false` to `true` is part of that separately approved change; the
script and checksum manifest must be reviewed and replaced atomically with the
`.env` edit. A restart must never validate a different MCP state than it starts.

Create `/usr/local/sbin/geem-prod-fail-start` as another root-owned executable.
On any failed start result it captures the running containers with the exact
approved project label, verifies that label again for every immutable ID, stops
those IDs directly through Docker, and then requires zero running containers
with that project label. It must not parse the possibly invalid Compose files
that caused preflight to fail. It never removes a container or volume and is a
categorical no-op when normal `ExecStop` already left no running project
containers:

```bash
#!/bin/sh
set -eu

project='<approved-existing-compose-project>'
running=$(/usr/bin/docker ps -q \
  --filter "label=com.docker.compose.project=$project")
if [ -n "$running" ]; then
  for container_id in $running; do
    test "$(/usr/bin/docker inspect "$container_id" --format \
      '{{index .Config.Labels "com.docker.compose.project"}}')" = "$project"
  done
  stop_status=0
  /usr/bin/timeout 90 /usr/bin/docker stop --time 60 $running \
    >/dev/null || stop_status=$?
else
  stop_status=0
fi
remaining=$(/usr/bin/docker ps -q \
  --filter "label=com.docker.compose.project=$project")
test -z "$remaining" || {
  printf 'fail-start containment left project containers running\n' >&2
  exit 1
}
test "$stop_status" -eq 0 || {
  printf 'fail-start containment stop command failed or timed out\n' >&2
  exit 1
}
printf 'fail-start containment: zero project containers running\n'
```

Replace the project placeholder with the same literal embedded in the wrapper
and prestart script. Direct stopping is required because malformed or drifted
Compose input may be the reason `ExecStartPre` failed. The containment script
does not use `down`, `--remove-orphans`, or `rm`; if an external recreator
starts an unknown container during containment, the zero-running check fails
and incident handling begins instead of deleting unreviewed state.

An illustrative **system-unit** command shape is below. Preserve Docker/network
ordering and finite startup/stop deadlines. Replace every path and user with the
reviewed production value; do not copy it verbatim:

```ini
[Unit]
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/absolute/path/to/Geem/infra
ExecStartPre=/usr/bin/timeout 120 /bin/sh -c 'until /usr/bin/docker info >/dev/null 2>&1; do /usr/bin/sleep 2; done'
ExecStartPre=/usr/bin/sha256sum --check --strict --quiet /etc/geem/phase13-start-artifacts.sha256
ExecStartPre=/usr/bin/timeout 180 /usr/local/sbin/geem-prod-prestart
ExecStart=/usr/local/sbin/geem-prod-compose up -d --wait --wait-timeout 300
ExecStartPost=/usr/bin/timeout 120 /usr/local/sbin/geem-prod-readiness
ExecStop=/usr/local/sbin/geem-prod-compose stop --timeout 60
ExecStopPost=/usr/bin/timeout 120 /usr/local/sbin/geem-prod-fail-start
TimeoutStartSec=600
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
```

If stage 0 found a **user unit**, it cannot rely on the system unit's
`Requires=docker.service` ordering. Use an explicit, bounded Docker-readiness
check and enable it for the user manager's boot target. Resolve the actual
absolute paths with `command -v` and review them before installing the unit.
If the deployment account cannot read every root-owned file in the checksum
manifest, do not omit those files or weaken their modes. Install an audited
sudoers rule that permits only this literal command (no wildcard or alternate
manifest), validate it with `visudo -cf`, and include that sudoers file in the
manifest:

```sudoers
<deployment-user> ALL=(root) NOPASSWD: /usr/bin/sha256sum --check --strict --quiet /etc/geem/phase13-start-artifacts.sha256
```

The user-unit shape then uses the exact noninteractive command:

```ini
[Unit]
Description=Geem production stack

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/absolute/path/to/Geem/infra
ExecStartPre=/usr/bin/timeout 120 /bin/sh -c 'until /usr/bin/docker info >/dev/null 2>&1; do /usr/bin/sleep 2; done'
ExecStartPre=/usr/bin/sudo -n /usr/bin/sha256sum --check --strict --quiet /etc/geem/phase13-start-artifacts.sha256
ExecStartPre=/usr/bin/timeout 180 /usr/local/sbin/geem-prod-prestart
ExecStart=/usr/local/sbin/geem-prod-compose up -d --wait --wait-timeout 300
ExecStartPost=/usr/bin/timeout 120 /usr/local/sbin/geem-prod-readiness
ExecStop=/usr/local/sbin/geem-prod-compose stop --timeout 60
ExecStopPost=/usr/bin/timeout 120 /usr/local/sbin/geem-prod-fail-start
TimeoutStartSec=600
TimeoutStopSec=120

[Install]
WantedBy=default.target
```

For a user unit that must start before an interactive login, confirm the
deployment account's linger state with `loginctl show-user
<deployment-user> -p Linger`. If it is not enabled, enabling it with
`sudo loginctl enable-linger <deployment-user>` is a reviewed host change, not
an implicit Cursor action. Verify after reboot that the user manager started
the unit without a login session.

Install the wrapper, prestart, readiness, containment, final unit, and any
drop-ins as `root:root`; executables are mode `0755`, unit/drop-ins are `0644`.
The checksum boundary must also include every input that persistent startup
parses or mounts: the root `.env`, checked-in base and tunnel files, external
hardening overlay, Cloudflared configuration/credential source, MCP PKI source
files, and any deployment-owned proxy/config files named by the overlay. A
credential, certificate, policy, image digest, or environment rotation is a
reviewed manifest replacement, not an unchecked edit. After final review,
checksum the exact absolute paths into a root-owned mode-`0444` manifest:

```bash
set -euo pipefail
umask 077
staged_manifest=$(mktemp)
root_staged_manifest="/etc/geem/.phase13-start-artifacts.$$.new"
cleanup_manifest_stage() {
  rm -f "$staged_manifest"
  sudo rm -f "$root_staged_manifest"
}
trap cleanup_manifest_stage EXIT HUP INT TERM

sudo sha256sum \
  /usr/local/sbin/geem-prod-compose \
  /usr/local/sbin/geem-prod-prestart \
  /usr/local/sbin/geem-prod-readiness \
  /usr/local/sbin/geem-prod-fail-start \
  "$GEEM_DEPLOY_ROOT/.env" \
  "$GEEM_DEPLOY_ROOT/infra/docker-compose.yml" \
  "$GEEM_DEPLOY_ROOT/infra/docker-compose.tunnel.yml" \
  "$GEEM_PRODUCTION_OVERLAY" \
  <every-external-config-secret-and-pki-source-path> \
  <exact-user-unit-artifact-verifier-sudoers-path-if-used> \
  <installed-unit-absolute-path> \
  > "$staged_manifest"
sudo sha256sum --check --strict --quiet "$staged_manifest"
sudo test ! -e "$root_staged_manifest"
sudo install -o root -g root -m 0444 \
  "$staged_manifest" "$root_staged_manifest"
sudo sha256sum --check --strict --quiet "$root_staged_manifest"
sudo mv "$root_staged_manifest" \
  /etc/geem/phase13-start-artifacts.sha256
sudo sha256sum --check --strict \
  /etc/geem/phase13-start-artifacts.sha256
sudo sha256sum /etc/geem/phase13-start-artifacts.sha256
```

Record the final manifest checksum in the signed change evidence. Expand the
external-input and conditional sudoers placeholders to separate literal paths,
or remove the conditional entry when a system unit is used; do not leave a
placeholder in the installed command. If the unit has drop-ins, list every
exact drop-in path in the manifest too. A changed project, ingress, volume,
CIDR, image digest, MCP state, environment, secret/config source, command, or
unit requires a new reviewed manifest; never regenerate it merely to silence
`ExecStartPre`.

After review, use exactly the scope discovered in stage 0. For a system unit:

```bash
sudo systemctl daemon-reload
sudo systemctl enable geem-stack
```

For a user unit, use these instead—never both sets:

```bash
systemctl --user daemon-reload
systemctl --user enable geem-stack
```

The legacy unit must already be inactive from stage 7 before these commands.
Do not perform the first normal start yet. The first start of the replacement
unit is the deliberate failure test below; starting it normally first would
make a later `start` a no-op and would not exercise containment.

Before accepting the supervisor, prove fail-start containment deliberately in
the maintenance window. Stop the currently running, already-validated stack
through the persistent wrapper and prove that no project container remains
running. Then, through the same configuration-management workflow, install one
temporary drop-in for the new unit that clears `ExecStartPost`, stops `worker`,
then runs the real readiness script:

```bash
/usr/bin/timeout 90 /usr/local/sbin/geem-prod-compose stop --timeout 60
test -z "$(docker ps -q \
  --filter "label=com.docker.compose.project=$GEEM_COMPOSE_PROJECT")"
```

```ini
[Service]
ExecStartPost=
ExecStartPost=/usr/local/sbin/geem-prod-compose stop --timeout 30 worker
ExecStartPost=/usr/bin/timeout 120 /usr/local/sbin/geem-prod-readiness
```

Create a separately reviewed temporary checksum manifest using the same exact
path list as the permanent manifest plus this one exact drop-in. Never let an
unlisted drop-in bypass the checksum boundary. Reload the one discovered
system/user scope and start the unit. The first post-start command creates a
deliberate missing-required-service condition, so the real readiness command
must fail, the start job must be nonzero, and `ExecStopPost` must contain the
partial start. Retain categorical evidence from:

```bash
if <systemctl-in-the-discovered-scope> start geem-stack; then
  printf 'deliberate readiness failure unexpectedly passed\n' >&2
  exit 1
fi
test -z "$(docker ps -q \
  --filter "label=com.docker.compose.project=$GEEM_COMPOSE_PROJECT")"
printf 'deliberate readiness failure: zero project containers running\n'
```

Remove only that exact temporary drop-in through the approved workflow and
atomically restore the pre-reviewed permanent checksum manifest. Reload the
same scope, verify the permanent artifact manifest again, then start normally
with `sudo systemctl start geem-stack` for the system scope or
`systemctl --user start geem-stack` for the user scope. Require readiness
success. If `start` reports the replacement unit active without executing its
finite readiness gate, stop: the handoff was not tested correctly. Also rerun
the full project-label inventory: it must contain zero unexpected containers
and exact required service cardinality. This test is incomplete if it merely
observes a failed unit while any project container remains running.

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
- Beat runs the least-privilege `app.worker.beat_app:beat_app`, with only
  production mode, internal Redis, and MCP false, and without an `env_file`,
  application/datastore/provider/MCP secrets, or any network beyond the
  dedicated internal application broker; both
  `beat.deploy.replicas` and live Beat cardinality equal one;
- Workspace WhatsApp surface binding uses the exact internal
  `ChannelBinding.id`, not `AppConnection.id`, and has E2E coverage;
- the proxy independently denies every reviewed non-global and
  deployment-specific range, including the custom CIDR set;
- the development base/tunnel topology is fully overridden by the reviewed
  production-hardening overlay;
- fixed-provider proxy, MCP proxy, and ingress each have a distinct
  single-member external-route network;
- application, gateway, proxy, frontend, datastore, and ingress images are
  pinned by an approved digest manifest rather than unresolved mutable tags;
- the MCP-only catalog reconciler passes dry-run/apply/verify and no broad
  all-App seed or ad hoc SQL is used;
- external SMTP and any other non-HTTP dependency has a reviewed egress path;
- the gateway runs as one replica while legacy sessions are in memory, unless
  strict session affinity for every legacy handle is proven; and
- all intended monitoring, certificate-expiry alerts, and response owners are
  active.

If a later approved release fixes a blocker, retain the commit, test, and live
evidence that closes it. Do not simply remove the checklist item.

## 12. Release-candidate and paid-product gate

Production `MCP_CONNECTOR_ENABLED` must remain `false` throughout this stage.
Use a separate
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
6. Test Workspace Chat, public API, Widget, and direct WhatsApp only with
   matching exact-SHA Workspace/API artifacts containing the
   `ChannelBinding.id` contract fix and unit/E2E evidence.
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

Attach exact release SHA/image digests, topology/policy checksums, paid-flow
evidence, surface/write/ambiguity tests, controlled-reboot evidence, monitoring,
and rollback rehearsal to the RC sign-off. A functional UAT run, production
infrastructure readiness, or a `coming_soon` row is not an RC substitute.

Only a signed RC approval may authorize stage 13. Never use zero/placeholder
prices or temporarily bypass publication checks.

## 13. Enable production API and worker only after RC sign-off

Only after stages 0–12 pass, the signed RC approval names the exact production
release, and an operator explicitly authorizes enablement may the shared value
change to:

```dotenv
MCP_CONNECTOR_ENABLED=true
```

The final Compose overlay must continue enforcing Beat's exact broker-only
command, three-variable environment, no-secret/no-`env_file` contract, and
false MCP flag. Before recreation, rerun the repository-owned topology
validator from the exact digest-pinned API image with `--mcp-enabled true`;
checking the old running Beat container is insufficient because it still has
its pre-edit configuration. Use the same project, ingress, and physical-volume
arguments approved in stage 7:

```bash
geem-prod-compose config --format json \
  | docker run --rm -i --pull never --network none --read-only \
      --cap-drop ALL --security-opt no-new-privileges:true \
      --entrypoint python "$GEEM_API_IMAGE" \
      -m app.ops.validate_production_compose \
      --project "$GEEM_COMPOSE_PROJECT" \
      --mcp-enabled true \
      --ingress-service cloudflared \
      --volume postgres_data=<recorded-postgres-engine-volume> \
      --volume redis_data=<recorded-redis-engine-volume> \
      --volume qdrant_data=<recorded-qdrant-engine-volume> \
      --volume minio_data=<recorded-minio-engine-volume> \
      --required-blocked-network <reviewed-host-vpc-or-corporate-cidr>
```

The validator receives only rendered JSON on stdin: no deployment environment file,
secret, host mount, Docker socket, or service network. Never replace it with
`docker compose run`.

Recreate API and worker only, then run the finite readiness script and repeat
the live flag, Beat isolation, mTLS, direct-public, datastore, and provider
canaries:

```bash
geem-prod-compose up -d --no-deps --force-recreate \
  --wait --wait-timeout 300 api worker
timeout 120 /usr/local/sbin/geem-prod-readiness
geem-prod-compose ps api worker beat mcp-egress-gateway mcp-egress-proxy
curl --fail --silent --show-error "$GEEM_PUBLIC_API_ORIGIN/api/health/ready"
```

Startup must validate the internal gateway/proxy origins, readable client PKI,
protocol order, timeouts, provider key, exact model IDs, and capability matrix.
Do not weaken a startup assertion to make the service start.

Keep the production catalog row `coming_soon` until the post-enable checks pass.
Then an authorized Platform Admin may run the product-specific publication
validator and publish the production row named in the RC approval. Follow
publication with a bounded read-only production canary. Infrastructure or flag
enablement alone never authorizes publication.

## 14. Emergency disable and rollback

The normal rollback is a product/runtime disable, not a schema downgrade.

For immediate containment:

1. Move the catalog row to `coming_soon` or unpublish it.
2. Set `MCP_CONNECTOR_ENABLED=false` in the preserved production `.env`.
3. Keep Beat on its broker-only command/environment with MCP false and exactly
   one replica.
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

### Security-incident path

Use the incident process, not routine rollback, if a container received
unintended secrets, a forbidden egress/datastore probe succeeds, an image or
policy checksum is unknown, or unauthorized access is suspected. Immediately:

1. freeze release automation and new MCP admission;
2. preserve container/image IDs, creation times, orchestrator events, policy
   checksums, and redacted logs without dumping environments or secret values;
3. identify exposed **variable names**, credential owners, access scope, and
   affected time window through the secret manager and deployment definition;
4. contain the affected workload/boundary under incident-command approval;
5. revoke/rotate affected credentials in dependency order, using the separate
   encryption-key migration whenever ciphertext identity is involved; and
6. rebuild from the last approved registry manifest, rerun restore/isolation
   evidence, and resume only after incident closure.

Deleting a container, clearing logs, rotating `JWT_SECRET` or
`SECRETS_ENCRYPTION_KEY`, or changing a datastore password ad hoc can destroy
evidence or availability. In particular, discovering that MinIO, `minio-init`,
the gateway, or a proxy inherited the application `.env` is a credential
exposure incident even if the service appeared healthy.

Before a planned application-code rollback, deny/expire pending approvals,
reconcile ambiguous writes/deliveries, revoke bindings and grants, and perform
best-effort OAuth revocation. Preserve the gateway while cleanup requires it.

Return to the recorded prior SHA/image only if the release owner confirms it is
compatible with the upgraded schema. Restore PostgreSQL or other state only
under the tested disaster-recovery plan. Do not run an Alembic downgrade merely
to turn MCP off.

## Production evidence checklist

- [ ] Operator input table is complete; no value was guessed.
- [ ] Current/target full SHAs and the signed registry manifest (top/platform digests) are recorded.
- [ ] Worktree was clean and the source update was a reviewed fast-forward.
- [ ] One new immutable PostgreSQL/MinIO/Qdrant/Redis/configuration recovery set passes isolated restores.
- [ ] Effective encryption identity is unchanged.
- [ ] Modern Compose accepts the complete merged topology.
- [ ] Hardening removes dev state and whole-app MinIO env injection, pins images, and preserves physical volumes.
- [ ] Per-environment mTLS chains, SAN/EKU, key matches, permissions, and expiry pass.
- [ ] One-network cardinality passes; atomic application/proxy CIDR sets and checksums cover actual ranges.
- [ ] API/worker have no direct public route; fixed-provider and non-HTTP dependency canaries pass.
- [ ] Alembic current/head includes `0041_openwa_binding_backfill`.
- [ ] MCP-only catalog dry-run/apply/verify passes; the row is unique and `coming_soon` with no placeholder plans.
- [ ] Workspace and Platform Admin production artifacts match the backend release.
- [ ] Positive datastore and negative gateway isolation controls pass against the same live services.
- [ ] Provider proxy, MCP proxy, and ingress have separate one-member external-route networks.
- [ ] Full mTLS, no-port, direct-public, custom parity, static topology, and public MCP canaries pass.
- [ ] Legacy supervisor handoff, finite all-service readiness, and controlled reboot preserve the exact topology.
- [ ] Every release blocker is closed with code/test/live evidence.
- [ ] Separate RC paid lifecycle, all intended surfaces, approvals, ambiguity handling, and rollback pass.
- [ ] RC sign-off names the exact release before production API/worker enablement.
- [ ] Post-RC API/worker enablement leaves Beat on its broker-only command,
  exact three-variable environment, no secrets, MCP false, and exactly one
  declared/live replica while production remains unpublished until final
  authorization.
- [ ] Monitoring, alert ownership, PKI rotation, and emergency disable are operational.
- [ ] Security-incident ownership and secret-exposure/forbidden-route containment are operational.

## Source-of-truth references

- [Detailed MCP configuration/isolation/operations runbook](./mcp-connectors.md)
- [General production deployment guide](../deployment.md)
- [Phase 13 product and protocol plan](../../.cursor/plans/mcp.plan.md)
- [Application settings and startup assertions](../../apps/api/app/core/config.py)
- [Least-privilege Celery Beat application](../../apps/api/app/worker/beat_app.py)
- [Non-mutating production Compose validator](../../apps/api/app/ops/validate_production_compose.py)
- [MCP-only catalog reconciler](../../apps/api/app/apps_catalog/reconcile_mcp.py)
- [MCP migrations](../../apps/api/migrations/versions)
- [Base Compose topology](../../infra/docker-compose.yml)
- [Production tunnel overlay](../../infra/docker-compose.tunnel.yml)
- [MCP live isolation smoke](../../infra/mcp-egress/verify-isolation.sh)
- [MCP proxy policy](../../infra/mcp-egress/proxy/squid.conf)
- [MCP proxy CIDR renderer](../../infra/mcp-egress/proxy/render_config.py)
- [Fixed-provider proxy policy](../../infra/app-egress/proxy/squid.conf)
- [PKI layout contract](../../infra/mcp-egress/pki/README.md)
- [Gateway runtime contract](../../apps/mcp_egress_gateway/README.md)
