import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Activity } from 'lucide-react';
import { SimpleLineChart } from '@/components/charts/SimpleLineChart';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { formatTokens } from '@/lib/format';
import {
  fetchPlatformWorkspaceUsageSummary,
  fetchPlatformWorkspaceUsageTrend,
  platformQueryKeys,
  usageDatePreset,
} from '@/services/api/platform';

type WorkspaceUsageSectionProps = {
  workspaceId: string;
};

export function WorkspaceUsageSection({ workspaceId }: WorkspaceUsageSectionProps) {
  const { t, i18n } = useTranslation();
  const range = useMemo(() => usageDatePreset(30), []);

  const summaryQuery = useQuery({
    queryKey: platformQueryKeys.workspaceUsageSummary(workspaceId, range),
    queryFn: () => fetchPlatformWorkspaceUsageSummary(workspaceId, range),
    enabled: Boolean(workspaceId),
    staleTime: 60_000,
  });
  const trendQuery = useQuery({
    queryKey: platformQueryKeys.workspaceUsageTrend(workspaceId, range),
    queryFn: () => fetchPlatformWorkspaceUsageTrend(workspaceId, range),
    enabled: Boolean(workspaceId),
    staleTime: 60_000,
  });

  const chartPoints =
    trendQuery.data?.points.map((point) => ({ date: point.date, value: point.billed_tokens })) ?? [];

  return (
    <Card data-testid="workspace-usage-section">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="size-4" aria-hidden />
          {t('usage.workspaceSectionTitle')}
        </CardTitle>
        <CardDescription>
          {summaryQuery.data
            ? t('usage.workspaceSectionRange', {
                from: formatAdminDate(summaryQuery.data.from_day, i18n.language),
                to: formatAdminDate(summaryQuery.data.to_day, i18n.language),
              })
            : t('usage.workspaceSectionHint')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {summaryQuery.data ? (
          <p className="text-2xl font-semibold">
            {formatTokens(summaryQuery.data.total_billed_tokens, i18n.language)}
            <span className="ms-2 text-sm font-normal text-muted-foreground">
              {t('usage.summary.total')}
            </span>
          </p>
        ) : null}
        <SimpleLineChart
          points={chartPoints}
          locale={i18n.language}
          emptyLabel={t('usage.trendEmpty')}
          valueLabel={t('usage.trendTitle')}
          data-testid="workspace-usage-chart"
        />
      </CardContent>
    </Card>
  );
}
