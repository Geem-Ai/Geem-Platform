import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';
import {
  getWhatsAppQr,
  getWhatsAppStatus,
  type WhatsAppConnection,
} from '@/services/api/apps';
import { WhatsAppStatusBadge } from './WhatsAppStatusBadge';
import {
  isConnectingStatus,
  isReadyStatus,
  isTerminalStatus,
  normalizeProviderStatus,
} from '../lib';

export function WhatsAppQrStep({
  appSlug,
  initialConnection,
  onReady,
}: {
  appSlug: string;
  initialConnection: WhatsAppConnection;
  onReady?: (connection: WhatsAppConnection) => void;
}) {
  const { t } = useTranslation();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const [polling, setPolling] = useState(true);
  /** Persist last QR so status/query toggles do not blank the image. */
  const [qrCode, setQrCode] = useState<string | null>(null);
  const wasReadyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const statusQuery = useQuery({
    queryKey: queryKeys.appConnection(workspaceId, appSlug, initialConnection.id),
    queryFn: () => getWhatsAppStatus(appSlug, initialConnection.id),
    initialData: initialConnection,
    enabled: Boolean(workspaceId),
    refetchInterval: polling ? 2000 : false,
  });

  const connection = statusQuery.data ?? initialConnection;
  const provider = normalizeProviderStatus(connection.provider_status);
  const linking = isConnectingStatus(connection);
  const fetchQr = Boolean(workspaceId) && polling && provider === 'qr_ready';

  useEffect(() => {
    if (isTerminalStatus(connection) && !linking) {
      setPolling(false);
    }
    // Only provider `ready` closes the dialog — never Geem `active` alone.
    const ready = normalizeProviderStatus(connection.provider_status) === 'ready';
    if (ready && !wasReadyRef.current) {
      wasReadyRef.current = true;
      setPolling(false);
      onReadyRef.current?.(connection);
    }
    if (!ready) {
      wasReadyRef.current = false;
    }
  }, [connection, linking]);

  const qrQuery = useQuery({
    queryKey: queryKeys.appConnection(
      workspaceId,
      appSlug,
      `${initialConnection.id}:qr`,
    ),
    queryFn: () => getWhatsAppQr(appSlug, initialConnection.id),
    enabled: fetchQr,
    staleTime: 4_000,
    gcTime: 60_000,
    refetchInterval: fetchQr ? 5_000 : false,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  useEffect(() => {
    const next = qrQuery.data?.qr_code;
    if (next) {
      setQrCode(next);
    }
  }, [qrQuery.data?.qr_code]);

  const errorKey = (() => {
    if (statusQuery.error instanceof ApiError) {
      return errorMessageKey(statusQuery.error.code);
    }
    // Keep showing the last QR if a refresh fails (engine often rotates codes).
    if (!qrCode && qrQuery.error instanceof ApiError) {
      return errorMessageKey(qrQuery.error.code);
    }
    return null;
  })();

  const showQrImage = Boolean(qrCode) && !isReadyStatus(connection);

  return (
    <div className="space-y-4" data-testid="whatsapp-qr-step">
      <div className="flex flex-wrap items-center gap-2">
        <WhatsAppStatusBadge connection={connection} />
        {connection.phone ? (
          <span className="text-sm text-muted-foreground" data-testid="whatsapp-phone">
            {connection.phone}
          </span>
        ) : null}
      </div>

      <ol className="list-decimal space-y-1 ps-5 text-sm text-muted-foreground">
        <li>{t('apps.whatsapp.qr.step1')}</li>
        <li>{t('apps.whatsapp.qr.step2')}</li>
        <li>{t('apps.whatsapp.qr.step3')}</li>
      </ol>

      {showQrImage ? (
        <div className="flex justify-center rounded-xl border border-border bg-background p-4">
          <img
            src={qrCode!}
            alt={t('apps.whatsapp.qr.alt')}
            className="h-56 w-56"
            data-testid="whatsapp-qr-image"
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="whatsapp-qr-waiting">
          {t('apps.whatsapp.qr.waiting')}
        </p>
      )}

      {errorKey ? (
        <p className="text-sm text-destructive" role="alert">
          {t(errorKey)}
        </p>
      ) : null}
    </div>
  );
}
