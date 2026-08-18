import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { AppIcon } from '@/features/apps/components/AppIcon';
import { cn } from '@/lib/utils';

type ConnectionsEmptyStateProps = {
  appSlug: string;
  appName: string;
  iconUrl?: string | null;
  title: string;
  hint?: string;
  canConnect: boolean;
  connectPending?: boolean;
  connectDisabled?: boolean;
  connectLabel: string;
  onConnect: () => void;
  footer?: ReactNode;
  className?: string;
};

export function ConnectionsEmptyState({
  appSlug,
  appName,
  iconUrl,
  title,
  hint,
  canConnect,
  connectPending,
  connectDisabled,
  connectLabel,
  onConnect,
  footer,
  className,
}: ConnectionsEmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border bg-muted/20 px-6 py-12 text-center',
        className,
      )}
      data-testid="connections-empty"
    >
      <div
        className="flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground"
        aria-hidden
      >
        <AppIcon
          slug={appSlug}
          name={appName}
          iconUrl={iconUrl}
          size="md"
          className="size-12 w-12 h-12 border-0 bg-transparent p-1.5 shadow-none grayscale opacity-55"
        />
      </div>
      <div className="space-y-1 max-w-sm">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {hint ? (
          <p className="text-xs text-muted-foreground leading-relaxed">{hint}</p>
        ) : null}
      </div>
      {canConnect ? (
        <Button
          size="sm"
          disabled={connectDisabled || connectPending}
          data-testid="connection-connect"
          onClick={onConnect}
        >
          {connectLabel}
        </Button>
      ) : null}
      {footer}
    </div>
  );
}
