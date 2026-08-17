import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { CatalogApp } from '@/services/api/apps';
import {
  formatAppBillingLabel,
  localizeCatalogApp,
} from '../lib/billing-label';
import { AppIcon } from './AppIcon';

export function AppBillingBadge({ app }: { app: CatalogApp }) {
  const { t } = useTranslation();
  const label = formatAppBillingLabel(app, t);
  const variant =
    app.status === 'coming_soon'
      ? 'warning'
      : app.installation_status === 'active'
        ? 'success'
        : 'secondary';
  return (
    <Badge variant={variant} appearance="light" size="sm" className="shrink-0">
      {app.installation_status === 'active' ? t('apps.installed') : label}
    </Badge>
  );
}

export function AppCard({
  app,
  onOpen,
}: {
  app: CatalogApp;
  onOpen?: (app: CatalogApp) => void;
}) {
  const { t } = useTranslation();
  const localized = localizeCatalogApp(app, t);
  const categoryLabel = t(app.category.name_key, {
    defaultValue: app.category.slug,
  });

  return (
    <Card
      data-testid={`app-card-${app.slug}`}
      className={cn(
        'group relative flex flex-col gap-0 overflow-hidden cursor-pointer shadow-none',
        'transition-[background-color,box-shadow,border-color] duration-200',
        'hover:border-primary/25 hover:shadow-sm hover:bg-accent/20',
      )}
    >
      <CardContent className="flex flex-col gap-4 p-4 sm:p-5 h-full">
        <button
          type="button"
          className={cn(
            'flex flex-col gap-4 text-start w-full min-h-0 flex-1 cursor-pointer',
            'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/30 rounded-md',
          )}
          onClick={() => onOpen?.(app)}
          aria-label={localized.name}
        >
          <div className="flex items-start gap-3">
            <AppIcon
              slug={app.slug}
              name={localized.name}
              iconUrl={app.icon_url}
              size="sm"
            />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold tracking-tight leading-5 line-clamp-1">
                  {localized.name}
                </h3>
                <AppBillingBadge app={app} />
              </div>
              <p className="text-xs text-muted-foreground">{categoryLabel}</p>
            </div>
          </div>

          <p className="text-sm text-muted-foreground leading-relaxed line-clamp-2 min-h-10">
            {localized.shortDescription}
          </p>

          <div className="mt-auto flex items-center justify-between gap-2 pt-3 border-t border-border/70">
            <span className="text-xs font-medium text-primary">
              {t('apps.viewDetails')}
            </span>
            {app.installation_status === 'active' ? (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Check className="size-3.5 text-green-600" aria-hidden />
                {t('apps.installed')}
              </span>
            ) : null}
          </div>
        </button>
      </CardContent>
    </Card>
  );
}

export function AppGrid({
  apps,
  emptyLabel,
  onOpen,
}: {
  apps: CatalogApp[];
  emptyLabel: string;
  onOpen?: (app: CatalogApp) => void;
}) {
  if (!apps.length) {
    return (
      <div
        data-testid="apps-empty"
        className="rounded-xl border border-dashed border-border px-5 py-10 text-center text-sm text-muted-foreground"
      >
        {emptyLabel}
      </div>
    );
  }
  return (
    <div
      data-testid="apps-grid"
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
    >
      {apps.map((app) => (
        <AppCard key={app.id} app={app} onOpen={onOpen} />
      ))}
    </div>
  );
}
