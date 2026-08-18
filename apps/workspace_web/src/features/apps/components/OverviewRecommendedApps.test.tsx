import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { CatalogApp, CatalogAppList } from '@/services/api/apps';
import { OverviewRecommendedApps } from './OverviewRecommendedApps';

const useApps = vi.hoisted(() => vi.fn());

vi.mock('../hooks/useAppsQueries', () => ({
  useApps: (...args: unknown[]) => useApps(...args),
}));

function catalogApp(partial: Partial<CatalogApp> = {}): CatalogApp {
  return {
    id: 'app-1',
    slug: 'google-drive',
    name: 'Google Drive',
    short_description: 'Connect Drive',
    description: null,
    category: {
      slug: 'knowledge',
      name_key: 'apps.categories.knowledge',
      description_key: null,
      icon: null,
      sort_order: 10,
    },
    icon_url: '/brand/apps/google-drive.svg',
    billing_type: 'free',
    status: 'published',
    is_featured: true,
    sort_order: 10,
    plans: [],
    installation: null,
    installation_status: null,
    can_install: true,
    can_uninstall: false,
    access_requirement: 'free',
    access: null,
    connector: null,
    has_active_connection: false,
    ...partial,
  };
}

function listResponse(items: CatalogApp[]): CatalogAppList {
  return { items, total: items.length, limit: 50, offset: 0 };
}

describe('OverviewRecommendedApps', () => {
  beforeEach(async () => {
    useApps.mockReset();
    await i18n.changeLanguage('en');
  });

  it('renders featured catalog apps and a browse link', () => {
    useApps.mockReturnValue({
      data: listResponse([
        catalogApp(),
        catalogApp({
          id: 'app-2',
          slug: 'whatsapp',
          name: 'WhatsApp',
          is_featured: true,
          sort_order: 30,
        }),
      ]),
      isLoading: false,
    });

    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <OverviewRecommendedApps />
        </MemoryRouter>
      </I18nextProvider>,
    );

    expect(screen.getByTestId('overview-recommended-apps')).toBeInTheDocument();
    expect(screen.getByTestId('app-card-google-drive')).toBeInTheDocument();
    expect(screen.getByTestId('app-card-whatsapp')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: i18n.t('overview.viewApps') })).toHaveAttribute(
      'href',
      '/apps',
    );
  });

  it('hides the card while loading or when the catalog is empty', () => {
    useApps.mockReturnValue({ data: undefined, isLoading: true });
    const { unmount } = render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <OverviewRecommendedApps />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.queryByTestId('overview-recommended-apps')).not.toBeInTheDocument();
    unmount();

    useApps.mockReturnValue({ data: listResponse([]), isLoading: false });
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <OverviewRecommendedApps />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.queryByTestId('overview-recommended-apps')).not.toBeInTheDocument();
  });
});
