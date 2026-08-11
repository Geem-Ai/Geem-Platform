import type { CSSProperties } from 'react';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { LayoutProvider } from './context';
import { Wrapper } from './wrapper';

export function WorkspaceLayout() {
  const { t } = useTranslation();

  return (
    <>
      <Helmet>
        <title>{t('app.name')}</title>
      </Helmet>

      <LayoutProvider
        bodyClassName="bg-muted"
        style={
          {
            '--sidebar-width': '255px',
            '--sidebar-header-height': '60px',
            '--header-height': '60px',
            '--header-height-mobile': '60px',
          } as CSSProperties
        }
      >
        <Wrapper />
      </LayoutProvider>
    </>
  );
}
