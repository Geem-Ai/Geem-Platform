import type {
  CatalogApp,
  WhatsAppConnection,
  WhatsAppProviderStatus,
} from '@/services/api/apps';

export function isWhatsAppApp(
  app: Pick<CatalogApp, 'slug' | 'connector'>,
): boolean {
  return app.slug === 'whatsapp' || app.connector?.key === 'openwa';
}

export function getAppConnectionLimit(
  app: Pick<CatalogApp, 'plans' | 'access'>,
): number | null {
  const activePlan =
    app.plans.find((plan) => plan.id === app.access?.plan_id) ??
    app.plans.find((plan) => plan.is_default) ??
    app.plans[0];
  const raw = activePlan?.entitlements?.connections;
  const count =
    typeof raw === 'number'
      ? raw
      : typeof raw === 'string'
        ? Number(raw)
        : Number.NaN;
  if (!Number.isFinite(count) || count < 0) {
    return null;
  }
  return Math.trunc(count);
}

export function normalizeProviderStatus(
  value: WhatsAppProviderStatus | null | undefined,
): string {
  return String(value ?? '').trim().toLowerCase();
}

export function isReadyStatus(
  connection: Pick<WhatsAppConnection, 'status' | 'provider_status'> | null | undefined,
): boolean {
  const provider = normalizeProviderStatus(connection?.provider_status);
  // Explicit OpenWA lifecycle always wins — an ACTIVE Geem row can still be
  // re-linking (qr_ready / authenticating) after reconnect.
  if (provider === 'ready') return true;
  if (
    provider === 'qr_ready' ||
    provider === 'authenticating' ||
    provider === 'created' ||
    provider === 'initializing' ||
    provider === 'failed' ||
    provider === 'disconnected' ||
    provider === 'action_required'
  ) {
    return false;
  }
  return connection?.status === 'active';
}

export function isTerminalStatus(
  connection: Pick<WhatsAppConnection, 'status' | 'provider_status'> | null | undefined,
): boolean {
  const provider = normalizeProviderStatus(connection?.provider_status);
  return (
    isReadyStatus(connection) ||
    provider === 'failed' ||
    provider === 'disconnected' ||
    provider === 'action_required' ||
    connection?.status === 'disconnected' ||
    connection?.status === 'revoked' ||
    connection?.status === 'error'
  );
}

export function isConnectingStatus(
  connection: Pick<WhatsAppConnection, 'status' | 'provider_status'> | null | undefined,
): boolean {
  if (!connection || isReadyStatus(connection)) return false;
  const provider = normalizeProviderStatus(connection.provider_status);
  if (
    provider === 'failed' ||
    provider === 'disconnected' ||
    provider === 'action_required'
  ) {
    return false;
  }
  if (
    connection.status === 'disconnected' ||
    connection.status === 'revoked' ||
    connection.status === 'error'
  ) {
    return false;
  }
  // Provider linking states win even if Geem row is still ACTIVE mid-reconnect.
  if (
    provider === 'created' ||
    provider === 'initializing' ||
    provider === 'qr_ready' ||
    provider === 'authenticating'
  ) {
    return true;
  }
  return (
    connection.status === 'connecting' ||
    connection.status === 'pending'
  );
}

export function formatPairingCode(value: string | null | undefined): string {
  const compact = String(value ?? '').replace(/\s+/g, '').trim().toUpperCase();
  if (compact.length !== 8) return compact;
  return `${compact.slice(0, 4)} ${compact.slice(4)}`;
}

export function normalizePhoneForRequest(value: string): string {
  const digits = value.replace(/[^\d]/g, '');
  return digits.startsWith('00') ? digits.slice(2) : digits;
}
