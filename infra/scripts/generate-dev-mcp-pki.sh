#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PKI_DIR="${MCP_EGRESS_PKI_DIR:-${INFRA_DIR}/mcp-egress/pki}"

if ! command -v openssl >/dev/null 2>&1; then
	echo "openssl is required to generate local MCP egress PKI" >&2
	exit 1
fi

required=(
	"${PKI_DIR}/ca/ca.crt"
	"${PKI_DIR}/server/server.crt"
	"${PKI_DIR}/server/server.key"
	"${PKI_DIR}/client/client.crt"
	"${PKI_DIR}/client/client.key"
)

for path in "${required[@]}"; do
	if [[ -f ${path} ]]; then
		echo "MCP egress PKI already exists under ${PKI_DIR} (skipping generation)"
		exit 0
	fi
done

mkdir -p "${PKI_DIR}"/{ca,server,client}
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

openssl genrsa -out "${work}/ca.key" 4096
openssl req -x509 -new -nodes \
	-key "${work}/ca.key" \
	-sha256 -days 825 \
	-out "${PKI_DIR}/ca/ca.crt" \
	-subj "/CN=Geem Dev MCP Egress CA"

openssl genrsa -out "${PKI_DIR}/server/server.key" 2048
openssl req -new \
	-key "${PKI_DIR}/server/server.key" \
	-out "${work}/server.csr" \
	-subj "/CN=mcp-egress-gateway"
cat >"${work}/server.ext" <<'EOF'
subjectAltName=DNS:mcp-egress-gateway
extendedKeyUsage=serverAuth
EOF
openssl x509 -req \
	-in "${work}/server.csr" \
	-CA "${PKI_DIR}/ca/ca.crt" \
	-CAkey "${work}/ca.key" \
	-CAcreateserial \
	-out "${PKI_DIR}/server/server.crt" \
	-days 825 \
	-sha256 \
	-extfile "${work}/server.ext"

openssl genrsa -out "${PKI_DIR}/client/client.key" 2048
openssl req -new \
	-key "${PKI_DIR}/client/client.key" \
	-out "${work}/client.csr" \
	-subj "/CN=geem-api-mcp-client"
cat >"${work}/client.ext" <<'EOF'
extendedKeyUsage=clientAuth
EOF
openssl x509 -req \
	-in "${work}/client.csr" \
	-CA "${PKI_DIR}/ca/ca.crt" \
	-CAkey "${work}/ca.key" \
	-CAcreateserial \
	-out "${PKI_DIR}/client/client.crt" \
	-days 825 \
	-sha256 \
	-extfile "${work}/client.ext"

chmod 644 "${PKI_DIR}/ca/ca.crt" "${PKI_DIR}/server/server.crt" "${PKI_DIR}/client/client.crt"
chmod 400 "${PKI_DIR}/server/server.key" "${PKI_DIR}/client/client.key"

echo "Generated local MCP egress PKI under ${PKI_DIR}"
echo "Keep these files out of git. Rotate before sharing a development environment."
