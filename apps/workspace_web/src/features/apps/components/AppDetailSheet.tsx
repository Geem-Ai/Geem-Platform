import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  floatingSheetPanel,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { canManageWorkspace } from '@/features/workspaces/lib/roles';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { CatalogApp } from '@/services/api/apps';
import { useApp } from '../hooks/useAppsQueries';
import {
  formatAppBillingLabel,
  localizeCatalogApp,
} from '../lib/billing-label';
import { AppBillingBadge } from './AppCard';
import { AppIcon } from './AppIcon';
import { AppInstallButton } from './AppInstallButton';
import { AppPlanCard } from './AppPlanCard';
import { AppSubscriptionStatus } from './AppSubscriptionStatus';
import { AppConnectionsPanel } from '../connections/components/AppConnectionsPanel';
import { AppSyncHistoryPanel } from '../connections/components/AppSyncHistoryPanel';

const SHEET_PANEL = floatingSheetPanel(
  'sm:w-[min(100%-2.5rem,36rem)]',
  'lg:w-[40rem]',
);

type AppDetailSheetProps = {
  slug: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function shouldShowPlans(app: CatalogApp): boolean {
  const access = app.access;
  if (app.plans.length === 0) return false;
  return (
    app.billing_type === 'free' ||
    (app.billing_type === 'one_time' && !access?.commercially_entitled) ||
    (app.billing_type === 'subscription' && Boolean(access?.can_purchase))
  );
}

function AppPlansSection({
  app,
  canManage,
  showTitle = true,
}: {
  app: CatalogApp;
  canManage: boolean;
  showTitle?: boolean;
}) {
  const { t } = useTranslation();
  if (!shouldShowPlans(app)) return null;
  return (
    <div className="space-y-3" data-testid="app-plans-section">
      {showTitle ? (
        <h3 className="text-sm font-semibold">
          {app.billing_type === 'subscription'
            ? t('apps.billing.selectPlan')
            : t('apps.plans')}
        </h3>
      ) : null}
      {app.plans.map((plan) => (
        <AppPlanCard
          key={plan.id}
          app={app}
          plan={plan}
          canManage={canManage}
        />
      ))}
    </div>
  );
}

export function AppDetailSheet({ slug, open, onOpenChange }: AppDetailSheetProps) {
  const { t } = useTranslation();
  const { currentMembership, currentWorkspace } = useWorkspace();
  const role = currentMembership?.role ?? currentWorkspace?.role;
  const canManage = canManageWorkspace(role);
  const query = useApp(open ? slug : undefined);
  const app = query.data;
  const localized = app ? localizeCatalogApp(app, t) : null;
  const categoryLabel = app
    ? t(app.category.name_key, { defaultValue: app.category.slug })
    : '';
  const access = app?.access;
  const showPlans = app ? shouldShowPlans(app) : false;
  const showSyncTab = Boolean(
    app?.connector &&
      app.connector.kind !== 'channel' &&
      app.connector.supports_sync,
  );
  const useConnectorTabs = Boolean(app?.connector && (showSyncTab || showPlans));
  const installed = app?.installation_status === 'active';
  const defaultTab = !installed && showPlans ? 'plans' : 'connections';

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="end" className={SHEET_PANEL} data-testid="app-detail-sheet">
        <SheetHeader className="border-b py-3.5 px-5 border-border text-start">
          <SheetTitle className="font-medium">
            {localized?.name ?? t('apps.title')}
          </SheetTitle>
        </SheetHeader>

        <SheetBody className="p-0 grow min-h-0">
          <ScrollArea className="h-full">
            <div className="p-5 space-y-5">
              {query.isLoading ? (
                <div className="space-y-4" data-testid="app-detail-loading">
                  <div className="flex gap-3">
                    <div className="size-12 rounded-xl bg-muted animate-pulse" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-1/2 rounded bg-muted animate-pulse" />
                      <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
                    </div>
                  </div>
                  <div className="h-24 rounded-xl bg-muted animate-pulse" />
                </div>
              ) : null}

              {query.isError ? (
                <p className="text-sm text-destructive" data-testid="app-detail-error">
                  {t(
                    errorMessageKey(
                      query.error instanceof ApiError
                        ? query.error.code
                        : 'not_found',
                    ),
                  )}
                </p>
              ) : null}

              {app && localized ? (
                <>
                  <div className="flex items-start gap-3">
                    <AppIcon
                      slug={app.slug}
                      name={localized.name}
                      iconUrl={app.icon_url}
                      size="lg"
                    />
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold tracking-tight">
                          {localized.name}
                        </h2>
                        <AppBillingBadge app={app} />
                        {access?.commercially_entitled &&
                        app.billing_type === 'one_time' ? (
                          <Badge variant="success" appearance="light" size="sm">
                            {t('apps.billing.purchased')}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="text-sm text-muted-foreground">{categoryLabel}</p>
                      <p className="text-sm text-muted-foreground">
                        {formatAppBillingLabel(app, t)}
                      </p>
                      {access?.status === 'entitled_not_installed' &&
                      app.billing_type === 'one_time' ? (
                        <p
                          className="text-sm text-muted-foreground"
                          data-testid="app-one-time-entitled-not-installed"
                        >
                          {t('apps.billing.entitledNotInstalled')}
                        </p>
                      ) : null}
                      {access?.commercially_entitled &&
                      app.billing_type === 'one_time' ? (
                        <p className="text-sm text-muted-foreground">
                          {t('apps.billing.lifetimeAccess')}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold">{t('apps.about')}</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
                      {localized.description ?? localized.shortDescription}
                    </p>
                  </div>

                  {installed && !app.connector ? (
                    <div
                      role="note"
                      className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
                    >
                      {t('apps.integrationLater')}
                    </div>
                  ) : null}

                  <AppSubscriptionStatus app={app} canManage={canManage} />

                  {useConnectorTabs ? (
                    <Tabs
                      key={`${app.slug}-${defaultTab}`}
                      defaultValue={defaultTab}
                      className="gap-3"
                      data-testid="app-detail-tabs"
                    >
                      <TabsList aria-label={t('apps.detailTabs')}>
                        <TabsTrigger
                          value="connections"
                          data-testid="app-tab-connections"
                        >
                          {t('apps.connections.title')}
                        </TabsTrigger>
                        {showSyncTab ? (
                          <TabsTrigger
                            value="sync"
                            data-testid="app-tab-sync"
                          >
                            {t('apps.connections.syncHistory')}
                          </TabsTrigger>
                        ) : null}
                        {showPlans ? (
                          <TabsTrigger
                            value="plans"
                            data-testid="app-tab-plans"
                          >
                            {app.billing_type === 'subscription'
                              ? t('apps.billing.selectPlan')
                              : t('apps.plans')}
                          </TabsTrigger>
                        ) : null}
                      </TabsList>

                      <TabsContent value="connections" className="space-y-3">
                        <AppConnectionsPanel
                          app={app}
                          canManage={canManage}
                          showTitle={false}
                          showSyncHistory={false}
                        />
                      </TabsContent>

                      {showSyncTab ? (
                        <TabsContent value="sync" className="space-y-3">
                          <AppSyncHistoryPanel app={app} />
                        </TabsContent>
                      ) : null}

                      {showPlans ? (
                        <TabsContent value="plans" className="space-y-3">
                          <AppPlansSection
                            app={app}
                            canManage={canManage}
                            showTitle={false}
                          />
                        </TabsContent>
                      ) : null}
                    </Tabs>
                  ) : app?.connector ? (
                    <AppConnectionsPanel app={app} canManage={canManage} />
                  ) : (
                    <AppPlansSection app={app} canManage={canManage} />
                  )}
                </>
              ) : null}
            </div>
          </ScrollArea>
        </SheetBody>

        {app ? (
          <SheetFooter className="flex-row border-t justify-end items-center p-5 border-border gap-2 sm:space-x-0">
            <AppInstallButton app={app} canManage={canManage} />
          </SheetFooter>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
