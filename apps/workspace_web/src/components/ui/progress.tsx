import * as React from 'react';
import { cn } from '@/lib/utils';

type ProgressProps = React.ComponentProps<'div'> & {
  value?: number;
  /** Accessible label describing the progress. */
  label?: string;
  indicatorClassName?: string;
};

/**
 * Lightweight progress bar (0–100). No third-party dependency.
 */
function Progress({
  value = 0,
  label,
  className,
  indicatorClassName,
  ...props
}: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      aria-label={label}
      data-slot="progress"
      className={cn(
        'relative h-2 w-full overflow-hidden rounded-full bg-muted',
        className,
      )}
      {...props}
    >
      <div
        data-slot="progress-indicator"
        className={cn(
          'h-full rounded-full bg-primary transition-[width] duration-500 ease-out',
          indicatorClassName,
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export { Progress };
