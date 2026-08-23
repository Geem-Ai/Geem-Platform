import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
      <AlertDialogContent data-testid="gateway-config-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>
            {isCreate ? t('paymentGateways.addConfiguration') : t('paymentGateways.configure')}
            {gateway ? ` — ${gateway.display_name}` : ''}
          </AlertDialogTitle>
          <AlertDialogDescription>{t('paymentGateways.subtitle')}</AlertDialogDescription>
        </AlertDialogHeader>

        {gateway?.code === 'clickpay' ? (
          <div className="space-y-4 py-1">
            <div className="space-y-2">
              <Label htmlFor="gateway-profile-id">{t('paymentGateways.profileId')}</Label>
              <Input
                id="gateway-profile-id"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
                autoComplete="off"
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
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={testMode}
                onChange={(e) => setTestMode(e.target.checked)}
                data-testid="gateway-test-mode"
              />
              {t('paymentGateways.testMode')}
            </label>
          </div>
        ) : gateway?.code === 'noop' ? (
          <p className="text-sm text-muted-foreground py-2">
            {t('paymentGateways.notConfigured')}
          </p>
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
