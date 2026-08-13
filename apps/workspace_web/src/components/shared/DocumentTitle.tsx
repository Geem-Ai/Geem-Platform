import { useLayoutEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';

type DocumentTitleProps = {
  /** Page label shown before the product name. Omit for the default product title. */
  title?: string | null;
};

/**
 * Sets the browser tab title for the current screen.
 * useLayoutEffect is the source of truth so nested layout Helmets cannot
 * overwrite the page title after paint.
 */
export function DocumentTitle({ title }: DocumentTitleProps) {
  const { t } = useTranslation();
  const name = t('app.name');
  const trimmed = title?.trim() ?? '';
  const full = trimmed
    ? t('app.documentTitle', { page: trimmed, name })
    : t('app.defaultTitle', { name, tagline: t('app.tagline') });

  useLayoutEffect(() => {
    document.title = full;
  }, [full]);

  return (
    <Helmet>
      <title>{full}</title>
    </Helmet>
  );
}
