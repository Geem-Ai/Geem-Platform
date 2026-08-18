import type { TFunction } from 'i18next';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { Meter } from '@/services/api/usage';
import {
  DAY_MS,
  formatBytesLabel,
  formatCount,
  formatPeriodDateTime,
  isUnlimitedLimit,
  meterPercentage,
  meterWarningLevel,
  quotaProgressClass,
  remainingHoursMinutes,
  type QuotaWarningLevel,
  type RemainingHoursMinutes,
} from '../lib/quota';

type QuotaMeterProps = {
  title: string;
  meter: Meter;
  testId: string;
  format?: 'count' | 'bytes' | 'tokens';
  compact?: boolean;
  layout?: 'card' | 'row';
  icon?: LucideIcon;
  className?: string;
  /** Relative countdown: days when ≥24h, otherwise hours and minutes. */
  resetDisplay?: 'absolute' | 'countdown';
};

function resetCountdownLabel(
  remaining: RemainingHoursMinutes | null,
  t: TFunction,
): string {
  if (!remaining || remaining.totalMs < 60_000) {
    return t('usage.periodResetsSoon');
  }
  if (remaining.totalMs >= DAY_MS) {
    return t('usage.periodResetsIn', {
      duration: t('usage.day', { count: remaining.days }),
    });
  }
  const hoursLabel = t('usage.hour', { count: remaining.hours });
  const minutesLabel = t('usage.minute', { count: remaining.minutes });
  if (remaining.hours > 0 && remaining.minutes > 0) {
    return t('usage.periodResetsInCompound', {
      hours: hoursLabel,
      minutes: minutesLabel,
    });
  }
  if (remaining.hours > 0) {
    return t('usage.periodResetsIn', { duration: hoursLabel });
  }
  return t('usage.periodResetsIn', { duration: minutesLabel });
}

function statusBadgeVariant(
  level: QuotaWarningLevel,
): 'secondary' | 'warning' | 'destructive' | 'success' {
  if (level === 'exhausted' || level === 'critical') return 'destructive';
  if (level === 'approaching') return 'warning';
  return 'success';
}

export function QuotaMeter({
  title,
  meter,
  testId,
  format = 'count',
  compact = false,
  layout = 'card',
  icon: Icon,
  className,
  resetDisplay = 'absolute',
}: QuotaMeterProps) {
  const { t, i18n } = useTranslation();
  const unlimited = isUnlimitedLimit(meter.limit);
  const level = meterWarningLevel(meter);
  const pct = unlimited
    ? 0
    : meterPercentage(meter.used, meter.limit, meter.reserved);
  const formatValue = (n: number) =>
    format === 'bytes'
      ? formatBytesLabel(n, i18n.language, (unit) => t(`usage.units.${unit}`))
      : formatCount(n, i18n.language);
  const periodEndAbsolute = formatPeriodDateTime(meter.period_end, i18n.language);
  const periodEndLabel =
    resetDisplay === 'countdown' && meter.period_end
      ? resetCountdownLabel(remainingHoursMinutes(meter.period_end), t)
      : periodEndAbsolute
        ? t('usage.periodEnds', { time: periodEndAbsolute })
        : null;
  const showBadge = level !== 'normal';

  const status = (
    <span data-testid={`${testId}-level`} data-level={level}>
      {showBadge ? (
        <Badge variant={statusBadgeVariant(level)} appearance="light" size="sm">
          {t(`usage.warning.${level}`)}
        </Badge>
      ) : (
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {t('usage.warning.healthy')}
        </span>
      )}
    </span>
  );

  const progress =
    unlimited || meter.limit <= 0 ? null : (
      <Progress
        value={pct}
        label={title}
        className={cn(layout === 'row' ? 'h-1.5' : 'h-2')}
        indicatorClassName={quotaProgressClass(level)}
      />
    );

  const stats = (
    <dl
      className={cn(
        'grid gap-x-4 gap-y-1 text-xs',
        layout === 'row' ? 'grid-cols-3 sm:grid-cols-4' : 'grid-cols-2 sm:grid-cols-4',
      )}
    >
      <div>
        <dt className="text-muted-foreground">{t('usage.used')}</dt>
        <dd className="font-medium tabular-nums mt-0.5" data-testid={`${testId}-used`}>
          {formatValue(meter.used)}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">{t('usage.limit')}</dt>
        <dd className="font-medium tabular-nums mt-0.5" data-testid={`${testId}-limit`}>
          {unlimited ? t('usage.unlimited') : formatValue(meter.limit)}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">{t('usage.remaining')}</dt>
        <dd className="font-medium tabular-nums mt-0.5" data-testid={`${testId}-remaining`}>
          {unlimited ? t('usage.unlimited') : formatValue(meter.remaining)}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">{t('usage.percentage')}</dt>
        <dd className="font-medium tabular-nums mt-0.5" data-testid={`${testId}-percentage`}>
          {unlimited ? '—' : `${Math.round(pct)}%`}
        </dd>
      </div>
    </dl>
  );

  const caption = (
    <>
      {unlimited ? (
        <CardDescription>{t('usage.unlimited')}</CardDescription>
      ) : meter.limit <= 0 ? (
        <CardDescription>{t('usage.noAllowance')}</CardDescription>
      ) : null}
      {periodEndLabel ? (
        <p
          className="text-xs text-muted-foreground"
          data-testid={`${testId}-period`}
          title={resetDisplay === 'countdown' ? (periodEndAbsolute ?? undefined) : undefined}
        >
          {periodEndLabel}
        </p>
      ) : null}
      {format === 'bytes' && !unlimited ? (
        <p className="text-xs text-muted-foreground tabular-nums">
          {t('usage.exactBytes', { bytes: formatCount(meter.used, i18n.language) })}
        </p>
      ) : null}
    </>
  );

  if (layout === 'row') {
    return (
      <div
        data-testid={testId}
        className={cn('px-5 py-4 space-y-3', className)}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            {Icon ? (
              <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <Icon className="size-3.5" aria-hidden />
              </div>
            ) : null}
            <div className="min-w-0">
              <p className="text-sm font-medium leading-none">{title}</p>
              {!unlimited && meter.limit > 0 ? (
                <p className="text-xs text-muted-foreground mt-1.5 tabular-nums">
                  {formatValue(meter.used)}
                  <span className="text-muted-foreground/80"> / {formatValue(meter.limit)}</span>
                </p>
              ) : null}
            </div>
          </div>
          {status}
        </div>
        {progress}
        {stats}
        {caption}
      </div>
    );
  }

  return (
    <Card
      className={cn(compact ? 'shadow-none' : 'shadow-xs', className)}
      data-testid={testId}
    >
      <CardHeader className={cn(compact ? 'min-h-0 py-3 px-4' : 'min-h-14')}>
        <div className="flex items-center gap-2.5 min-w-0">
          {Icon ? (
            <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Icon className="size-3.5" aria-hidden />
            </div>
          ) : null}
          <CardTitle className="text-sm">{title}</CardTitle>
        </div>
        {status}
      </CardHeader>
      <CardContent className={cn(compact ? 'px-4 pb-4 pt-0 space-y-3' : 'space-y-4')}>
        {!unlimited && meter.limit > 0 ? (
          <div>
            <p className="text-2xl font-semibold tracking-tight tabular-nums leading-none">
              {formatValue(meter.used)}
            </p>
            <p className="text-xs text-muted-foreground mt-1.5">
              {t('usage.ofLimit', { limit: formatValue(meter.limit) })}
            </p>
          </div>
        ) : null}
        {progress}
        {stats}
        {caption}
      </CardContent>
    </Card>
  );
}
