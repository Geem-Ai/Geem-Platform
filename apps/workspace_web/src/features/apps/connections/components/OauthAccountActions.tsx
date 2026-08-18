import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { AppConnection } from '@/services/api/apps';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  useDisconnectConnection,
  useStartConnection,
} from '../hooks/useConnectionQueries';

function oauthReturnPath(slug: string, fallback?: string): string {
  return fallback || `/apps/${slug}`;
}

/**
 * Disconnect and/or reconnect an OAuth knowledge-source account
 * (Google Drive, OneDrive) so the user can pick a different email.
 */
export function OauthAccountActions({
  connection,
  returnPath,
  showSwitch = true,
  showDisconnect = true,
  compact = false,
  inline = false,
}: {
  connection: AppConnection;
  returnPath?: string;
  showSwitch?: boolean;
  showDisconnect?: boolean;
  compact?: boolean;
  /** Render confirm in place (avoids nested dialogs). */
  inline?: boolean;
}) {
  const { t } = useTranslation();
  const disconnect = useDisconnectConnection();
  const start = useStartConnection();
  const [mode, setMode] = useState<'switch' | 'disconnect' | null>(null);
  const pending = disconnect.isPending || start.isPending;
  const slug = connection.app_slug;
  const path = oauthReturnPath(slug, returnPath);
  const canDisconnect = connection.capabilities.can_disconnect;
  const switchVariant = compact ? 'ghost' : 'outline';

  const error =
    disconnect.isError || start.isError
      ? t(
          errorMessageKey(
            disconnect.error instanceof ApiError
              ? disconnect.error.code
              : start.error instanceof ApiError
                ? start.error.code
                : 'unknown',
          ),
        )
      : null;

  function startOAuth() {
    start.mutate(
      {
        slug,
        connectionId: connection.id,
        returnPath: path,
      },
      {
        onSuccess: (data) => {
          if (data.authorization_url) {
            window.location.assign(data.authorization_url);
            return;
          }
          setMode(null);
        },
      },
    );
  }

  function confirm() {
    disconnect.mutate(
      { slug, connectionId: connection.id },
      {
        onSuccess: () => {
          if (mode === 'switch') {
            startOAuth();
            return;
          }
          setMode(null);
        },
      },
    );
  }

  if (!canDisconnect || (!showSwitch && !showDisconnect)) {
    return null;
  }

  const confirmTitle =
    mode === 'switch'
      ? t('apps.connections.switchAccountTitle')
      : t('apps.connections.disconnectTitle');
  const confirmHint =
    mode === 'switch'
      ? t('apps.connections.switchAccountHint')
      : t('apps.connections.disconnectHint');
  const confirmTestId =
    mode === 'switch'
      ? 'connection-switch-account-confirm'
      : 'connection-disconnect-confirm';
  const confirmLabel =
    mode === 'switch'
      ? t('apps.connections.switchAccount')
      : t('apps.connections.disconnect');

  if (inline && mode) {
    return (
      <div className="space-y-2" data-testid="connection-account-confirm-inline">
        <p className="text-sm font-medium">{confirmTitle}</p>
        <p className="text-xs text-muted-foreground">{confirmHint}</p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setMode(null)}
            disabled={pending}
          >
            {t('common.cancel')}
          </Button>
          <Button
            size="sm"
            variant={mode === 'disconnect' ? 'destructive' : 'primary'}
            disabled={pending}
            data-testid={confirmTestId}
            onClick={confirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <>
      {showSwitch ? (
        <Button
          size="sm"
          variant={switchVariant}
          disabled={pending}
          onClick={() => setMode('switch')}
          data-testid="connection-switch-account"
        >
          {t('apps.connections.switchAccount')}
        </Button>
      ) : null}
      {showDisconnect ? (
        <Button
          size="sm"
          variant={compact ? 'ghost' : 'destructive'}
          disabled={pending}
          onClick={() => setMode('disconnect')}
          data-testid="connection-disconnect"
        >
          {t('apps.connections.disconnect')}
        </Button>
      ) : null}

      <Dialog open={mode !== null} onOpenChange={(open) => !open && setMode(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmTitle}</DialogTitle>
            <DialogDescription>{confirmHint}</DialogDescription>
          </DialogHeader>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setMode(null)} disabled={pending}>
              {t('common.cancel')}
            </Button>
            <Button
              variant={mode === 'disconnect' ? 'destructive' : 'primary'}
              disabled={pending}
              data-testid={confirmTestId}
              onClick={confirm}
            >
              {confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
