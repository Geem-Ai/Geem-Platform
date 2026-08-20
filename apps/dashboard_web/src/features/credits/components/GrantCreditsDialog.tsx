import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowLeft, Building2, Coins } from 'lucide-react';
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
  workspaceName?: string;
  currentBalance: number;
  onGranted: () => void;
};

export function GrantCreditsDialog({
  open,
  onOpenChange,
  workspaceId,
  workspaceName,
  currentBalance,
  onGranted,
}: GrantCreditsDialogProps) {
  const { t, i18n } = useTranslation();
  const displayWorkspaceName = workspaceName ?? t('credits.selectedWorkspace');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [confirmStep, setConfirmStep] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);

  const amountNum = Number(amount);
  const amountValid = Number.isSafeInteger(amountNum) && amountNum > 0;
  const amountInvalid = amount.length > 0 && !amountValid;
  const reasonValid = reason.trim().length > 0;
  const canProceed = amountValid && reasonValid;
  const projectedBalance = currentBalance + amountNum;

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
      <AlertDialogContent
        className="max-h-[90dvh] overflow-y-auto"
        data-testid="grant-credits-dialog"
      >
        <AlertDialogHeader>
          <AlertDialogTitle>
            {confirmStep ? t('credits.grantConfirmTitle') : t('credits.grantTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {confirmStep
              ? t('credits.grantConfirmHint', {
                  amount: formatInteger(amountNum, i18n.language),
                  workspace: displayWorkspaceName,
                })
              : t('credits.grantHint', { workspace: displayWorkspaceName })}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 p-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Building2 className="size-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{displayWorkspaceName}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t('credits.currentBalance', {
                balance: formatInteger(currentBalance, i18n.language),
              })}
            </p>
          </div>
        </div>

        {!confirmStep ? (
          <div className="space-y-3 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="grant-credits-amount">{t('credits.amount')}</Label>
              <Input
                id="grant-credits-amount"
                type="number"
                min={1}
                step={1}
                inputMode="numeric"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                aria-invalid={amountInvalid}
                aria-describedby={
                  amountInvalid ? 'grant-credits-amount-error' : 'grant-credits-amount-hint'
                }
                data-testid="grant-credits-amount"
              />
              {amountInvalid ? (
                <p
                  id="grant-credits-amount-error"
                  className="text-xs text-destructive"
                  data-testid="grant-credits-amount-error"
                  role="alert"
                >
                  {t('credits.amountInvalid')}
                </p>
              ) : (
                <p id="grant-credits-amount-hint" className="text-xs text-muted-foreground">
                  {t('credits.amountHint')}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grant-credits-reason">{t('common.reasonRequired')}</Label>
              <textarea
                id="grant-credits-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                rows={3}
                required
                aria-required="true"
                aria-describedby="grant-credits-reason-count"
                placeholder={t('common.reasonPlaceholder')}
                className="flex w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                data-testid="grant-credits-reason"
              />
              <p
                id="grant-credits-reason-count"
                className="text-end text-[11px] tabular-nums text-muted-foreground"
              >
                {t('credits.charactersUsed', { count: reason.length })}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-3" data-testid="grant-credits-summary">
            <div className="grid gap-3 sm:grid-cols-3">
              <SummaryItem
                label={t('credits.amount')}
                value={`+${formatInteger(amountNum, i18n.language)}`}
              />
              <SummaryItem
                label={t('credits.balance')}
                value={formatInteger(currentBalance, i18n.language)}
              />
              <SummaryItem
                label={t('credits.projectedBalance')}
                value={formatInteger(projectedBalance, i18n.language)}
              />
            </div>
            <div className="rounded-xl border border-border p-3">
              <p className="text-xs font-medium text-muted-foreground">{t('credits.grantReason')}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-5">{reason.trim()}</p>
            </div>
          </div>
        )}

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
            <>
              <Button
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => {
                  setConfirmStep(false);
                  setRequestId(null);
                }}
                data-testid="grant-credits-back"
              >
                <ArrowLeft className="size-3.5 rtl:rotate-180" aria-hidden />
                {t('credits.back')}
              </Button>
              <Button
                disabled={mutation.isPending || !requestId}
                onClick={() => mutation.mutate()}
                data-testid="grant-credits-confirm"
              >
                <Coins className="size-3.5" aria-hidden />
                {mutation.isPending ? t('common.working') : t('credits.grantConfirm')}
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-muted/20 p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-base font-semibold tabular-nums">
        <bdi dir="ltr">{value}</bdi>
      </p>
    </div>
  );
}
