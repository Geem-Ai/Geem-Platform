import { useTranslation } from 'react-i18next';
import { Badge, BadgeDot } from '@/components/ui/badge';
import type { WhatsAppConnection } from '@/services/api/apps';
import { resolveWhatsAppUiStatus, type WhatsAppUiStatusKey } from '../lib';

const IN_PROGRESS: WhatsAppUiStatusKey[] = [
  'connecting',
  'waitingForQr',
  'authenticating',
];

export function WhatsAppStatusBadge({
  connection,
}: {
  connection: Pick<WhatsAppConnection, 'status' | 'provider_status'>;
}) {
  const { t } = useTranslation();
  const status = resolveWhatsAppUiStatus(connection);
  const inProgress = IN_PROGRESS.includes(status.key);

  return (
    <Badge
      variant={status.variant}
      appearance="light"
      size="sm"
      data-testid={`whatsapp-status-${status.key}`}
    >
      <BadgeDot className={inProgress ? 'animate-pulse opacity-100' : undefined} />
      {t(`apps.whatsapp.status.${status.key}`)}
    </Badge>
  );
}
