import { describe, expect, it } from 'vitest';
import type { CatalogApp } from '@/services/api/apps';
import { pickRecommendedApps } from './recommended';

function app(partial: Partial<CatalogApp>): CatalogApp {
  return {
    id: partial.id ?? partial.slug ?? 'app',
    slug: 'demo',
    name: 'Demo',
    short_description: 'x',
    description: null,
    category: {
      slug: 'knowledge',
      name_key: 'apps.categories.knowledge',
      description_key: null,
      icon: null,
      sort_order: 0,
    },
    icon_url: null,
    billing_type: 'free',
    status: 'published',
    is_featured: false,
    sort_order: 0,
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

describe('pickRecommendedApps', () => {
  it('prefers featured uninstalled apps, then featured installed, then others', () => {
    const drive = app({
      id: 'drive',
      slug: 'google-drive',
      is_featured: true,
      sort_order: 10,
    });
    const whatsapp = app({
      id: 'wa',
      slug: 'whatsapp',
      is_featured: true,
      sort_order: 30,
      installation_status: 'active',
    });
    const other = app({
      id: 'other',
      slug: 'other',
      is_featured: false,
      sort_order: 5,
    });
    const draft = app({
      id: 'draft',
      slug: 'draft',
      status: 'draft',
      is_featured: true,
    });

    expect(pickRecommendedApps([other, whatsapp, draft, drive], 4).map((a) => a.slug)).toEqual([
      'google-drive',
      'whatsapp',
      'other',
    ]);
  });

  it('caps the list at the requested limit', () => {
    const apps = [
      app({ id: 'a', slug: 'a', is_featured: true, sort_order: 1 }),
      app({ id: 'b', slug: 'b', is_featured: true, sort_order: 2 }),
      app({ id: 'c', slug: 'c', is_featured: true, sort_order: 3 }),
    ];
    expect(pickRecommendedApps(apps, 2).map((a) => a.slug)).toEqual(['a', 'b']);
  });
});
