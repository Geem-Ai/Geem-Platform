import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { ApiKey } from '@/services/api/api-keys';
import { maskedApiKey } from '../lib/status';

type RevokeApiKeyDialogProps = {
  apiKey: ApiKey | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  isPending?: boolean;
};

export function RevokeApiKeyDialog({
  apiKey,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: RevokeApiKeyDialogProps) {
  const { t } = useTranslation();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="revoke-api-key-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('apiKeys.revokeTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('apiKeys.revokeHint')}</AlertDialogDescription>
        </AlertDialogHeader>
        {apiKey ? (
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
            <p className="font-medium">{apiKey.name}</p>
            <p className="font-mono text-xs text-muted-foreground mt-1" dir="ltr">
              {maskedApiKey(apiKey)}
            </p>
          </div>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={isPending || !apiKey}
            onClick={(event) => {
              event.preventDefault();
              onConfirm();
            }}
            data-testid="revoke-api-key-confirm"
          >
            {t('apiKeys.revoke')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
