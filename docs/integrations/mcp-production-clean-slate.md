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
- The infrastructure may finish running behind either approved Geem-only
  ingress-hold mode. Because controlled-reboot validation is deferred, this
  procedure does not release public traffic; that later release remains a
  separate gate.
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

## Geem-only ingress hold: choose exactly one mode

Keep public requests away from application origins throughout migration,
isolation checks, the deliberate unit failure, the successful normal unit
start, bounded monitoring, and the pending controlled-reboot test. Choose and
record exactly one of these modes before cutover.

### Mode A: independent external hold

Use an externally managed Cloudflare maintenance control scoped only to the
exact Geem public origins/tunnel. It must be independent of both legacy and
candidate Compose lifecycles and remain effective if either `cloudflared`
container starts, restarts, or is recreated.

A host-firewall implementation is acceptable only when reinspection proves the
legacy tunnel's egress network contains zero unrelated endpoints and exact
rules cover both the legacy egress identity/subnet and candidate
`public_egress` subnet without matching anything else. If the legacy network is
shared with any unrelated endpoint, firewall Mode A is forbidden. Never modify
or flush a shared chain.

### Mode B: exact local maintenance tunnel

Use this owner-authorized offline fallback when the host cannot administer the
public zone and a shared legacy network makes firewall Mode A unsafe. It
requires the existing locally managed Geem tunnel and DNS routes to remain
unchanged. It does not create or edit a Cloudflare tunnel, DNS record, route, or
zone policy.

The active production tunnel configuration must be byte-identical to the
approved release's
`infra/cloudflared/config.maintenance.yml`. That tracked file maps every exact
Geem hostname and `*.geem.ai` to Cloudflared's built-in `http_status:503`
service, maps the final catch-all to `http_status:404`, and contains no
application origin. Cloudflare documents `http_status` as a built-in service,
so it makes no upstream connection. The reviewed maintenance Compose overlay
also removes Cloudflared from `application_ingress`, removes its application
dependencies, and leaves it attached only to `public_egress`.

Treat the complete Mode B maintenance runtime pack as one coupled, immutable
unit, not as a config-file substitution. The active pack contains:

- the root-owned, byte-identical maintenance config at
  `/etc/geem/cloudflared/config.maintenance.yml`;
- the root-owned, byte-identical maintenance overlay at
  `/etc/geem/docker-compose.maintenance-ingress.yml`;
- the wrapper's four-file selection, in order: checked-in base, checked-in
  tunnel, deployment-owned production hardening, then maintenance overlay;
- pre-start validation with the literal `--cloudflared-mode maintenance`, plus
  unit/readiness behavior that starts Cloudflared last; and
- one checksum manifest covering that complete pack and all other startup
  inputs.

The maintenance overlay must be the final Compose file. It is what removes the
live config resource and `application_ingress`; selecting the maintenance
config without selecting that overlay is forbidden. The later live release
uses a different, equally coupled three-file runtime pack and the literal
`--cloudflared-mode live`.

Before downtime, extract the maintenance template from the exact release SHA,
install it as a staged `root:65532` mode-`0440` regular file, and require all of
the following without exposing credentials or opening a network:

- byte equality with the tracked release template;
- equality of its tunnel UUID and credentials path with the reviewed live
  locally managed tunnel;
- `cloudflared --config /etc/cloudflared/config.yml tunnel ingress validate`
  succeeds in the exact local Cloudflared image with `--network none`, the
  config mounted read-only, and no application environment;
- `cloudflared --config /etc/cloudflared/config.yml tunnel ingress rule <URL>`
  selects `http_status:503` for `geem.ai`,
  `www.geem.ai`, `api.geem.ai`, `hub.geem.ai`, `mtfm.geem.ai`, and a random
  `*.geem.ai` hostname, while an unrelated hostname selects the final
  `http_status:404`; and
- no ingress service contains `http://`, `https://`, `unix:`, `tcp:`, `ssh:`,
  `rdp:`, `smb:`, `bastion`, or `hello_world`.

The persistent pre-start script must repeat byte equality for both tracked
maintenance files, isolated Cloudflared validation, rule-selection checks,
four-file rendered-topology validation, and manifest verification on every
start. Include the active copies and tracked templates in the permanent
checksum manifest. Any divergence fails closed before Cloudflared starts.

Mode B uses the same locally managed tunnel UUID as the legacy connector, so
the transition must be serialized. Before cutover, prove through available
account inventory that no other connector replica can serve this tunnel. If
account inventory is unavailable, record the owner's explicit assertion that
this PC is the sole intentional connector host and combine it with the local
container inventory and repeated cache-busted probes before and after the
swap. Evidence of an unknown remote replica is a hard stop. Never run legacy
live-routing and candidate maintenance connectors concurrently for this tunnel.

Mode B begins with a deliberate offline transition: neutralize the legacy Geem
supervisor, set only the verified legacy Geem Cloudflared container's restart
policy to `no`, stop that exact container, and prove it cannot return. After the
remaining verified legacy Geem containers stop and the checkout reaches the
approved SHA, install and validate the complete maintenance runtime pack, then
start only candidate Cloudflared with `--no-deps` before starting any
application service. Require fresh, repeated cache-busted external probes to
return `503` for every Geem origin. Until that proof passes, no datastore,
migration, bootstrap, API, worker, frontend, or MCP service may start.

Candidate Cloudflared running under Mode B is the maintenance control, not a
traffic-release event. If it stops, Geem remains unavailable rather than
falling through to an application origin. Never restart legacy Cloudflared with
its live-routing config during rollback.

Both modes must leave `law-firm`, the host's system Cloudflared, Apache,
Ollama/`ollama-bridge`, shared networks, unrelated public hosts, and unrelated
Cloudflare accounts/zones untouched. If neither mode can be established, stop
before legacy downtime and report that single actionable blocker.

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
- `/etc/geem/cloudflared/config.yml`, `config.maintenance.yml`, and
  `credentials.json`;
- for Mode B, `/etc/geem/docker-compose.maintenance-ingress.yml` as a
  byte-identical root-owned copy of the tracked release overlay;
- `/etc/geem/mcp-egress/` with the documented CA certificate and server/client
  leaf certificate/key layout;
- `/usr/local/sbin/geem-prod-compose`;
- the selected ingress-hold artifacts: Mode A rule scripts/unit or the exact
  Mode B maintenance runtime pack and validation script;
- finite pre-start, readiness, and failed-start containment scripts; and
- a staged root-owned system `geem-stack` unit outside its live systemd path.

Do not install or enable the replacement unit during pre-staging. The single
discovered legacy system/user unit remains the controller until the offline
cutover explicitly neutralizes it. Never install or enable parallel system and
user units.

The production hardening overlay must follow the complete fragment and network
map in [`Create the production hardening
overlay`](./mcp-connectors.md#5-create-the-production-hardening-overlay), with
these clean-slate substitutions:

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

Install the Cloudflared source directory as `root:65532` mode `0750` and the
live config, maintenance config, and credentials as `root:65532` mode `0440`
so container UID/GID `65532` can read but not write them. Install the Mode B
maintenance overlay as a `root:root` mode `0444` regular file. Require the
maintenance config and overlay to be byte-identical to the tracked files at the
approved release SHA. The rendered Compose config/secret targets retain the
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
choose a new release ID; do not reuse or clear it. The sole resume exception is
an exact volume created by an earlier stopped attempt under this same approved
clean-slate operation: it may be reused only after proving it has never been
mounted by any container, has zero current references, has the recorded
driver/labels, and contains no entries. If any proof fails, preserve it and use
a new release ID.

## 3. Complete non-disruptive preflight

The persistent wrapper for the live runtime pack must select, in this order:

1. `infra/docker-compose.yml`;
2. `infra/docker-compose.tunnel.yml`; and
3. `/etc/geem/docker-compose.production-hardening.yml`.

The persistent wrapper for the Mode B maintenance runtime pack must append:

4. `/etc/geem/docker-compose.maintenance-ingress.yml`.

The Mode B overlay must be last. It cannot be an optional environment-driven
path. While the maintenance hold is selected, every wrapper invocation and
unit action must use all four files, and every topology validator invocation
must include `--cloudflared-mode maintenance`. The live three-file pack must
use `--cloudflared-mode live`. Switching between those contracts requires an
atomic replacement of the whole runtime pack described below; changing only a
Cloudflared config file is forbidden.

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

For Mode A, install, enable, and start the independent hold after those checks.
Prove the reviewed maintenance/denial response on every exact Geem origin while
legacy Cloudflared is still running. For an allowed host-firewall hold, also
prove both exact subnet rules with synthetic egress probes and packet-counter
changes that cannot reach an unrelated subnet. Keep that hold active throughout
every following step.

For Mode B, do not mutate Cloudflare or stop legacy traffic during preflight.
Stage the exact maintenance config, maintenance overlay, four-file wrapper,
pre-start mode, and validation script. Run every isolated template and wrapper
syntax check above, and record that the public offline window begins only at
section 4. These paths are not used by the legacy connector. Do not invoke the
candidate wrapper until the bytes, existing tunnel identity, and sole-connector
gate pass.

## 4. Execute the bounded offline cutover

1. Stop and disable only the exact proven legacy Geem supervisor/recreator,
   then prove that unit inactive and disabled before stopping any legacy
   container. If its stop action could select another project, neutralize only
   that exact unsafe hook first; then stop and disable the unit, prove it
   inactive and disabled, and stop the verified Geem containers directly.
2. Under Mode B, update only the verified legacy Geem Cloudflared container to
   restart policy `no`, stop that exact container first, and prove it remains
   stopped. This begins the owner-authorized public offline window. Never change
   the restart policy of, or stop, a system/foreign Cloudflared container.
3. Stop the other verified running legacy Geem container IDs in dependency-safe
   order. Under Mode A, stop the verified Geem Cloudflared ID in that same
   sequence. Leave unrelated and already exited containers untouched. Require
   all expected old Geem IDs to be stopped before continuing.
4. Under Mode A, prove from an external vantage that every exact Geem public
   origin still shows the reviewed maintenance/denial state and not a legacy or
   candidate application response. Under Mode B, require only an unavailable
   tunnel/offline response at this point; no candidate application exists yet.
5. Only now fast-forward the clean shared checkout with
   `git merge --ff-only <approved-release-sha>`. Require exact target `HEAD`, a
   clean worktree, and the expected Phase 13 artifacts. Never use reset.
6. Install the selected complete runtime pack from the already staged regular
   files. Under Mode A this is the reviewed three-file wrapper and live
   validator mode. Under Mode B, re-prove byte equality with both tracked
   maintenance files, then atomically install the four-file wrapper, maintenance
   pre-start mode, maintenance config, maintenance overlay, and provisional
   checksum manifest. Never select one Mode B artifact without the others.
7. Run `config --quiet`, then stream rendered JSON into the exact local API
   image. Do not print or save the rendered Compose JSON. This example is the
   Mode B command; Mode A must use the literal `--cloudflared-mode live` instead:

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
      --cloudflared-mode maintenance \
      --volume postgres_data="$POSTGRES_VOLUME_NAME" \
      --volume redis_data="$REDIS_VOLUME_NAME" \
      --volume qdrant_data="$QDRANT_VOLUME_NAME" \
      --volume minio_data="$MINIO_VOLUME_NAME" \
      --required-blocked-network '<each-reviewed-non-Compose-CIDR>'
```

Put the same literal validator arguments, including
`--allow-local-image-ids` and the selected `--cloudflared-mode`, in the
root-owned persistent pre-start script. Under Mode B, inspect the rendered JSON
without saving it and require Cloudflared to have only `public_egress`, no
`depends_on`, exactly one maintenance config binding, and no live config
declaration.

8. Under Mode B, repeat the isolated validation/rule checks against
   `/etc/geem/cloudflared/config.maintenance.yml`, then run exactly through the
   four-file wrapper:

```bash
sudo -n /usr/local/sbin/geem-prod-compose up -d --no-deps cloudflared
```

   Require the candidate project to contain exactly one container and require
   it to be Cloudflared. From an external vantage, use unique cache-busting
   paths and request `Cache-Control: no-cache`; require status `503` on every
   exact Geem origin and a random wildcard hostname. Stop on any application
   body, redirect to an application, non-maintenance success, or unexpected
   candidate container. Mode A leaves candidate Cloudflared stopped here.
9. Start only the new datastores, initializer, and three egress-boundary
   services.
10. Verify that each datastore is mounted to exactly one of the new named
   volumes at the canonical destination.
11. Wait boundedly for PostgreSQL, then run the one-shot migration before normal
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

Before final application acceptance—and before starting candidate Cloudflared
under Mode A; the maintenance-only Mode B instance is already running:

- require exactly one running container for every required internal
  long-running service except `cloudflared` and exactly one successful MinIO
  initializer;
- run the production topology validator again against the selected rendered
  runtime pack and its literal selected mode;
- run `infra/mcp-egress/verify-isolation.sh` through the persistent wrapper;
- prove the gateway has no host port and cannot reach application datastores;
- prove API/worker can reach their datastores and the gateway through mTLS;
- prove API, worker, Beat, and gateway have no direct public route;
- prove the MCP proxy denies private, metadata, deployment, and Compose CIDRs;
- verify all internal readiness endpoints before Mode A starts Cloudflared;
  under Mode B, the already-running maintenance connector must remain isolated
  on `public_egress` only; and
- verify the unrelated no-touch assets retain their original IDs, states,
  mounts, and network membership.

After those internal checks pass, install the already reviewed replacement
scripts and system unit at their live root-owned paths. The selected ingress
hold remains active. The wrapper, pre-start script, readiness script, unit, and
manifest must all select the same live or maintenance runtime pack. The
replacement unit's normal start must:

1. validate checksums and the rendered topology;
2. start the complete internal service list without `cloudflared`;
3. pass finite internal readiness and isolation checks;
4. start the new `cloudflared` service last; and
5. pass a bounded external probe proving Mode A's maintenance/denial state or
   Mode B's exact `503` state still hides every Geem origin.

Remove the bootstrap password first, then create the permanent root-owned
startup checksum manifest over every live input: selected wrapper and Compose
file list, deployment overlay, `/etc/geem/production.env`, local-image
manifest, tunnel files, PKI files, the selected ingress-hold scripts/unit or
complete maintenance runtime pack, pre-start/readiness/containment scripts,
final unit/drop-ins, and checked-in base/tunnel files. In Mode B it must include
both active maintenance files and both tracked source files. Preserve those
exact permanent manifest bytes in a separately named root-owned evidence file.

The replacement unit's first start must be a deliberate readiness-failure
test, not a normal start:

1. Stop the manually validated new-project containers, including candidate
   Cloudflared under Mode B, and prove zero remain running. Mode A's external
   hold must remain active. Mode B is expected to be tunnel-unavailable or
   return a Cloudflare-side `5xx` during this bounded test; it must never expose
   an application response.
2. Install one temporary drop-in that clears the normal post-start commands,
   stops `worker` after the internal start, and invokes the real readiness
   script so the start must fail.
3. Create a separately named temporary evidence manifest containing the exact
   permanent path list plus that drop-in. Atomically install those temporary
   bytes at the canonical checksum-manifest path.
4. Reload the system manager and start the unit. Require a nonzero start result,
   require candidate Cloudflared never started, and require failed-start
   containment to leave zero new-project containers running. Under Mode B,
   accept only continued tunnel unavailability/`5xx` from outside.
5. With the unit inactive, remove only the temporary drop-in and atomically
   restore the exact preserved permanent manifest bytes. Require byte equality,
   ownership/mode, and strict checksum verification before another reload.
6. Start the unit normally. Only after internal readiness succeeds may its
   final post-start action start Cloudflared through the selected wrapper.
   Require full long-running-service cardinality including exactly one
   Cloudflared. Prove Mode A still returns its reviewed maintenance/denial
   state, or Mode B has restored repeated exact `503` responses with no
   application body, for the public API, Workspace, Platform Admin, marketing,
   and wildcard origins. Rerun the unrelated-asset comparison.
7. Enable the replacement system unit only after that successful normal start.
   Require the legacy user/system unit to remain inactive and disabled.

Do not reboot the host during this cutover because that would interrupt assets
outside Geem's authorized scope. Record controlled-reboot validation as a
pending operations gate; do not claim that reboot persistence was tested and do
not release the selected ingress hold during this procedure.

Release the selected hold only in a later owner-authorized operation after the
controlled reboot succeeds, bounded monitoring is active, and the exact Geem
origins are ready. Under Mode A, remove only the exact hold rule and disable
only its exact hold unit, then immediately probe every exact and wildcard live
origin. On any failure, re-establish only that exact hold, verify the reviewed
maintenance/denial response again, and report the failed gate; record owner and
timestamp only after every live probe succeeds. Under Mode B, first stage and
validate a complete live runtime pack: tracked live config at
`/etc/geem/cloudflared/config.yml`, the
three-file wrapper without the maintenance overlay, literal
`--cloudflared-mode live` in pre-start validation, matching unit/readiness
behavior, and a new checksum manifest. Preserve the complete currently active
maintenance pack for rollback.

Then stop and temporarily disable the exact replacement `geem-stack` unit.
Require its bounded stop/containment path to stop candidate maintenance
Cloudflared first, prove the unit inactive and disabled, and leave zero project
containers running before selecting the live pack. Differing connectors for
the same tunnel UUID must never overlap. Install the whole validated live pack
while the unit is inactive, reload the system manager, and start the unit
normally. Its pre-start must validate the live pack, start all internal
services, prove readiness/isolation, and start live Cloudflared last. Require
the unit active, exact service cardinality, and every live-origin probe before
re-enabling it. A brief unavailable interval is expected because no
Cloudflare-side traffic steering is available.

If any start or origin check fails, require failed-start containment to leave
zero project containers, keep the exact unit inactive and disabled, restore
the complete preserved maintenance runtime pack—not only its config
file—reload, and start the unit normally. Its pre-start must validate with
literal `--cloudflared-mode maintenance`, restore the internal services, and
start only maintenance Cloudflared last. Require the unit active, repeated
`503` responses, and exact service cardinality before re-enabling it. Record
owner and timestamp. Until that separate release succeeds, leave the candidate
infrastructure behind the selected hold.

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
5. keep Mode A's independent hold active; under Mode B, accept only a
   fail-closed offline/`5xx` state after candidate Cloudflared stops. Keep all
   unrelated assets untouched.

Keep both old and new supervisors neutralized during containment. Reinspect the
recorded legacy mounts before any restart. If an exact legacy container has a
repository source bind, a legacy restart is permitted only from a still-clean
worktree after switching non-destructively to the recorded legacy commit with
`git switch --detach <legacy-sha>`. When no legacy container has such a bind,
leave the checkout at the target SHA. Revalidate every legacy ID and mount,
start the legacy datastores first, then application services, and start only
the legacy Geem Cloudflared container last only under Mode A. Before and after
starting that tunnel, prove the same independent hold still denies every exact
Geem public origin. Under Mode B, never restart legacy Cloudflared with its live
config; keep it restart-disabled and stopped.

If the checkout remains at the approved target SHA, revalidate the complete
four-file maintenance pack and start only candidate maintenance Cloudflared
with `--no-deps`; repeated external probes must restore exact `503`. If a
legacy source bind requires switching the checkout to `<legacy-sha>`, the
candidate wrapper is forbidden because its checked-in base and tunnel paths no
longer resolve to approved candidate bytes. In that branch, revalidate the
preserved stopped candidate maintenance container's exact full ID, image,
project/service labels, root-owned maintenance-config checksum, read-only
mounts, and sole `public_egress` network membership, then restart only that
exact container ID directly. Never recreate it through Compose at the legacy
SHA. If the preserved container is absent, running, changed, or cannot pass all
checks, leave public Geem offline. Rollback never authorizes public traffic.
Do not automatically re-enable the legacy supervisor. If those preconditions
do not pass, leave Geem offline and report the failed checkpoint; never
improvise a broad rollback against project `infra`.

## Stop conditions

Stop only for an actionable execution failure: dirty/divergent source, inability
to install Compose V2, image build/pull failure, missing required secret,
colliding new project/volume/network, ownership ambiguity that could affect an
unrelated asset, inability to establish either exact ingress-hold mode, failed
migration, failed topology/isolation/readiness gate, or unexpected mutation
outside Geem.

Do not stop merely to request another read-only inventory, disposable-data
audit, backup, restore rehearsal, legal/finance countersignature, signed image
manifest, or registry publication when the exact clean-slate authorization and
local-image mode above were supplied.
