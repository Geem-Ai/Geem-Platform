from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Request

from app.core.config import Settings, get_settings


@dataclass(slots=True, frozen=True)
class WorkspaceResolutionHint:
    """Candidate workspace identity from Host / headers — NOT authorization.

    Resolution sources leave room for future API-key path (Phase 7) without
    competing context systems.

    Precedence (first match wins):
      1. Host subdomain slug (if not reserved / infra)
      2. X-Workspace-Slug — ONLY when Settings.is_local
      3. X-Workspace-Id — routing hint in all envs (membership still required)
    """

    slug: str | None = None
    workspace_id: UUID | None = None
    source: str = "none"  # host | header_slug | header_id | none


def extract_subdomain_slug(
    host: str,
    root_domain: str,
    *,
    reserved_slugs: frozenset[str] | None = None,
) -> str | None:
    """Return workspace slug from `{slug}.{root}` or `{slug}.localhost` style hosts.

    Infrastructure / reserved names (api, admin, www, …) never resolve as tenants.
    """
    if not host:
        return None
    hostname = host.split(":")[0].strip().lower()
    root = root_domain.strip().lower().lstrip(".")
    if not hostname or hostname in {root, f"www.{root}", "localhost", "127.0.0.1"}:
        return None

    # Platform admin host is never a tenant slug (any admin.* label).
    if hostname.startswith("admin."):
        return None

    slug = _slug_from_host(hostname, root)
    if slug is None:
        return None
    reserved = reserved_slugs if reserved_slugs is not None else get_settings().reserved_slugs
    if slug in reserved:
        return None
    return slug


def _slug_from_host(hostname: str, root: str) -> str | None:
    if hostname.endswith(".localhost"):
        # acme.localhost → acme ; www.localhost / api.localhost blocked via reserved
        prefix = hostname[: -len(".localhost")]
        if prefix and "." not in prefix:
            return prefix
        return None

    if root and hostname.endswith(f".{root}"):
        prefix = hostname[: -(len(root) + 1)]
        if prefix and "." not in prefix:
            return prefix
    return None


def resolve_workspace_hint(request: Request, settings: Settings | None = None) -> WorkspaceResolutionHint:
    """Extract workspace UX/context hints. Membership is verified separately."""
    cfg = settings or get_settings()
    host = request.headers.get("host", "")

    slug = extract_subdomain_slug(host, cfg.app_root_domain, reserved_slugs=cfg.reserved_slugs)
    if slug:
        return WorkspaceResolutionHint(slug=slug, source="host")

    # X-Workspace-Slug is a local/dev fallback only — never trust in production.
    header_slug = request.headers.get("X-Workspace-Slug")
    if header_slug:
        if cfg.is_local:
            return WorkspaceResolutionHint(
                slug=header_slug.strip().lower(),
                source="header_slug",
            )

    header_id = request.headers.get("X-Workspace-Id")
    if header_id:
        try:
            return WorkspaceResolutionHint(workspace_id=UUID(header_id), source="header_id")
        except ValueError:
            return WorkspaceResolutionHint(source="none")

    return WorkspaceResolutionHint(source="none")
