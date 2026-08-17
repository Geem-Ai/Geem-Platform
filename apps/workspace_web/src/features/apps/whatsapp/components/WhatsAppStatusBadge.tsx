import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import type { WhatsAppConnection } from '@/services/api/apps';
import { normalizeProviderStatus } from '../lib';

function resolveStatus(
  connection: Pick<WhatsAppConnection, 'status' | 'provider_status'>,
): {
  key:
    | 'connecting'
    | 'waitingForQr'
    | 'authenticating'
    | 'connected'
    | 'disconnected'
    | 'actionRequired'
    | 'failed';
  variant: 'info' | 'success' | 'warning' | 'secondary' | 'destructive';
} {
  const provider = normalizeProviderStatus(connection.provider_status);
  if (provider === 'qr_ready') {
    return { key: 'waitingForQr', variant: 'warning' };
  }
  if (provider === 'authenticating') {
    return { key: 'authenticating', variant: 'info' };
  }
  if (provider === 'ready') {
    return { key: 'connected', variant: 'success' };
  }
  if (connection.status === 'active' && !provider) {
    return { key: 'connected', variant: 'success' };
  }
  if (provider === 'disconnected' || connection.status === 'disconnected') {
    return { key: 'disconnected', variant: 'secondary' };
  }
  if (provider === 'action_required') {
    return { key: 'actionRequired', variant: 'warning' };
  }
  if (provider === 'failed' || connection.status === 'error') {
    return { key: 'failed', variant: 'destructive' };
  }
  return { key: 'connecting', variant: 'info' };
}

export function WhatsAppStatusBadge({
  connection,
}: {
  connection: Pick<WhatsAppConnection, 'status' | 'provider_status'>;
}) {
  const { t } = useTranslation();
  const status = resolveStatus(connection);

  return (
    <Badge
      variant={status.variant}
      appearance="light"
      size="sm"
      data-testid={`whatsapp-status-${status.key}`}
    >
      {t(`apps.whatsapp.status.${status.key}`)}
    </Badge>
  );
}
