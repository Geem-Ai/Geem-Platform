import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, CircleAlert, Clock } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  paymentNoticeFromState,
  type PaymentNotice,
} from '../lib/outcome';

function titleKey(notice: PaymentNotice): string {
  if (notice === 'success') return 'billing.paymentSuccessTitle';
  if (notice === 'failed') return 'billing.paymentFailedTitle';
  return 'billing.paymentPendingTitle';
}

function hintKey(notice: PaymentNotice): string {
  if (notice === 'success') return 'billing.paymentSuccessHint';
  if (notice === 'failed') return 'billing.paymentFailedHint';
  return 'billing.paymentPendingHint';
}

export function PaymentOutcomeDialog() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const notice = paymentNoticeFromState(location.state);
  const [open, setOpen] = useState(Boolean(notice));

  useEffect(() => {
    if (notice) setOpen(true);
  }, [notice]);

  function dismiss() {
    setOpen(false);
    if (notice) {
      navigate('.', { replace: true, state: {} });
    }
  }

  if (!notice) return null;

  const Icon =
    notice === 'success' ? CheckCircle2 : notice === 'failed' ? CircleAlert : Clock;

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) dismiss();
      }}
    >
      <AlertDialogContent data-testid="billing-payment-outcome-dialog" data-notice={notice}>
        <AlertDialogHeader>
          <div className="flex items-start gap-3">
            <Icon
              className={
                notice === 'success'
                  ? 'size-5 text-primary mt-0.5 shrink-0'
                  : notice === 'failed'
                    ? 'size-5 text-destructive mt-0.5 shrink-0'
                    : 'size-5 text-muted-foreground mt-0.5 shrink-0'
              }
              aria-hidden
            />
            <div className="min-w-0 space-y-2">
              <AlertDialogTitle>{t(titleKey(notice))}</AlertDialogTitle>
              <AlertDialogDescription>{t(hintKey(notice))}</AlertDialogDescription>
            </div>
          </div>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction
            data-testid="billing-payment-outcome-continue"
            onClick={dismiss}
          >
            {notice === 'failed' ? t('billing.tryAgain') : t('billing.continueToSubscription')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
