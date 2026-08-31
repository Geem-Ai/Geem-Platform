# Fresh Geem installation on a shared Linux server

This is the authoritative production deployment procedure for **Geem** on the
existing Linux server. It deliberately installs a new Geem release, new empty
datastore volumes, and a new Cloudflare Tunnel. It does not upgrade, recover,
or roll back an older Geem deployment.

The server also hosts the unrelated **law-firm** project. “Remove the previous
Docker deployment” therefore means remove only Docker objects that are proven
to belong to Geem. It never means uninstall Docker Engine, erase
`/var/lib/docker`, restart the host Docker daemon, or prune host-wide Docker
state. Those actions would cross the deployment boundary and can destroy or
interrupt law-firm.

The operator has accepted downtime and deletion of old Geem test/seed data.
No old Geem backup or data migration is required. That authorization does not
extend to law-firm, other applications, shared host services, other Cloudflare
zones, or Cloudflare tunnels that are not proven to serve only Geem.

The detailed MCP configuration and isolation contract is in
[MCP Connectors](./integrations/mcp-connectors.md). This guide owns the host
lifecycle: maintenance, removal, source staging, verified-image retrieval,
tunnel and DNS creation, fresh database bootstrap, persistent startup, and
traffic release.

## Outcome

A successful installation has all of the following:

- exact release source at `/opt/geem/releases/<git-sha>` with
  `/opt/geem/current` pointing to it;
- the fixed Compose project name `geem-production`;
- production configuration and secrets below `/etc/geem`, readable only by
  root except for narrowly required container-readable files;
- four new, empty, explicitly named datastore volumes;
- immutable local Docker image IDs with `pull_policy: never`;
- one new locally managed Cloudflare Tunnel and six proxied `geem.ai` DNS
  routes;
- no host-published application ports, development bind mounts, mutable image
  tags, or direct public route from the API, worker, Beat, or MCP gateway;
- exactly one root-owned systemd unit using the same validated three-file
  Compose pack on every start, with every container-level restart policy set to
  `no` so Docker cannot bypass ingress-last ordering; and
- old Geem Docker objects removed and an exclusively Geem old tunnel deleted;
  a shared/ambiguous old tunnel is preserved after its exact Geem DNS routes
  move away, with all protected law-firm identities unchanged.

MCP starts fail-closed with `MCP_CONNECTOR_ENABLED=false`. Publishing the paid
MCP App, creating signed prices, enabling connector writes, or changing the
catalog row from `coming_soon` is a separate product-release decision.

## Authorization and safety boundary

Run the installation from a root shell or from an execution session in which
`sudo -n true` succeeds for the complete maintenance window. Do not grant the
deployment user membership in the `docker` group as a substitute; Docker socket
access is effectively root access and persists after this operation.

Before changing anything, validate every reused parent and create a new,
attempt-specific root-only state directory. Never consume or overwrite an old
attempt's deletion allow-list, WAF rule ID, tunnel ID, or protected manifest:

```bash
for path in /etc/geem /etc/geem/install-attempts /etc/geem/cloudflare; do
  if [ -e "$path" ] || [ -L "$path" ]; then
    test -d "$path"
    test ! -L "$path"
    test "$(sudo stat -c '%u:%g' "$path")" = 0:0
    test -z "$(sudo find "$path" -maxdepth 0 -perm /022 -print -quit)"
  fi
done
sudo install -d -o root -g root -m 0711 /etc/geem
sudo install -d -o root -g root -m 0700 /etc/geem/install-attempts
sudo install -d -o root -g root -m 0700 /etc/geem/cloudflare
attempt_id="fresh-$(date -u +%Y%m%d%H%M%S)-$(openssl rand -hex 8)"
GEEM_INSTALL_STATE="/etc/geem/install-attempts/$attempt_id"
printf '%s\n' "$GEEM_INSTALL_STATE" \
  | grep -Eq '^/etc/geem/install-attempts/fresh-[0-9]{14}-[0-9a-f]{16}$'
test ! -e "$GEEM_INSTALL_STATE"
test ! -L "$GEEM_INSTALL_STATE"
sudo install -d -o root -g root -m 0700 "$GEEM_INSTALL_STATE"
test "$(sudo readlink -f "$GEEM_INSTALL_STATE")" = "$GEEM_INSTALL_STATE"
test ! -e /etc/geem/.current-install-attempt.next
test ! -L /etc/geem/.current-install-attempt.next
sudo sh -c 'set -euC; umask 077; printf "%s\n" "$1" > "$2"' sh \
  "$GEEM_INSTALL_STATE" /etc/geem/.current-install-attempt.next
test -f /etc/geem/.current-install-attempt.next
test ! -L /etc/geem/.current-install-attempt.next
sudo chown root:root /etc/geem/.current-install-attempt.next
sudo chmod 0400 /etc/geem/.current-install-attempt.next
test "$(sudo stat -c '%u:%g:%a' \
  /etc/geem/.current-install-attempt.next)" = 0:0:400
sudo mv -Tf /etc/geem/.current-install-attempt.next \
  /etc/geem/current-install-attempt
```

Mode `0711` on `/etc/geem` permits the two fixed container UIDs to traverse to
their individually protected bind-mounted files without allowing directory
listing. Sensitive child directories and files retain the stricter modes
specified below.

At the start of every later shell, reload `GEEM_INSTALL_STATE` from
`/etc/geem/current-install-attempt`; require exactly one line, the
`/etc/geem/install-attempts/fresh-...` prefix, a non-symlink directory owned by
`root:root` mode `0700`, and a value identical to the approved attempt. Use
`${GEEM_INSTALL_STATE:?}` before every write or deletion. Every later reference
to the attempt state means that one directory. Record exact
identifiers, not names matched by a glob, below it. Every destructive command
must consume an exact identifier from that attempt's recorded allow-list and
re-check its ownership immediately before acting. If the re-check differs,
stop. Previous `/etc/geem/install-state` or `install-attempts/*` content is
retired evidence only and is never current authority.

Use this fail-closed reload before a later attempt-state operation:

```bash
test -f /etc/geem/current-install-attempt
test ! -L /etc/geem/current-install-attempt
test "$(sudo stat -c '%u:%g:%a' \
  /etc/geem/current-install-attempt)" = 0:0:400
GEEM_INSTALL_STATE="$(sudo sed -n '1p' /etc/geem/current-install-attempt)"
test "$(sudo awk 'END { print NR }' \
  /etc/geem/current-install-attempt)" -eq 1
printf '%s\n' "${GEEM_INSTALL_STATE:?}" \
  | grep -Eq '^/etc/geem/install-attempts/fresh-[0-9]{14}-[0-9a-f]{16}$'
test -d "$GEEM_INSTALL_STATE"
test ! -L "$GEEM_INSTALL_STATE"
test "$(sudo readlink -f "$GEEM_INSTALL_STATE")" = "$GEEM_INSTALL_STATE"
test "$(sudo stat -c '%u:%g:%a' "$GEEM_INSTALL_STATE")" = 0:0:700
```

The following commands are forbidden on this shared server:

```text
apt remove docker*                 # or dnf/yum/pacman equivalents
rm -rf /var/lib/docker
docker system prune
docker container prune
docker image prune
docker network prune
docker volume prune
docker compose down                # against an old/ambiguous project
systemctl restart docker
```

Do not use an unresolved shell glob, substring match, project-name guess, or
repository path alone as deletion authority. Do not touch `infra_default` if
law-firm or any unknown container is attached to it.

## Required authority and inputs

The installation must have these inputs before old Geem is stopped:

1. A full, immutable Git commit SHA that is already green in CI and is a
   descendant of the intended release line. A branch name or `latest` is not a
   deployment identity.
2. Read access to the Git repository, its Actions run artifacts, and the eight
   GHCR production packages. The exact SHA must have one explicitly selected,
   successful `Production image publication` run.
3. An `x86_64`/`linux/amd64` host matching the published and tested image
   platform.
4. Docker Engine and Docker Compose V2 with support for `!reset` and
   `!override`. Preserve a working shared daemon. Install or update Docker only
   if it is absent and no unrelated Docker workload can be interrupted.
5. A root-owned production environment derived from `.env.example`.
6. The independent `geem.ai` WAF credential described below.
7. Separate Cloudflare Tunnel and DNS lifecycle authority, or a root-only
   Cloudflare account certificate for the account that owns `geem.ai`.
8. A reviewed set of eleven non-overlapping Docker CIDRs that collide with no
   host, VPN, VPC, law-firm, or other Docker network.

### Cloudflare maintenance credential

The existing credential is:

```text
/etc/geem/cloudflare/maintenance.json
```

Its expected JSON shape is:

```json
{"api_token":"REDACTED"}
```

Require `root:root` ownership and mode `0600`. Never print the file, place its
token on a command line, write it to a log, or copy it into the repository.

The declared permissions are sufficient for the independent maintenance hold:

- `Zone -> Zone -> Read`;
- `Zone -> WAF -> Edit`; and
- zone resource restricted to `geem.ai`.

They are **not** sufficient to list, delete, or create Cloudflare Tunnels, and
they cannot update DNS. Keep this WAF token independent from tunnel lifecycle
authority.

### Cloudflare tunnel lifecycle credential

To delete the old Geem tunnel, create a new one, and repoint DNS, provision a
second least-privilege token at:

```text
/etc/geem/cloudflare/tunnel-lifecycle.json
```

Expected shape:

```json
{
  "api_token": "REDACTED",
  "account_id": "REDACTED"
}
```

It needs:

- `Account -> Cloudflare Tunnel -> Edit`, restricted to the owning account;
- `Zone -> DNS -> Edit`, restricted to `geem.ai`;
- `Zone -> Zone -> Read`, restricted to `geem.ai`; and
- optionally `Account -> Account Settings -> Read` when account discovery is
  required.

Require `root:root` mode `0600` and apply the same no-output rule as the WAF
token. A root-only `cert.pem` produced by `cloudflared tunnel login` can perform
the lifecycle work instead, but it is account-wide and is therefore less
preferred. A tunnel credential JSON can only run its one tunnel; it cannot
list, create, route, or delete tunnels.

If neither the lifecycle token nor the correct account certificate is present,
the fresh installation is blocked before old tunnel deletion. The WAF token
does not fill that gap.

## Fixed production identities

Use these identities exactly:

| Purpose | Identity |
|---|---|
| Compose project | `geem-production` |
| Release root | `/opt/geem/releases/<full-sha>` |
| Active release link | `/opt/geem/current` |
| Environment | `/etc/geem/production.env` |
| Hardening overlay | `/etc/geem/docker-compose.production-hardening.yml` |
| Compose wrapper | `/usr/local/sbin/geem-prod-compose` |
| Cloudflared config | `/etc/geem/cloudflared/config.yml` |
| Tunnel credential | `/etc/geem/cloudflared/credentials.json` |
| MCP PKI | `/etc/geem/mcp-egress/pki` |
| Start manifest | `/etc/geem/start-artifacts.sha256` |
| Release identity | `/etc/geem/release-sha` |
| Installation identity | `/etc/geem/install-id` and label `com.geem.production.install` |
| Current install attempt | `/etc/geem/current-install-attempt` -> one new `/etc/geem/install-attempts/fresh-*` directory |
| Image manifest | `/etc/geem/image-manifest` |
| API image ID file | `/etc/geem/api-image-id` |
| Validator arguments | `/etc/geem/production-validator.args` |
| systemd unit | `geem-production.service` |

The production Compose pack is always, in this order:

1. `/opt/geem/current/infra/docker-compose.yml`;
2. `/opt/geem/current/infra/docker-compose.tunnel.yml`; and
3. `/etc/geem/docker-compose.production-hardening.yml`.

There is no production maintenance Compose overlay. Cloudflare WAF is the
independent maintenance control, so the runtime pack is identical before and
after public release.

## 1. Record protected assets once

Capture enough read-only evidence to prevent a Geem deletion from reaching
law-firm. This is a bounded inventory, not an upgrade or recovery audit.

Record, at minimum:

- all running and stopped container IDs, their full Compose project/service
  labels, restart policy, image ID, mounts, and network attachments;
- all volume names, drivers, labels, mountpoints, and every referencing
  container ID;
- all network IDs, labels, CIDRs, and endpoint container IDs;
- exact system and user units, cron jobs, timers, or process supervisors that
  can recreate a Geem container;
- current Geem tunnel UUID from its credential file, its Cloudflare name,
  current connector IDs, and exact DNS record IDs/targets; and
- a protected manifest containing every law-firm and unknown container,
  volume, network, unit, and tunnel identity.

An object is removable only when positive evidence proves it is Geem-owned.
Compose labels are primary evidence. For old unlabeled objects, require a
combination of exact container configuration, Geem-only mount/source path,
image provenance, network membership, and public routing. Ambiguous means
protected.

Store the approved Geem deletion allow-list and protected manifest under the
exact attempt-specific `$GEEM_INSTALL_STATE`. Do not repeatedly rediscover or
broaden them later.
At each mutation boundary, compare current exact IDs to these recorded files.

## 2. Activate the independent WAF maintenance hold

Verify the WAF token through the Cloudflare token-verification endpoint, resolve
exactly one active zone named `geem.ai`, and obtain the zone ID. Abort if the
token resolves another zone or more than one candidate.

Use the zone Rulesets API and the
`http_request_firewall_custom` phase entry point. Add one rule; never replace
the ruleset or alter unrelated rules. The rule contract is:

```text
description: Geem fresh-install maintenance hold
expression:  (http.host in {"geem.ai" "www.geem.ai" "api.geem.ai" "hub.geem.ai" "mtfm.geem.ai"} or (ends_with(http.host, ".geem.ai") and not (http.host in {<verified-exact-protected-hostnames>})))
action:      block
response:    HTTP 403 text/plain "Geem maintenance"
```

Replace the placeholder with a space-separated quoted set; when the verified
set is empty, remove the entire `and not (...)` clause. Before creating the
rule, enumerate every exact DNS hostname in the `geem.ai` zone. Exclude a
non-production hostname only when an exact protected DNS record currently
shadows the wildcard and does not target the old/new production tunnel. Known
candidates are `app-uat`, `api-uat`, `landpage-uat`, and `admin-uat`, but never
exclude one merely because it is on that list. Add every other verified
protected hostname, evaluate the final expression against the complete recorded
hostname list, and stop if an active protected name would match.

Cloudflare custom block responses accept a 4xx status, not 503. If the zone
plan does not permit a custom response body, use Cloudflare's ordinary block
response and retain the same expression. Record the exact ruleset ID and new
rule ID in `$GEEM_INSTALL_STATE/cloudflare-waf.json`. Never find a rule by
description for deletion after it has been created.

From outside the production host, use unique cache-busting paths and evaluate
the six required names against the DNS inventory:

- `geem.ai`;
- `www.geem.ai`;
- `api.geem.ai`;
- `hub.geem.ai`;
- `mtfm.geem.ai`; and
- one random, nonexistent `<label>.geem.ai` hostname.

Every name currently covered by a proxied exact or wildcard record must return
the 403 maintenance/block response. A required name recorded as truly absent
may instead return NXDOMAIN/no route; record that safe absence. An existing
unproxied production record is not protected by WAF: change that exact
Geem-owned record to proxied under the lifecycle authority and require 403, or
stop. Never accept a reachable origin response as maintenance proof.

Do not stop old Geem until every currently routed production name is held by
WAF and every recorded absent name has no route. Later, after all six records
target the new tunnel, all six plus the random wildcard must return 403 before
the hold can be released. Keep the exact rule active through removal,
installation, tunnel replacement, migrations, bootstrap, persistent-start
testing, and final internal acceptance.
If the UAT names are active, prove they remain outside this rule. Do not use a
zone-wide “block every `*.geem.ai`” expression that also takes UAT offline.

## 3. Remove the previous Geem deployment

### Neutralize recreators

For each positively identified Geem systemd unit, user unit, timer, cron job, or
other supervisor:

1. inspect its current definition again;
2. prove it starts only approved Geem container IDs/project paths;
3. stop and disable that exact recreator; and
4. prove it is inactive and cannot restart the containers.

Do not disable a shared supervisor or anything that mentions law-firm. Retired
historical `geem-stack` units are not valid production units and must not be
reinstalled from an old checkout.

### Remove exact Geem containers

For every container ID in the approved Geem allow-list, re-check the complete
64-character ID and ownership labels. Set only that container's restart policy
to `no`, stop Cloudflared first, then stop application workers, frontends, API,
and datastores. Remove only those exact container IDs.

Do not use `docker compose down` for the old deployment: its project identity
may collide with `infra_default` or another application. Do not remove an
image; image layers can be shared and a fresh install does not require image
cleanup.

### Remove old Geem volumes and networks

Old Geem data is disposable, but a volume may be removed only when:

- its exact name/ID is in the approved Geem allow-list;
- no remaining container references it;
- no protected manifest entry uses its mountpoint; and
- its labels and recorded destination still match.

Remove every approved old Geem volume by exact name (the normal datastore set
is PostgreSQL, Redis, Qdrant, and MinIO). Preserve every ambiguous, law-firm, or
unknown volume.

Remove a Geem network only when its exact ID is approved and it has zero
remaining endpoints. Never remove `infra_default` while any law-firm or unknown
endpoint is attached. A shared or ambiguous network remains in place; the new
Geem install uses nine newly named networks and does not need it.

### Delete the old Geem Cloudflare Tunnel

Stop all connectors for the approved old Geem tunnel before deleting its
Cloudflare resource. Through the lifecycle credential:

1. resolve the exact old UUID from the recorded credential and Cloudflare
   account inventory;
2. prove every active connector is stopped;
3. prove its reviewed routes are limited to the Geem production hostnames;
4. record every exact production `geem.ai` DNS record ID currently targeting
   it and record which required fresh-install names are absent; and
5. delete only that exact tunnel UUID.

An unknown connector, non-Geem route, account mismatch, or unapproved tunnel ID
is a hard stop for tunnel deletion, but not for the rest of the fresh Geem
installation. Preserve that tunnel, record it as protected, and later repoint
only the exact Geem DNS record IDs to the new tunnel. Never bulk-delete tunnels.
The DNS records and tunnel are independent; keep their exact IDs for in-place
update to the new tunnel target rather than deleting unrelated DNS. A preserved
shared tunnel may be retired only in a separate, independently authorized task
after every non-Geem route has moved.

Recompare the protected manifest. Law-firm containers, mounts, networks,
services, and public routes must be unchanged. At this point Geem is expected
to be offline behind WAF.

After every approved old-Geem container is removed, require
`docker ps -aq --filter label=com.docker.compose.project=geem-production` to
return nothing. A protected/law-firm/unknown container already carrying that
fixed project label blocks deployment; do not rely on its service name or let
the new systemd containment select it.

## 4. Stage the exact fresh release

Fetch the approved full SHA without moving or reusing an old production
checkout. Create `/opt/geem/releases/<full-sha>`, check out that commit in
detached mode, and require:

- `git rev-parse HEAD` equals the approved full SHA;
- the worktree is clean;
- the SHA is available from the trusted Geem remote; and
- the expected deployment, Compose, validator, PKI, and systemd files exist.

Create `/opt/geem/current` as a symlink to that immutable directory only after
those checks pass. Do not run `git pull` in a live release directory and do not
deploy a branch tip that can move during the operation.

Stage and freeze the tree from the root maintenance shell. Create `/opt/geem`
and `/opt/geem/releases` as `root:root 0755`; create the exact release directory
as root; fetch and detach the full SHA there; then recursively set that one
validated release tree to `root:root` and remove every group/world write bit.
Reject any symlink in the `/opt/geem` or `/opt/geem/releases` path. Create a
root-owned `.current.next` symlink and atomically rename it to `current`; refuse
to replace a real directory. Recheck that both parent directories are
`root:root 0755`, the final link resolves to the exact release directory, and
the release has no group/world-writable entry. This prevents an unprivileged
user from swapping source between preflight and Compose execution.

One acceptable command shape is:

```bash
for path in /opt/geem /opt/geem/releases; do
  if [ -e "$path" ] || [ -L "$path" ]; then
    test -d "$path"
    test ! -L "$path"
    test "$(sudo stat -c '%u:%g' "$path")" = 0:0
    test -z "$(sudo find "$path" -maxdepth 0 -perm /022 -print -quit)"
  fi
done
sudo install -d -o root -g root -m 0755 /opt/geem /opt/geem/releases
: "${APPROVED_RELEASE_SHA:?set the explicitly approved full release SHA}"
release_sha="$APPROVED_RELEASE_SHA"
printf '%s\n' "$release_sha" | grep -Eq '^[0-9a-f]{40}$'
release_dir="/opt/geem/releases/$release_sha"
case "$release_dir" in /opt/geem/releases/[0-9a-f][0-9a-f]*) ;; *) exit 1 ;; esac
test ! -e "$release_dir"
sudo git clone --no-checkout https://github.com/Geem-Ai/Geem-Platform.git \
  "$release_dir"
sudo git -C "$release_dir" fetch --no-tags origin "$release_sha"
sudo git -C "$release_dir" checkout --detach "$release_sha"
test "$(sudo git -C "$release_dir" rev-parse HEAD)" = "$release_sha"
test -z "$(sudo git -C "$release_dir" status --porcelain)"
sudo chown -R root:root "$release_dir"
sudo find "$release_dir" -xdev -perm /022 -exec chmod go-w -- {} +
test ! -e /opt/geem/.current.next
test ! -L /opt/geem/.current.next
sudo ln -s "$release_dir" /opt/geem/.current.next
test ! -e /opt/geem/current || test -L /opt/geem/current
sudo mv -Tf /opt/geem/.current.next /opt/geem/current
test "$(sudo readlink -f /opt/geem/current)" = "$release_dir"
test -z "$(sudo find "$release_dir" -xdev -perm /022 -print -quit)"
test ! -e /etc/geem/.release-sha.next
test ! -L /etc/geem/.release-sha.next
sudo sh -c 'set -euC; umask 077; printf "%s\n" "$1" > "$2"' sh \
  "$release_sha" /etc/geem/.release-sha.next
test -f /etc/geem/.release-sha.next
test ! -L /etc/geem/.release-sha.next
sudo chown root:root /etc/geem/.release-sha.next
sudo chmod 0400 /etc/geem/.release-sha.next
test "$(sudo stat -c '%u:%g:%a' /etc/geem/.release-sha.next)" = 0:0:400
sudo mv -Tf /etc/geem/.release-sha.next /etc/geem/release-sha
test "$(sudo sed -n '1p' /etc/geem/release-sha)" = "$release_sha"
test "$(sudo awk 'END { print NR }' /etc/geem/release-sha)" -eq 1
```

The abbreviated release-path pattern above is only an additional shell guard;
the preceding full-SHA validation and the post-check against `release-sha` are
authoritative.

Preserve the repository's tracked modes: `0644` for both Compose files and the
static deny list, and `0755` for `verify-isolation.sh`. The persistent preflight
checks these files, owners, modes, release identity, and symlink target on every
managed start.

The command atomically writes the exact 40-character lowercase SHA plus one
newline to `/etc/geem/release-sha`, owned by `root:root` and mode `0400` only
after the release tree and symlink pass. Require
`readlink -f /opt/geem/current` to equal
`/opt/geem/releases/$(cat /etc/geem/release-sha)`; the persistent preflight
enforces the same identity on every start.

## 5. Prepare production configuration and secrets

Create `/etc/geem/production.env` from the selected release's `.env.example`,
then replace every development/default value. Keep `root:root` mode `0600`.
At minimum, verify:

```dotenv
APP_ENV=production
APP_NAME=Geem
APP_URL=https://api.geem.ai
CORS_ORIGINS=https://hub.geem.ai,https://mtfm.geem.ai
AUTH_REQUIRED=true
LEGACY_MVP_WRITES_ENABLED=false
APP_ROOT_DOMAIN=geem.ai
APP_ADMIN_HOST=mtfm.geem.ai
TRUST_PROXY_HEADERS=true

DATABASE_URL=postgresql+psycopg://<user>:<encoded-password>@postgres:5432/<db>
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
MINIO_ENDPOINT=minio:9000
MINIO_SECURE=false

MCP_CONNECTOR_ENABLED=false
GEEM_INSTALL_ID=geem-<full-release-sha>-<14-digit-utc-timestamp>
MCP_EGRESS_GATEWAY_URL=https://mcp-egress-gateway:8443
MCP_EGRESS_PROXY_URL=http://mcp-egress-proxy:3128
MCP_EGRESS_PKI_DIR=/etc/geem/mcp-egress/pki
MCP_ALLOW_PRIVATE_EGRESS=false
MCP_PROXY_REQUIRE_BLOCKED_NETWORKS=true

EMAIL_PROVIDER=smtp
EMAIL_VERIFICATION_REQUIRED=true
SMTP_HOST=mail-relay
SMTP_PORT=25
SMTP_USE_TLS=false
SMTP_ALLOW_PLAINTEXT_RELAY=true
SMTP_FROM_EMAIL=<envelope-sender>
MAIL_RELAY_UPSTREAM_HOST=<external-submission-host>
MAIL_RELAY_UPSTREAM_PORT=587
MAIL_RELAY_UPSTREAM_USERNAME=<mailbox-user>
MAIL_RELAY_UPSTREAM_PASSWORD=<mailbox-password>
MAIL_RELAY_UPSTREAM_FROM=<envelope-sender>
```

The application tier has no mail egress route, so it submits in the clear to the
`mail-relay` service on an internal network and the relay performs the only
credentialed STARTTLS hop upstream. Keep `SMTP_USERNAME` and `SMTP_PASSWORD`
empty: the mailbox credential belongs to `MAIL_RELAY_UPSTREAM_*` so only the
relay holds it. `SMTP_ALLOW_PLAINTEXT_RELAY` is accepted only for a bare Compose
service name; a host with a dot or a port must still negotiate TLS itself.
Verification and reset mail is delivered by the Celery worker, so registration
does not fail when the upstream submission host is unavailable.

Generate independent, strong values for JWT, PostgreSQL, MinIO, bootstrap admin,
credential encryption, OAuth/session signing, and every enabled provider. Do
not reuse the old Geem secrets and do not copy values from law-firm. Percent-
encode reserved password characters in `DATABASE_URL`.

Leave `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` present only until
the one-time bootstrap succeeds. Never print the file or render Compose JSON to
disk/logs.

### Select network CIDRs

Inspect host routes and every Docker network, including law-firm. Select eleven
unused, non-overlapping CIDRs and set:

```text
APPLICATION_DATA_SUBNET
APPLICATION_BROKER_SUBNET
APPLICATION_INGRESS_SUBNET
APPLICATION_PROVIDER_CONTROL_SUBNET
APPLICATION_PROVIDER_EGRESS_SUBNET
MAIL_RELAY_CONTROL_SUBNET
MAIL_RELAY_EGRESS_SUBNET
MCP_EGRESS_CONTROL_SUBNET
MCP_PROXY_CONTROL_SUBNET
MCP_PUBLIC_EGRESS_SUBNET
PUBLIC_EGRESS_SUBNET
```

Do not copy example CIDRs without checking the actual host. Add host/VPN/VPC
and other deployment CIDRs to `MCP_EGRESS_BLOCKED_NETWORKS` and to the
preflight validator's repeated required-blocked-network arguments.

The hardening overlay also requires `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, and `MINIO_BUCKET`.
After image construction, set these image variables to their reviewed raw
local IDs:

```text
POSTGRES_IMAGE
REDIS_IMAGE
QDRANT_IMAGE
MINIO_IMAGE
GEEM_API_IMAGE
APP_EGRESS_PROXY_IMAGE
MAIL_RELAY_IMAGE
MCP_EGRESS_GATEWAY_IMAGE
MCP_EGRESS_PROXY_IMAGE
WORKSPACE_WEB_IMAGE
DASHBOARD_WEB_IMAGE
LANDPAGE_WEB_IMAGE
CLOUDFLARED_IMAGE
```

### Create new volumes

Choose a unique installation ID derived from the release SHA plus a timestamp.
It must match `^[a-z0-9][a-z0-9_.-]{7,127}$`. Write exactly that value plus one
newline to `/etc/geem/install-id` as `root:root` mode `0400`, and set the same
value as `GEEM_INSTALL_ID` in `production.env`. The hardening overlay applies
`com.geem.production.install=<exact-id>` to every Geem container; do not reuse
the ID for another attempt. Create four previously nonexistent volumes with
Geem/install labels and set:

```text
POSTGRES_VOLUME_NAME
REDIS_VOLUME_NAME
QDRANT_VOLUME_NAME
MINIO_VOLUME_NAME
```

Each physical name must be unique to this install. If any candidate name
already exists, choose a new installation ID. Do not empty or reuse it. Before
first start, require zero container references and an empty mountpoint for all
four.

### Create MCP PKI

Follow [`infra/mcp-egress/pki/README.md`](../infra/mcp-egress/pki/README.md)
to create a new private CA, server identity, and API/worker client identity at
`/etc/geem/mcp-egress/pki`. Use the documented ownership and file modes. Remove
the CA private key from the production server after certificates are issued and
verified. Because local Compose file-backed secrets retain host ownership,
prove host UID/GID `10001` is not assigned to or usable by law-firm or another
host principal before installing the gateway key. Apply the same collision
check to Cloudflared UID/GID `65532`. A collision is a source/configuration
blocker, not permission to make a private key world-readable or readable by an
unapproved group.

### Install the hardening overlay

Copy the selected release's
`infra/docker-compose.production-hardening.example.yml` byte-for-byte to
`/etc/geem/docker-compose.production-hardening.yml`, owned by root and mode
`0600`. Supply all required substitutions through `production.env`; do not edit
the reviewed topology to resolve a host-specific value. Require every
long-running service to render `restart: "no"` and `minio-init` to have no
restart policy. `geem-production.service` is the sole lifecycle owner; Docker
must never auto-restore Cloudflared before preflight and internal verification.

## 6. Retrieve and pin the CI-verified images

Production never builds Geem images. Python and operating-system package
repositories are mutable, so rebuilding a green source SHA later would not
prove that production received the bytes tested by CI. The
`Production image publication` workflow runs only after the exact main-branch
release gate succeeds. It builds eight `linux/amd64` images once, pushes them
to GHCR, exercises the exact pushed digests, and publishes an artifact mapping
the source SHA and workflow run to those digests.

Require `uname -m` to return `x86_64`. A different architecture needs a new
reviewed publication target and exact-platform tests; do not build locally as a
workaround.

First record every protected law-firm/unknown `RepoTag -> image ID` mapping.
That mapping must be byte-for-byte identical after image retrieval. Do not
"restore" a changed tag: any change is a failed maintenance operation.

Through the authenticated GitHub API, find successful runs of
`.github/workflows/production-images.yml` whose `headSha` exactly equals
`/etc/geem/release-sha`. Select one explicit run ID; never select "latest" or a
branch name. Confirm that its triggering release-gate run was also successful,
was a `push` from this repository, and used the same full SHA. Record both run
IDs in the installation evidence.

Download from that run the one artifact named
`geem-production-images-<full-sha>-run-<run-id>-<attempt>`. Verify
`manifest.json.sha256` with `sha256sum --check`, then require all of these
properties with `jq -e`:

- `schema_version` is `1`;
- `source_sha` is the exact release SHA;
- `publication_run_id` and `publication_run_attempt` identify the selected
  successful run;
- `source_gate_run_id` identifies its successful upstream release gate;
- `platform` is exactly `linux/amd64`;
- `images` contains exactly `api`, `app_egress_proxy`, `mail_relay`,
  `mcp_egress_gateway`, `mcp_egress_proxy`, `workspace_web`,
  `dashboard_web`, and `landpage_web`; and
- `build_bases` exactly matches the five reviewed direct `linux/amd64`
  platform-manifest references in
  `infra/images/production-build-bases.env`;
- `runtime_images` exactly matches the five reviewed direct `linux/amd64`
  Postgres, Redis, Qdrant, MinIO, and Cloudflared references in
  `infra/images/production-runtime-images.env`; and
- every `images` value is an expected lowercase `ghcr.io/geem-ai/...`
  repository plus one `@sha256:<64-lowercase-hex>` digest; build/runtime lock
  values use their reviewed upstream repositories and the same digest shape.

Use a root-only GitHub credential with read access to this repository's Actions
artifacts and GHCR packages. Pass the token to `docker login ghcr.io` through
standard input; never place it on a command line or in the repository. Pull
each of the eight `images` values and five `runtime_images` values by its
complete digest reference. Do not resolve or pull their human-readable source
tags. For each reference, record both the registry digest and the raw local
image ID returned by:

```bash
sudo docker image inspect --format '{{.Id}}' \
  'ghcr.io/geem-ai/<expected-package>@sha256:<approved-64-hex-digest>'
```

Set `GEEM_API_IMAGE`, `APP_EGRESS_PROXY_IMAGE`, `MAIL_RELAY_IMAGE`,
`MCP_EGRESS_GATEWAY_IMAGE`, `MCP_EGRESS_PROXY_IMAGE`,
`WORKSPACE_WEB_IMAGE`, `DASHBOARD_WEB_IMAGE`, and `LANDPAGE_WEB_IMAGE` to
those raw IDs. The API image is reused unchanged by API, worker, and Beat.

Set `POSTGRES_IMAGE`, `REDIS_IMAGE`, `QDRANT_IMAGE`, `MINIO_IMAGE`, and
`CLOUDFLARED_IMAGE` to the raw local IDs corresponding to the five locked
`runtime_images` values. Pull the fixed `minio-init` reference
`quay.io/minio/mc@sha256:993e8c454a7ec632923f7e3e61adf1d473261da6354cefd641aedd33a2cfe112`
the same way; its reviewed registry digest remains in the overlay.

Never run a production-host `docker build`, `docker compose build`, Buildx
build, mutable-tag pull, retag, Compose `pull`, or host-wide cache/image prune.
The production workflow uses the validator's local-image mode: configurable
images are raw local IDs, the fixed MinIO client remains a registry digest, all
services use `pull_policy: never`, and every referenced image must already
exist locally.

Create `/etc/geem/image-manifest` as canonical JSON owned by `root:root` mode
`0400`. It must preserve the downloaded publication identity and eight registry
digests, five build-base identities, and five third-party runtime references;
add the exact local IDs for all deployable images. Compare it bidirectionally with the rendered
Compose model: every service appears exactly once, the API/worker/Beat mapping
is identical, no unrecorded ID appears, and each raw ID still resolves locally.
Recompare the protected law-firm image mapping and require equality.

## 7. Create the new Cloudflare Tunnel and DNS routes

Create one new **locally managed** tunnel through the lifecycle credential,
using a unique name such as `geem-production-<short-sha>-<utc-timestamp>` and a
new 32-byte tunnel secret. Keep API request bodies containing the secret in
root-only temporary files, never command arguments or logs.

Use `POST /accounts/<account-id>/cfd_tunnel` with the exact fields
`name`, `config_src: "local"`, and `tunnel_secret`. Reject a response whose
account ID, returned name, tunnel UUID, or `config_src` differs from the
request. A remotely managed (`config_src: "cloudflare"`) tunnel is not
compatible with the reviewed host-owned ingress configuration.

Install the resulting tunnel credential at
`/etc/geem/cloudflared/credentials.json` with exactly:

```json
{
  "AccountTag": "<owning-account-id>",
  "TunnelSecret": "<base64-secret>",
  "TunnelID": "<new-uuid>"
}
```

Render `infra/cloudflared/config.yml` to
`/etc/geem/cloudflared/config.yml` by replacing only
`REPLACE_WITH_NEW_TUNNEL_UUID` with that exact UUID. Reject any remaining
`REPLACE_` marker or the recorded old tunnel UUID. Preserve the checked-in
hostname order and final `http_status:404` fallback.

Preserve the four exact UAT `http_status:404` rules before the production
wildcard. An existing exact UAT DNS record takes precedence and stays on its
protected target. If that exact record is absent, wildcard DNS can reach the
new tunnel, but Cloudflared must select the exact 404 rule rather than the
production Workspace origin. Do not create or repoint UAT DNS as part of this
installation.

Update only the recorded production DNS record IDs so these proxied CNAMEs
target `<new-uuid>.cfargotunnel.com`. For a required name with no exact existing
record, first prove that absence through the zone API, then create that one
record. Do not replace an existing non-Geem record:

| DNS name | Origin selected by Cloudflared |
|---|---|
| `geem.ai` | `http://landpage_web:80` |
| `www.geem.ai` | `http://landpage_web:80` |
| `api.geem.ai` | `http://api:8000` |
| `hub.geem.ai` | `http://workspace_web:80` |
| `mtfm.geem.ai` | `http://dashboard_web:80` |
| `*.geem.ai` | `http://workspace_web:80` |

Do not touch UAT records or any other zone. Verify every exact DNS record ID,
type, name, proxied flag, and new target through the API. Validate the rendered
Cloudflared ingress config with the exact pinned Cloudflared image on
`--network none`, and prove rule selection for all five exact hosts, a random
tenant hostname, all four reserved UAT hostnames (exact 404), and an
unrelated-host 404.

For local Compose file-backed config/secret mounts, set:

```text
/etc/geem/cloudflared                  root:65532 0750
/etc/geem/cloudflared/config.yml       root:65532 0440
/etc/geem/cloudflared/credentials.json root:65532 0440
```

Prove UID/GID 65532 can read but cannot write both files.

## 8. Install and validate the persistent Compose wrapper

Install `/usr/local/sbin/geem-prod-compose` as `root:root` mode `0755`:

```sh
#!/bin/sh
set -eu
exec /usr/bin/docker compose \
  --project-name geem-production \
  --env-file /etc/geem/production.env \
  --profile mcp \
  -f /opt/geem/current/infra/docker-compose.yml \
  -f /opt/geem/current/infra/docker-compose.tunnel.yml \
  -f /etc/geem/docker-compose.production-hardening.yml \
  "$@"
```

Use this wrapper for every production `config`, `up`, `run`, `exec`, `ps`,
`logs`, and `stop` command. Never invoke the base or tunnel file directly.

Run `config --quiet`, then stream `config --format json` directly into the
exact local API image with `--network none`, `--read-only`, all capabilities
dropped, and this validator contract:

```text
python -m app.ops.validate_production_compose
--project geem-production
--install-id <exact-GEEM_INSTALL_ID>
--mcp-enabled false
--allow-local-image-ids
--expected-api-image <exact-GEEM_API_IMAGE-local-sha256-ID>
--ingress-service cloudflared
--volume postgres_data=<exact-new-volume>
--volume redis_data=<exact-new-volume>
--volume qdrant_data=<exact-new-volume>
--volume minio_data=<exact-new-volume>
--required-blocked-network <repeat-for-each-reviewed-host/VPN/VPC/CIDR>
```

For persistent startup, keep the expected API ID in `/etc/geem/api-image-id`
and the install ID in `/etc/geem/install-id`. The preflight uses the exact API
image to execute the networkless validator and appends both dynamic arguments.
This prevents a different validator image from approving the application image
that will actually run and binds every service to the one approved installation.

Do not save the rendered JSON: it can contain secrets. Validation must pass
before the first new container starts. Also require:

- no unexpected service, network, config, secret, bind mount, host port,
  `build`, mutable image, or privileged/root override;
- the API launch remains `uvicorn app.main:app` with
  `--host 0.0.0.0 --port 8000 --no-access-log`, so request URLs are not
  emitted by Uvicorn access logs;
- the exact eleven IPAM networks and four external volumes;
- Cloudflared using only `/etc/geem/cloudflared/config.yml` and credentials;
- API/worker/gateway/Beat public-route isolation, including mail: they reach
  `mail-relay` only over `mail_relay_control` and never hold the submission
  route themselves; and
- one authorized service on each external-route network.

## 9. Start the fresh stack

The WAF hold remains active throughout this section.

1. Start only PostgreSQL, Redis, Qdrant, MinIO, `minio-init`, the app egress
   proxy, the mail relay, MCP proxy, and MCP gateway. Do not start API, worker,
   Beat, frontend, or Cloudflared yet.
2. Require all four datastore containers to mount exactly the four new volumes
   at their canonical destinations. Require the initializer to finish
   successfully and all boundaries to be healthy.
3. Wait boundedly for PostgreSQL, then run the one-shot empty-schema migration:

   ```bash
   sudo /usr/local/sbin/geem-prod-compose run --rm --no-deps api alembic upgrade head
   ```

4. On that verified empty database, run the clean bootstrap:

   ```bash
   sudo /usr/local/sbin/geem-prod-compose run --rm --no-deps api python -m app.identity.bootstrap
   ```

5. Remove `BOOTSTRAP_ADMIN_PASSWORD` from `/etc/geem/production.env`
   immediately after bootstrap. Preserve it only in the operator's external
   secret store.
6. Run the MCP catalog reconciler in dry-run, apply, and verify order:

   ```bash
   sudo /usr/local/sbin/geem-prod-compose run --rm --no-deps api python -m app.apps_catalog.reconcile_mcp --dry-run
   sudo /usr/local/sbin/geem-prod-compose run --rm --no-deps api python -m app.apps_catalog.reconcile_mcp --apply
   sudo /usr/local/sbin/geem-prod-compose run --rm --no-deps api python -m app.apps_catalog.reconcile_mcp --verify
   ```

   It must leave the MCP App `coming_soon` and create no plan or signed price.
7. Start API, worker, exactly one Beat, Workspace, Platform Admin, and marketing
   without Cloudflared. Require the API ready endpoint and current Alembic head.
8. Run the deployed isolation gate through the wrapper:

   ```bash
   sudo env \
     MCP_SMOKE_COMPOSE_WRAPPER=/usr/local/sbin/geem-prod-compose \
     MCP_SMOKE_ENV_FILE=/etc/geem/production.env \
     /opt/geem/current/infra/mcp-egress/verify-isolation.sh
   ```

9. Re-run the rendered-topology validator, then start Cloudflared last. The
   local verifier requires one container ID to remain running, non-restarting,
   and unchanged for a bounded 25-second window. Separately query Cloudflare's
   tunnel-connections/status API through the lifecycle token and require at
   least one healthy connector for the exact new tunnel UUID. A stable local
   process alone is not proof that the edge accepted it. Require exactly one
   running container for every long-running Geem service.
10. With WAF still active, prove all public Geem hostnames continue to return
    the maintenance block, not an origin response.

Recompare the protected manifest after each container/network creation stage.
Any law-firm identity, state, mount, or endpoint change is a failure.

## 10. Make the stack persistent

Do not install either retired historical `geem-stack` unit. Install the reviewed
files from the exact release with these exact owners and modes:

```bash
sudo install -o root -g root -m 0644 \
  /opt/geem/current/infra/systemd/geem-production.service \
  /etc/systemd/system/geem-production.service
sudo install -o root -g root -m 0755 \
  /opt/geem/current/infra/systemd/geem-production-preflight \
  /usr/local/sbin/geem-production-preflight
sudo install -o root -g root -m 0755 \
  /opt/geem/current/infra/systemd/geem-production-verify \
  /usr/local/sbin/geem-production-verify
sudo install -o root -g root -m 0755 \
  /opt/geem/current/infra/systemd/geem-production-stop \
  /usr/local/sbin/geem-production-stop
```

The unit starts internal services, verifies topology/readiness/isolation, and
starts Cloudflared last. Its failure containment stops Cloudflared first and
then services carrying both the exact `geem-production` project label and the
immutable installation label. It never restarts Docker or selects another
Compose project/install. Its ingress stage proves a stable local connector
process; the external Cloudflare API check in section 9 proves edge health.
Because all container restart policies are `no`, this unit is also the only
component allowed to restore Geem after host or Docker startup.

Create `/etc/geem/start-artifacts.sha256` only after the bootstrap password is
removed. The API image file contains exactly its raw `sha256:<64-hex>` ID. The
validator argument file contains one literal argument per line and only the
stored portion of the section 8 contract: exactly one `--mcp-enabled` pair,
exactly one `--volume` pair for each of the four logical volumes, and one or
more `--required-blocked-network` pairs. Put each flag and value on separate
lines. Do not put `--project`, `--allow-local-image-ids`,
`--expected-api-image`, `--install-id`, `--ingress-service`, or any other flag
in that file. Preflight rejects every unapproved stored flag and appends those
five trusted arguments from fixed code and separately checked identity files
after the stored arguments.
`release-sha`, the API image file, and validator arguments are `root:root` mode
`0400`.

The persistent preflight also requires every checksum-listed path to remain a
regular non-symlink file with its documented exact owner and mode. This
includes `production.env` and the hardening overlay at `root:root 0600`, the
image manifest and identity/argument files at `root:root 0400`, the installed
unit at `root:root 0644`, helpers at `root:root 0755`, Cloudflared files at
`root:65532 0440`, and all PKI files and directories at the modes in the PKI
guide. Permission drift is a failed preflight even when file bytes are
unchanged.

Hash the following absolute paths—no glob and no relative path—into a new file
on the `/etc/geem` filesystem:

```bash
test -f /etc/geem/current-install-attempt
test ! -L /etc/geem/current-install-attempt
test "$(sudo stat -c '%u:%g:%a' \
  /etc/geem/current-install-attempt)" = 0:0:400
GEEM_INSTALL_STATE="$(sudo sed -n '1p' /etc/geem/current-install-attempt)"
test "$(sudo awk 'END { print NR }' \
  /etc/geem/current-install-attempt)" -eq 1
printf '%s\n' "${GEEM_INSTALL_STATE:?current install attempt is required}" \
  | grep -Eq '^/etc/geem/install-attempts/fresh-[0-9]{14}-[0-9a-f]{16}$'
test -d "$GEEM_INSTALL_STATE"
test ! -L "$GEEM_INSTALL_STATE"
test "$(sudo readlink -f "$GEEM_INSTALL_STATE")" = "$GEEM_INSTALL_STATE"
test "$(sudo stat -c '%u:%g:%a' "$GEEM_INSTALL_STATE")" = 0:0:700
state_manifest="$GEEM_INSTALL_STATE/start-artifacts.sha256.new"
test ! -e "$state_manifest"
test ! -L "$state_manifest"
test ! -e /etc/geem/start-artifacts.sha256.next
test ! -L /etc/geem/start-artifacts.sha256.next
sudo sh -c 'set -euC; umask 077; output=$1; shift; \
  /usr/bin/sha256sum "$@" > "$output"' sh "$state_manifest" \
  /usr/local/sbin/geem-prod-compose \
  /etc/geem/production.env \
  /etc/geem/docker-compose.production-hardening.yml \
  /etc/systemd/system/geem-production.service \
  /usr/local/sbin/geem-production-preflight \
  /usr/local/sbin/geem-production-verify \
  /usr/local/sbin/geem-production-stop \
  /opt/geem/current/infra/docker-compose.yml \
  /opt/geem/current/infra/docker-compose.tunnel.yml \
  /opt/geem/current/infra/mcp-egress/verify-isolation.sh \
  /opt/geem/current/infra/mcp-egress/proxy/static-deny-networks.txt \
  /etc/geem/cloudflared/config.yml \
  /etc/geem/cloudflared/credentials.json \
  /etc/geem/image-manifest \
  /etc/geem/release-sha \
  /etc/geem/install-id \
  /etc/geem/api-image-id \
  /etc/geem/production-validator.args \
  /etc/geem/mcp-egress/pki/ca/ca.crt \
  /etc/geem/mcp-egress/pki/server/server.crt \
  /etc/geem/mcp-egress/pki/server/server.key \
  /etc/geem/mcp-egress/pki/client/client.crt \
  /etc/geem/mcp-egress/pki/client/client.key
test -f "$state_manifest"
test ! -L "$state_manifest"
test "$(sudo stat -c '%u:%g:%a' "$state_manifest")" = 0:0:600
sudo sh -c 'set -euC; umask 022; cat "$1" > "$2"' sh \
  "$state_manifest" /etc/geem/start-artifacts.sha256.next
test -f /etc/geem/start-artifacts.sha256.next
test ! -L /etc/geem/start-artifacts.sha256.next
sudo chown root:root /etc/geem/start-artifacts.sha256.next
sudo chmod 0444 /etc/geem/start-artifacts.sha256.next
test "$(sudo stat -c '%u:%g:%a' \
  /etc/geem/start-artifacts.sha256.next)" = 0:0:444
sudo mv -T /etc/geem/start-artifacts.sha256.next \
  /etc/geem/start-artifacts.sha256
```

The preflight verifies every hash, the full release SHA and active symlink, a
direct Docker project-label no-orphan/cardinality gate, and the rendered
topology on every start without sourcing the application environment as shell
code.

Stop the manually started new project, prove no Geem container remains running,
then load and start the unit:

```bash
sudo /usr/local/sbin/geem-production-stop
test -z "$(sudo docker ps -q \
  --filter label=com.docker.compose.project=geem-production)"
sudo systemctl daemon-reload
sudo systemctl start geem-production.service
sudo systemctl --no-pager --full status geem-production.service
sudo systemctl enable geem-production.service
```

Require internal validation to complete before Cloudflared starts. Require the
unit active, the Cloudflared stability window passed, and a healthy connector
for the exact new UUID in Cloudflare's API before enabling it for boot or
releasing WAF.

Do not reboot the shared server merely to test Geem. A controlled reboot needs
separate authorization because it interrupts law-firm. Record reboot
verification as pending if no host-wide window exists; do not claim it passed.

## 11. Release traffic and close maintenance

Before removing WAF, require all of the following while the hold is still on:

- production Compose validation passes with `MCP_CONNECTOR_ENABLED=false`;
- API live and ready health checks pass internally;
- migration head and clean bootstrap state are correct;
- MCP mTLS and network-isolation smoke passes;
- all services have exact cardinality and the local Cloudflared process passed
  its bounded stability window;
- Cloudflare reports a healthy connector for the exact new tunnel and the new
  tunnel has no unexpected connector or route;
- all six DNS record IDs target the new tunnel; and
- every protected hostname excluded from WAF still has an exact DNS record that
  does not target the new tunnel, while every absent reserved UAT hostname
  selects the tunnel's exact 404 rule before the production wildcard; and
- the protected law-firm manifest still matches.

Delete only the exact WAF rule ID recorded in
`$GEEM_INSTALL_STATE/cloudflare-waf.json`. Do not delete or replace the
ruleset. Immediately probe all exact hosts plus a random tenant hostname with
cache-busting URLs. Require expected live content/API health and no old tunnel
UUID, Cloudflare 1016, 502, or maintenance response.

If every probe passes, record the release timestamp, Git SHA, image IDs, tunnel
UUID, DNS record IDs, WAF rule deletion response, service cardinality, and
protected-manifest comparison. Keep secrets and rendered Compose JSON out of
the evidence.

## Failure policy

There is no rollback to the deleted old Geem deployment and no need to recover
its data. On any failure after the WAF hold is active:

1. keep or recreate the exact WAF maintenance rule;
2. stop the exact new Cloudflared container first;
3. stop/disable `geem-production.service` if installed;
4. stop only containers carrying both the exact `geem-production` project
   label and the checksummed immutable installation label;
5. preserve new volumes and state files for diagnosis unless the operator
   explicitly starts another fresh-install attempt with new volume names;
6. prove law-firm is unchanged; and
7. report the single failed gate and the exact safe resume point.

Do not reactivate the old tunnel, old containers, or old supervisor. Do not
weaken the validator, attach application services to a public network, publish
host ports, or remove the WAF hold merely to continue.

## Updating after the fresh installation

This document covers the initial fresh installation only. A later release must
be staged at a new exact `/opt/geem/releases/<sha>` directory, retrieve the
explicitly selected CI-verified production image manifest, run release-specific
migrations through the persistent wrapper, atomically move
`/opt/geem/current`, regenerate the checksum manifest, and restart only
`geem-production.service` inside an approved maintenance window. Never use
`git pull` inside `/opt/geem/current` or rebuild release images on the host.

## Authoritative references

- [MCP Connectors configuration and isolation](./integrations/mcp-connectors.md)
- [Production Compose validator](../apps/api/app/ops/validate_production_compose.py)
- [MCP PKI contract](../infra/mcp-egress/pki/README.md)
- [Cloudflare WAF custom rule API](https://developers.cloudflare.com/waf/custom-rules/create-api/)
- [Cloudflare Tunnel permissions](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/tunnel-permissions/)
- [Cloudflare Tunnel API token scopes](https://developers.cloudflare.com/sandbox/api/tunnels/)
- [Cloudflare Tunnel routing and DNS independence](https://developers.cloudflare.com/tunnel/routing/)
- [Docker Engine uninstall/data behavior](https://docs.docker.com/engine/install/ubuntu/)
- [Docker pruning scope](https://docs.docker.com/engine/manage-resources/pruning/)
