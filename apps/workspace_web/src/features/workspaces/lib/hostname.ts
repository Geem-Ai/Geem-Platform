/**
 * Host-derived workspace slug for UX context.
 * Backend still resolves + authorizes independently.
 *
 * Keep reserved names aligned with backend Settings.reserved_slugs defaults
 * for UX only — backend remains authoritative.
 */

const RESERVED_HOST_SLUGS = new Set([
  'www',
  'api',
  'admin',
  'app',
  'dashboard',
  'status',
  'support',
  'docs',
  'mail',
  'smtp',
  'cdn',
  'assets',
  'static',
  'auth',
  'login',
  'register',
  'billing',
  'console',
  'workspace',
  'workspaces',
  'geem',
  'null',
  'undefined',
]);

export function extractHostWorkspaceSlug(
  hostname: string,
  rootDomain: string,
): string | null {
  const host = hostname.split(':')[0]?.trim().toLowerCase() ?? '';
  const root = rootDomain.trim().toLowerCase().replace(/^\./, '');
  if (!host || host === 'localhost' || host === '127.0.0.1') {
    return null;
  }
  if (host === `www.${root}` || host === root) {
    return null;
  }
  if (host.startsWith('admin.')) {
    return null;
  }

  let prefix: string | null = null;
  if (host.endsWith('.localhost')) {
    const p = host.slice(0, -'.localhost'.length);
    prefix = p && !p.includes('.') ? p : null;
  } else if (root && host.endsWith(`.${root}`)) {
    const p = host.slice(0, -(root.length + 1));
    prefix = p && !p.includes('.') ? p : null;
  }

  if (!prefix || RESERVED_HOST_SLUGS.has(prefix)) {
    return null;
  }
  return prefix;
}

/** Suggest a slug from a display name (UX only — backend validates). */
export function suggestSlugFromName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 63);
}

export function isLocalDevEnvironment(): boolean {
  return (
    import.meta.env.DEV ||
    import.meta.env.VITE_APP_ENV === 'local' ||
    import.meta.env.VITE_APP_ENV === 'development'
  );
}
