import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export type AdminMetricTone = 'primary' | 'success' | 'warning' | 'info' | 'neutral';

const toneStyles: Record<AdminMetricTone, string> = {
  primary: 'bg-primary/10 text-primary',
  success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
  warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
  info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  neutral: 'bg-muted text-muted-foreground',
};

type AdminMetricCardProps = {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  tone?: AdminMetricTone;
  loading?: boolean;
  testId?: string;
  compactValue?: boolean;
  to?: string;
};

export function AdminMetricCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = 'primary',
  loading = false,
  testId,
  compactValue = false,
  to,
}: AdminMetricCardProps) {
  const card = (
    <Card
      className={cn(
        'min-h-[7.5rem] shadow-xs',
        to && 'transition-[box-shadow,background-color] hover:bg-muted/30 hover:shadow-sm',
      )}
      data-testid={testId}
    >
      <CardContent className="flex h-full items-start gap-4 p-4">
        <span
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-xl',
            toneStyles[tone],
          )}
        >
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          {loading ? (
            <div className="h-8 w-24 animate-pulse rounded-md bg-muted" />
          ) : (
            <p
              className={cn(
                'font-semibold leading-tight tracking-tight tabular-nums',
                compactValue ? 'text-sm sm:text-base' : 'text-2xl',
              )}
            >
              {value}
            </p>
          )}
          {hint ? (
            <p className="text-xs leading-5 text-muted-foreground/90">{hint}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );

  if (to) {
    return (
      <Link
        to={to}
        className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        {card}
      </Link>
    );
  }

  return card;
}

type AdminSnapshotStatProps = {
  label: string;
  value: string;
  testId?: string;
};

export function AdminSnapshotStat({ label, value, testId }: AdminSnapshotStatProps) {
  return (
    <div
      className="rounded-xl border border-border/70 bg-muted/20 p-3.5"
      data-testid={testId}
    >
      <p className="text-xs font-medium leading-5 text-muted-foreground">{label}</p>
      <p className="mt-1.5 text-xl font-semibold tabular-nums tracking-tight">{value}</p>
    </div>
  );
}
