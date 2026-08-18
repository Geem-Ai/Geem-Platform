import type { CatalogApp } from '@/services/api/apps';

const VISIBLE_STATUSES = new Set<CatalogApp['status']>(['published', 'coming_soon']);

function isInstalled(app: CatalogApp): boolean {
  return app.installation_status === 'active';
}

function rank(app: CatalogApp): number {
  const featuredBoost = app.is_featured ? 0 : 2;
  const installedPenalty = isInstalled(app) ? 1 : 0;
  return featuredBoost + installedPenalty;
}

/**
 * Overview recommendations: featured catalog apps first, uninstalled before
 * installed, then other published/coming-soon apps to fill remaining slots.
 */
export function pickRecommendedApps(
  apps: readonly CatalogApp[],
  limit = 4,
): CatalogApp[] {
  return [...apps]
    .filter((app) => VISIBLE_STATUSES.has(app.status))
    .sort((a, b) => {
      const rankDelta = rank(a) - rank(b);
      if (rankDelta !== 0) return rankDelta;
      return a.sort_order - b.sort_order;
    })
    .slice(0, limit);
}
