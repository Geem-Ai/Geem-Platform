import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, CircleAlert, KeyRound } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type { PlatformPaymentGatewayListItem } from '@/services/api/types';

type GatewayConfigDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  gateway: PlatformPaymentGatewayListItem | null;
  pending?: boolean;
  onSubmit: (values: {
    profileId: string;
    serverKey: string;
    testMode: boolean;
  }) => void;
};

export function GatewayConfigDialog({
  open,
  onOpenChange,
  gateway,
  pending,
  onSubmit,
}: GatewayConfigDialogProps) {
  const { t } = useTranslation();
  const [profileId, setProfileId] = useState('');
  const [serverKey, setServerKey] = useState('');
  const [testMode, setTestMode] = useState(true);
  const isCreate = !gateway?.id;

  useEffect(() => {
    if (!open) {
      setProfileId('');
      setServerKey('');
      setTestMode(gateway?.test_mode ?? true);
      return;
    }
    setProfileId(gateway?.credential_field_status.profile_id ?? '');
    setServerKey('');
    setTestMode(gateway?.test_mode ?? true);
  }, [open, gateway]);

  const canSubmit =
    gateway?.code === 'noop' ||
    (profileId.trim().length > 0 && (isCreate ? serverKey.trim().length > 0 : true));

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        className="max-w-lg"
        data-testid="gateway-config-dialog"
      >
        <AlertDialogHeader>
          <AlertDialogTitle>
            {isCreate ? t('paymentGateways.addConfiguration') : t('paymentGateways.configure')}
            {gateway ? ` — ${gateway.display_name}` : ''}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {gateway?.code === 'noop'
              ? t('paymentGateways.dialog.noopHelp')
              : t('paymentGateways.dialog.clickpayHelp')}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {gateway?.code === 'clickpay' ? (
          <div className="space-y-5 py-1">
            {!isCreate ? (
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  {t('paymentGateways.card.credentials')}
                </p>
                <div className="flex flex-wrap gap-2">
                  <StatusChip
                    label={t('paymentGateways.profileId')}
                    configured={Boolean(gateway.credential_field_status.profile_id_configured)}
                  />
                  <StatusChip
                    label={t('paymentGateways.serverKey')}
                    configured={Boolean(gateway.credential_field_status.server_key_configured)}
                  />
                </div>
              </div>
            ) : null}

            <Separator />

            <div className="space-y-2">
              <Label htmlFor="gateway-profile-id">{t('paymentGateways.profileId')}</Label>
              <Input
                id="gateway-profile-id"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
                autoComplete="off"
                placeholder={t('paymentGateways.dialog.profileIdPlaceholder')}
                data-testid="gateway-profile-id"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="gateway-server-key">{t('paymentGateways.serverKey')}</Label>
              {gateway.credential_field_status.server_key_configured ? (
                <p className="text-xs text-muted-foreground" data-testid="gateway-server-key-status">
                  {t('paymentGateways.serverKeyConfigured')}
                </p>
              ) : null}
              <Input
                id="gateway-server-key"
                type="password"
                value={serverKey}
                onChange={(e) => setServerKey(e.target.value)}
                autoComplete="new-password"
                placeholder={isCreate ? undefined : t('paymentGateways.serverKeyHint')}
                data-testid="gateway-server-key"
              />
            </div>

            <div className="rounded-lg border border-border p-3">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={testMode}
                  onChange={(e) => setTestMode(e.target.checked)}
                  data-testid="gateway-test-mode"
                />
                <span>
                  <span className="block text-sm font-medium">{t('paymentGateways.testMode')}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {t('paymentGateways.dialog.testModeDescription')}
                  </span>
                </span>
              </label>
            </div>
          </div>
        ) : gateway?.code === 'noop' ? (
          <div className="space-y-3 py-2">
            <Badge variant="warning" appearance="light">
              {t('paymentGateways.card.noopDescription')}
            </Badge>
            <p className="text-sm text-muted-foreground">{t('paymentGateways.dialog.noopHelp')}</p>
          </div>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{t('common.cancel')}</AlertDialogCancel>
          <Button
            disabled={!canSubmit || pending}
            onClick={() =>
              onSubmit({
                profileId: profileId.trim(),
                serverKey: serverKey.trim(),
                testMode,
              })
            }
            data-testid="gateway-config-submit"
          >
            {pending ? t('common.working') : t('common.save')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function StatusChip({ label, configured }: { label: string; configured: boolean }) {
  const { t } = useTranslation();

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs',
        configured
          ? 'border-success/30 bg-success/5 text-success-accent dark:text-success'
          : 'border-border bg-background text-muted-foreground',
      )}
    >
      <KeyRound className="size-3" aria-hidden />
      {label}
      {configured ? (
        <>
          <CheckCircle2 className="size-3" aria-hidden />
          <span className="sr-only">{t('paymentGateways.configured')}</span>
        </>
      ) : (
        <>
          <CircleAlert className="size-3" aria-hidden />
          <span>{t('paymentGateways.card.credentialMissing')}</span>
        </>
      )}
    </span>
  );
}
