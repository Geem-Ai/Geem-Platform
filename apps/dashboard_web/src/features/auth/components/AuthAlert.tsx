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
        'flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-start text-sm leading-5',
        tone === 'warning'
          ? 'border-amber-500/30 bg-amber-50 text-amber-950 dark:bg-amber-500/10 dark:text-amber-100'
          : 'border-destructive/35 bg-destructive/5 text-destructive dark:bg-destructive/10',
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0">{children}</p>
    </div>
  );
}
