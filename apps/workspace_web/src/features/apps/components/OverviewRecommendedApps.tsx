import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import type { CatalogApp } from '@/services/api/apps';
import { useApps } from '../hooks/useAppsQueries';
import { pickRecommendedApps } from '../lib/recommended';
import { AppCard } from './AppCard';

export function OverviewRecommendedApps() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const appsQuery = useApps({ limit: 50, offset: 0 });

  const recommended = useMemo(
    () => pickRecommendedApps(appsQuery.data?.items ?? [], 4),
    [appsQuery.data?.items],
  );

  if (appsQuery.isLoading || recommended.length === 0) {
    return null;
  }

  function openApp(app: CatalogApp) {
    void navigate(`/apps/${app.slug}`);
  }

  return (
    <Card data-testid="overview-recommended-apps">
      <CardHeader>
        <div className="space-y-1.5 min-w-0">
          <CardTitle>{t('overview.recommendedTitle')}</CardTitle>
          <CardDescription>{t('overview.recommendedDescription')}</CardDescription>
        </div>
        <Button asChild variant="outline" size="sm" className="shrink-0">
          <Link to="/apps">{t('overview.viewApps')}</Link>
        </Button>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {recommended.map((app) => (
          <AppCard key={app.id} app={app} onOpen={openApp} />
        ))}
      </CardContent>
    </Card>
  );
}
