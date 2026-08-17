import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { CatalogApp } from '@/services/api/apps';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { localizeCatalogApp } from '../lib/billing-label';
import { useInstallApp, useUninstallApp } from '../hooks/useAppsQueries';
import { useState } from 'react';

export function AppInstallButton({
  app,
  canManage,
  size = 'default',
  className,
}: {
  app: CatalogApp;
  canManage: boolean;
  size?: 'sm' | 'default';
  className?: string;
}) {
  const { t } = useTranslation();
  const install = useInstallApp();
  const uninstall = useUninstallApp();
  const [confirm, setConfirm] = useState<'install' | 'uninstall' | null>(null);
  const localized = localizeCatalogApp(app, t);
  const access = app.access;

  if (app.status === 'coming_soon') {
    return (
      <Button
        type="button"
        disabled
        size={size}
        className={className}
        data-testid="app-coming-soon"
      >
        {t('apps.comingSoon')}
      </Button>
    );
  }

  // One-time licensed but not purchasing again
  if (
    app.billing_type === 'one_time' &&
    access?.commercially_entitled &&
    !access.can_install &&
    !access.can_uninstall
  ) {
    return (
      <Button
        type="button"
        disabled
        variant="outline"
        size={size}
        className={className}
        data-testid="app-purchased"
      >
        {t('apps.billing.purchased')}
      </Button>
    );
  }

  // Purchasing CTAs live on plan cards / subscription status panels.
  if (
    (app.billing_type === 'one_time' || app.billing_type === 'subscription') &&
    access?.can_purchase &&
    !access.can_install
  ) {
    return null;
  }

  if (!canManage) {
    if (app.installation_status === 'active') {
      return (
        <Button
          type="button"
          disabled
          variant="outline"
          size={size}
          className={className}
          data-testid="app-installed-readonly"
        >
          {t('apps.installed')}
        </Button>
      );
    }
    return (
      <p className="text-sm text-muted-foreground" data-testid="app-member-hint">
        {t('apps.memberHint')}
      </p>
    );
  }

  const pending = install.isPending || uninstall.isPending;
  const canInstall = access?.can_install ?? app.can_install;
  const canUninstall = access?.can_uninstall ?? app.can_uninstall;

  async function onConfirm() {
    try {
      if (confirm === 'install') {
        await install.mutateAsync(app.slug);
        toast.success(t('apps.toasts.installed', { name: localized.name }));
      } else if (confirm === 'uninstall') {
        await uninstall.mutateAsync(app.slug);
        toast.success(t('apps.toasts.uninstalled', { name: localized.name }));
      }
      setConfirm(null);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'unknown';
      toast.error(t(errorMessageKey(code)));
    }
  }

  return (
    <>
      {canUninstall ? (
        <Button
          type="button"
          variant="outline"
          size={size}
          className={className}
          disabled={pending}
          data-testid="app-uninstall"
          onClick={() => setConfirm('uninstall')}
        >
          {pending && uninstall.isPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : null}
          {t('apps.uninstall')}
        </Button>
      ) : null}
      {canInstall ? (
        <Button
          type="button"
          size={size}
          className={className}
          disabled={pending}
          data-testid="app-install"
          onClick={() => setConfirm('install')}
        >
          {pending && install.isPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : null}
          {access?.commercially_entitled && app.billing_type !== 'free'
            ? t('apps.install')
            : t('apps.install')}
        </Button>
      ) : null}
      {app.installation_status === 'active' && !canUninstall && !canInstall ? (
        <Button type="button" disabled variant="outline" size={size} className={className}>
          {t('apps.installed')}
        </Button>
      ) : null}

      <Dialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!pending && !open) setConfirm(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {confirm === 'uninstall'
                ? t('apps.uninstallTitle', { name: localized.name })
                : t('apps.installTitle', { name: localized.name })}
            </DialogTitle>
            <DialogDescription>
              {confirm === 'uninstall'
                ? t('apps.uninstallHint')
                : t('apps.installHint')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => setConfirm(null)}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              variant={confirm === 'uninstall' ? 'destructive' : 'primary'}
              disabled={pending}
              data-testid="app-confirm-action"
              onClick={() => void onConfirm()}
            >
              {pending ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : null}
              {confirm === 'uninstall' ? t('apps.uninstall') : t('apps.install')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
