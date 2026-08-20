import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
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
import { formatInteger } from '@/lib/format';
import { getErrorMessage } from '@/services/api/errors';
import { grantWorkspaceCredits, newCreditGrantRequestId } from '@/services/api/platform';

type GrantCreditsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  onGranted: () => void;
};

export function GrantCreditsDialog({
  open,
  onOpenChange,
  workspaceId,
  onGranted,
}: GrantCreditsDialogProps) {
  const { t, i18n } = useTranslation();
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [confirmStep, setConfirmStep] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);

  const amountNum = Number(amount);
  const amountValid = Number.isInteger(amountNum) && amountNum > 0;
  const reasonValid = reason.trim().length > 0;
  const canProceed = amountValid && reasonValid;

  const resetForm = () => {
    setAmount('');
    setReason('');
    setConfirmStep(false);
    setRequestId(null);
  };

  const mutation = useMutation({
    mutationFn: () => {
      if (!requestId) {
        throw new Error('Missing credit grant request_id');
      }
      return grantWorkspaceCredits(workspaceId, {
        amount: amountNum,
        reason: reason.trim(),
        request_id: requestId,
      });
    },
    onSuccess: (res) => {
      toast.success(
        res.idempotent_replay
          ? t('credits.grantReplay')
          : t('credits.grantSuccess', { amount: formatInteger(res.entry.amount, i18n.language) }),
      );
      resetForm();
      onOpenChange(false);
      onGranted();
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) resetForm();
        onOpenChange(next);
      }}
    >
      <AlertDialogContent data-testid="grant-credits-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>
            {confirmStep ? t('credits.grantConfirmTitle') : t('credits.grantTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {confirmStep
              ? t('credits.grantConfirmHint', {
                  amount: formatInteger(amountNum, i18n.language),
                })
              : t('credits.grantHint')}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {!confirmStep ? (
          <div className="space-y-3 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="grant-credits-amount">{t('credits.amount')}</Label>
              <Input
                id="grant-credits-amount"
                type="number"
                min={1}
                step={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                data-testid="grant-credits-amount"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grant-credits-reason">{t('common.reasonRequired')}</Label>
              <Input
                id="grant-credits-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                placeholder={t('common.reasonPlaceholder')}
                data-testid="grant-credits-reason"
              />
            </div>
          </div>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>{t('common.cancel')}</AlertDialogCancel>
          {!confirmStep ? (
            <Button
              disabled={!canProceed}
              onClick={() => {
                setRequestId(newCreditGrantRequestId());
                setConfirmStep(true);
              }}
              data-testid="grant-credits-continue"
            >
              {t('credits.continue')}
            </Button>
          ) : (
            <Button
              disabled={mutation.isPending || !requestId}
              onClick={() => mutation.mutate()}
              data-testid="grant-credits-confirm"
            >
              {mutation.isPending ? t('common.working') : t('credits.grantConfirm')}
            </Button>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
