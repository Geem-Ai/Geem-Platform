import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ApiUsagePeriodKey } from '@/services/api/api-keys';
import { API_USAGE_PERIODS, apiUsageHref } from '../lib/period';

type ApiUsagePeriodTabsProps = {
  period: ApiUsagePeriodKey;
  keyFilter: string | null;
};

export function ApiUsagePeriodTabs({ period, keyFilter }: ApiUsagePeriodTabsProps) {
  const { t } = useTranslation();

  return (
    <div
      className="inline-flex flex-wrap items-center gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5"
      role="tablist"
      aria-label={t('apiUsage.periodFilter')}
      data-testid="api-usage-period-filters"
    >
      {API_USAGE_PERIODS.map((value) => {
        const active = period === value;
        return (
          <Button
            key={value}
            variant="ghost"
            size="sm"
            asChild
            className={cn(
              'rounded-md',
              active
                ? 'bg-background text-foreground shadow-xs hover:bg-background'
                : 'text-muted-foreground',
            )}
          >
            <Link
              to={apiUsageHref(value, keyFilter, 1)}
              role="tab"
              aria-selected={active}
            >
              {t(`apiUsage.period.${value}`)}
            </Link>
          </Button>
        );
      })}
    </div>
  );
}
