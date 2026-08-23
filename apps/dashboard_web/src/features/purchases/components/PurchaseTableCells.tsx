import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AppWindow, ExternalLink } from 'lucide-react';
import {
  isAppPurchaseKind,
  purchaseAppHref,
  purchaseProductLabel,
} from '@/features/purchases/lib/labels';
import { cn } from '@/lib/utils';
import type { PlatformPurchaseTarget, PlatformPurchaseWorkspace } from '@/services/api/types';

const linkClassName =
  'group inline-flex min-w-0 max-w-full items-start gap-2 rounded-md text-start transition-colors hover:text-primary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring';

export function PurchaseWorkspaceCell({ workspace }: { workspace: PlatformPurchaseWorkspace }) {
  const { t } = useTranslation();

  return (
    <Link
      to={`/workspaces/${workspace.id}`}
      className={linkClassName}
      aria-label={t('purchases.viewWorkspace', { name: workspace.name })}
      data-testid={`purchase-workspace-link-${workspace.id}`}
      onClick={(event) => event.stopPropagation()}
    >
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium group-hover:underline">
          {workspace.name}
        </span>
        <span className="mt-0.5 block truncate font-mono text-xs text-muted-foreground">
          {workspace.slug}
        </span>
      </span>
      <ExternalLink
        className="mt-1 size-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        aria-hidden
      />
    </Link>
  );
}

export function PurchaseProductCell({
  kind,
  target,
}: {
  kind: string;
  target: PlatformPurchaseTarget;
}) {
  const { t } = useTranslation();
  const label = purchaseProductLabel(target);
  const href = isAppPurchaseKind(kind) ? purchaseAppHref(target) : null;

  if (!href) {
    return <span className="block max-w-[220px] truncate text-sm">{label}</span>;
  }

  return (
    <Link
      to={href}
      className={cn(linkClassName, 'max-w-[240px]')}
      aria-label={t('purchases.viewApp', { name: target.app_name ?? label })}
      data-testid={`purchase-app-link-${target.app_id ?? target.app_slug ?? 'unknown'}`}
      onClick={(event) => event.stopPropagation()}
    >
      <span
        className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/60 dark:text-violet-300"
        aria-hidden
      >
        <AppWindow className="size-4" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium group-hover:underline">{label}</span>
        {target.app_slug ? (
          <span className="mt-0.5 block truncate font-mono text-xs text-muted-foreground">
            {target.app_slug}
          </span>
        ) : null}
      </span>
      <ExternalLink
        className="mt-1 size-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        aria-hidden
      />
    </Link>
  );
}
