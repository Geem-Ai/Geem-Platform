import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { QrCode, Smartphone } from 'lucide-react';
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
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { invalidateAppsCache } from '@/features/apps/hooks/useAppsQueries';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  startWhatsAppConnection,
  type WhatsAppConnection,
  type WhatsAppConnectMode,
} from '@/services/api/apps';
import { queryKeys } from '@/services/api/query-keys';
import { isConnectingStatus } from '../lib';
import { WhatsAppPairingCodeStep } from './WhatsAppPairingCodeStep';
import { WhatsAppQrStep } from './WhatsAppQrStep';

type Step = 'choose' | 'qr' | 'pairing';

export function WhatsAppConnectDialog({
  appSlug,
  open,
  onOpenChange,
  resumeConnection = null,
}: {
  appSlug: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Existing connecting connection to resume (QR/pairing) without creating another. */
  resumeConnection?: WhatsAppConnection | null;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const openRef = useRef(open);
  openRef.current = open;

  const [step, setStep] = useState<Step>('choose');
  const [connection, setConnection] = useState<WhatsAppConnection | null>(null);

  const startMutation = useMutation({
    mutationFn: (mode: WhatsAppConnectMode) =>
      startWhatsAppConnection(appSlug, {
        connect_mode: mode,
        connection_id: resumeConnection?.id,
      }),
    onSuccess: async (result, mode) => {
      if (!openRef.current) {
        // Dialog closed while request was in flight — do not restore mid-flow UI.
        await Promise.all([
          invalidateAppsCache(queryClient, workspaceId, appSlug),
          queryClient.invalidateQueries({
            queryKey: queryKeys.appConnections(workspaceId, appSlug),
          }),
        ]);
        return;
      }
      setConnection(result);
      setStep(mode);
      await Promise.all([
        invalidateAppsCache(queryClient, workspaceId, appSlug),
        queryClient.invalidateQueries({
          queryKey: queryKeys.appConnections(workspaceId, appSlug),
        }),
      ]);
    },
  });

  useEffect(() => {
    if (!open) {
      setStep('choose');
      setConnection(null);
      startMutation.reset();
      return;
    }
    if (resumeConnection && isConnectingStatus(resumeConnection)) {
      setConnection(resumeConnection);
      const mode =
        resumeConnection.connect_mode === 'pairing' ? 'pairing' : 'qr';
      setStep(mode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resumeConnection?.id, resumeConnection?.connect_mode]);

  const errorKey =
    startMutation.error instanceof ApiError
      ? errorMessageKey(startMutation.error.code)
      : null;

  function handleReady(next: WhatsAppConnection) {
    setConnection(next);
    void queryClient.invalidateQueries({
      queryKey: queryKeys.appConnections(workspaceId, appSlug),
    });
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="whatsapp-connect-dialog">
        <DialogHeader>
          <DialogTitle>{t('apps.whatsapp.connect.title')}</DialogTitle>
          <DialogDescription>
            {step === 'choose'
              ? t('apps.whatsapp.connect.description')
              : t('apps.whatsapp.connect.followInstructions')}
          </DialogDescription>
        </DialogHeader>

        {step === 'choose' ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              className="flex flex-col items-start gap-2 rounded-xl border border-border p-4 text-start transition hover:bg-muted/40"
              data-testid="whatsapp-option-qr"
              disabled={startMutation.isPending}
              onClick={() => startMutation.mutate('qr')}
            >
              <QrCode className="size-6" aria-hidden />
              <span className="font-medium">{t('apps.whatsapp.connect.qrTitle')}</span>
              <span className="text-sm text-muted-foreground">
                {t('apps.whatsapp.connect.qrDescription')}
              </span>
            </button>
            <button
              type="button"
              className="flex flex-col items-start gap-2 rounded-xl border border-border p-4 text-start transition hover:bg-muted/40"
              data-testid="whatsapp-option-pairing"
              disabled={startMutation.isPending}
              onClick={() => startMutation.mutate('pairing')}
            >
              <Smartphone className="size-6" aria-hidden />
              <span className="font-medium">
                {t('apps.whatsapp.connect.pairingTitle')}
              </span>
              <span className="text-sm text-muted-foreground">
                {t('apps.whatsapp.connect.pairingDescription')}
              </span>
            </button>
          </div>
        ) : null}

        {step === 'qr' && connection ? (
          <WhatsAppQrStep
            appSlug={appSlug}
            initialConnection={connection}
            onReady={handleReady}
          />
        ) : null}

        {step === 'pairing' && connection ? (
          <WhatsAppPairingCodeStep
            appSlug={appSlug}
            initialConnection={connection}
            onReady={handleReady}
          />
        ) : null}

        {errorKey ? (
          <p className="text-sm text-destructive" role="alert">
            {t(errorKey)}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
