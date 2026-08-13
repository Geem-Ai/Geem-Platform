import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { copyText } from '@/lib/clipboard';

type CreatedSecretDialogProps = {
  secret: string | null;
  onClose: () => void;
};

export function CreatedSecretDialog({ secret, onClose }: CreatedSecretDialogProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const open = Boolean(secret);

  async function handleCopy() {
    if (!secret) return;
    const ok = await copyText(secret);
    if (ok) {
      setCopied(true);
      toast.success(t('apiKeys.copied'));
    } else {
      toast.error(t('apiKeys.copyFailed'));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setCopied(false);
          onClose();
        }
      }}
    >
      <DialogContent data-testid="created-api-key-dialog">
        <DialogHeader>
          <DialogTitle>{t('apiKeys.createdTitle')}</DialogTitle>
          <DialogDescription>{t('apiKeys.createdWarning')}</DialogDescription>
        </DialogHeader>
        {secret ? (
          <div className="space-y-3">
            <pre
              dir="ltr"
              className="break-all whitespace-pre-wrap rounded-md border border-border bg-muted/50 p-3 text-xs font-mono select-all"
              data-testid="created-api-key-secret"
            >
              {secret}
            </pre>
            <p className="text-sm text-muted-foreground">{t('apiKeys.createdHint')}</p>
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t('apiKeys.done')}
          </Button>
          <Button type="button" onClick={() => void handleCopy()} data-testid="copy-api-key">
            {copied ? t('apiKeys.copied') : t('apiKeys.copyKey')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
