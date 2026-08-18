import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  Check,
  LayoutGrid,
  Link2Off,
  LoaderCircle,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { CatalogApp, ConnectionStatus } from '@/services/api/apps';
import {
  localizeCatalogApp,
  resolveAppAccessBadge,
} from '../lib/billing-label';
import { AppBillingLabel } from './AppBillingLabel';
import { AppIcon } from './AppIcon';

export function AppBillingBadge({ app }: { app: CatalogApp }) {
  const { t } = useTranslation();
  const accessBadge = resolveAppAccessBadge(app);
  const showPriceHint =
    accessBadge.labelKey === 'apps.billing.oneTime' ||
    accessBadge.labelKey === 'apps.billing.subscription';

  return (
    <Badge
      variant={accessBadge.variant}
      appearance="light"
      size="sm"
      className="shrink-0"
      data-testid={`app-badge-${app.slug}`}
      data-access-status={app.access?.status ?? app.status}
    >
      {showPriceHint ? <AppBillingLabel app={app} /> : t(accessBadge.labelKey)}
    </Badge>
  );
}

type FooterConnection = {
  label: string;
  icon: 'check' | 'error' | 'loading' | 'reconnect' | 'off' | 'warn';
  tone: 'success' | 'destructive' | 'muted' | 'warning';
};

function footerConnection(app: CatalogApp, t: (key: string) => string): FooterConnection | null {
  if (app.installation_status !== 'active' || !app.connector) {
    return null;
  }

  const status = (app.connection_status || null) as ConnectionStatus | null;

  if (!status) {
    return {
      label: t('apps.connections.notConnected'),
      icon: 'off',
      tone: 'muted',
    };
  }

  switch (status) {
    case 'active':
      return {
        label: t('apps.connections.status.active'),
        icon: 'check',
        tone: 'success',
      };
    case 'degraded':
      return {
        label: t('apps.connections.status.degraded'),
        icon: 'warn',
        tone: 'warning',
      };
    case 'error':
      return {
        label: t('apps.connections.status.error'),
        icon: 'error',
        tone: 'destructive',
      };
    case 'connecting':
    case 'pending':
      return {
        label: t(`apps.connections.status.${status}`),
        icon: 'loading',
        tone: 'muted',
      };
    case 'disconnected':
      return {
        label: t('apps.connections.reconnect'),
        icon: 'reconnect',
        tone: 'muted',
      };
    case 'revoked':
      return {
        label: t('apps.connections.status.revoked'),
        icon: 'reconnect',
        tone: 'destructive',
      };
    default:
      return {
        label: t('apps.connections.notConnected'),
        icon: 'off',
        tone: 'muted',
      };
  }
}

function FooterIcon({
  icon,
  tone,
}: {
  icon: FooterConnection['icon'];
  tone: FooterConnection['tone'];
}) {
  const className = cn(
    'size-3.5 shrink-0',
    tone === 'success' && 'text-green-600',
    tone === 'destructive' && 'text-destructive',
    tone === 'warning' && 'text-amber-600',
    tone === 'muted' && 'text-muted-foreground',
  );
  switch (icon) {
    case 'check':
      return <Check className={className} aria-hidden />;
    case 'error':
      return <AlertCircle className={className} aria-hidden />;
    case 'loading':
      return <LoaderCircle className={cn(className, 'animate-spin')} aria-hidden />;
    case 'reconnect':
      return <RefreshCw className={className} aria-hidden />;
    case 'warn':
      return <AlertCircle className={className} aria-hidden />;
    case 'off':
      return <Link2Off className={className} aria-hidden />;
  }
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
  const connection = footerConnection(app, t);

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
            {connection ? (
              <span
                className={cn(
                  'inline-flex items-center gap-1 text-xs',
                  connection.tone === 'success' && 'text-green-700 dark:text-green-500',
                  connection.tone === 'destructive' && 'text-destructive',
                  connection.tone === 'warning' && 'text-amber-700 dark:text-amber-500',
                  connection.tone === 'muted' && 'text-muted-foreground',
                )}
                data-testid={`app-card-connection-${app.slug}`}
              >
                <FooterIcon icon={connection.icon} tone={connection.tone} />
                {connection.label}
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
        className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-muted/20 px-6 py-12 text-center"
      >
        <div
          className="flex size-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground"
          aria-hidden
        >
          <LayoutGrid className="size-6 opacity-70" />
        </div>
        <p className="text-sm font-medium text-foreground max-w-sm">{emptyLabel}</p>
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
