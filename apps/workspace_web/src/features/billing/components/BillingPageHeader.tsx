import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function BillingPageHeader({
  eyebrow,
  title,
  description,
  onRefresh,
  refreshing,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        {eyebrow ? (
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
          {description}
        </p>
      </div>
      {onRefresh ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing}
          className="shrink-0 self-start"
        >
          <RefreshCw className={cn('size-3.5', refreshing && 'animate-spin')} />
          {t('billing.refresh')}
        </Button>
      ) : null}
    </div>
  );
}
