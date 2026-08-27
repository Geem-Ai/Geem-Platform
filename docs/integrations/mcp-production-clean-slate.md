# Phase 13 MCP: owner-authorized clean-slate production-PC deployment

This is the narrow execution path for a single-host Geem installation whose
owner explicitly accepts downtime and the loss of all existing Geem
application data. It is a clean deployment onto new datastore volumes, not an
in-place data-preserving upgrade and not a shortcut for a customer-bearing
production system.

Use the detailed topology and isolation requirements in
[`mcp-connectors.md`](./mcp-connectors.md). This document overrides only the
recovery/waiver, old-volume-reuse, registry-image, and initial traffic-release
requirements called out below. Every other security boundary remains mandatory.

## Required operator authorization

Record one explicit authorization before execution:

> I own the scoped Geem installation and all of its current users and data are
> test or seed data. I authorize Geem downtime and irreversible loss of that
> application data for this clean-slate Phase 13 deployment. I do not authorize
> any change to another project, host service, or unrelated Docker asset.

That authorization permits the executor to stop only the proven legacy Geem
containers and to abandon their application state. It does not permit a broad
Docker cleanup, host reboot, or an operation against another Compose project.

## Exact exceptions to the data-preserving runbook

For this path only:

- Do not repeat the disposable-state audit, organizational countersignature, or
  restore-drill workflow. The owner authorization above is the decision.
- Do not reuse, empty, rename, or delete the legacy datastore volumes. Leave
  them quarantined and create four previously nonexistent, explicitly named
  volumes for the new release project.
- The production PC may build the Geem application images from an exact clean
  Git SHA. The final Compose model must contain no `build:` definitions and
  must refer to every locally built or pulled image by its exact local
  `sha256:<64-hex-image-id>`. Every service must also set
  `pull_policy: never` so persistent startup cannot replace or fetch an image.
- Invoke the production topology validator with
  `--allow-local-image-ids`. Without that explicit flag, its default signed
  registry-digest policy remains unchanged.
- A local image ID is valid only on the host where it was inspected. Record the
  source SHA, build inputs, source tag when applicable, and image ID in a
  root-owned release manifest. Do not run an image-prune operation while that
  release is installed.
- The legacy supervisor may be replaced by one root-owned system unit after its
  discovered system/user unit is stopped and disabled. This is a controlled
  scope migration: the old unit must never remain active or enabled in parallel.
- The infrastructure may finish running behind an independent Geem-only ingress
  hold. Because controlled-reboot validation is deferred, this procedure does
  not release public traffic; that later release remains a separate gate.
- The clean release uses `/etc/geem/production.env` for Compose interpolation
  and for API/worker `env_file`. Leave the legacy repository `.env` unchanged
  so a failed cutover can safely restart the retained legacy containers.

These exceptions do not authorize mutable tags in the final Compose model,
source bind mounts, development commands, host ports, shared public networks,
weak credentials, skipped migrations, or bypassing isolation tests.

## No-touch boundary

Before mutation, identify the exact legacy Geem containers by all of their
container ID, Compose working-directory label, config-file label, service
label, networks, and mounts. Keep an explicit deny list for every unrelated
container and service discovered on the host.

Never use any of the following during this path:

- `docker compose down` against the legacy project;
- `--remove-orphans`;
- `docker volume rm` or either volume/system prune command;
- project-name globs or name-prefix deletion;
- removal of a shared legacy network; or
- a host reboot as part of the initial cutover.

Stop legacy Geem containers only by their already verified full IDs. Do not
stop or modify an unrelated project, system Cloudflared, Apache, or a shared
network. A label collision is not ownership evidence.

## Independent Geem-only ingress hold

Before stopping legacy Geem or starting any new-project container, activate and
prove an ingress hold that is independent of both the legacy and candidate
Compose lifecycles. Scope it only to the exact Geem public origins/tunnel. It
must remain effective if either the legacy or candidate `cloudflared` container
starts, restarts, or is recreated.

The preferred mechanism is an externally managed Cloudflare maintenance
control over only those exact Geem public hosts/tunnel. A host-firewall
alternative is acceptable only when reinspection proves the legacy tunnel's
egress network contains zero unrelated endpoints and the rules cover both that
legacy egress identity/subnet and the exact candidate `public_egress` subnet
without matching anything else. Such rules must use the host's native firewall,
a dedicated forward hook that loads before Docker and cannot be reordered or
flushed by Docker, idempotent exact-rule checks, packet-counter evidence, a
fail-closed removal script reserved for the later release gate, and boot
ordering that restores the hold before either tunnel can auto-start. Do not
restart Docker, flush or replace a shared chain, or use mutable container/name
matches. If the legacy network is shared with any unrelated endpoint, the
host-firewall alternative is forbidden and the external Cloudflare control is
required. A mechanism that merely leaves either Cloudflared container stopped
is not an independent hold.

The hold must not match, stop, modify, reuse, or route through `law-firm`, the
host's system Cloudflared, Apache, Ollama/`ollama-bridge`, another Docker subnet,
or any unrelated public host. If no exact independent hold can be established
with the available host or Cloudflare authority, stop before legacy downtime
and report that single actionable blocker.

Keep the hold active through migration, isolation checks, the deliberate unit
failure, the successful normal unit start, bounded monitoring, and the pending
controlled-reboot test. Candidate Cloudflared running is not authorization to
release traffic.

## 1. Pre-stage the release while the old Geem stack is still running

1. Require a clean worktree, fetch the approved full release SHA, record the
   current legacy SHA/branch, and prove the legacy SHA is its ancestor. Do not
   move `HEAD`, switch the worktree, or edit the repository `.env` while any
   legacy Geem container is running; its source bind mounts and reload commands
   could otherwise load candidate code against the old database.
2. Install Docker Compose V2 if it is absent. Require `docker compose version`
   and the final `config --quiet` gate to pass before creating release
   containers.
3. Use a new project name, normally `geem-production`, and verify it is unused.
4. Pull the source-defined third-party images and build these Geem images from
   tracked bytes at the exact release SHA:
   - API, reused unchanged by API, worker, and Beat;
   - fixed-provider proxy;
   - MCP egress gateway;
   - MCP egress proxy;
   - Workspace production frontend;
   - Platform Admin production frontend; and
   - marketing production frontend.
5. Feed each build a `git archive` context for the exact release SHA, not the
   mutable working directory. For API, proxies, and frontends, archive the
   applicable subtree so its Dockerfile is at the context root. For the gateway,
   archive the repository root because its Dockerfile copies the shared
   outbound-policy module. This excludes untracked `.env`, `node_modules`,
   `dist`, caches, and other host files even when Git ignores them.
6. Build the three frontends with the exact production domains from the
   checked-in tunnel configuration. Use their `Dockerfile.prod` files. Build
   the gateway from the repository root because its Dockerfile copies the
   shared outbound-policy module.
7. Inspect each resulting image with `docker image inspect` and capture only
   its `.Id`. API, worker, and Beat must use one identical API image ID.
8. Create `/etc/geem/phase13-local-images.tsv` as `root:root` mode `0444` with
   explicit `release_sha`, `service`, `source_or_build`, `compose_reference`,
   and `engine_image_id` columns. Do not put secrets in this manifest. For every
   service except `minio-init`, `compose_reference` is the exact local
   `sha256:...` ID and therefore equals `engine_image_id`.
9. Before every pre-start validation, compare the rendered service image
   references bidirectionally with the manifest's `compose_reference` column.
   Inspect every `compose_reference` and require its returned `.Id` to equal the
   recorded `engine_image_id`. A missing, extra, substituted, or mistyped
   reference or ID is a build failure; do not fall back to a tag or network pull.

Every third-party service must also use its raw local image ID in the final
model. The sole exception is the MinIO initializer: its `compose_reference`
must remain the exact reviewed `quay.io/minio/mc@sha256:...` reference and
entrypoint from the source topology because the validator rejects any
substitute, including its local image ID. Pull it before freezing the manifest,
inspect that registry-digest reference, and record the resulting `.Id` as its
`engine_image_id`. Never run
`geem-prod-compose pull` after switching the final model to local IDs.

## 2. Prepare deployment-owned configuration

Create the following outside the Git checkout:

- `/etc/geem/production.env`;
- `/etc/geem/docker-compose.production-hardening.yml`;
- `/etc/geem/cloudflared/config.yml` and `credentials.json`;
- `/etc/geem/mcp-egress/` with the documented CA certificate and server/client
  leaf certificate/key layout;
- `/usr/local/sbin/geem-prod-compose`;
- the root-owned independent-ingress-hold rule scripts and system unit;
- finite pre-start, readiness, and failed-start containment scripts; and
- a staged root-owned system `geem-stack` unit outside its live systemd path.

Do not install or enable the replacement unit during pre-staging. The single
discovered legacy system/user unit remains the controller until the offline
cutover explicitly neutralizes it. Never install or enable parallel system and
user units.

The production hardening overlay must follow the complete fragment and network
map in
[`Create the production hardening overlay`](./mcp-connectors.md#5-create-the-production-hardening-overlay),
with these clean-slate substitutions:

- all `*_IMAGE` values are exact local `sha256:...` IDs captured above;
- every service sets `pull_policy: never`;
- the four external volume values are new release-owned names rather than the
  legacy names; and
- every validator command contains `--allow-local-image-ids`.

Choose nine explicit non-overlapping Docker subnets after comparing them with
all existing Docker, host, VPN, VPC, and corporate routes. Put the same complete
blocked CIDR set in the gateway and MCP proxy. Do not copy example CIDRs
without checking the host.

Generate new non-default PostgreSQL and MinIO credentials for the fresh
volumes. Preserve existing application/provider/tunnel secrets when they are
still required, and never print them. Keep `MCP_CONNECTOR_ENABLED=false` during
the cutover. Copy the legacy repository `.env` to
`/etc/geem/production.env` without printing it, merge the required values into
that external file, reject duplicate keys, and restrict it to `root:root` mode
`0600`. Do not edit the legacy repository `.env`. Provision a dedicated local
MCP CA certificate and leaf identities when no external PKI exists. Generate
and use the issuer key only in a protected tmpfs or external PKI, install the
CA certificate and leaf certificate/key pairs, then remove the issuer private
key from the production host. Never mount the issuer key into a container.
Install the gateway server key as
`root:10001` mode `0440`, the application client key as `root:root` mode
`0400`, and public certificates as mode `0644`.

Install the Cloudflared source directory as `root:65532` mode `0750` and both
source files as `root:65532` mode `0440` so container UID/GID `65532` can read
but not write them. The rendered Compose config/secret targets retain the
stricter documented modes.

For the fresh database, generate a dedicated strong
`SECRETS_ENCRYPTION_KEY` when the deployment does not already have an explicit
one. Do not silently rely on a weak or missing JWT fallback for newly encrypted
connector credentials.

Create these four volumes only after proving each exact name is absent:

- `<release-project>-postgres-data-<release-id>`;
- `<release-project>-redis-data-<release-id>`;
- `<release-project>-qdrant-data-<release-id>`; and
- `<release-project>-minio-data-<release-id>`.

Declare them `external: true` in the final overlay. If any name already exists,
choose a new release ID; do not reuse or clear it.

## 3. Complete non-disruptive preflight

The persistent wrapper must always select, in this order:

1. `infra/docker-compose.yml`;
2. `infra/docker-compose.tunnel.yml`; and
3. `/etc/geem/docker-compose.production-hardening.yml`.

It must also select the new project name,
`/etc/geem/production.env`, and the MCP profile. The overlay must reset the
base API/worker `env_file` to that exact external path; every other service
retains its documented least-privilege environment contract. The wrapper and
every clean-slate Compose command run as root so deployment secrets remain
unreadable to ordinary host processes.

While legacy Geem is still live, do not run the wrapper because its base and
tunnel paths still resolve through the legacy checkout. Instead complete only
non-disruptive gates: image builds and manifest comparison, external-file
permissions, PKI checks, Cloudflared parsing, unused new project name,
network-range selection, disk capacity, exact legacy/protected ID comparison,
and wrapper/script syntax checks. Volume-name absence is a recorded gate before
section 2 creates the volumes; at this point require the four exact new volumes
to exist with the expected driver/labels, have zero container references, and
require every legacy volume to retain its recorded state. Require every
placeholder to be resolved.

After those checks, install, enable, and start the independent Geem-only ingress
hold. Prove the reviewed maintenance/denial response on all exact Geem origins
while legacy Cloudflared is still running. For an allowed host-firewall hold,
also prove both exact subnet rules with synthetic egress probes and packet-
counter changes that cannot reach an unrelated subnet. Keep that hold active
throughout every following step.

## 4. Execute the bounded offline cutover

1. Stop and disable only the exact proven legacy Geem supervisor/recreator,
   then prove that unit inactive and disabled before stopping any legacy
   container. If its stop action could select another project, neutralize only
   that exact unsafe hook first; then stop and disable the unit, prove it
   inactive and disabled, and stop the verified Geem containers directly.
2. Stop the verified running legacy Geem container IDs in dependency-safe
   order. Leave unrelated and already exited containers untouched. Require all
   expected old Geem IDs to be stopped before continuing.
3. Before any candidate container starts, prove from an external vantage that
   every exact Geem public origin now shows the reviewed maintenance/denial
   state and not a legacy or candidate application response.
4. Only now fast-forward the clean shared checkout with
   `git merge --ff-only <approved-release-sha>`. Require exact target `HEAD`, a
   clean worktree, and the expected Phase 13 artifacts. Never use reset.
5. Run `config --quiet`, then stream rendered JSON into the exact local API
   image. Do not print or save the rendered Compose JSON:

```bash
sudo -n /usr/local/sbin/geem-prod-compose config --quiet
sudo -n /usr/local/sbin/geem-prod-compose config --format json \
  | sudo -n docker run --rm -i --pull never --network none --read-only \
      --cap-drop ALL --security-opt no-new-privileges:true \
      --entrypoint python "$GEEM_API_IMAGE" \
      -m app.ops.validate_production_compose \
      --project "$GEEM_COMPOSE_PROJECT" \
      --mcp-enabled false \
      --allow-local-image-ids \
      --ingress-service cloudflared \
      --volume postgres_data="$POSTGRES_VOLUME_NAME" \
      --volume redis_data="$REDIS_VOLUME_NAME" \
      --volume qdrant_data="$QDRANT_VOLUME_NAME" \
      --volume minio_data="$MINIO_VOLUME_NAME" \
      --required-blocked-network '<each-reviewed-non-Compose-CIDR>'
```

Put the same literal validator arguments, including
`--allow-local-image-ids`, in the root-owned persistent pre-start script.

6. Start only the new datastores, initializer, and three egress-boundary
   services.
7. Verify that each datastore is mounted to exactly one of the new named
   volumes at the canonical destination.
8. Wait boundedly for PostgreSQL, then run the one-shot migration before normal
   API startup:

```bash
sudo -n /usr/local/sbin/geem-prod-compose run --rm --no-deps \
  api alembic upgrade head
```

On the verified empty database, run the reviewed clean-install bootstrap with
non-empty `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` supplied from
the restricted environment file. Never print the password or the environment
file; the bootstrap command may identify the non-secret admin email in its
root-only execution log. Bootstrap creates the base identity, workspace, and
catalog state that Alembic and the MCP-only reconciler intentionally do not
create.

```bash
sudo -n /usr/local/sbin/geem-prod-compose run --rm --no-deps \
  api python -m app.identity.bootstrap
```

After successful bootstrap, remove `BOOTSTRAP_ADMIN_PASSWORD` from
`/etc/geem/production.env` before creating its final checksum. Preserve the
initial credential only in an operator-controlled secret location; do not
include it in the startup artifact pack.

Then run the MCP-only catalog reconciler in dry-run, apply, and verify modes.
Leave the catalog row `coming_soon`; do not create prices or publish the paid
App as part of infrastructure installation.

Start the remaining internal application services without Cloudflared, then
verify the database revision:

```bash
sudo -n /usr/local/sbin/geem-prod-compose up -d --wait --wait-timeout 300 \
  api worker beat workspace_web dashboard_web landpage_web
sudo -n /usr/local/sbin/geem-prod-compose exec -T api alembic current
sudo -n /usr/local/sbin/geem-prod-compose exec -T api alembic heads
```

The current head must include `0041_openwa_binding_backfill`.

## 5. Acceptance and persistence

Before starting Cloudflared:

- require exactly one running container for every required internal
  long-running service except `cloudflared` and exactly one successful MinIO
  initializer;
- run the production topology validator again against the live configuration;
- run `infra/mcp-egress/verify-isolation.sh` through the persistent wrapper;
- prove the gateway has no host port and cannot reach application datastores;
- prove API/worker can reach their datastores and the gateway through mTLS;
- prove API, worker, Beat, and gateway have no direct public route;
- prove the MCP proxy denies private, metadata, deployment, and Compose CIDRs;
- verify all internal readiness endpoints before starting Cloudflared; and
- verify the unrelated no-touch assets retain their original IDs, states,
  mounts, and network membership.

After those internal checks pass, install the already reviewed replacement
scripts and system unit at their live root-owned paths. The independent ingress
hold remains active. The replacement unit's normal start must:

1. validate checksums and the rendered topology;
2. start the complete internal service list without `cloudflared`;
3. pass finite internal readiness and isolation checks;
4. start the new `cloudflared` service last; and
5. pass a bounded external probe proving the expected maintenance/denial state
   still hides every Geem origin.

Remove the bootstrap password first, then create the permanent root-owned
startup checksum manifest over every live input: wrapper, overlay,
`/etc/geem/production.env`, local-image manifest, tunnel files, PKI files,
ingress-hold scripts/unit, pre-start/readiness/containment scripts, final
unit/drop-ins, and checked-in base/tunnel Compose files. Preserve those exact
permanent manifest bytes in a separately named root-owned evidence file.

The replacement unit's first start must be a deliberate readiness-failure
test, not a normal start:

1. Stop the manually validated new-project containers and prove zero remain
   running. Cloudflared has not started yet.
2. Install one temporary drop-in that clears the normal post-start commands,
   stops `worker` after the internal start, and invokes the real readiness
   script so the start must fail.
3. Create a separately named temporary evidence manifest containing the exact
   permanent path list plus that drop-in. Atomically install those temporary
   bytes at the canonical checksum-manifest path.
4. Reload the system manager and start the unit. Require a nonzero start result,
   require Cloudflared never started, and require failed-start containment to
   leave zero new-project containers running.
5. With the unit inactive, remove only the temporary drop-in and atomically
   restore the exact preserved permanent manifest bytes. Require byte equality,
   ownership/mode, and strict checksum verification before another reload.
6. Start the unit normally. Only after internal readiness succeeds may its
   final post-start action start Cloudflared. Require full long-running-service
   cardinality including exactly one Cloudflared, prove the independent hold
   still returns the reviewed maintenance/denial state for the public API,
   Workspace, Platform Admin, and marketing origins, and rerun the
   unrelated-asset comparison.
7. Enable the replacement system unit only after that successful normal start.
   Require the legacy user/system unit to remain inactive and disabled.

Do not reboot the host during this cutover because that would interrupt assets
outside Geem's authorized scope. Record controlled-reboot validation as a
pending operations gate; do not claim that reboot persistence was tested and do
not release the independent ingress hold during this procedure.

Release the independent hold only in a later owner-authorized operation after
the controlled reboot succeeds, bounded monitoring is active, and the exact
Geem origins are ready. The release action must remove only the exact hold rule,
disable only its exact hold unit, record owner and timestamp, and then verify all
four public origins. Until then, leave the candidate infrastructure running
behind the hold.

Success for this path means Phase 13 schema, catalog row, MCP gateway/proxy,
frontends, isolation, and persistent startup are installed behind the active
ingress hold with `MCP_CONNECTOR_ENABLED=false` and the App still `coming_soon`.
Runtime enablement, traffic release, plan creation, payment testing, and App
publication are separate product-release decisions.

## Failure containment

Before stopping the legacy stack, record its exact Git SHA, branch, container
IDs, service labels, mounts, and safe start order. After the legacy stop, any
failed migration, topology, isolation, readiness, or public-ingress gate must:

1. when the replacement system unit has been installed, stop and disable that
   exact unit first and prove it inactive so it cannot recreate containers;
2. stop the new Cloudflared container first when it exists;
3. enumerate new-project container IDs, revalidate their exact project label,
   and stop only those IDs without removing them;
4. leave every fresh and legacy volume intact; and
5. keep the independent ingress hold active and unrelated assets untouched.

Keep both old and new supervisors neutralized during containment. Reinspect the
recorded legacy mounts before any restart. If an exact legacy container has a
repository source bind, a legacy restart is permitted only from a still-clean
worktree after switching non-destructively to the recorded legacy commit with
`git switch --detach <legacy-sha>`. When no legacy container has such a bind,
leave the checkout at the target SHA. Revalidate every legacy ID and mount,
start the legacy datastores first, then application services, and start only
the legacy Geem Cloudflared container last. Before and after starting that
tunnel, prove the same independent hold still denies every exact Geem public
origin; rollback never authorizes public traffic. Do not automatically re-enable
the legacy supervisor. If those preconditions do not pass, leave Geem offline
and report the failed checkpoint; never improvise a broad rollback against
project `infra`.

## Stop conditions

Stop only for an actionable execution failure: dirty/divergent source, inability
to install Compose V2, image build/pull failure, missing required secret,
colliding new project/volume/network, ownership ambiguity that could affect an
unrelated asset, inability to establish the exact independent ingress hold,
failed migration, failed topology/isolation/readiness gate, or unexpected
mutation outside Geem.

Do not stop merely to request another read-only inventory, disposable-data
audit, backup, restore rehearsal, legal/finance countersignature, signed image
manifest, or registry publication when the exact clean-slate authorization and
local-image mode above were supplied.
