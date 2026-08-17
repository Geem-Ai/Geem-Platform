import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { copyText } from '@/lib/clipboard';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';
import {
  getWhatsAppStatus,
  requestWhatsAppPairingCode,
  type WhatsAppConnection,
  type WhatsAppPairingCodeResponse,
} from '@/services/api/apps';
import { WhatsAppStatusBadge } from './WhatsAppStatusBadge';
import {
  formatPairingCode,
  isTerminalStatus,
  normalizePhoneForRequest,
  normalizeProviderStatus,
} from '../lib';

export function WhatsAppPairingCodeStep({
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
  const [phoneNumber, setPhoneNumber] = useState('');
  const [polling, setPolling] = useState(true);
  const [pairing, setPairing] = useState<WhatsAppPairingCodeResponse | null>(null);
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

  useEffect(() => {
    if (isTerminalStatus(connection)) {
      setPolling(false);
    }
    const ready = normalizeProviderStatus(connection.provider_status) === 'ready';
    if (ready && !wasReadyRef.current) {
      wasReadyRef.current = true;
      setPairing(null);
      onReadyRef.current?.(connection);
    }
    if (!ready) {
      wasReadyRef.current = false;
    }
  }, [connection]);

  const pairingMutation = useMutation({
    mutationFn: (payload: { phone_number: string }) =>
      requestWhatsAppPairingCode(appSlug, initialConnection.id, payload),
    onSuccess: (result) => setPairing(result),
  });

  const errorKey =
    statusQuery.error instanceof ApiError
      ? errorMessageKey(statusQuery.error.code)
      : pairingMutation.error instanceof ApiError
        ? errorMessageKey(pairingMutation.error.code)
        : null;

  async function handleCopy() {
    if (!pairing?.pairing_code) return;
    const ok = await copyText(pairing.pairing_code);
    if (ok) {
      toast.success(t('apps.whatsapp.pairing.copySuccess'));
      return;
    }
    toast.error(t('apps.whatsapp.pairing.copyFailed'));
  }

  return (
    <div className="space-y-4" data-testid="whatsapp-pairing-step">
      <div className="flex flex-wrap items-center gap-2">
        <WhatsAppStatusBadge connection={connection} />
        {connection.phone ? (
          <span className="text-sm text-muted-foreground">{connection.phone}</span>
        ) : null}
      </div>

      <div className="space-y-2">
        <h4 className="text-sm font-medium">{t('apps.whatsapp.pairing.title')}</h4>
        <p className="text-sm text-muted-foreground">
          {t('apps.whatsapp.pairing.instructions')}
        </p>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="whatsapp-phone" className="text-sm font-medium">
          {t('apps.whatsapp.pairing.phoneLabel')}
        </label>
        <Input
          id="whatsapp-phone"
          value={phoneNumber}
          onChange={(event) =>
            setPhoneNumber(event.target.value.replace(/[^\d+\s()-]/g, ''))
          }
          placeholder={t('apps.whatsapp.pairing.phonePlaceholder')}
          inputMode="tel"
          data-testid="whatsapp-phone-input"
        />
        <p className="text-xs text-muted-foreground">
          {t('apps.whatsapp.pairing.phoneHint')}
        </p>
      </div>

      {errorKey ? <p className="text-sm text-destructive">{t(errorKey)}</p> : null}

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() =>
            pairingMutation.mutate({
              phone_number: normalizePhoneForRequest(phoneNumber),
            })
          }
          disabled={!normalizePhoneForRequest(phoneNumber) || pairingMutation.isPending}
          data-testid="whatsapp-request-pairing"
        >
          {pairingMutation.isPending
            ? t('apps.whatsapp.pairing.requesting')
            : t('apps.whatsapp.pairing.request')}
        </Button>
      </div>

      {pairing?.pairing_code ? (
        <div
          className="rounded-xl border border-border bg-muted/20 p-4 space-y-3"
          data-testid="whatsapp-pairing-code"
        >
          <div className="space-y-1">
            <p className="text-sm font-medium">{t('apps.whatsapp.pairing.codeLabel')}</p>
            <p className="font-mono text-2xl tracking-[0.3em]">
              {formatPairingCode(pairing.pairing_code)}
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleCopy()}
              data-testid="whatsapp-copy-pairing"
            >
              {t('apps.whatsapp.pairing.copy')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
