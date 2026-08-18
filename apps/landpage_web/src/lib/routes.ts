import type { Locale } from './i18n';
import { localizedPath } from './site';

/** Homepage section anchors (same across locales). */
export const homeAnchors = {
  product: 'product',
  experts: 'experts',
  knowledge: 'knowledge',
  integrations: 'integrations',
  channels: 'channels',
  api: 'api',
  security: 'security-overview',
  apps: 'apps',
} as const;

export function homeHash(locale: Locale, anchor: keyof typeof homeAnchors): string {
  return `${localizedPath(locale)}#${homeAnchors[anchor]}`;
}

export function switchLocalePath(currentLocale: Locale, nextLocale: Locale, pathname: string): string {
  const withoutLocale = pathname.replace(new RegExp(`^/${currentLocale}(?=/|$)`), '') || '';
  const clean = withoutLocale.replace(/^\/+|\/+$/g, '');
  return clean ? `/${nextLocale}/${clean}` : `/${nextLocale}`;
}
