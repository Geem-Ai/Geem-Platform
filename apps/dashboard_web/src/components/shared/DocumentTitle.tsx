import { useLayoutEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';

type DocumentTitleProps = {
  title?: string | null;
};

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
