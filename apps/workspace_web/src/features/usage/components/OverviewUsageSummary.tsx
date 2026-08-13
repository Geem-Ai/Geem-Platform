import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useSubscription, useUsageSummary } from '../hooks/useUsageQueries';
import {
  formatBytesLabel,
  formatCount,
  meterPercentage,
  meterWarningLevel,
  quotaProgressClass,
  type ByteUnitKey,
} from '../lib/quota';

export function OverviewUsageSummary() {
  const { t, i18n } = useTranslation();
  const summaryQuery = useUsageSummary();
  const subscriptionQuery = useSubscription();
  const summary = summaryQuery.data;
  const subscription = subscriptionQuery.data;

  if (summaryQuery.isLoading || !summary) {
    return null;
  }

  const monthly = summary.ai.monthly;
  const monthlyPct = meterPercentage(
    monthly.used,
    monthly.limit,
    monthly.reserved,
  );
  const storagePct = meterPercentage(
    summary.storage.used_bytes,
    summary.storage.limit_bytes,
    summary.storage.reserved_bytes,
  );
  const byteUnit = (unit: ByteUnitKey) => t(`usage.units.${unit}`);

  return (
    <Card data-testid="overview-usage">
      <CardHeader>
        <CardTitle>{t('overview.usageTitle')}</CardTitle>
        <CardDescription>{t('overview.usageDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {subscription ? (
          <p className="text-sm">
            <span className="text-muted-foreground">{t('usage.plan')}: </span>
            <span className="font-medium">{subscription.plan.name}</span>
          </p>
        ) : null}

        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span>{t('usage.monthly')}</span>
            <span className="tabular-nums text-muted-foreground">
              {formatCount(monthly.used, i18n.language)} /{' '}
              {formatCount(monthly.limit, i18n.language)}
            </span>
          </div>
          <Progress
            value={monthlyPct}
            label={t('usage.monthly')}
            indicatorClassName={quotaProgressClass(meterWarningLevel(monthly))}
          />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span>{t('usage.storage')}</span>
            <span className="tabular-nums text-muted-foreground">
              {formatBytesLabel(summary.storage.used_bytes, i18n.language, byteUnit)}{' '}
              /{' '}
              {formatBytesLabel(summary.storage.limit_bytes, i18n.language, byteUnit)}
            </span>
          </div>
          <Progress
            value={storagePct}
            label={t('usage.storage')}
            indicatorClassName={quotaProgressClass(
              meterWarningLevel({
                ...summary.storage_bytes,
                used: summary.storage.used_bytes,
                limit: summary.storage.limit_bytes,
                remaining: summary.storage.remaining_bytes,
                reserved: summary.storage.reserved_bytes,
              }),
            )}
          />
        </div>

        <Button asChild variant="outline" size="sm">
          <Link to="/billing/usage">{t('overview.viewUsage')}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
