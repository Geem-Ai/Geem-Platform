import type { Locale } from './i18n';

const DEFAULT_SITE = 'https://geem.ai';
const DEFAULT_WORKSPACE = 'https://app.geem.ai';
const DEFAULT_API = 'https://api.geem.ai';

function stripTrailingSlash(url: string): string {
  return url.replace(/\/$/, '');
}

export function getSiteConfig() {
  const siteUrl = stripTrailingSlash(
    import.meta.env.PUBLIC_SITE_URL || DEFAULT_SITE,
  );
  const workspaceUrl = stripTrailingSlash(
    import.meta.env.PUBLIC_WORKSPACE_URL || DEFAULT_WORKSPACE,
  );
  const signupUrl =
    import.meta.env.PUBLIC_SIGNUP_URL || `${workspaceUrl}/register`;
  const loginUrl = `${workspaceUrl}/login`;
  const contactUrl = import.meta.env.PUBLIC_CONTACT_URL || '';
  const docsUrl = import.meta.env.PUBLIC_DOCS_URL || '';
  const apiBaseUrl = stripTrailingSlash(
    import.meta.env.PUBLIC_API_BASE_URL || DEFAULT_API,
  );

  return {
    siteUrl,
    workspaceUrl,
    signupUrl,
    loginUrl,
    contactUrl,
    docsUrl,
    apiBaseUrl,
    ogImageUrl: `${siteUrl}/og-geem.jpg`,
    ogImageType: 'image/jpeg',
    ogImageWidth: 1200,
    ogImageHeight: 630,
  };
}

export type SiteConfig = ReturnType<typeof getSiteConfig>;

export function localizedPath(locale: Locale, path = ''): string {
  const clean = path.replace(/^\/+|\/+$/g, '');
  return clean ? `/${locale}/${clean}` : `/${locale}`;
}

export function absoluteUrl(locale: Locale, path = ''): string {
  const { siteUrl } = getSiteConfig();
  return `${siteUrl}${localizedPath(locale, path)}`;
}

export function contactHref(locale: Locale): string {
  const { contactUrl } = getSiteConfig();
  if (contactUrl) return contactUrl;
  return localizedPath(locale, 'contact');
}
