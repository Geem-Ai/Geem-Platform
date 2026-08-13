import type { ReactNode } from 'react';
import { AlertTriangle, CircleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';

type AuthAlertProps = {
  tone?: 'error' | 'warning';
  children: ReactNode;
};

export function AuthAlert({ tone = 'error', children }: AuthAlertProps) {
  const Icon = tone === 'warning' ? AlertTriangle : CircleAlert;

  return (
    <div
      role="alert"
      data-testid="auth-alert"
      data-tone={tone}
      className={cn(
        'flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm leading-5',
        tone === 'warning'
          ? 'border-yellow-500/35 bg-yellow-50 text-yellow-950 dark:border-yellow-500/30 dark:bg-yellow-500/10 dark:text-yellow-50'
          : 'border-destructive/40 bg-destructive/5 text-destructive',
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0">{children}</p>
    </div>
  );
}
