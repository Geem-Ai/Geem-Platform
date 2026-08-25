import { ExternalLink, KeyRound, RefreshCw, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { MoneyAmount } from '@/features/billing/components/MoneyAmount';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { AppAccessStatus, CatalogApp } from '@/services/api/apps';
import { useAgentsAiUsage } from '../hooks/useAppsQueries';
import { localizeAppPlanName } from '../lib/billing-label';

const DEFAULT_CLIENT_AGENT_DOCS_URL =
  'https://github.com/Geem-Ai/Geem-Platform/blob/main/docs/integrations/client-agent-api.md';

function clientAgentDocsUrl(): string {
  return (
    import.meta.env.VITE_CLIENT_AGENT_DOCS_URL?.trim() ||
    DEFAULT_CLIENT_AGENT_DOCS_URL
  );
}

function formatDateTime(value: string | null | undefined, locale: string): string {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function statusVariant(
  status: AppAccessStatus,
): 'success' | 'warning' | 'secondary' | 'destructive' | 'info' {
  if (status === 'active') return 'success';
  if (status === 'expired') return 'destructive';
  if (status === 'entitled_not_installed') return 'warning';
  if (status === 'not_entitled') return 'info';
  return 'secondary';
}

function endpoint(baseUrl: string, leaf: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${leaf.replace(/^\/+/, '')}`;
}

export function AgentsAiPanel({ app }: { app: CatalogApp }) {
  const { t, i18n } = useTranslation();
  const published = app.status === 'published';
  const usageQuery = useAgentsAiUsage(published);
  const usage = usageQuery.data;

  if (!published) {
    return (
      <div
        role="note"
        className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
        data-testid="agents-ai-coming-soon"
      >
        {t('apps.agentsAi.comingSoonHint')}
      </div>
    );
  }

  if (usageQuery.isLoading) {
    return (
      <div className="space-y-3" data-testid="agents-ai-usage-loading">
        <div className="h-24 animate-pulse rounded-xl bg-muted" />
        <div className="h-32 animate-pulse rounded-xl bg-muted" />
      </div>
    );
  }

  if (usageQuery.isError || !usage) {
    const message =
      usageQuery.error instanceof ApiError
        ? t(errorMessageKey(usageQuery.error.code))
        : t('apps.agentsAi.usageLoadError');
    return (
      <div
        className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 space-y-3"
        data-testid="agents-ai-usage-error"
      >
        <p className="text-sm text-destructive">{message}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void usageQuery.refetch()}
        >
          <RefreshCw className="size-3.5" aria-hidden />
          {t('apps.retry')}
        </Button>
      </div>
    );
  }

  const access = usage.access;
  const daily = usage.agent_requests_daily;
  const planName =
    localizeAppPlanName(access.plan_code, access.plan_name, t) ??
    t('apps.agentsAi.noPlan');
  const currentPlan = app.plans.find(
    (plan) =>
      (access.plan_id != null && plan.id === access.plan_id) ||
      (access.plan_code != null && plan.code === access.plan_code),
  );
  // The usage authority carries the subscribed plan's commercial display
  // fields even after that tier stops accepting new sales. Fall back to the
  // catalog plan for a rolling deployment with an older usage response.
  const planPriceAmount =
    access.plan_price_amount ?? currentPlan?.price_amount ?? null;
  const planCurrency = access.plan_currency ?? currentPlan?.currency ?? null;
  const planBillingInterval =
    access.plan_billing_interval ?? currentPlan?.billing_interval ?? null;
  const percent = daily.limit > 0 ? (daily.used / daily.limit) * 100 : 0;
  const number = new Intl.NumberFormat(i18n.language);
  const modelsUrl = endpoint(usage.base_url, 'models');

  return (
    <div className="space-y-4" data-testid="agents-ai-panel">
      <section className="rounded-xl border border-border p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t('apps.agentsAi.accessTitle')}</h3>
          <Badge
            variant={statusVariant(access.status)}
            appearance="light"
            size="sm"
            data-testid={`agents-ai-access-${access.status}`}
          >
            {t(`apps.agentsAi.accessStatus.${access.status}`)}
          </Badge>
        </div>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.plan')}
            </dt>
            <dd className="flex flex-wrap items-center gap-1 font-medium">
              <span>{planName}</span>
              {planPriceAmount &&
              planCurrency &&
              Number(planPriceAmount) > 0 ? (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <span aria-hidden>·</span>
                  <MoneyAmount
                    amount={planPriceAmount}
                    currency={planCurrency}
                  />
                  {planBillingInterval === 'monthly' ? (
                    <span>{t('apps.billing.perMonth')}</span>
                  ) : null}
                </span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.installation')}
            </dt>
            <dd className="font-medium">
              {access.installed
                ? t('apps.agentsAi.installedState')
                : t('apps.agentsAi.notInstalledState')}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.periodStart')}
            </dt>
            <dd>{formatDateTime(access.current_period_start, i18n.language)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.periodEnd')}
            </dt>
            <dd>{formatDateTime(access.current_period_end, i18n.language)}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded-xl border border-border p-4 space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold">{t('apps.agentsAi.usageTitle')}</h3>
            <p className="text-xs text-muted-foreground">
              {t('apps.agentsAi.usageHint')}
            </p>
          </div>
          <p className="text-sm font-semibold tabular-nums" data-testid="agents-ai-daily-usage">
            {t('apps.agentsAi.usageValue', {
              used: number.format(daily.used),
              limit: number.format(daily.limit),
            })}
          </p>
        </div>
        <Progress
          value={percent}
          label={t('apps.agentsAi.usageProgressLabel')}
          data-testid="agents-ai-usage-progress"
          indicatorClassName={
            daily.limit > 0 && daily.used >= daily.limit
              ? 'bg-destructive'
              : undefined
          }
        />
        <p className="text-xs text-muted-foreground" data-testid="agents-ai-reset-at">
          {t('apps.agentsAi.resetsAt', {
            date: formatDateTime(daily.reset_at, i18n.language),
          })}
        </p>
      </section>

      <section className="rounded-xl border border-border p-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold">{t('apps.agentsAi.integrationTitle')}</h3>
          <p className="text-xs text-muted-foreground">
            {t('apps.agentsAi.integrationHint')}
          </p>
        </div>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.baseUrl')}
            </dt>
            <dd>
              <code dir="ltr" className="block break-all text-xs font-mono">
                {usage.base_url}
              </code>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.modelsEndpoint')}
            </dt>
            <dd>
              <code dir="ltr" className="block break-all text-xs font-mono">
                {modelsUrl}
              </code>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              {t('apps.agentsAi.model')}
            </dt>
            <dd>
              <code dir="ltr" className="block break-all text-xs font-mono">
                {usage.model}
              </code>
            </dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button asChild variant="outline" size="sm">
            <Link to="/api/keys">
              <KeyRound className="size-3.5" aria-hidden />
              {t('apps.agentsAi.manageKeys')}
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to="/experts">
              <Users className="size-3.5" aria-hidden />
              {t('apps.agentsAi.manageExperts')}
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={clientAgentDocsUrl()} target="_blank" rel="noreferrer">
              <ExternalLink className="size-3.5" aria-hidden />
              {t('apps.agentsAi.documentation')}
            </a>
          </Button>
        </div>
      </section>
    </div>
  );
}
