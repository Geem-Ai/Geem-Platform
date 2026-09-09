#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT="$(cd "${INFRA_DIR}/.." && pwd)"

cd "${INFRA_DIR}"

if [[ ! -f "${ROOT}/.env" ]]; then
	cp "${ROOT}/.env.example" "${ROOT}/.env"
	echo "Created ${ROOT}/.env — set OPENROUTER_API_KEY before using AI features."
fi

for pair in \
	"apps/workspace_web/.env.example:apps/workspace_web/.env" \
	"apps/dashboard_web/.env.example:apps/dashboard_web/.env" \
	"apps/landpage_web/.env.example:apps/landpage_web/.env"; do
	src="${pair%%:*}"
	dst="${pair##*:}"
	if [[ ! -f "${ROOT}/${dst}" ]]; then
		cp "${ROOT}/${src}" "${ROOT}/${dst}"
		echo "Created ${ROOT}/${dst}"
	fi
done

compose_files=(-f docker-compose.yml -f docker-compose.local.yml)
if grep -Eq '^[[:space:]]*MCP_CONNECTOR_ENABLED[[:space:]]*=[[:space:]]*true([[:space:]]*#.*)?$' "${ROOT}/.env"; then
	"${SCRIPT_DIR}/generate-dev-mcp-pki.sh"
	compose_files=(-f docker-compose.yml -f docker-compose.local-mcp.yml)
fi

exec docker compose --env-file "${ROOT}/.env" "${compose_files[@]}" up -d --build "$@"
