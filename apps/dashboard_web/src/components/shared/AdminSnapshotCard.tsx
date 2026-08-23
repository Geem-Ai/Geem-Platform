import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';

type AdminCardTone = 'primary' | 'info' | 'success' | 'warning' | 'neutral';

const toneStyles: Record<AdminCardTone, string> = {
  primary: 'bg-primary/10 text-primary',
  info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
  warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
  neutral: 'bg-muted text-muted-foreground',
};

type AdminCardHeaderProps = {
  icon: LucideIcon;
  title: string;
  description?: string;
  tone?: AdminCardTone;
  trailing?: ReactNode;
};

export function AdminCardHeader({
  icon: Icon,
  title,
  description,
  tone = 'primary',
  trailing,
}: AdminCardHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 flex-1 items-start gap-4">
        <span
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-xl',
            toneStyles[tone],
          )}
        >
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 space-y-2">
          <h3 className="text-base font-semibold leading-tight tracking-tight text-foreground">
            {title}
          </h3>
          {description ? (
            <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
        </div>
      </div>
      {trailing ? <div className="shrink-0 self-center sm:self-start">{trailing}</div> : null}
    </div>
  );
}

type AdminSnapshotCardProps = {
  icon: LucideIcon;
  title: string;
  description?: string;
  testId?: string;
  children: ReactNode;
  tone?: AdminCardTone;
};

export function AdminSnapshotCard({
  icon: Icon,
  title,
  description,
  testId,
  children,
  tone = 'primary',
}: AdminSnapshotCardProps) {
  return (
    <Card className="shadow-xs" data-testid={testId}>
      <CardHeader className="space-y-0 px-5 pt-5 pb-4 sm:px-6">
        <AdminCardHeader icon={Icon} title={title} description={description} tone={tone} />
      </CardHeader>
      <CardContent className="grid gap-3 px-5 pb-5 sm:grid-cols-2 sm:px-6 sm:pb-6">
        {children}
      </CardContent>
    </Card>
  );
}
