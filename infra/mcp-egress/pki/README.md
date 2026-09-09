# MCP egress mTLS files

This directory is intentionally empty in Git. Production uses a dedicated CA,
one server identity for the MCP egress gateway, and one client identity shared
by the API and worker. Do not reuse a public web certificate, application JWT,
connector-encryption key, or provider credential.

The installed layout is:

```text
/etc/geem/mcp-egress/pki/ca/ca.crt
/etc/geem/mcp-egress/pki/server/server.crt
/etc/geem/mcp-egress/pki/server/server.key
/etc/geem/mcp-egress/pki/client/client.crt
/etc/geem/mcp-egress/pki/client/client.key
```

The server certificate must contain `DNS:mcp-egress-gateway` and only the
`serverAuth` extended-key usage. The client certificate must contain only the
`clientAuth` extended-key usage. Generate a new CA and leaves for each fresh
production installation.

## Production issuance

Prefer an internal PKI or secret manager. Give it the requirements above and
either stage the five deliverable files in a new root-only directory and set
`issue_dir` to that path for the install commands, or install them directly
with the documented ownership/modes and continue at the verification commands.
The CA private key must never be installed under `/etc/geem`.

When no internal issuer exists, run this bounded procedure as root. It creates
the CA in a new root-only temporary directory, issues 397-day RSA leaf
certificates, installs only the required artifacts, and then destroys the
temporary CA key. Keep the terminal and command history private.

```bash
export LC_ALL=C
umask 077
issue_dir="$(mktemp -d /root/geem-mcp-pki.XXXXXX)"
case "$issue_dir" in
  /root/geem-mcp-pki.*) ;;
  *) echo "Unsafe issuance directory" >&2; exit 1 ;;
esac

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$issue_dir/ca.key"
openssl req -new -x509 -sha256 -days 3650 \
  -key "$issue_dir/ca.key" \
  -subj "/CN=Geem MCP Egress Production CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash" \
  -out "$issue_dir/ca.crt"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$issue_dir/server.key"
openssl req -new -sha256 -key "$issue_dir/server.key" \
  -subj "/CN=mcp-egress-gateway" -out "$issue_dir/server.csr"
printf '%s\n' \
  'basicConstraints=critical,CA:FALSE' \
  'keyUsage=critical,digitalSignature,keyEncipherment' \
  'extendedKeyUsage=serverAuth' \
  'subjectAltName=DNS:mcp-egress-gateway' \
  'subjectKeyIdentifier=hash' \
  'authorityKeyIdentifier=keyid,issuer' \
  >"$issue_dir/server.ext"
openssl x509 -req -sha256 -days 397 \
  -in "$issue_dir/server.csr" \
  -CA "$issue_dir/ca.crt" -CAkey "$issue_dir/ca.key" -CAcreateserial \
  -extfile "$issue_dir/server.ext" -out "$issue_dir/server.crt"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$issue_dir/client.key"
openssl req -new -sha256 -key "$issue_dir/client.key" \
  -subj "/CN=geem-api-worker" -out "$issue_dir/client.csr"
printf '%s\n' \
  'basicConstraints=critical,CA:FALSE' \
  'keyUsage=critical,digitalSignature,keyEncipherment' \
  'extendedKeyUsage=clientAuth' \
  'subjectKeyIdentifier=hash' \
  'authorityKeyIdentifier=keyid,issuer' \
  >"$issue_dir/client.ext"
openssl x509 -req -sha256 -days 397 \
  -in "$issue_dir/client.csr" \
  -CA "$issue_dir/ca.crt" -CAkey "$issue_dir/ca.key" -CAserial "$issue_dir/ca.srl" \
  -extfile "$issue_dir/client.ext" -out "$issue_dir/client.crt"
```

## Install and verify

Create directories and copy files without replacing them through a symlink.
The numeric gateway group is intentional: the gateway runs as UID/GID `10001`
and receives group-read access, while root retains ownership and the gateway
cannot replace its identity. API and worker currently run as root in their
container.
On a shared host, first require `getent passwd 10001` to return no unrelated
host user and require no unrelated host user to belong to GID `10001`. Stop on
a collision; do not grant another application access to this key.

```bash
test -d /etc/geem
for component in \
  /etc/geem \
  /etc/geem/mcp-egress \
  /etc/geem/mcp-egress/pki \
  /etc/geem/mcp-egress/pki/ca \
  /etc/geem/mcp-egress/pki/server \
  /etc/geem/mcp-egress/pki/client \
  /etc/geem/mcp-egress/pki/ca/ca.crt \
  /etc/geem/mcp-egress/pki/server/server.crt \
  /etc/geem/mcp-egress/pki/server/server.key \
  /etc/geem/mcp-egress/pki/client/client.crt \
  /etc/geem/mcp-egress/pki/client/client.key; do
  test ! -L "$component"
done
for source in ca.crt server.crt server.key client.crt client.key; do
  test -f "$issue_dir/$source"
  test ! -L "$issue_dir/$source"
done
install -d -o root -g root -m 0755 /etc/geem/mcp-egress/pki
install -d -o root -g root -m 0755 /etc/geem/mcp-egress/pki/ca
install -d -o root -g 10001 -m 0750 /etc/geem/mcp-egress/pki/server
install -d -o root -g root -m 0700 /etc/geem/mcp-egress/pki/client
install -o root -g root -m 0644 "$issue_dir/ca.crt" \
  /etc/geem/mcp-egress/pki/ca/ca.crt
install -o root -g 10001 -m 0440 "$issue_dir/server.crt" \
  /etc/geem/mcp-egress/pki/server/server.crt
install -o root -g 10001 -m 0440 "$issue_dir/server.key" \
  /etc/geem/mcp-egress/pki/server/server.key
install -o root -g root -m 0644 "$issue_dir/client.crt" \
  /etc/geem/mcp-egress/pki/client/client.crt
install -o root -g root -m 0400 "$issue_dir/client.key" \
  /etc/geem/mcp-egress/pki/client/client.key
```

If an internal PKI supplied the installed files, set the same ownership and
modes before verification. Then verify the chains, minimum remaining lifetime,
SAN, EKUs, and both key pairs:

```bash
export LC_ALL=C
pki=/etc/geem/mcp-egress/pki
openssl verify -CAfile "$pki/ca/ca.crt" \
  "$pki/server/server.crt" "$pki/client/client.crt"
openssl x509 -checkend 2592000 -noout -in "$pki/ca/ca.crt"
openssl x509 -checkend 2592000 -noout -in "$pki/server/server.crt"
openssl x509 -checkend 2592000 -noout -in "$pki/client/client.crt"
test "$(openssl x509 -noout -ext basicConstraints \
  -in "$pki/ca/ca.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'CA:TRUE,pathlen:0'
test "$(openssl x509 -noout -ext keyUsage \
  -in "$pki/ca/ca.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'CertificateSign,CRLSign'
test "$(openssl x509 -noout -ext basicConstraints \
  -in "$pki/server/server.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'CA:FALSE'
test "$(openssl x509 -noout -ext keyUsage \
  -in "$pki/server/server.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'DigitalSignature,KeyEncipherment'
test "$(openssl x509 -noout -ext basicConstraints \
  -in "$pki/client/client.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'CA:FALSE'
test "$(openssl x509 -noout -ext keyUsage \
  -in "$pki/client/client.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'DigitalSignature,KeyEncipherment'
test "$(openssl x509 -noout -ext subjectAltName \
  -in "$pki/server/server.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'DNS:mcp-egress-gateway'
test "$(openssl x509 -noout -ext extendedKeyUsage \
  -in "$pki/server/server.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'TLSWebServerAuthentication'
test "$(openssl x509 -noout -ext extendedKeyUsage \
  -in "$pki/client/client.crt" | sed -n '2,$p' | tr -d '[:space:]')" = \
  'TLSWebClientAuthentication'

test "$(openssl pkey -in "$pki/server/server.key" -pubout -outform DER \
  | sha256sum)" = \
  "$(openssl x509 -in "$pki/server/server.crt" -pubkey -noout \
  | openssl pkey -pubin -outform DER | sha256sum)"
test "$(openssl pkey -in "$pki/client/client.key" -pubout -outform DER \
  | sha256sum)" = \
  "$(openssl x509 -in "$pki/client/client.crt" -pubkey -noout \
  | openssl pkey -pubin -outform DER | sha256sum)"
test ! -e "$pki/ca/ca.key"
```

For the local issuance path, destroy the entire validated temporary directory
only after installation and verification. Validate the prefix again so the
removal cannot expand to another path:

```bash
case "$issue_dir" in
  /root/geem-mcp-pki.*)
    find "$issue_dir" -type f -exec shred -u -- {} +
    rmdir "$issue_dir"
    ;;
  *) echo "Refusing unsafe cleanup path" >&2; exit 1 ;;
esac
unset issue_dir pki
```

Record certificate fingerprints and expiry dates, not private-key material, in
the installation evidence. Include all five installed files in the protected
startup checksum manifest.

For local development, use a separate short-lived CA and leaf certificates.
Keep generated files ignored by Git and rotate them before sharing the
environment.
