import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { errorMessageKey, isQuotaErrorCode, type ApiErrorCode } from '@/services/api/errors';
import { usePermissions } from '@/features/authz/usePermissions';
import { WorkspacePermission } from '@/features/authz/permissions';
import type { QuotaWarningLevel } from '../lib/quota';

function hintKeyForCode(code: ApiErrorCode): string {
  if (code === 'expert_limit_reached') return 'quota.expertHint';
  if (code === 'storage_quota_exceeded') return 'quota.storageHint';
  return 'quota.chatHint';
}

type QuotaAlertProps = {
  level?: QuotaWarningLevel;
  code?: ApiErrorCode | null;
  title?: string;
  description?: string;
  showUsageLink?: boolean;
  compact?: boolean;
  className?: string;
};

export function QuotaAlert({
  level,
  code,
  title,
  description,
  showUsageLink = true,
  compact = false,
  className,
}: QuotaAlertProps) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const manage = can(WorkspacePermission.BILLING_MANAGE);

  const resolvedLevel: QuotaWarningLevel =
    level ??
    (code && isQuotaErrorCode(code) ? 'exhausted' : 'approaching');

  const heading =
    title ??
    (code ? t(errorMessageKey(code)) : t(`usage.warning.${resolvedLevel}`));
  const body =
    description ??
    (code ? t(hintKeyForCode(code)) : undefined);

  const tone =
    resolvedLevel === 'exhausted' || resolvedLevel === 'critical'
      ? 'destructive'
      : 'warning';

  return (
    <div
      role="alert"
      data-testid="quota-alert"
      data-level={resolvedLevel}
      data-code={code ?? undefined}
      className={cn(
        'rounded-xl border px-4 py-3 text-sm',
        tone === 'destructive'
          ? 'border-destructive/40 bg-destructive/5 text-destructive'
          : 'border-[var(--color-warning-accent,var(--color-yellow-500))]/40 bg-[var(--color-warning-soft,var(--color-yellow-100))]/60 text-foreground',
        compact && 'px-3 py-2 text-xs',
        className,
      )}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="size-4 shrink-0 mt-0.5" aria-hidden />
        <div className="min-w-0 space-y-1">
          <p className="font-medium leading-5">{heading}</p>
          {body ? <p className="text-muted-foreground leading-5">{body}</p> : null}
          {showUsageLink && manage ? (
            <Link
              to="/billing/usage"
              className="inline-flex text-xs font-medium underline-offset-2 hover:underline"
            >
              {t('usage.viewUsage')}
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  );
}
